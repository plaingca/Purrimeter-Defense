"""
Alerts API routes.
"""

from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import Alert, AlertState, get_db
from backend.utils import to_utc_isoformat

router = APIRouter()


class AlertResponse(BaseModel):
    """Schema for alert response."""
    id: str
    camera_id: str
    rule_id: str
    state: str
    message: Optional[str]
    detected_objects: List[dict]
    detection_confidence: Optional[float]
    triggered_at: str
    ended_at: Optional[str]
    
    class Config:
        from_attributes = True


@router.get("/", response_model=List[AlertResponse])
async def list_alerts(
    camera_id: Optional[str] = None,
    rule_id: Optional[str] = None,
    state: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List alerts with optional filters."""
    query = select(Alert).order_by(desc(Alert.triggered_at))
    
    if camera_id:
        query = query.where(Alert.camera_id == camera_id)
    if rule_id:
        query = query.where(Alert.rule_id == rule_id)
    if state:
        query = query.where(Alert.state == state)
    
    query = query.offset(offset).limit(limit)
    
    result = await db.execute(query)
    alerts = result.scalars().all()
    
    return [
        AlertResponse(
            id=a.id,
            camera_id=a.camera_id,
            rule_id=a.rule_id,
            state=a.state.value if a.state else "unknown",
            message=a.message,
            detected_objects=a.detected_objects or [],
            detection_confidence=a.detection_confidence,
            triggered_at=to_utc_isoformat(a.triggered_at),
            ended_at=to_utc_isoformat(a.ended_at),
        )
        for a in alerts
    ]


@router.get("/active", response_model=List[AlertResponse])
async def list_active_alerts(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """List currently active alerts."""
    # Get from rule engine state
    pipeline_manager = request.app.state.pipeline_manager
    rule_states = pipeline_manager.rule_engine.get_rule_states()
    
    active_alerts = []
    for rule_id, state in rule_states.items():
        if state["is_in_alert"]:
            active_alerts.append({
                "id": state["current_alert_id"],
                "rule_id": rule_id,
                "rule_name": state["rule_name"],
                "is_active": True,
            })
    
    return active_alerts


@router.get("/stats/summary")
async def get_alert_stats(
    camera_id: Optional[str] = None,
    since: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
):
    """Get alert statistics."""
    from sqlalchemy import func
    
    query = select(
        func.count(Alert.id).label("total_count"),
        func.count(Alert.id).filter(Alert.state == AlertState.TRIGGERED).label("triggered_count"),
    )
    
    if camera_id:
        query = query.where(Alert.camera_id == camera_id)
    if since:
        query = query.where(Alert.triggered_at >= since)
    
    result = await db.execute(query)
    row = result.first()
    
    return {
        "total_alerts": row.total_count or 0,
        "triggered_count": row.triggered_count or 0,
    }


@router.get("/timeline")
async def get_alert_timeline(
    camera_id: Optional[str] = None,
    hours: int = Query(default=24, ge=1, le=168),
    db: AsyncSession = Depends(get_db),
):
    """Get alert timeline for visualization."""
    from sqlalchemy import func
    from datetime import timedelta
    
    since = datetime.utcnow() - timedelta(hours=hours)
    
    query = select(Alert).where(Alert.triggered_at >= since)
    
    if camera_id:
        query = query.where(Alert.camera_id == camera_id)
    
    query = query.order_by(Alert.triggered_at)
    
    result = await db.execute(query)
    alerts = result.scalars().all()
    
    timeline = []
    for alert in alerts:
        timeline.append({
            "id": alert.id,
            "camera_id": alert.camera_id,
            "rule_id": alert.rule_id,
            "triggered_at": to_utc_isoformat(alert.triggered_at),
            "ended_at": to_utc_isoformat(alert.ended_at),
            "duration_seconds": (
                (alert.ended_at - alert.triggered_at).total_seconds()
                if alert.ended_at else None
            ),
        })
    
    return {
        "hours": hours,
        "since": to_utc_isoformat(since),
        "alerts": timeline,
    }


@router.get("/events")
async def get_detection_events(
    camera_id: Optional[str] = None,
    rule_id: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """
    Get combined detection events with alert and recording details.
    This is the main endpoint for the event explorer.
    """
    from sqlalchemy.orm import selectinload, joinedload
    from datetime import timedelta
    from backend.database import Recording, Rule, Camera
    
    # Default to last 7 days if no date range specified
    if not date_from:
        date_from = datetime.utcnow() - timedelta(days=7)
    else:
        # Strip timezone info to make naive datetime (database uses naive UTC)
        date_from = date_from.replace(tzinfo=None) if date_from.tzinfo else date_from
    
    if not date_to:
        date_to = datetime.utcnow()
    else:
        # Strip timezone info to make naive datetime (database uses naive UTC)
        date_to = date_to.replace(tzinfo=None) if date_to.tzinfo else date_to
    
    # Build query with eager loading of relationships
    query = (
        select(Alert)
        .options(
            selectinload(Alert.recording),
            selectinload(Alert.rule),
            selectinload(Alert.camera),
        )
        .where(Alert.triggered_at >= date_from)
        .where(Alert.triggered_at <= date_to)
        .order_by(desc(Alert.triggered_at))
    )
    
    if camera_id:
        query = query.where(Alert.camera_id == camera_id)
    if rule_id:
        query = query.where(Alert.rule_id == rule_id)
    
    # Get total count for pagination
    count_query = select(Alert).where(Alert.triggered_at >= date_from).where(Alert.triggered_at <= date_to)
    if camera_id:
        count_query = count_query.where(Alert.camera_id == camera_id)
    if rule_id:
        count_query = count_query.where(Alert.rule_id == rule_id)
    
    from sqlalchemy import func
    count_result = await db.execute(select(func.count()).select_from(count_query.subquery()))
    total_count = count_result.scalar()
    
    query = query.offset(offset).limit(limit)
    
    result = await db.execute(query)
    alerts = result.unique().scalars().all()
    
    events = []
    for alert in alerts:
        event = {
            "id": alert.id,
            "type": "detection",
            "camera_id": alert.camera_id,
            "camera_name": alert.camera.name if alert.camera else None,
            "rule_id": alert.rule_id,
            "rule_name": alert.rule.name if alert.rule else None,
            "primary_target": alert.rule.primary_target if alert.rule else None,
            "secondary_target": alert.rule.secondary_target if alert.rule else None,
            "state": alert.state.value if alert.state else "unknown",
            "message": alert.message,
            "detected_objects": alert.detected_objects or [],
            "detection_confidence": alert.detection_confidence,
            "triggered_at": to_utc_isoformat(alert.triggered_at),
            "ended_at": to_utc_isoformat(alert.ended_at),
            "duration_seconds": (
                (alert.ended_at - alert.triggered_at).total_seconds()
                if alert.ended_at else None
            ),
            "recording": None,
        }
        
        # Include recording data if available
        if alert.recording:
            rec = alert.recording
            event["recording"] = {
                "id": rec.id,
                "filename": rec.filename,
                "filepath": rec.filepath,
                "duration_seconds": rec.duration_seconds,
                "file_size_bytes": rec.file_size_bytes,
                "thumbnail_path": rec.thumbnail_path,
                "mask_thumbnail_path": rec.mask_thumbnail_path,
                "mask_video_path": rec.mask_video_path,
                "discord_sent": rec.discord_sent,
            }
        
        events.append(event)
    
    return {
        "events": events,
        "total_count": total_count,
        "limit": limit,
        "offset": offset,
        "date_from": to_utc_isoformat(date_from),
        "date_to": to_utc_isoformat(date_to),
    }


@router.get("/events/daily-summary")
async def get_daily_event_summary(
    camera_id: Optional[str] = None,
    days: int = Query(default=30, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
):
    """Get daily event counts for the timeline chart."""
    from sqlalchemy import func, cast, Date
    from datetime import timedelta
    
    since = datetime.utcnow() - timedelta(days=days)
    
    query = (
        select(
            cast(Alert.triggered_at, Date).label("date"),
            func.count(Alert.id).label("count"),
        )
        .where(Alert.triggered_at >= since)
        .group_by(cast(Alert.triggered_at, Date))
        .order_by(cast(Alert.triggered_at, Date))
    )
    
    if camera_id:
        query = query.where(Alert.camera_id == camera_id)
    
    result = await db.execute(query)
    rows = result.all()
    
    # Build complete date range with zeros for missing days
    summary = {}
    current = since.date()
    end = datetime.utcnow().date()
    while current <= end:
        summary[current.isoformat()] = 0
        current += timedelta(days=1)
    
    # Fill in actual counts
    for row in rows:
        summary[row.date.isoformat()] = row.count
    
    return {
        "days": days,
        "since": to_utc_isoformat(since),
        "summary": [{"date": k, "count": v} for k, v in summary.items()],
    }


# This must be last because it's a catch-all for /{alert_id}
@router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(alert_id: str, db: AsyncSession = Depends(get_db)):
    """Get a specific alert by ID."""
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()
    
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    return AlertResponse(
        id=alert.id,
        camera_id=alert.camera_id,
        rule_id=alert.rule_id,
        state=alert.state.value if alert.state else "unknown",
        message=alert.message,
        detected_objects=alert.detected_objects or [],
        detection_confidence=alert.detection_confidence,
        triggered_at=to_utc_isoformat(alert.triggered_at),
        ended_at=to_utc_isoformat(alert.ended_at),
    )
