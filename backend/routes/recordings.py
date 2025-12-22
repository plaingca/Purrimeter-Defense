"""
Recordings API routes.
"""

from typing import List, Optional
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import Recording, get_db
from backend.config import settings

router = APIRouter()


class RecordingResponse(BaseModel):
    """Schema for recording response."""
    id: str
    camera_id: str
    alert_id: Optional[str]
    filename: str
    filepath: str
    duration_seconds: Optional[float]
    file_size_bytes: Optional[int]
    thumbnail_path: Optional[str]
    started_at: str
    ended_at: Optional[str]
    discord_sent: bool
    created_at: str
    
    class Config:
        from_attributes = True


@router.get("/", response_model=List[RecordingResponse])
async def list_recordings(
    camera_id: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List recordings, optionally filtered by camera."""
    query = select(Recording).order_by(desc(Recording.created_at))
    
    if camera_id:
        query = query.where(Recording.camera_id == camera_id)
    
    query = query.offset(offset).limit(limit)
    
    result = await db.execute(query)
    recordings = result.scalars().all()
    
    return [
        RecordingResponse(
            id=r.id,
            camera_id=r.camera_id,
            alert_id=r.alert_id,
            filename=r.filename,
            filepath=r.filepath,
            duration_seconds=r.duration_seconds,
            file_size_bytes=r.file_size_bytes,
            thumbnail_path=r.thumbnail_path,
            started_at=r.started_at.isoformat(),
            ended_at=r.ended_at.isoformat() if r.ended_at else None,
            discord_sent=r.discord_sent,
            created_at=r.created_at.isoformat(),
        )
        for r in recordings
    ]


@router.get("/{recording_id}", response_model=RecordingResponse)
async def get_recording(recording_id: str, db: AsyncSession = Depends(get_db)):
    """Get a specific recording by ID."""
    result = await db.execute(select(Recording).where(Recording.id == recording_id))
    recording = result.scalar_one_or_none()
    
    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found")
    
    return RecordingResponse(
        id=recording.id,
        camera_id=recording.camera_id,
        alert_id=recording.alert_id,
        filename=recording.filename,
        filepath=recording.filepath,
        duration_seconds=recording.duration_seconds,
        file_size_bytes=recording.file_size_bytes,
        thumbnail_path=recording.thumbnail_path,
        started_at=recording.started_at.isoformat(),
        ended_at=recording.ended_at.isoformat() if recording.ended_at else None,
        discord_sent=recording.discord_sent,
        created_at=recording.created_at.isoformat(),
    )


@router.get("/{recording_id}/video")
async def get_recording_video(recording_id: str, db: AsyncSession = Depends(get_db)):
    """Stream or download a recording video."""
    result = await db.execute(select(Recording).where(Recording.id == recording_id))
    recording = result.scalar_one_or_none()
    
    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found")
    
    video_path = Path(recording.filepath)
    
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video file not found")
    
    return FileResponse(
        path=video_path,
        media_type="video/mp4",
        filename=recording.filename,
    )


@router.get("/{recording_id}/thumbnail")
async def get_recording_thumbnail(recording_id: str, db: AsyncSession = Depends(get_db)):
    """Get a recording's thumbnail image."""
    result = await db.execute(select(Recording).where(Recording.id == recording_id))
    recording = result.scalar_one_or_none()
    
    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found")
    
    if not recording.thumbnail_path:
        raise HTTPException(status_code=404, detail="Thumbnail not available")
    
    thumbnail_path = Path(recording.thumbnail_path)
    
    if not thumbnail_path.exists():
        raise HTTPException(status_code=404, detail="Thumbnail file not found")
    
    return FileResponse(
        path=thumbnail_path,
        media_type="image/jpeg",
    )


@router.delete("/{recording_id}")
async def delete_recording(recording_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a recording and its files."""
    result = await db.execute(select(Recording).where(Recording.id == recording_id))
    recording = result.scalar_one_or_none()
    
    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found")
    
    # Delete files
    video_path = Path(recording.filepath)
    if video_path.exists():
        video_path.unlink()
    
    if recording.thumbnail_path:
        thumbnail_path = Path(recording.thumbnail_path)
        if thumbnail_path.exists():
            thumbnail_path.unlink()
    
    # Delete from database
    await db.delete(recording)
    await db.commit()
    
    return {"message": "Recording deleted", "id": recording_id}


@router.get("/stats/summary")
async def get_recording_stats(
    camera_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Get recording statistics."""
    from sqlalchemy import func
    
    query = select(
        func.count(Recording.id).label("total_count"),
        func.sum(Recording.duration_seconds).label("total_duration"),
        func.sum(Recording.file_size_bytes).label("total_size"),
    )
    
    if camera_id:
        query = query.where(Recording.camera_id == camera_id)
    
    result = await db.execute(query)
    row = result.first()
    
    return {
        "total_recordings": row.total_count or 0,
        "total_duration_seconds": float(row.total_duration or 0),
        "total_size_bytes": int(row.total_size or 0),
        "total_size_mb": round((row.total_size or 0) / (1024 * 1024), 2),
    }

