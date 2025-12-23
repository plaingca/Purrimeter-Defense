"""
Camera stream handling with frame buffer for recordings.

Includes automatic reconnection and recovery from RTSP stream loss.
"""

import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Callable, AsyncIterator, Deque
from enum import Enum
import threading
import time
import structlog
import cv2
import numpy as np
from PIL import Image

from backend.config import settings

logger = structlog.get_logger()


class StreamStatus(str, Enum):
    """Status of the camera stream connection."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


@dataclass
class TimestampedFrame:
    """A frame with its capture timestamp."""
    frame: np.ndarray
    timestamp: datetime
    frame_number: int


@dataclass
class CameraStream:
    """
    Manages an RTSP camera stream with frame buffering for pre-roll recordings.
    
    Maintains a ring buffer of recent frames for pre-roll capability,
    and provides async iteration over frames.
    
    Features automatic reconnection on stream loss with exponential backoff.
    """
    camera_id: str
    rtsp_url: str
    name: str = "Camera"
    fps: int = 30
    width: int = 1920
    height: int = 1080
    
    # Reconnection settings
    max_consecutive_failures: int = 10  # Failures before attempting reconnect
    initial_reconnect_delay: float = 1.0  # Initial delay in seconds
    max_reconnect_delay: float = 30.0  # Maximum delay between reconnection attempts
    reconnect_backoff_factor: float = 2.0  # Exponential backoff multiplier
    
    # Internal state
    _capture: Optional[cv2.VideoCapture] = field(default=None, repr=False)
    _running: bool = field(default=False, repr=False)
    _frame_buffer: Deque[TimestampedFrame] = field(default_factory=deque, repr=False)
    _current_frame: Optional[TimestampedFrame] = field(default=None, repr=False)
    _frame_count: int = field(default=0, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _read_thread: Optional[threading.Thread] = field(default=None, repr=False)
    _subscribers: list = field(default_factory=list, repr=False)
    
    # Connection state tracking
    _status: StreamStatus = field(default=StreamStatus.DISCONNECTED, repr=False)
    _consecutive_failures: int = field(default=0, repr=False)
    _reconnect_attempts: int = field(default=0, repr=False)
    _last_successful_read: Optional[float] = field(default=None, repr=False)
    _status_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    
    def __post_init__(self):
        # Initialize frame buffer with configured size
        self._frame_buffer = deque(maxlen=settings.FRAME_BUFFER_SIZE)
    
    def _set_status(self, status: StreamStatus):
        """Thread-safe status update."""
        with self._status_lock:
            if self._status != status:
                old_status = self._status
                self._status = status
                logger.info(
                    "Camera stream status changed",
                    camera_id=self.camera_id,
                    old_status=old_status.value,
                    new_status=status.value,
                )
    
    @property
    def status(self) -> StreamStatus:
        """Get current connection status."""
        with self._status_lock:
            return self._status
    
    @property
    def reconnect_attempts(self) -> int:
        """Get number of reconnection attempts since last successful connection."""
        return self._reconnect_attempts
    
    def _open_capture(self) -> bool:
        """Open the RTSP capture. Returns True on success."""
        try:
            # Release existing capture if any
            if self._capture is not None:
                try:
                    self._capture.release()
                except Exception:
                    pass
                self._capture = None
            
            # Open RTSP stream with timeout settings
            self._capture = cv2.VideoCapture(self.rtsp_url)
            
            if not self._capture.isOpened():
                logger.error("Failed to open camera stream", camera_id=self.camera_id)
                return False
            
            # Configure capture for lower latency
            self._capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
            # Get actual dimensions
            actual_width = int(self._capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_height = int(self._capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            actual_fps = self._capture.get(cv2.CAP_PROP_FPS)
            
            logger.info(
                "Camera stream opened",
                camera_id=self.camera_id,
                width=actual_width,
                height=actual_height,
                fps=actual_fps,
            )
            
            # Reset failure counters on successful connection
            self._consecutive_failures = 0
            self._reconnect_attempts = 0
            self._last_successful_read = time.time()
            
            return True
            
        except Exception as e:
            logger.error("Error opening camera stream", camera_id=self.camera_id, error=str(e))
            return False
    
    async def start(self) -> bool:
        """Start the camera stream."""
        if self._running:
            return True
        
        self._set_status(StreamStatus.CONNECTING)
        logger.info("Starting camera stream", camera_id=self.camera_id, url=self.rtsp_url)
        
        try:
            if not self._open_capture():
                self._set_status(StreamStatus.ERROR)
                return False
            
            self._running = True
            self._set_status(StreamStatus.CONNECTED)
            
            # Start frame reading thread
            self._read_thread = threading.Thread(
                target=self._read_frames_loop,
                daemon=True,
                name=f"camera-{self.camera_id}",
            )
            self._read_thread.start()
            
            return True
            
        except Exception as e:
            logger.error("Error starting camera stream", camera_id=self.camera_id, error=str(e))
            self._set_status(StreamStatus.ERROR)
            return False
    
    async def stop(self):
        """Stop the camera stream."""
        logger.info("Stopping camera stream", camera_id=self.camera_id)
        self._running = False
        self._set_status(StreamStatus.DISCONNECTED)
        
        if self._read_thread:
            self._read_thread.join(timeout=5.0)
            
        if self._capture:
            try:
                self._capture.release()
            except Exception:
                pass
            self._capture = None
        
        self._frame_buffer.clear()
        self._consecutive_failures = 0
        self._reconnect_attempts = 0
        logger.info("Camera stream stopped", camera_id=self.camera_id)
    
    def _reconnect(self) -> bool:
        """
        Attempt to reconnect to the RTSP stream with exponential backoff.
        
        Returns True if reconnection successful, False otherwise.
        """
        self._set_status(StreamStatus.RECONNECTING)
        self._reconnect_attempts += 1
        
        # Calculate delay with exponential backoff
        delay = min(
            self.initial_reconnect_delay * (self.reconnect_backoff_factor ** (self._reconnect_attempts - 1)),
            self.max_reconnect_delay
        )
        
        logger.info(
            "Attempting to reconnect camera stream",
            camera_id=self.camera_id,
            attempt=self._reconnect_attempts,
            delay_seconds=delay,
        )
        
        # Wait before reconnecting
        time.sleep(delay)
        
        # Check if we should still be running
        if not self._running:
            return False
        
        # Attempt to reconnect
        if self._open_capture():
            self._set_status(StreamStatus.CONNECTED)
            logger.info(
                "Camera stream reconnected successfully",
                camera_id=self.camera_id,
                attempts=self._reconnect_attempts,
            )
            return True
        else:
            self._set_status(StreamStatus.RECONNECTING)
            return False
    
    def _read_frames_loop(self):
        """
        Background thread that continuously reads frames.
        
        Includes automatic reconnection on stream loss.
        """
        frame_interval = 1.0 / self.fps
        last_frame_time = 0
        
        while self._running:
            # Check if capture is valid
            if self._capture is None or not self._capture.isOpened():
                if self._running:
                    if not self._reconnect():
                        continue  # Retry reconnection
                else:
                    break
            
            current_time = time.time()
            
            # Rate limit frame reading
            if current_time - last_frame_time < frame_interval:
                time.sleep(0.001)
                continue
            
            try:
                ret, frame = self._capture.read()
            except Exception as e:
                logger.error("Exception reading frame", camera_id=self.camera_id, error=str(e))
                ret = False
                frame = None
            
            if not ret or frame is None:
                self._consecutive_failures += 1
                
                if self._consecutive_failures >= self.max_consecutive_failures:
                    logger.warning(
                        "Too many consecutive frame read failures, attempting reconnect",
                        camera_id=self.camera_id,
                        failures=self._consecutive_failures,
                    )
                    self._consecutive_failures = 0
                    
                    if not self._reconnect():
                        continue  # Retry reconnection
                else:
                    # Brief sleep before retrying
                    time.sleep(0.1)
                continue
            
            # Successful read - reset failure counter
            self._consecutive_failures = 0
            self._last_successful_read = time.time()
            
            # Ensure we're marked as connected
            if self.status != StreamStatus.CONNECTED:
                self._set_status(StreamStatus.CONNECTED)
            
            last_frame_time = current_time
            self._frame_count += 1
            
            timestamped_frame = TimestampedFrame(
                frame=frame,
                timestamp=datetime.utcnow(),
                frame_number=self._frame_count,
            )
            
            with self._lock:
                self._current_frame = timestamped_frame
                self._frame_buffer.append(timestamped_frame)
                
                # Notify subscribers
                for callback in self._subscribers:
                    try:
                        callback(timestamped_frame)
                    except Exception as e:
                        logger.error("Subscriber callback error", error=str(e))
    
    def get_current_frame(self) -> Optional[TimestampedFrame]:
        """Get the most recent frame."""
        with self._lock:
            return self._current_frame
    
    def get_frame_as_pil(self) -> Optional[Image.Image]:
        """Get the current frame as a PIL Image."""
        frame = self.get_current_frame()
        if frame is None:
            return None
        
        # Convert BGR to RGB
        rgb_frame = cv2.cvtColor(frame.frame, cv2.COLOR_BGR2RGB)
        return Image.fromarray(rgb_frame)
    
    def get_pre_roll_frames(self, seconds: float = None) -> list[TimestampedFrame]:
        """
        Get frames from the buffer for pre-roll recording.
        
        Args:
            seconds: Number of seconds of pre-roll to get (default: config setting)
            
        Returns:
            List of frames, oldest first
        """
        if seconds is None:
            seconds = settings.RECORDING_PRE_ROLL_SECONDS
        
        frames_needed = int(seconds * self.fps)
        
        with self._lock:
            # Get the last N frames from buffer
            available_frames = list(self._frame_buffer)
            
        if len(available_frames) <= frames_needed:
            return available_frames
        
        return available_frames[-frames_needed:]
    
    def subscribe(self, callback: Callable[[TimestampedFrame], None]):
        """Subscribe to new frames."""
        with self._lock:
            self._subscribers.append(callback)
    
    def unsubscribe(self, callback: Callable[[TimestampedFrame], None]):
        """Unsubscribe from new frames."""
        with self._lock:
            if callback in self._subscribers:
                self._subscribers.remove(callback)
    
    async def frames(self, sample_rate: float = None) -> AsyncIterator[TimestampedFrame]:
        """
        Async iterator that yields frames at a specified sample rate.
        
        Args:
            sample_rate: Frames per second to yield (default: detection sample rate)
        """
        if sample_rate is None:
            sample_rate = settings.DETECTION_SAMPLE_RATE
        
        interval = 1.0 / sample_rate
        last_yield_time = 0
        
        while self._running:
            current_time = time.time()
            
            if current_time - last_yield_time >= interval:
                frame = self.get_current_frame()
                if frame:
                    yield frame
                    last_yield_time = current_time
            
            await asyncio.sleep(0.01)  # Small sleep to prevent busy loop
    
    def get_jpeg_frame(self, quality: int = 80) -> Optional[bytes]:
        """Get current frame as JPEG bytes for streaming."""
        frame = self.get_current_frame()
        if frame is None:
            return None
        
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
        _, jpeg = cv2.imencode('.jpg', frame.frame, encode_param)
        return jpeg.tobytes()
    
    @property
    def is_running(self) -> bool:
        """Check if stream is running."""
        return self._running
    
    @property
    def frame_count(self) -> int:
        """Get total frames read."""
        return self._frame_count

