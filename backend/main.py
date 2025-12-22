"""
🐱 Purrimeter Defense - Main Application
A vision-based intrusion detection system for enforcing strict counter boundaries.
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.config import settings
from backend.database import init_db, get_all_cameras, get_rules_for_camera
from backend.routes import cameras, rules, recordings, alerts, streams, actions, detection
from backend.services.pipeline_manager import PipelineManager
from backend.services.sam3_service import SAM3Service

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifespan manager."""
    logger.info("🐱 Purrimeter Defense starting up...")
    
    # Initialize database
    await init_db()
    logger.info("✅ Database initialized")
    
    # Initialize SAM3 service
    app.state.sam3_service = SAM3Service()
    await app.state.sam3_service.initialize()
    logger.info("✅ SAM3 model loaded")
    
    # Initialize pipeline manager
    app.state.pipeline_manager = PipelineManager(app.state.sam3_service)
    await app.state.pipeline_manager.start()
    logger.info("✅ Pipeline manager started")
    
    # Load existing cameras and start their pipelines
    try:
        existing_cameras = await get_all_cameras()
        for camera in existing_cameras:
            if camera.enabled:
                success = await app.state.pipeline_manager.add_camera(camera)
                if success:
                    logger.info("✅ Camera pipeline started", camera=camera.name, camera_id=camera.id)
                    
                    # Load rules for this camera
                    camera_rules = await get_rules_for_camera(camera.id)
                    for rule in camera_rules:
                        if rule.enabled:
                            await app.state.pipeline_manager.add_rule(rule)
                else:
                    logger.warning("⚠️ Failed to start camera pipeline", camera=camera.name)
        
        logger.info(f"✅ Loaded {len(existing_cameras)} cameras")
    except Exception as e:
        logger.error("Failed to load cameras", error=str(e))
    
    logger.info("🚀 Purrimeter Defense is ready to protect your counters!")
    
    yield
    
    # Cleanup
    logger.info("🐱 Purrimeter Defense shutting down...")
    await app.state.pipeline_manager.stop()
    logger.info("✅ Pipeline manager stopped")


app = FastAPI(
    title="🐱 Purrimeter Defense",
    description="Vision-based intrusion detection for enforcing strict counter boundaries against mischievous kitties",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for recordings
app.mount("/recordings", StaticFiles(directory=settings.RECORDINGS_PATH), name="recordings")

# Include routers
app.include_router(cameras.router, prefix="/api/cameras", tags=["Cameras"])
app.include_router(rules.router, prefix="/api/rules", tags=["Rules"])
app.include_router(recordings.router, prefix="/api/recordings", tags=["Recordings"])
app.include_router(alerts.router, prefix="/api/alerts", tags=["Alerts"])
app.include_router(streams.router, prefix="/api/streams", tags=["Streams"])
app.include_router(actions.router, prefix="/api/actions", tags=["Actions"])
app.include_router(detection.router, prefix="/api/detection", tags=["Detection"])


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "Purrimeter Defense",
        "timestamp": datetime.utcnow().isoformat(),
        "emoji": "🐱",
    }


@app.get("/")
async def root():
    """Root endpoint with fun cat defense message."""
    return {
        "message": "🐱 Welcome to Purrimeter Defense!",
        "description": "Your counters are under our watchful protection.",
        "status": "Vigilant",
        "docs": "/docs",
    }

