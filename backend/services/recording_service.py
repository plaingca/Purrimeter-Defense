"""
Recording service for capturing alert videos with pre-roll.

Supports two recording modes:
1. Video-only (cv2.VideoWriter) - when audio is disabled
2. Video+Audio (FFmpeg) - when audio is enabled, records directly from RTSP
"""

import asyncio
import os
import subprocess
import signal
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Union
import uuid
import structlog
import cv2
import numpy as np

from backend.config import settings
from backend.services.camera_stream import CameraStream, TimestampedFrame
from backend.utils import to_utc_isoformat

logger = structlog.get_logger()


@dataclass
class ActiveRecording:
    """Represents an active recording session."""
    recording_id: str
    camera_id: str
    alert_id: str
    filepath: Path
    started_at: datetime
    writer: Optional[cv2.VideoWriter] = None
    ffmpeg_process: Optional[asyncio.subprocess.Process] = None
    pre_roll_filepath: Optional[Path] = None  # Temp file for pre-roll frames
    main_filepath: Optional[Path] = None  # Main recording with audio
    rtsp_url: Optional[str] = None
    frame_count: int = 0
    pre_roll_written: bool = False
    use_audio: bool = False


class RecordingService:
    """
    Service for managing video recordings with pre-roll capability.
    
    Features:
    - Pre-roll: Captures frames before the trigger event
    - Post-roll: Continues recording after alert ends
    - Thumbnail generation
    - Video encoding/transcoding
    - Audio recording (when enabled, uses FFmpeg to record from RTSP)
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
        
        When audio is enabled (RECORDING_INCLUDE_AUDIO=True):
        1. Pre-roll frames are written to a temp video file (silent)
        2. FFmpeg starts recording from RTSP with audio
        3. At stop, files are concatenated
        
        When audio is disabled:
        - Uses cv2.VideoWriter (original behavior)
        
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
        use_audio = settings.RECORDING_INCLUDE_AUDIO
        
        logger.info(
            "Starting recording",
            recording_id=recording_id,
            camera_id=camera_stream.camera_id,
            alert_id=alert_id,
            filepath=str(filepath),
            audio_enabled=use_audio,
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
        
        if use_audio:
            # Audio mode: Use FFmpeg to record from RTSP
            recording = await self._start_audio_recording(
                recording_id=recording_id,
                camera_id=camera_stream.camera_id,
                alert_id=alert_id,
                filepath=filepath,
                rtsp_url=camera_stream.rtsp_url,
                pre_roll_frames=pre_roll_frames,
                width=width,
                height=height,
            )
        else:
            # Video-only mode: Use cv2.VideoWriter
            recording = await self._start_video_only_recording(
                recording_id=recording_id,
                camera_stream=camera_stream,
                alert_id=alert_id,
                filepath=filepath,
                pre_roll_frames=pre_roll_frames,
                width=width,
                height=height,
            )
        
        async with self._lock:
            self._active_recordings[recording_id] = recording
        
        return recording_id
    
    async def _start_audio_recording(
        self,
        recording_id: str,
        camera_id: str,
        alert_id: str,
        filepath: Path,
        rtsp_url: str,
        pre_roll_frames: List[TimestampedFrame],
        width: int,
        height: int,
    ) -> ActiveRecording:
        """Start recording with audio using FFmpeg."""
        
        # File paths for temp files
        pre_roll_filepath = filepath.with_stem(filepath.stem + "_preroll")
        main_filepath = filepath.with_stem(filepath.stem + "_main")
        
        # Write pre-roll frames to temp video (silent)
        if pre_roll_frames:
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            pre_roll_writer = cv2.VideoWriter(
                str(pre_roll_filepath),
                fourcc,
                settings.RECORDING_FPS,
                (width, height),
            )
            
            if not pre_roll_writer.isOpened():
                logger.error("Failed to create pre-roll video writer")
                raise RuntimeError(f"Failed to create pre-roll video writer: {pre_roll_filepath}")
            
            for frame in pre_roll_frames:
                pre_roll_writer.write(frame.frame)
            
            pre_roll_writer.release()
            
            # Transcode pre-roll to H.264 for proper concatenation
            pre_roll_h264 = pre_roll_filepath.with_stem(pre_roll_filepath.stem + "_h264")
            transcode_cmd = [
                'ffmpeg', '-y',
                '-i', str(pre_roll_filepath),
                '-c:v', 'libx264',
                '-preset', 'ultrafast',
                '-crf', '23',
                '-an',  # No audio for pre-roll
                str(pre_roll_h264),
            ]
            
            process = await asyncio.create_subprocess_exec(
                *transcode_cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await process.communicate()
            
            if process.returncode == 0:
                os.remove(pre_roll_filepath)
                os.rename(pre_roll_h264, pre_roll_filepath)
            else:
                logger.warning("Pre-roll transcode failed", stderr=stderr.decode()[:500])
            
            logger.info(f"Wrote {len(pre_roll_frames)} pre-roll frames to {pre_roll_filepath}")
        
        # Start FFmpeg to record from RTSP with audio
        ffmpeg_cmd = [
            'ffmpeg', '-y',
            '-rtsp_transport', 'tcp',
            '-i', rtsp_url,
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-crf', '23',
            '-c:a', 'aac',  # Audio codec
            '-b:a', '128k',  # Audio bitrate
            '-movflags', '+faststart',
            '-t', str(settings.RECORDING_MAX_DURATION_SECONDS),
            str(main_filepath),
        ]
        
        logger.info("Starting FFmpeg recording with audio", cmd=' '.join(ffmpeg_cmd[:5]) + '...')
        
        ffmpeg_process = await asyncio.create_subprocess_exec(
            *ffmpeg_cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        
        recording = ActiveRecording(
            recording_id=recording_id,
            camera_id=camera_id,
            alert_id=alert_id,
            filepath=filepath,
            started_at=datetime.utcnow(),
            ffmpeg_process=ffmpeg_process,
            pre_roll_filepath=pre_roll_filepath if pre_roll_frames else None,
            main_filepath=main_filepath,
            rtsp_url=rtsp_url,
            frame_count=len(pre_roll_frames),
            pre_roll_written=True,
            use_audio=True,
        )
        
        return recording
    
    async def _start_video_only_recording(
        self,
        recording_id: str,
        camera_stream: CameraStream,
        alert_id: str,
        filepath: Path,
        pre_roll_frames: List[TimestampedFrame],
        width: int,
        height: int,
    ) -> ActiveRecording:
        """Start video-only recording using cv2.VideoWriter."""
        
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
            use_audio=False,
        )
        
        # Write pre-roll frames
        for frame in pre_roll_frames:
            writer.write(frame.frame)
            recording.frame_count += 1
        
        recording.pre_roll_written = True
        
        # Subscribe to new frames
        def frame_callback(frame: TimestampedFrame):
            self._write_frame(recording_id, frame)
        
        camera_stream.subscribe(frame_callback)
        
        # Store callback for unsubscription
        recording._frame_callback = frame_callback
        recording._camera_stream = camera_stream
        
        return recording
    
    def _write_frame(self, recording_id: str, frame: TimestampedFrame):
        """Write a frame to the recording (called from camera thread). Only for video-only mode."""
        if recording_id not in self._active_recordings:
            return
        
        recording = self._active_recordings[recording_id]
        
        # Audio recordings use FFmpeg, not frame callbacks
        if recording.use_audio:
            return
        
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
            if recording.writer:
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
        
        For audio recordings:
        1. Wait for post-roll
        2. Stop FFmpeg process
        3. Concatenate pre-roll video with main recording
        
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
        
        if recording.use_audio:
            # Stop FFmpeg and finalize audio recording
            await self._stop_audio_recording(recording)
        else:
            # Stop video-only recording
            await self._stop_video_only_recording(recording)
        
        ended_at = datetime.utcnow()
        duration = (ended_at - recording.started_at).total_seconds()
        
        async with self._lock:
            del self._active_recordings[recording_id]
        
        # Get file size
        file_size = recording.filepath.stat().st_size if recording.filepath.exists() else 0
        
        # Generate thumbnail
        thumbnail_path = await self._generate_thumbnail(recording.filepath)
        
        # Transcode to web-compatible format (only for video-only recordings)
        if not recording.use_audio:
            web_filepath = await self._transcode_for_web(recording.filepath)
        else:
            web_filepath = recording.filepath  # Already in good format
        
        logger.info(
            "Recording stopped",
            recording_id=recording_id,
            duration=duration,
            frames=recording.frame_count,
            file_size=file_size,
            audio_enabled=recording.use_audio,
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
            "started_at": to_utc_isoformat(recording.started_at),
            "ended_at": to_utc_isoformat(ended_at),
            "thumbnail_path": str(thumbnail_path) if thumbnail_path else None,
            "has_audio": recording.use_audio,
        }
    
    async def _stop_audio_recording(self, recording: ActiveRecording):
        """Stop FFmpeg recording and concatenate with pre-roll."""
        
        # Stop FFmpeg gracefully
        if recording.ffmpeg_process:
            try:
                # Send 'q' to FFmpeg to stop gracefully
                recording.ffmpeg_process.send_signal(signal.SIGINT)
                
                try:
                    _, stderr = await asyncio.wait_for(
                        recording.ffmpeg_process.communicate(),
                        timeout=10.0
                    )
                except asyncio.TimeoutError:
                    logger.warning("FFmpeg didn't stop gracefully, terminating")
                    recording.ffmpeg_process.terminate()
                    await recording.ffmpeg_process.wait()
                
                logger.info("FFmpeg recording stopped")
                
            except Exception as e:
                logger.error("Error stopping FFmpeg", error=str(e))
                try:
                    recording.ffmpeg_process.kill()
                except:
                    pass
        
        # Concatenate pre-roll with main recording
        if recording.pre_roll_filepath and recording.pre_roll_filepath.exists():
            await self._concatenate_recordings(
                pre_roll_path=recording.pre_roll_filepath,
                main_path=recording.main_filepath,
                output_path=recording.filepath,
            )
        elif recording.main_filepath and recording.main_filepath.exists():
            # No pre-roll, just rename main to final
            os.rename(recording.main_filepath, recording.filepath)
    
    async def _stop_video_only_recording(self, recording: ActiveRecording):
        """Stop video-only recording using cv2.VideoWriter."""
        
        # Unsubscribe from frames
        if hasattr(recording, '_camera_stream') and hasattr(recording, '_frame_callback'):
            recording._camera_stream.unsubscribe(recording._frame_callback)
        
        # Close writer
        if recording.writer:
            recording.writer.release()
    
    async def _concatenate_recordings(
        self,
        pre_roll_path: Path,
        main_path: Path,
        output_path: Path,
    ):
        """Concatenate pre-roll video with main recording using FFmpeg.
        
        Since pre-roll has no audio and main recording has audio, we need to
        add a silent audio track to pre-roll before concatenation.
        """
        
        if not main_path.exists():
            logger.warning("Main recording file not found, using pre-roll only", main_path=str(main_path))
            if pre_roll_path.exists():
                os.rename(pre_roll_path, output_path)
            return
        
        # If no pre-roll, just use main recording
        if not pre_roll_path or not pre_roll_path.exists():
            os.rename(main_path, output_path)
            return
        
        # First, add silent audio track to pre-roll to match main recording's audio
        pre_roll_with_audio = pre_roll_path.with_stem(pre_roll_path.stem + "_audio")
        concat_list_path = output_path.with_suffix('.txt')
        
        try:
            # Get pre-roll duration
            probe_cmd = [
                'ffprobe', '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                str(pre_roll_path)
            ]
            
            probe_process = await asyncio.create_subprocess_exec(
                *probe_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await probe_process.communicate()
            pre_roll_duration = float(stdout.decode().strip()) if stdout else 5.0
            
            # Add silent audio to pre-roll (matching AAC format of main recording)
            add_audio_cmd = [
                'ffmpeg', '-y',
                '-i', str(pre_roll_path),
                '-f', 'lavfi', '-i', f'anullsrc=r=8000:cl=mono:d={pre_roll_duration}',
                '-c:v', 'copy',
                '-c:a', 'aac',
                '-b:a', '128k',
                '-shortest',
                str(pre_roll_with_audio),
            ]
            
            logger.info("Adding silent audio to pre-roll", duration=pre_roll_duration)
            
            process = await asyncio.create_subprocess_exec(
                *add_audio_cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await process.communicate()
            
            if process.returncode != 0:
                logger.warning("Failed to add silent audio to pre-roll", stderr=stderr.decode()[:300])
                # Fall back to main recording only
                os.rename(main_path, output_path)
                return
            
            # Now concatenate with matching audio streams
            with open(concat_list_path, 'w') as f:
                f.write(f"file '{pre_roll_with_audio}'\n")
                f.write(f"file '{main_path}'\n")
            
            # Use FFmpeg concat demuxer
            concat_cmd = [
                'ffmpeg', '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', str(concat_list_path),
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-crf', '23',
                '-c:a', 'aac',
                '-b:a', '128k',
                '-movflags', '+faststart',
                str(output_path),
            ]
            
            logger.info("Concatenating recordings", pre_roll=str(pre_roll_with_audio), main=str(main_path))
            
            process = await asyncio.create_subprocess_exec(
                *concat_cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            
            _, stderr = await process.communicate()
            
            if process.returncode == 0:
                logger.info("Recordings concatenated successfully with audio")
            else:
                logger.error("Concatenation failed", stderr=stderr.decode()[:500])
                # Fall back to main recording (which has audio)
                if main_path.exists():
                    os.rename(main_path, output_path)
            
        finally:
            # Clean up temp files
            for temp_file in [concat_list_path, pre_roll_path, main_path, pre_roll_with_audio]:
                try:
                    if temp_file and temp_file.exists():
                        os.remove(temp_file)
                except Exception as e:
                    logger.warning(f"Failed to remove temp file {temp_file}: {e}")
    
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
    
    async def _transcode_for_web(self, video_path: Path, preserve_audio: bool = True) -> Optional[Path]:
        """Transcode video to web-compatible H.264 format, preserving audio if present."""
        try:
            output_path = video_path.with_stem(video_path.stem + "_web").with_suffix('.mp4')
            
            # Use ffmpeg for transcoding, include audio codec
            cmd = [
                'ffmpeg', '-y',
                '-i', str(video_path),
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-crf', '23',
            ]
            
            if preserve_audio:
                cmd.extend(['-c:a', 'aac', '-b:a', '128k'])
            else:
                cmd.extend(['-an'])  # No audio
            
            cmd.extend(['-movflags', '+faststart', str(output_path)])
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            
            _, stderr = await process.communicate()
            
            if process.returncode == 0:
                # Remove original, rename transcoded
                os.remove(video_path)
                os.rename(output_path, video_path)
                return video_path
            else:
                logger.error("Transcoding failed", stderr=stderr.decode()[:500])
                
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
                "started_at": to_utc_isoformat(r.started_at),
                "frame_count": r.frame_count,
                "duration": (datetime.utcnow() - r.started_at).total_seconds(),
            }
            for r in self._active_recordings.values()
        ]

