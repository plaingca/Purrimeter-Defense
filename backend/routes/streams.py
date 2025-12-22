"""
Video streaming and WebSocket routes.

Optimized for responsiveness - all blocking operations run in thread pools.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import io
import json
import time
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request, Response, HTTPException, Query
from fastapi.responses import StreamingResponse
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import structlog

from backend.config import settings

logger = structlog.get_logger()

router = APIRouter()

# Larger thread pool for image processing (CPU-bound work)
_image_executor = ThreadPoolExecutor(
    max_workers=settings.IMAGE_PROCESSING_WORKERS, 
    thread_name_prefix="stream-img"
)

# Cache for overlay frames to avoid re-rendering
@dataclass
class CachedOverlay:
    jpeg_bytes: bytes
    timestamp: float
    detection_hash: str

_overlay_cache: Dict[str, CachedOverlay] = {}
_cache_ttl_ms = settings.OVERLAY_CACHE_MS


def _get_detection_hash(detections: dict) -> str:
    """Create a simple hash of detection state for cache invalidation."""
    if not detections:
        return "empty"
    # Hash based on detection count and first bbox
    parts = []
    for label, dets in detections.items():
        parts.append(f"{label}:{len(dets)}")
        if dets:
            parts.append(str(dets[0].bbox[:2]))  # Just first detection position
    return "|".join(parts)


@router.get("/{camera_id}/mjpeg")
async def mjpeg_stream(
    camera_id: str, 
    request: Request,
):
    """
    MJPEG video stream for a camera (raw, no overlays).
    
    This provides a simple HTTP-based video stream that works in <img> tags.
    """
    pipeline_manager = request.app.state.pipeline_manager
    
    async def generate():
        """Generate MJPEG frames."""
        frame_interval = 1.0 / settings.MJPEG_FPS
        
        while True:
            try:
                jpeg = pipeline_manager.get_current_frame_jpeg(camera_id)
                
                if jpeg:
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n"
                        + jpeg
                        + b"\r\n"
                    )
                
                await asyncio.sleep(frame_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("MJPEG stream error", error=str(e))
                await asyncio.sleep(0.5)
    
    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.get("/{camera_id}/mjpeg_overlay")
async def mjpeg_overlay_stream(
    camera_id: str, 
    request: Request,
):
    """
    MJPEG video stream with detection mask overlays.
    
    Uses caching to avoid re-rendering unchanged detection states.
    """
    pipeline_manager = request.app.state.pipeline_manager
    sam3_service = request.app.state.sam3_service
    
    async def generate():
        """Generate MJPEG frames with cached overlays."""
        # Slower frame rate for overlay stream to reduce CPU load
        frame_interval = 1.0 / 8  # 8 FPS for overlay stream
        loop = asyncio.get_running_loop()
        
        while True:
            try:
                jpeg = await get_frame_with_overlay_cached(
                    pipeline_manager, sam3_service, camera_id, loop
                )
                
                if jpeg:
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n"
                        + jpeg
                        + b"\r\n"
                    )
                
                await asyncio.sleep(frame_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("MJPEG overlay stream error", error=str(e), camera_id=camera_id)
                await asyncio.sleep(0.5)
    
    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


async def get_frame_with_overlay_cached(
    pipeline_manager, 
    sam3_service, 
    camera_id: str, 
    loop
) -> Optional[bytes]:
    """Get current frame with detection masks overlaid, using caching."""
    
    camera_stream = pipeline_manager.get_camera_stream(camera_id)
    if not camera_stream:
        return None
    
    # Get current detections
    pipeline = pipeline_manager._pipelines.get(camera_id)
    detections = pipeline.last_detections if pipeline else {}
    
    # Check cache
    detection_hash = _get_detection_hash(detections)
    cached = _overlay_cache.get(camera_id)
    now_ms = time.time() * 1000
    
    if cached and cached.detection_hash == detection_hash:
        if (now_ms - cached.timestamp) < _cache_ttl_ms:
            # Cache hit - return cached overlay
            return cached.jpeg_bytes
    
    # Cache miss - need to render
    pil_image = await loop.run_in_executor(_image_executor, camera_stream.get_frame_as_pil)
    if pil_image is None:
        return None
    
    # Flatten all detections
    all_detections = []
    for dets in detections.values():
        all_detections.extend(dets)
    
    if not all_detections:
        # No detections, return plain frame
        jpeg = await loop.run_in_executor(_image_executor, _pil_to_jpeg, pil_image, 75)
        return jpeg
    
    # Render overlay in thread pool (all CPU-bound work)
    jpeg = await loop.run_in_executor(
        _image_executor,
        _render_overlay_sync,
        pil_image,
        all_detections,
        sam3_service,
    )
    
    # Update cache
    _overlay_cache[camera_id] = CachedOverlay(
        jpeg_bytes=jpeg,
        timestamp=now_ms,
        detection_hash=detection_hash,
    )
    
    return jpeg


def _render_overlay_sync(pil_image: Image.Image, detections: list, sam3_service) -> bytes:
    """Render overlay synchronously (runs in thread pool)."""
    # Create visualization with masks
    visualization = sam3_service.masks_to_visualization(pil_image, detections, alpha=0.4)
    
    # Draw labels
    output = _draw_mask_labels(visualization.convert("RGB"), detections)
    
    # Convert to JPEG
    return _pil_to_jpeg(output, 75)


def _pil_to_jpeg(img: Image.Image, quality: int = 80) -> bytes:
    """Convert PIL image to JPEG bytes."""
    buffer = io.BytesIO()
    img.convert("RGB").save(buffer, format="JPEG", quality=quality, optimize=False)
    return buffer.getvalue()


def _draw_mask_labels(image: Image.Image, detections: list) -> Image.Image:
    """Draw labels on the image for each detection."""
    draw = ImageDraw.Draw(image)
    
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
    except:
        font = ImageFont.load_default()
    
    for det in detections:
        x1, y1, x2, y2 = det.bbox
        
        label = f"{det.label} {det.confidence:.0%}"
        
        # Draw label with background
        bbox = draw.textbbox((x1, max(0, y1 - 22)), label, font=font)
        # Add padding
        draw.rectangle(
            [bbox[0] - 3, bbox[1] - 1, bbox[2] + 3, bbox[3] + 1], 
            fill=(168, 85, 247)  # Purple
        )
        draw.text((x1, max(0, y1 - 22)), label, fill=(255, 255, 255), font=font)
    
    return image


@router.get("/{camera_id}/snapshot")
async def camera_snapshot(camera_id: str, request: Request, quality: int = 80):
    """
    Get a single snapshot from a camera.
    """
    pipeline_manager = request.app.state.pipeline_manager
    
    jpeg = pipeline_manager.get_current_frame_jpeg(camera_id, quality)
    
    if not jpeg:
        raise HTTPException(status_code=404, detail="Camera not available")
    
    return Response(content=jpeg, media_type="image/jpeg")


@router.websocket("/{camera_id}/ws")
async def websocket_stream(websocket: WebSocket, camera_id: str):
    """
    WebSocket video stream with detection overlays.
    
    Sends:
    - Binary messages: JPEG frame data
    - Text messages: JSON detection data
    """
    await websocket.accept()
    
    # Get pipeline manager from app state
    app = websocket.app
    pipeline_manager = app.state.pipeline_manager
    
    logger.info("WebSocket stream connected", camera_id=camera_id)
    
    try:
        frame_interval = 1.0 / settings.MJPEG_FPS
        detection_interval = 0.5  # 2 fps for detection updates
        last_frame_time = 0
        last_detection_time = 0
        
        while True:
            current_time = asyncio.get_event_loop().time()
            
            # Send frame
            if current_time - last_frame_time >= frame_interval:
                jpeg = pipeline_manager.get_current_frame_jpeg(camera_id)
                if jpeg:
                    await websocket.send_bytes(jpeg)
                    last_frame_time = current_time
            
            # Send detections (less frequently)
            if current_time - last_detection_time >= detection_interval:
                detections = pipeline_manager.get_current_detections(camera_id)
                status = pipeline_manager.get_pipeline_status(camera_id)
                
                await websocket.send_json({
                    "type": "detection_update",
                    "camera_id": camera_id,
                    "detections": detections,
                    "status": status,
                })
                last_detection_time = current_time
            
            # Check for incoming messages (client can send control messages)
            try:
                message = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=0.01,
                )
                data = json.loads(message)
                
                # Handle client commands
                if data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                    
            except asyncio.TimeoutError:
                pass
            except json.JSONDecodeError:
                pass
            
            await asyncio.sleep(0.02)  # Yield control more frequently
            
    except WebSocketDisconnect:
        logger.info("WebSocket stream disconnected", camera_id=camera_id)
    except Exception as e:
        logger.error("WebSocket error", camera_id=camera_id, error=str(e))
        await websocket.close()


@router.websocket("/alerts")
async def websocket_alerts(websocket: WebSocket):
    """
    WebSocket for real-time alert notifications.
    
    Broadcasts all alert events to connected clients.
    """
    await websocket.accept()
    
    app = websocket.app
    pipeline_manager = app.state.pipeline_manager
    
    logger.info("Alert WebSocket connected")
    
    # Queue for this client
    alert_queue = asyncio.Queue()
    
    # Register callback for alerts
    async def on_alert(alert_id, rule, evaluation):
        await alert_queue.put({
            "type": "alert_triggered",
            "alert_id": alert_id,
            "rule_id": rule.id,
            "rule_name": rule.name,
            "camera_id": rule.camera_id,
            "message": evaluation.message,
            "confidence": evaluation.confidence,
            "detected_objects": evaluation.detected_objects,
        })
    
    async def on_alert_end(alert_id, rule):
        await alert_queue.put({
            "type": "alert_ended",
            "alert_id": alert_id,
            "rule_id": rule.id,
            "rule_name": rule.name,
            "camera_id": rule.camera_id,
        })
    
    # Register callbacks
    pipeline_manager.rule_engine.on_alert(on_alert)
    pipeline_manager.rule_engine.on_alert_end(on_alert_end)
    
    try:
        while True:
            # Wait for alerts
            try:
                alert_data = await asyncio.wait_for(
                    alert_queue.get(),
                    timeout=30.0,
                )
                await websocket.send_json(alert_data)
            except asyncio.TimeoutError:
                # Send keepalive
                await websocket.send_json({"type": "ping"})
                
    except WebSocketDisconnect:
        logger.info("Alert WebSocket disconnected")
    except Exception as e:
        logger.error("Alert WebSocket error", error=str(e))
    finally:
        # Unregister callbacks
        try:
            pipeline_manager.rule_engine._on_alert_callbacks.remove(on_alert)
            pipeline_manager.rule_engine._on_alert_end_callbacks.remove(on_alert_end)
        except ValueError:
            pass  # Already removed


@router.get("/status")
async def get_all_stream_status(request: Request):
    """Get status of all camera streams."""
    pipeline_manager = request.app.state.pipeline_manager
    return pipeline_manager.get_all_pipeline_status()
