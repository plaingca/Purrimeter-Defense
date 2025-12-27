"""
Recordings API routes.
"""

from typing import List, Optional
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Depends, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import Recording, get_db
from backend.config import settings
from backend.utils import to_utc_isoformat

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
    mask_thumbnail_path: Optional[str]
    mask_video_path: Optional[str]
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
            mask_thumbnail_path=r.mask_thumbnail_path,
            mask_video_path=r.mask_video_path,
            started_at=to_utc_isoformat(r.started_at),
            ended_at=to_utc_isoformat(r.ended_at),
            discord_sent=r.discord_sent,
            created_at=to_utc_isoformat(r.created_at),
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
        mask_thumbnail_path=recording.mask_thumbnail_path,
        mask_video_path=recording.mask_video_path,
        started_at=to_utc_isoformat(recording.started_at),
        ended_at=to_utc_isoformat(recording.ended_at),
        discord_sent=recording.discord_sent,
        created_at=to_utc_isoformat(recording.created_at),
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


@router.get("/{recording_id}/mask-thumbnail")
async def get_recording_mask_thumbnail(recording_id: str, db: AsyncSession = Depends(get_db)):
    """Get a recording's mask thumbnail image showing what triggered the detection."""
    result = await db.execute(select(Recording).where(Recording.id == recording_id))
    recording = result.scalar_one_or_none()
    
    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found")
    
    if not recording.mask_thumbnail_path:
        raise HTTPException(status_code=404, detail="Mask thumbnail not available")
    
    mask_thumbnail_path = Path(recording.mask_thumbnail_path)
    
    if not mask_thumbnail_path.exists():
        raise HTTPException(status_code=404, detail="Mask thumbnail file not found")
    
    return FileResponse(
        path=mask_thumbnail_path,
        media_type="image/jpeg",
    )


@router.get("/{recording_id}/mask-video")
async def get_recording_mask_video(recording_id: str, db: AsyncSession = Depends(get_db)):
    """Get a recording's mask video with detection overlays on every frame."""
    result = await db.execute(select(Recording).where(Recording.id == recording_id))
    recording = result.scalar_one_or_none()
    
    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found")
    
    if not recording.mask_video_path:
        raise HTTPException(status_code=404, detail="Mask video not available - run mask video generation first")
    
    mask_video_path = Path(recording.mask_video_path)
    
    if not mask_video_path.exists():
        raise HTTPException(status_code=404, detail="Mask video file not found")
    
    return FileResponse(
        path=mask_video_path,
        media_type="video/mp4",
        filename=f"{recording.filename.replace('.mp4', '_mask.mp4')}",
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
    
    if recording.mask_thumbnail_path:
        mask_thumbnail_path = Path(recording.mask_thumbnail_path)
        if mask_thumbnail_path.exists():
            mask_thumbnail_path.unlink()
    
    if recording.mask_video_path:
        mask_video_path = Path(recording.mask_video_path)
        if mask_video_path.exists():
            mask_video_path.unlink()
    
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


@router.get("/mask-generation/status")
async def get_mask_generation_status(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Get mask video generation status for all recordings."""
    from sqlalchemy import func
    import json
    
    # Get counts
    total_query = select(func.count(Recording.id))
    with_mask_query = select(func.count(Recording.id)).where(Recording.mask_video_path != None)
    
    total_result = await db.execute(total_query)
    with_mask_result = await db.execute(with_mask_query)
    
    total_recordings = total_result.scalar() or 0
    with_mask_videos = with_mask_result.scalar() or 0
    pending = total_recordings - with_mask_videos
    
    # Get list of recordings pending mask generation
    pending_query = (
        select(Recording.id, Recording.filename, Recording.duration_seconds)
        .where(Recording.mask_video_path == None)
        .order_by(Recording.created_at.desc())
        .limit(10)
    )
    pending_result = await db.execute(pending_query)
    pending_recordings = [
        {
            "id": r.id,
            "filename": r.filename,
            "duration_seconds": r.duration_seconds,
        }
        for r in pending_result.all()
    ]
    
    # Check for batch processing progress file
    batch_progress = None
    progress_file = settings.RECORDINGS_PATH / "mask_generation_progress.json"
    try:
        if progress_file.exists():
            with open(progress_file, 'r') as f:
                batch_progress = json.load(f)
    except Exception:
        pass
    
    # Check if pipeline manager has any active mask generation tasks
    currently_processing = None
    active_tasks = []
    
    try:
        pipeline_manager = request.app.state.pipeline_manager
        if hasattr(pipeline_manager, '_mask_video_tasks'):
            active_tasks = list(pipeline_manager._mask_video_tasks.keys())
            if active_tasks:
                # Get details for the first active task
                recording_id = active_tasks[0]
                rec_result = await db.execute(
                    select(Recording).where(Recording.id == recording_id)
                )
                rec = rec_result.scalar_one_or_none()
                if rec:
                    currently_processing = {
                        "recording_id": recording_id,
                        "filename": rec.filename,
                        "duration_seconds": rec.duration_seconds,
                    }
    except Exception:
        pass
    
    # Use batch progress if available and no pipeline task is active
    if batch_progress and not currently_processing:
        currently_processing = {
            "filename": batch_progress.get("current_filename"),
            "current_frame": batch_progress.get("current_frame", 0),
            "total_frames": batch_progress.get("total_frames", 0),
            "percent_video": batch_progress.get("percent_video", 0),
            "batch_current": batch_progress.get("current_recording", 0),
            "batch_total": batch_progress.get("total_recordings", 0),
        }
    
    is_batch_running = batch_progress is not None and batch_progress.get("status") == "processing"
    
    return {
        "total_recordings": total_recordings,
        "with_mask_videos": with_mask_videos,
        "pending": pending,
        "percent_complete": round(100 * with_mask_videos / total_recordings, 1) if total_recordings > 0 else 100,
        "currently_processing": currently_processing,
        "active_tasks_count": len(active_tasks),
        "is_batch_running": is_batch_running,
        "pending_recordings": pending_recordings,
    }

