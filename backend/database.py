"""
Database configuration and models for Purrimeter Defense.
"""

from datetime import datetime
from typing import Optional, List
from enum import Enum as PyEnum

from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, ForeignKey, Text, JSON, Enum, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

from backend.config import settings

# Create async engine
engine = create_async_engine(
    settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://"),
    echo=False,
    pool_size=5,
    max_overflow=10,
)

# Create async session factory
AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

Base = declarative_base()


class AlertState(str, PyEnum):
    """Alert state enumeration."""
    IDLE = "idle"
    TRIGGERED = "triggered"
    RECORDING = "recording"
    COOLDOWN = "cooldown"


class Camera(Base):
    """Camera source configuration."""
    __tablename__ = "cameras"
    
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    rtsp_url = Column(String, nullable=False)
    enabled = Column(Boolean, default=True)
    fps = Column(Integer, default=30)
    width = Column(Integer, default=1920)
    height = Column(Integer, default=1080)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    rules = relationship("Rule", back_populates="camera", cascade="all, delete-orphan")
    recordings = relationship("Recording", back_populates="camera", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="camera", cascade="all, delete-orphan")


class RuleConditionType(str, PyEnum):
    """Types of rule conditions."""
    OBJECT_DETECTED = "object_detected"
    OBJECT_IN_ZONE = "object_in_zone"
    OBJECT_OVER_OBJECT = "object_over_object"
    OBJECT_COUNT = "object_count"


class Rule(Base):
    """Detection rule configuration."""
    __tablename__ = "rules"
    
    id = Column(String, primary_key=True)
    camera_id = Column(String, ForeignKey("cameras.id"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text)
    enabled = Column(Boolean, default=True)
    
    # Detection targets (what to look for)
    primary_target = Column(String, nullable=False)  # e.g., "cat", "dog"
    secondary_target = Column(String)  # e.g., "counter", "table" (for spatial rules)
    
    # Condition
    condition_type = Column(Enum(RuleConditionType), default=RuleConditionType.OBJECT_DETECTED)
    condition_params = Column(JSON, default=dict)  # Additional parameters like zone coordinates
    
    # Alert settings
    alert_message = Column(String, default="🚨 Alert triggered!")
    cooldown_seconds = Column(Integer, default=30)
    
    # Actions to run on alert start/end
    on_alert_start_actions = Column(JSON, default=list)
    on_alert_end_actions = Column(JSON, default=list)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    camera = relationship("Camera", back_populates="rules")
    alerts = relationship("Alert", back_populates="rule", cascade="all, delete-orphan")


class Recording(Base):
    """Recording metadata."""
    __tablename__ = "recordings"
    
    id = Column(String, primary_key=True)
    camera_id = Column(String, ForeignKey("cameras.id"), nullable=False)
    alert_id = Column(String, ForeignKey("alerts.id"))
    
    filename = Column(String, nullable=False)
    filepath = Column(String, nullable=False)
    duration_seconds = Column(Float)
    file_size_bytes = Column(Integer)
    
    thumbnail_path = Column(String)
    
    started_at = Column(DateTime, nullable=False)
    ended_at = Column(DateTime)
    
    # Discord status
    discord_sent = Column(Boolean, default=False)
    discord_message_id = Column(String)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    camera = relationship("Camera", back_populates="recordings")
    alert = relationship("Alert", back_populates="recording")


class Alert(Base):
    """Alert event tracking."""
    __tablename__ = "alerts"
    
    id = Column(String, primary_key=True)
    camera_id = Column(String, ForeignKey("cameras.id"), nullable=False)
    rule_id = Column(String, ForeignKey("rules.id"), nullable=False)
    
    state = Column(Enum(AlertState), default=AlertState.TRIGGERED)
    message = Column(String)
    
    # Detection details
    detected_objects = Column(JSON, default=list)
    detection_confidence = Column(Float)
    
    triggered_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    ended_at = Column(DateTime)
    
    # Relationships
    camera = relationship("Camera", back_populates="alerts")
    rule = relationship("Rule", back_populates="alerts")
    recording = relationship("Recording", back_populates="alert", uselist=False)


class ActionLog(Base):
    """Log of actions executed."""
    __tablename__ = "action_logs"
    
    id = Column(String, primary_key=True)
    alert_id = Column(String, ForeignKey("alerts.id"))
    
    action_type = Column(String, nullable=False)
    action_params = Column(JSON, default=dict)
    
    success = Column(Boolean, default=True)
    error_message = Column(Text)
    
    executed_at = Column(DateTime, default=datetime.utcnow)


async def init_db():
    """Initialize database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncSession:
    """Get database session."""
    async with AsyncSessionLocal() as session:
        yield session


async def get_all_cameras() -> List[Camera]:
    """Get all cameras from the database."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Camera))
        return result.scalars().all()


async def get_rules_for_camera(camera_id: str) -> List[Rule]:
    """Get all rules for a specific camera."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Rule).where(Rule.camera_id == camera_id)
        )
        return result.scalars().all()

