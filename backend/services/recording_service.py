"""
Recording service for capturing alert videos with pre-roll.
"""

import asyncio
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, List
import uuid
import structlog
import cv2
import numpy as np

from backend.config import settings
from backend.services.camera_stream import CameraStream, TimestampedFrame

logger = structlog.get_logger()


@dataclass
class ActiveRecording:
    """Represents an active recording session."""
    recording_id: str
    camera_id: str
    alert_id: str
    filepath: Path
    started_at: datetime
    writer: cv2.VideoWriter
    frame_count: int = 0
    pre_roll_written: bool = False


class RecordingService:
    """
    Service for managing video recordings with pre-roll capability.
    
    Features:
    - Pre-roll: Captures frames before the trigger event
    - Post-roll: Continues recording after alert ends
    - Thumbnail generation
    - Video encoding/transcoding
    """
    
    def __init__(self):
        self._active_recordings: dict[str, ActiveRecording] = {}
        self._lock = asyncio.Lock()
    
    async def start_recording(
        self,
        camera_stream: CameraStream,
        alert_id: str,
        pre_roll_seconds: float = None,
    ) -> str:
        """
        Start a new recording with pre-roll frames.
        
        Args:
            camera_stream: The camera stream to record from
            alert_id: Associated alert ID
            pre_roll_seconds: Seconds of pre-roll to include
            
        Returns:
            Recording ID
        """
        if pre_roll_seconds is None:
            pre_roll_seconds = settings.RECORDING_PRE_ROLL_SECONDS
        
        recording_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"{camera_stream.camera_id}_{timestamp}_{recording_id[:8]}.mp4"
        filepath = settings.RECORDINGS_PATH / filename
        
        logger.info(
            "Starting recording",
            recording_id=recording_id,
            camera_id=camera_stream.camera_id,
            alert_id=alert_id,
            filepath=str(filepath),
        )
        
        # Get pre-roll frames
        pre_roll_frames = camera_stream.get_pre_roll_frames(pre_roll_seconds)
        logger.info(f"Got {len(pre_roll_frames)} pre-roll frames")
        
        # Determine video dimensions from first frame
        if pre_roll_frames:
            height, width = pre_roll_frames[0].frame.shape[:2]
        else:
            current = camera_stream.get_current_frame()
            if current:
                height, width = current.frame.shape[:2]
            else:
                width, height = camera_stream.width, camera_stream.height
        
        # Create video writer
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        writer = cv2.VideoWriter(
            str(filepath),
            fourcc,
            settings.RECORDING_FPS,
            (width, height),
        )
        
        if not writer.isOpened():
            logger.error("Failed to create video writer", filepath=str(filepath))
            raise RuntimeError(f"Failed to create video writer: {filepath}")
        
        recording = ActiveRecording(
            recording_id=recording_id,
            camera_id=camera_stream.camera_id,
            alert_id=alert_id,
            filepath=filepath,
            started_at=datetime.utcnow(),
            writer=writer,
        )
        
        # Write pre-roll frames
        for frame in pre_roll_frames:
            writer.write(frame.frame)
            recording.frame_count += 1
        
        recording.pre_roll_written = True
        
        async with self._lock:
            self._active_recordings[recording_id] = recording
        
        # Subscribe to new frames
        def frame_callback(frame: TimestampedFrame):
            self._write_frame(recording_id, frame)
        
        camera_stream.subscribe(frame_callback)
        
        # Store callback for unsubscription
        recording._frame_callback = frame_callback
        recording._camera_stream = camera_stream
        
        return recording_id
    
    def _write_frame(self, recording_id: str, frame: TimestampedFrame):
        """Write a frame to the recording (called from camera thread)."""
        if recording_id not in self._active_recordings:
            return
        
        recording = self._active_recordings[recording_id]
        
        # Check max duration
        elapsed = (datetime.utcnow() - recording.started_at).total_seconds()
        if elapsed > settings.RECORDING_MAX_DURATION_SECONDS:
            logger.warning(
                "Recording max duration reached",
                recording_id=recording_id,
                elapsed=elapsed,
            )
            return
        
        try:
            recording.writer.write(frame.frame)
            recording.frame_count += 1
        except Exception as e:
            logger.error("Error writing frame", recording_id=recording_id, error=str(e))
    
    async def stop_recording(
        self,
        recording_id: str,
        post_roll_seconds: float = None,
    ) -> Optional[dict]:
        """
        Stop a recording after a post-roll period.
        
        Args:
            recording_id: Recording to stop
            post_roll_seconds: Additional seconds to record after alert ends
            
        Returns:
            Recording metadata dict or None if not found
        """
        if post_roll_seconds is None:
            post_roll_seconds = settings.RECORDING_POST_ROLL_SECONDS
        
        async with self._lock:
            if recording_id not in self._active_recordings:
                logger.warning("Recording not found", recording_id=recording_id)
                return None
            
            recording = self._active_recordings[recording_id]
        
        # Wait for post-roll
        if post_roll_seconds > 0:
            logger.info(
                "Recording post-roll",
                recording_id=recording_id,
                seconds=post_roll_seconds,
            )
            await asyncio.sleep(post_roll_seconds)
        
        # Unsubscribe from frames
        if hasattr(recording, '_camera_stream') and hasattr(recording, '_frame_callback'):
            recording._camera_stream.unsubscribe(recording._frame_callback)
        
        # Close writer
        recording.writer.release()
        
        ended_at = datetime.utcnow()
        duration = (ended_at - recording.started_at).total_seconds()
        
        async with self._lock:
            del self._active_recordings[recording_id]
        
        # Get file size
        file_size = recording.filepath.stat().st_size if recording.filepath.exists() else 0
        
        # Generate thumbnail
        thumbnail_path = await self._generate_thumbnail(recording.filepath)
        
        # Transcode to web-compatible format
        web_filepath = await self._transcode_for_web(recording.filepath)
        
        logger.info(
            "Recording stopped",
            recording_id=recording_id,
            duration=duration,
            frames=recording.frame_count,
            file_size=file_size,
        )
        
        return {
            "recording_id": recording_id,
            "camera_id": recording.camera_id,
            "alert_id": recording.alert_id,
            "filename": recording.filepath.name,
            "filepath": str(web_filepath or recording.filepath),
            "duration_seconds": duration,
            "file_size_bytes": file_size,
            "frame_count": recording.frame_count,
            "started_at": recording.started_at.isoformat(),
            "ended_at": ended_at.isoformat(),
            "thumbnail_path": str(thumbnail_path) if thumbnail_path else None,
        }
    
    async def _generate_thumbnail(self, video_path: Path) -> Optional[Path]:
        """Generate a thumbnail from the video."""
        try:
            thumbnail_path = video_path.with_suffix('.jpg')
            
            # Extract frame at 1 second (or first frame if video is shorter)
            cap = cv2.VideoCapture(str(video_path))
            
            # Try to seek to 1 second
            fps = cap.get(cv2.CAP_PROP_FPS)
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(fps))
            
            ret, frame = cap.read()
            if not ret:
                # Try first frame
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = cap.read()
            
            cap.release()
            
            if ret:
                # Resize for thumbnail
                height, width = frame.shape[:2]
                max_dim = 320
                scale = max_dim / max(width, height)
                new_width = int(width * scale)
                new_height = int(height * scale)
                
                thumbnail = cv2.resize(frame, (new_width, new_height))
                cv2.imwrite(str(thumbnail_path), thumbnail)
                
                return thumbnail_path
                
        except Exception as e:
            logger.error("Thumbnail generation failed", error=str(e))
        
        return None
    
    async def _transcode_for_web(self, video_path: Path) -> Optional[Path]:
        """Transcode video to web-compatible H.264 format."""
        try:
            output_path = video_path.with_stem(video_path.stem + "_web").with_suffix('.mp4')
            
            # Use ffmpeg for transcoding
            cmd = [
                'ffmpeg', '-y',
                '-i', str(video_path),
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-crf', '23',
                '-movflags', '+faststart',
                str(output_path),
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            _, stderr = await process.communicate()
            
            if process.returncode == 0:
                # Remove original, rename transcoded
                os.remove(video_path)
                os.rename(output_path, video_path)
                return video_path
            else:
                logger.error("Transcoding failed", stderr=stderr.decode())
                
        except Exception as e:
            logger.error("Transcoding error", error=str(e))
        
        return None
    
    def get_active_recordings(self) -> List[dict]:
        """Get list of active recordings."""
        return [
            {
                "recording_id": r.recording_id,
                "camera_id": r.camera_id,
                "alert_id": r.alert_id,
                "started_at": r.started_at.isoformat(),
                "frame_count": r.frame_count,
                "duration": (datetime.utcnow() - r.started_at).total_seconds(),
            }
            for r in self._active_recordings.values()
        ]

