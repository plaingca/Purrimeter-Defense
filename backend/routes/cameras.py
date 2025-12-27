"""
Camera management API routes.
"""

from typing import List, Optional
import uuid

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import Camera, get_db
from backend.utils import to_utc_isoformat

router = APIRouter()


class CameraCreate(BaseModel):
    """Schema for creating a camera."""
    name: str = Field(..., description="Display name for the camera")
    rtsp_url: str = Field(..., description="RTSP stream URL")
    fps: int = Field(default=30, ge=1, le=60, description="Frames per second")
    width: int = Field(default=1920, ge=320, le=3840, description="Frame width")
    height: int = Field(default=1080, ge=240, le=2160, description="Frame height")
    enabled: bool = Field(default=True, description="Whether camera is active")


class CameraUpdate(BaseModel):
    """Schema for updating a camera."""
    name: Optional[str] = None
    rtsp_url: Optional[str] = None
    fps: Optional[int] = Field(default=None, ge=1, le=60)
    width: Optional[int] = Field(default=None, ge=320, le=3840)
    height: Optional[int] = Field(default=None, ge=240, le=2160)
    enabled: Optional[bool] = None


class CameraResponse(BaseModel):
    """Schema for camera response."""
    id: str
    name: str
    rtsp_url: str
    fps: int
    width: int
    height: int
    enabled: bool
    created_at: str
    updated_at: str
    
    class Config:
        from_attributes = True


@router.get("/", response_model=List[CameraResponse])
async def list_cameras(db: AsyncSession = Depends(get_db)):
    """List all configured cameras."""
    result = await db.execute(select(Camera))
    cameras = result.scalars().all()
    
    return [
        CameraResponse(
            id=c.id,
            name=c.name,
            rtsp_url=c.rtsp_url,
            fps=c.fps,
            width=c.width,
            height=c.height,
            enabled=c.enabled,
            created_at=to_utc_isoformat(c.created_at),
            updated_at=to_utc_isoformat(c.updated_at),
        )
        for c in cameras
    ]


@router.post("/", response_model=CameraResponse)
async def create_camera(
    camera: CameraCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Add a new camera."""
    camera_id = str(uuid.uuid4())
    
    db_camera = Camera(
        id=camera_id,
        name=camera.name,
        rtsp_url=camera.rtsp_url,
        fps=camera.fps,
        width=camera.width,
        height=camera.height,
        enabled=camera.enabled,
    )
    
    db.add(db_camera)
    await db.commit()
    await db.refresh(db_camera)
    
    # Add to pipeline manager if enabled
    if camera.enabled:
        pipeline_manager = request.app.state.pipeline_manager
        await pipeline_manager.add_camera(db_camera)
    
    return CameraResponse(
        id=db_camera.id,
        name=db_camera.name,
        rtsp_url=db_camera.rtsp_url,
        fps=db_camera.fps,
        width=db_camera.width,
        height=db_camera.height,
        enabled=db_camera.enabled,
        created_at=to_utc_isoformat(db_camera.created_at),
        updated_at=to_utc_isoformat(db_camera.updated_at),
    )


@router.get("/{camera_id}", response_model=CameraResponse)
async def get_camera(camera_id: str, db: AsyncSession = Depends(get_db)):
    """Get a specific camera by ID."""
    result = await db.execute(select(Camera).where(Camera.id == camera_id))
    camera = result.scalar_one_or_none()
    
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    return CameraResponse(
        id=camera.id,
        name=camera.name,
        rtsp_url=camera.rtsp_url,
        fps=camera.fps,
        width=camera.width,
        height=camera.height,
        enabled=camera.enabled,
        created_at=to_utc_isoformat(camera.created_at),
        updated_at=to_utc_isoformat(camera.updated_at),
    )


@router.patch("/{camera_id}", response_model=CameraResponse)
async def update_camera(
    camera_id: str,
    update: CameraUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Update a camera's configuration."""
    result = await db.execute(select(Camera).where(Camera.id == camera_id))
    camera = result.scalar_one_or_none()
    
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    # Check if we need to restart the pipeline
    restart_needed = False
    was_enabled = camera.enabled
    
    # Update fields
    update_data = update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(camera, field, value)
        if field in ("rtsp_url", "fps", "width", "height"):
            restart_needed = True
    
    await db.commit()
    await db.refresh(camera)
    
    pipeline_manager = request.app.state.pipeline_manager
    
    # Handle pipeline updates
    if restart_needed or (was_enabled and not camera.enabled):
        await pipeline_manager.remove_camera(camera_id)
    
    if camera.enabled and (restart_needed or not was_enabled):
        await pipeline_manager.add_camera(camera)
    
    return CameraResponse(
        id=camera.id,
        name=camera.name,
        rtsp_url=camera.rtsp_url,
        fps=camera.fps,
        width=camera.width,
        height=camera.height,
        enabled=camera.enabled,
        created_at=to_utc_isoformat(camera.created_at),
        updated_at=to_utc_isoformat(camera.updated_at),
    )


@router.delete("/{camera_id}")
async def delete_camera(
    camera_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Delete a camera."""
    result = await db.execute(select(Camera).where(Camera.id == camera_id))
    camera = result.scalar_one_or_none()
    
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    # Remove from pipeline
    pipeline_manager = request.app.state.pipeline_manager
    await pipeline_manager.remove_camera(camera_id)
    
    # Delete from database
    await db.delete(camera)
    await db.commit()
    
    return {"message": "Camera deleted", "id": camera_id}


@router.get("/{camera_id}/status")
async def get_camera_status(camera_id: str, request: Request):
    """Get real-time status of a camera pipeline."""
    pipeline_manager = request.app.state.pipeline_manager
    status = pipeline_manager.get_pipeline_status(camera_id)
    
    if not status:
        raise HTTPException(status_code=404, detail="Camera pipeline not found")
    
    return status


@router.post("/{camera_id}/restart")
async def restart_camera(
    camera_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Restart a camera's pipeline."""
    result = await db.execute(select(Camera).where(Camera.id == camera_id))
    camera = result.scalar_one_or_none()
    
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    pipeline_manager = request.app.state.pipeline_manager
    
    await pipeline_manager.remove_camera(camera_id)
    success = await pipeline_manager.add_camera(camera)
    
    return {
        "message": "Camera restarted" if success else "Failed to restart camera",
        "success": success,
    }

