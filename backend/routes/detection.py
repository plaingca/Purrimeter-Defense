"""
Detection preview API routes for visualizing SAM3 detections.

All heavy operations are offloaded to thread pools to keep the HTTP interface responsive.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import base64
import io
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel
from PIL import Image, ImageDraw, ImageFont
import numpy as np

router = APIRouter()

# Dedicated thread pool for image processing (separate from inference)
_image_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="image-proc")


class DetectionPreviewRequest(BaseModel):
    """Request for detection preview."""
    camera_id: str
    prompts: List[str]
    confidence_threshold: float = 0.5


class DetectionResult(BaseModel):
    """Detection result with mask info."""
    label: str
    confidence: float
    bbox: List[int]
    center: List[int]
    area: int


class DetectionPreviewResponse(BaseModel):
    """Response with detection results and visualization."""
    detections: dict[str, List[DetectionResult]]
    frame_base64: Optional[str] = None
    visualization_base64: Optional[str] = None


def _pil_to_base64(img: Image.Image, format: str = "JPEG") -> str:
    """Convert PIL image to base64 (runs in thread pool)."""
    buffer = io.BytesIO()
    if format == "JPEG":
        img = img.convert("RGB")
    img.save(buffer, format=format, quality=85)
    return base64.b64encode(buffer.getvalue()).decode()


def _pil_to_jpeg_bytes(img: Image.Image, quality: int = 80) -> bytes:
    """Convert PIL image to JPEG bytes (runs in thread pool)."""
    buffer = io.BytesIO()
    img.convert("RGB").save(buffer, format="JPEG", quality=quality)
    return buffer.getvalue()


def _draw_detection_labels(image: Image.Image, detections: list) -> Image.Image:
    """Draw bounding boxes and labels on the image (runs in thread pool)."""
    draw = ImageDraw.Draw(image)
    
    # Try to load a font, fall back to default
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
    except:
        font = ImageFont.load_default()
    
    colors = [
        (255, 107, 107),  # Red
        (78, 205, 196),   # Teal
        (255, 230, 109),  # Yellow
        (170, 166, 157),  # Gray
        (255, 159, 243),  # Pink
    ]
    
    for i, det in enumerate(detections):
        color = colors[i % len(colors)]
        x1, y1, x2, y2 = det.bbox
        
        # Draw bounding box
        draw.rectangle([x1, y1, x2, y2], outline=color, width=3)
        
        # Draw label background
        label = f"{det.label} {det.confidence:.0%}"
        bbox = draw.textbbox((x1, y1 - 20), label, font=font)
        draw.rectangle([bbox[0] - 2, bbox[1] - 2, bbox[2] + 2, bbox[3] + 2], fill=color)
        
        # Draw label text
        draw.text((x1, y1 - 20), label, fill=(0, 0, 0), font=font)
    
    return image


@router.post("/preview", response_model=DetectionPreviewResponse)
async def get_detection_preview(
    req: DetectionPreviewRequest,
    request: Request,
):
    """
    Run detection on current camera frame and return results with visualization.
    """
    pipeline_manager = request.app.state.pipeline_manager
    sam3_service = request.app.state.sam3_service
    
    # Get current frame from camera
    camera_stream = pipeline_manager.get_camera_stream(req.camera_id)
    if not camera_stream:
        raise HTTPException(status_code=404, detail="Camera pipeline not found")
    
    pil_image = camera_stream.get_frame_as_pil()
    if pil_image is None:
        raise HTTPException(status_code=503, detail="No frame available")
    
    # Run detection (already uses its own thread pool)
    detections = await sam3_service.detect_objects(
        pil_image,
        req.prompts,
        confidence_threshold=req.confidence_threshold,
    )
    
    # Convert detections to response format
    detection_results = {}
    all_detections = []
    
    for label, dets in detections.items():
        detection_results[label] = [
            DetectionResult(
                label=d.label,
                confidence=d.confidence,
                bbox=list(d.bbox),
                center=list(d.center),
                area=d.area,
            )
            for d in dets
        ]
        all_detections.extend(dets)
    
    # Create visualization and encode images in thread pool
    loop = asyncio.get_running_loop()
    
    visualization = sam3_service.masks_to_visualization(pil_image, all_detections)
    
    # Run image encoding in parallel
    frame_b64_future = loop.run_in_executor(
        _image_executor, _pil_to_base64, pil_image, "JPEG"
    )
    vis_b64_future = loop.run_in_executor(
        _image_executor, _pil_to_base64, visualization.convert("RGB"), "JPEG"
    )
    
    frame_b64, vis_b64 = await asyncio.gather(frame_b64_future, vis_b64_future)
    
    return DetectionPreviewResponse(
        detections=detection_results,
        frame_base64=frame_b64,
        visualization_base64=vis_b64,
    )


@router.get("/preview/{camera_id}/stream")
async def stream_detection_preview(
    camera_id: str,
    prompts: str = Query(..., description="Comma-separated list of prompts"),
    confidence: float = Query(default=0.5),
    request: Request = None,
):
    """
    Stream detection visualization as MJPEG.
    
    Uses async generators with proper yielding to keep other requests responsive.
    """
    pipeline_manager = request.app.state.pipeline_manager
    sam3_service = request.app.state.sam3_service
    
    prompt_list = [p.strip() for p in prompts.split(",") if p.strip()]
    
    if not prompt_list:
        raise HTTPException(status_code=400, detail="No prompts provided")
    
    async def generate():
        """Generate MJPEG frames with detection overlays."""
        loop = asyncio.get_running_loop()
        
        while True:
            try:
                # Yield control to allow other requests
                await asyncio.sleep(0)
                
                camera_stream = pipeline_manager.get_camera_stream(camera_id)
                if not camera_stream:
                    await asyncio.sleep(1)
                    continue
                
                pil_image = camera_stream.get_frame_as_pil()
                if pil_image is None:
                    await asyncio.sleep(0.1)
                    continue
                
                # Run detection (uses its own thread pool)
                detections = await sam3_service.detect_objects(
                    pil_image,
                    prompt_list,
                    confidence_threshold=confidence,
                )
                
                # Create visualization
                all_detections = []
                for dets in detections.values():
                    all_detections.extend(dets)
                
                if all_detections:
                    visualization = sam3_service.masks_to_visualization(pil_image, all_detections)
                    output_image = visualization.convert("RGB")
                else:
                    output_image = pil_image
                
                # Add detection labels and encode in thread pool
                output_image = await loop.run_in_executor(
                    _image_executor,
                    _draw_detection_labels,
                    output_image,
                    all_detections,
                )
                
                jpeg_bytes = await loop.run_in_executor(
                    _image_executor,
                    _pil_to_jpeg_bytes,
                    output_image,
                    80,
                )
                
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + jpeg_bytes
                    + b"\r\n"
                )
                
                # Rate limit - inference takes time, this just adds a small gap
                await asyncio.sleep(0.1)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Detection stream error: {e}")
                await asyncio.sleep(1)
    
    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.get("/test/{camera_id}")
async def test_detection(
    camera_id: str,
    prompt: str = Query(default="cat"),
    request: Request = None,
):
    """
    Quick test endpoint - returns a single detection frame.
    """
    pipeline_manager = request.app.state.pipeline_manager
    sam3_service = request.app.state.sam3_service
    loop = asyncio.get_running_loop()
    
    camera_stream = pipeline_manager.get_camera_stream(camera_id)
    if not camera_stream:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    pil_image = camera_stream.get_frame_as_pil()
    if pil_image is None:
        raise HTTPException(status_code=503, detail="No frame available")
    
    # Run detection (uses its own thread pool)
    detections = await sam3_service.detect_objects(
        pil_image,
        [prompt],
        confidence_threshold=0.3,
    )
    
    all_detections = detections.get(prompt, [])
    
    # Create visualization
    if all_detections:
        visualization = sam3_service.masks_to_visualization(pil_image, all_detections)
        output_image = await loop.run_in_executor(
            _image_executor,
            _draw_detection_labels,
            visualization.convert("RGB"),
            all_detections,
        )
    else:
        output_image = pil_image
    
    # Encode in thread pool
    jpeg_bytes = await loop.run_in_executor(
        _image_executor,
        _pil_to_jpeg_bytes,
        output_image,
        90,
    )
    
    return Response(
        content=jpeg_bytes,
        media_type="image/jpeg",
    )


@router.get("/status")
async def get_detection_status(request: Request):
    """
    Get status of the detection service.
    Quick endpoint to verify API responsiveness.
    """
    sam3_service = request.app.state.sam3_service
    
    return {
        "initialized": sam3_service._initialized,
        "model_loaded": sam3_service.model is not None,
        "device": sam3_service.device,
        "status": "ready" if sam3_service._initialized and sam3_service.model else "not_ready",
    }
