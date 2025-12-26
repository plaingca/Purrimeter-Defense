"""
Mask Video Generation Service.

Processes video recordings with SAM3 inference and overlays detection masks on each frame.
"""

import asyncio
import cv2
import numpy as np
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
import structlog
from PIL import Image

from backend.config import settings
from backend.services.sam3_service import SAM3Service, Detection

logger = structlog.get_logger()


class MaskVideoService:
    """
    Service for generating mask overlay videos.
    
    Takes a video recording, runs SAM3 inference on each frame,
    and generates a new video with detection masks overlaid.
    """
    
    def __init__(self, sam3_service: SAM3Service):
        self.sam3_service = sam3_service
    
    async def generate_mask_video(
        self,
        video_path: Path,
        output_path: Path,
        primary_target: str,
        secondary_target: Optional[str] = None,
        confidence_threshold: float = 0.5,
        rule_name: str = "Detection",
        progress_callback: Optional[callable] = None,
    ) -> Optional[str]:
        """
        Generate a mask video from an existing recording.
        
        Args:
            video_path: Path to source video
            output_path: Path for output mask video
            primary_target: Primary detection target (e.g., "cat")
            secondary_target: Optional secondary target (e.g., "counter")
            confidence_threshold: Minimum confidence for detections
            rule_name: Name of the rule for overlay text
            progress_callback: Optional callback(current_frame, total_frames)
            
        Returns:
            Path to generated mask video, or None if failed
        """
        if not video_path.exists():
            logger.error("Source video not found", path=str(video_path))
            return None
        
        try:
            # Open source video
            cap = cv2.VideoCapture(str(video_path))
            if not cap.isOpened():
                logger.error("Failed to open video", path=str(video_path))
                return None
            
            # Get video properties
            fps = cap.get(cv2.CAP_PROP_FPS)
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            
            logger.info(
                "Starting mask video generation",
                source=str(video_path),
                output=str(output_path),
                fps=fps,
                resolution=f"{width}x{height}",
                total_frames=total_frames,
                primary_target=primary_target,
                secondary_target=secondary_target,
            )
            
            # Create output video writer
            # Use mp4v codec, will transcode to h264 after
            temp_output = output_path.with_suffix('.temp.mp4')
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            writer = cv2.VideoWriter(str(temp_output), fourcc, fps, (width, height))
            
            if not writer.isOpened():
                logger.error("Failed to create output video writer")
                cap.release()
                return None
            
            # Build prompts list
            prompts = [primary_target]
            if secondary_target:
                prompts.append(secondary_target)
            
            # Color scheme
            primary_color = (0, 100, 255)  # Orange-red in BGR
            secondary_color = (255, 150, 0)  # Blue in BGR
            
            frame_count = 0
            start_time = datetime.now()
            
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                
                frame_count += 1
                
                # Convert frame to PIL for SAM3
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pil_image = Image.fromarray(frame_rgb)
                
                # Run SAM3 inference
                detections = await self.sam3_service.detect_objects(
                    pil_image,
                    prompts,
                    confidence_threshold=confidence_threshold,
                )
                
                # Create overlay
                overlay = frame.copy()
                
                # Draw primary target detections
                primary_detections = detections.get(primary_target, [])
                for detection in primary_detections:
                    self._draw_detection(
                        overlay, detection, primary_color, height, width
                    )
                
                # Draw secondary target detections
                if secondary_target:
                    secondary_detections = detections.get(secondary_target, [])
                    for detection in secondary_detections:
                        self._draw_detection(
                            overlay, detection, secondary_color, height, width,
                            label_position="bottom"
                        )
                
                # Blend overlay with original
                result = cv2.addWeighted(frame, 0.3, overlay, 0.7, 0)
                
                # Add header info
                cv2.putText(
                    result, f"Rule: {rule_name}", 
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2
                )
                
                # Add detection counts
                counts = f"{primary_target}: {len(primary_detections)}"
                if secondary_target:
                    secondary_count = len(detections.get(secondary_target, []))
                    counts += f" | {secondary_target}: {secondary_count}"
                cv2.putText(
                    result, counts,
                    (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1
                )
                
                # Add frame counter and progress
                progress_text = f"Frame {frame_count}/{total_frames}"
                cv2.putText(
                    result, progress_text,
                    (width - 200, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1
                )
                
                # Write frame
                writer.write(result)
                
                # Progress callback
                if progress_callback and frame_count % 10 == 0:
                    try:
                        progress_callback(frame_count, total_frames)
                    except:
                        pass
                
                # Log progress periodically
                if frame_count % 30 == 0:
                    elapsed = (datetime.now() - start_time).total_seconds()
                    fps_actual = frame_count / elapsed if elapsed > 0 else 0
                    eta = (total_frames - frame_count) / fps_actual if fps_actual > 0 else 0
                    logger.info(
                        "Mask video progress",
                        frame=frame_count,
                        total=total_frames,
                        percent=f"{100*frame_count/total_frames:.1f}%",
                        fps=f"{fps_actual:.1f}",
                        eta_seconds=f"{eta:.0f}",
                    )
            
            # Release resources
            cap.release()
            writer.release()
            
            # Transcode to h264 for web compatibility
            logger.info("Transcoding to h264...")
            await self._transcode_to_h264(temp_output, output_path)
            
            # Clean up temp file
            if temp_output.exists():
                temp_output.unlink()
            
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.info(
                "Mask video generation complete",
                output=str(output_path),
                frames_processed=frame_count,
                total_time_seconds=f"{elapsed:.1f}",
                avg_fps=f"{frame_count/elapsed:.2f}",
            )
            
            return str(output_path)
            
        except Exception as e:
            logger.error("Mask video generation failed", error=str(e))
            import traceback
            traceback.print_exc()
            return None
    
    def _draw_detection(
        self,
        frame: np.ndarray,
        detection: Detection,
        color: Tuple[int, int, int],
        frame_height: int,
        frame_width: int,
        label_position: str = "top",
    ):
        """Draw a detection on the frame with mask, bounding box, and label."""
        
        # Draw mask if available
        if detection.mask is not None and detection.mask.size > 0:
            mask = detection.mask
            
            # Resize mask to frame size if needed
            if mask.shape[:2] != (frame_height, frame_width):
                mask = cv2.resize(
                    mask.astype(np.uint8), 
                    (frame_width, frame_height), 
                    interpolation=cv2.INTER_NEAREST
                )
            
            # Apply colored mask overlay
            mask_bool = mask > 0
            if np.any(mask_bool):
                # Create colored overlay for mask region
                colored_mask = np.zeros_like(frame)
                colored_mask[mask_bool] = color
                
                # Blend mask with frame
                frame[mask_bool] = cv2.addWeighted(
                    frame[mask_bool], 0.5,
                    colored_mask[mask_bool], 0.5, 0
                )
                
                # Draw mask contours for better visibility
                contours, _ = cv2.findContours(
                    mask.astype(np.uint8), 
                    cv2.RETR_EXTERNAL, 
                    cv2.CHAIN_APPROX_SIMPLE
                )
                cv2.drawContours(frame, contours, -1, color, 2)
        
        # Draw bounding box
        x1, y1, x2, y2 = detection.bbox
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        
        # Draw label with confidence
        label = f"{detection.label}: {detection.confidence:.0%}"
        label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        
        if label_position == "top":
            label_y1 = max(0, y1 - label_size[1] - 10)
            label_y2 = y1
            text_y = y1 - 5
        else:
            label_y1 = y2
            label_y2 = min(frame_height, y2 + label_size[1] + 10)
            text_y = y2 + label_size[1] + 5
        
        cv2.rectangle(
            frame, 
            (x1, label_y1), 
            (x1 + label_size[0] + 10, label_y2), 
            color, -1
        )
        cv2.putText(
            frame, label, 
            (x1 + 5, text_y), 
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2
        )
    
    async def _transcode_to_h264(self, input_path: Path, output_path: Path):
        """Transcode video to h264 for web compatibility."""
        cmd = [
            'ffmpeg', '-y',
            '-i', str(input_path),
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-crf', '23',
            '-c:a', 'copy',
            '-movflags', '+faststart',
            str(output_path),
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        
        _, stderr = await process.communicate()
        
        if process.returncode != 0:
            logger.error("Transcoding failed", stderr=stderr.decode()[:500])
            # Fall back to just renaming
            if input_path.exists():
                import shutil
                shutil.move(str(input_path), str(output_path))

