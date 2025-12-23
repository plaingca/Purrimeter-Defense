"""
Configuration settings for Purrimeter Defense.
"""

from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Database
    DATABASE_URL: str = "postgresql://purrimeter:purrimeter@postgres:5432/purrimeter"
    
    # Redis
    REDIS_URL: str = "redis://redis:6379"
    
    # HuggingFace
    HF_TOKEN: Optional[str] = None
    
    # SAM3 Model
    SAM3_MODEL_ID: str = "facebook/sam3"
    SAM3_DEVICE: str = "cuda"
    SAM3_DTYPE: str = "float16"
    SAM3_MAX_CONCURRENT_INFERENCE: int = 1  # Only 1 inference at a time on GPU
    SAM3_INFERENCE_WORKERS: int = 1  # Single inference worker to avoid GPU contention
    
    # Image processing (CPU-bound, can be parallel)
    IMAGE_PROCESSING_WORKERS: int = 8  # More workers for image encoding/decoding
    
    # Streaming settings
    MJPEG_FPS: int = 10  # Lower FPS for MJPEG streams to reduce load
    OVERLAY_CACHE_MS: int = 500  # Cache overlay renders for 500ms
    
    # Recording settings
    RECORDINGS_PATH: Path = Path("/app/recordings")
    RECORDING_PRE_ROLL_SECONDS: int = 5
    RECORDING_POST_ROLL_SECONDS: int = 3
    RECORDING_FPS: int = 15
    RECORDING_MAX_DURATION_SECONDS: int = 300  # 5 minutes max
    RECORDING_INCLUDE_AUDIO: bool = True  # Record audio from RTSP stream
    
    # Frame buffer for pre-roll (ring buffer size)
    FRAME_BUFFER_SIZE: int = 150  # 5 seconds at 30fps
    
    # Detection settings
    DETECTION_CONFIDENCE_THRESHOLD: float = 0.5
    DETECTION_SAMPLE_RATE: float = 0.5  # Samples per second (1 every 2 seconds to reduce GPU load)
    DETECTION_CONSECUTIVE_FRAMES: int = 1  # Consecutive detections required to trigger alert (1 = instant)
    
    # Discord
    DISCORD_WEBHOOK_URL: Optional[str] = None
    
    # Smart home
    KASA_DEVICE_IP: Optional[str] = None
    
    # Tapo Camera Speaker
    TAPO_CAMERA_IP: Optional[str] = None
    TAPO_CAMERA_USER: Optional[str] = None
    TAPO_CAMERA_PASSWORD: Optional[str] = None
    
    # Alert settings
    ALERT_COOLDOWN_SECONDS: int = 30  # Minimum time between alerts for same rule
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

# Ensure recordings directory exists
settings.RECORDINGS_PATH.mkdir(parents=True, exist_ok=True)

