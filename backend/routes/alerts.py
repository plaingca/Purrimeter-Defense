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
            triggered_at=a.triggered_at.isoformat(),
            ended_at=a.ended_at.isoformat() if a.ended_at else None,
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
        triggered_at=alert.triggered_at.isoformat(),
        ended_at=alert.ended_at.isoformat() if alert.ended_at else None,
    )


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
            "triggered_at": alert.triggered_at.isoformat(),
            "ended_at": alert.ended_at.isoformat() if alert.ended_at else None,
            "duration_seconds": (
                (alert.ended_at - alert.triggered_at).total_seconds()
                if alert.ended_at else None
            ),
        })
    
    return {
        "hours": hours,
        "since": since.isoformat(),
        "alerts": timeline,
    }

