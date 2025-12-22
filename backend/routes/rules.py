"""
Detection rules API routes.
"""

from typing import List, Optional, Dict, Any
import uuid

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import Rule, RuleConditionType, Camera, get_db

router = APIRouter()


class ActionConfig(BaseModel):
    """Configuration for an action to execute."""
    type: str = Field(..., description="Action type (e.g., 'discord_webhook', 'kasa_smart_plug')")
    params: Dict[str, Any] = Field(default_factory=dict, description="Action parameters")


class ZoneConfig(BaseModel):
    """Configuration for a detection zone."""
    x1: int = Field(..., description="Left coordinate")
    y1: int = Field(..., description="Top coordinate")
    x2: int = Field(..., description="Right coordinate")
    y2: int = Field(..., description="Bottom coordinate")


class RuleCreate(BaseModel):
    """Schema for creating a detection rule."""
    camera_id: str = Field(..., description="ID of the camera this rule applies to")
    name: str = Field(..., description="Display name for the rule")
    description: Optional[str] = Field(None, description="Rule description")
    primary_target: str = Field(..., description="Primary object to detect (e.g., 'cat')")
    secondary_target: Optional[str] = Field(None, description="Secondary object for spatial rules (e.g., 'counter')")
    condition_type: str = Field(
        default="object_detected",
        description="Type of condition: object_detected, object_in_zone, object_over_object, object_count"
    )
    condition_params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Condition parameters (e.g., zone coordinates, threshold)"
    )
    alert_message: str = Field(
        default="🚨 Alert triggered!",
        description="Message to display when alert triggers"
    )
    cooldown_seconds: int = Field(
        default=30,
        ge=0,
        le=3600,
        description="Minimum seconds between alerts"
    )
    on_alert_start_actions: List[ActionConfig] = Field(
        default_factory=list,
        description="Actions to execute when alert starts"
    )
    on_alert_end_actions: List[ActionConfig] = Field(
        default_factory=list,
        description="Actions to execute when alert ends"
    )
    enabled: bool = Field(default=True, description="Whether rule is active")


class RuleUpdate(BaseModel):
    """Schema for updating a rule."""
    name: Optional[str] = None
    description: Optional[str] = None
    primary_target: Optional[str] = None
    secondary_target: Optional[str] = None
    condition_type: Optional[str] = None
    condition_params: Optional[Dict[str, Any]] = None
    alert_message: Optional[str] = None
    cooldown_seconds: Optional[int] = Field(default=None, ge=0, le=3600)
    on_alert_start_actions: Optional[List[ActionConfig]] = None
    on_alert_end_actions: Optional[List[ActionConfig]] = None
    enabled: Optional[bool] = None


class RuleResponse(BaseModel):
    """Schema for rule response."""
    id: str
    camera_id: str
    name: str
    description: Optional[str]
    primary_target: str
    secondary_target: Optional[str]
    condition_type: str
    condition_params: Dict[str, Any]
    alert_message: str
    cooldown_seconds: int
    on_alert_start_actions: List[Dict[str, Any]]
    on_alert_end_actions: List[Dict[str, Any]]
    enabled: bool
    created_at: str
    updated_at: str
    
    class Config:
        from_attributes = True


def rule_to_response(rule: Rule) -> RuleResponse:
    """Convert a Rule model to RuleResponse."""
    return RuleResponse(
        id=rule.id,
        camera_id=rule.camera_id,
        name=rule.name,
        description=rule.description,
        primary_target=rule.primary_target,
        secondary_target=rule.secondary_target,
        condition_type=rule.condition_type.value if rule.condition_type else "object_detected",
        condition_params=rule.condition_params or {},
        alert_message=rule.alert_message,
        cooldown_seconds=rule.cooldown_seconds,
        on_alert_start_actions=rule.on_alert_start_actions or [],
        on_alert_end_actions=rule.on_alert_end_actions or [],
        enabled=rule.enabled,
        created_at=rule.created_at.isoformat(),
        updated_at=rule.updated_at.isoformat(),
    )


@router.get("/", response_model=List[RuleResponse])
async def list_rules(
    camera_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """List all detection rules, optionally filtered by camera."""
    query = select(Rule)
    if camera_id:
        query = query.where(Rule.camera_id == camera_id)
    
    result = await db.execute(query)
    rules = result.scalars().all()
    
    return [rule_to_response(r) for r in rules]


@router.post("/", response_model=RuleResponse)
async def create_rule(
    rule: RuleCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Create a new detection rule."""
    # Verify camera exists
    camera_result = await db.execute(select(Camera).where(Camera.id == rule.camera_id))
    if not camera_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Camera not found")
    
    # Parse condition type
    try:
        condition_type = RuleConditionType(rule.condition_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid condition type. Must be one of: {[t.value for t in RuleConditionType]}"
        )
    
    rule_id = str(uuid.uuid4())
    
    db_rule = Rule(
        id=rule_id,
        camera_id=rule.camera_id,
        name=rule.name,
        description=rule.description,
        primary_target=rule.primary_target,
        secondary_target=rule.secondary_target,
        condition_type=condition_type,
        condition_params=rule.condition_params,
        alert_message=rule.alert_message,
        cooldown_seconds=rule.cooldown_seconds,
        on_alert_start_actions=[a.model_dump() for a in rule.on_alert_start_actions],
        on_alert_end_actions=[a.model_dump() for a in rule.on_alert_end_actions],
        enabled=rule.enabled,
    )
    
    db.add(db_rule)
    await db.commit()
    await db.refresh(db_rule)
    
    # Register with pipeline manager
    if rule.enabled:
        pipeline_manager = request.app.state.pipeline_manager
        await pipeline_manager.add_rule(db_rule)
    
    return rule_to_response(db_rule)


@router.get("/{rule_id}", response_model=RuleResponse)
async def get_rule(rule_id: str, db: AsyncSession = Depends(get_db)):
    """Get a specific rule by ID."""
    result = await db.execute(select(Rule).where(Rule.id == rule_id))
    rule = result.scalar_one_or_none()
    
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    
    return rule_to_response(rule)


@router.patch("/{rule_id}", response_model=RuleResponse)
async def update_rule(
    rule_id: str,
    update: RuleUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Update a rule's configuration."""
    result = await db.execute(select(Rule).where(Rule.id == rule_id))
    rule = result.scalar_one_or_none()
    
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    
    was_enabled = rule.enabled
    
    # Update fields
    update_data = update.model_dump(exclude_unset=True)
    
    for field, value in update_data.items():
        if field == "condition_type" and value is not None:
            try:
                value = RuleConditionType(value)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid condition type. Must be one of: {[t.value for t in RuleConditionType]}"
                )
        elif field in ("on_alert_start_actions", "on_alert_end_actions") and value is not None:
            value = [a.model_dump() if hasattr(a, 'model_dump') else a for a in value]
        
        setattr(rule, field, value)
    
    await db.commit()
    await db.refresh(rule)
    
    # Update pipeline manager
    pipeline_manager = request.app.state.pipeline_manager
    
    if was_enabled and not rule.enabled:
        # Rule was disabled - remove it
        await pipeline_manager.remove_rule(rule_id, rule.camera_id)
    elif not was_enabled and rule.enabled:
        # Rule was enabled - add it
        await pipeline_manager.add_rule(rule)
    elif rule.enabled:
        # Rule is still enabled - update it (this clears any active alert)
        await pipeline_manager.update_rule(rule)
    
    return rule_to_response(rule)


@router.delete("/{rule_id}")
async def delete_rule(
    rule_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Delete a rule."""
    result = await db.execute(select(Rule).where(Rule.id == rule_id))
    rule = result.scalar_one_or_none()
    
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    
    # Remove from pipeline
    pipeline_manager = request.app.state.pipeline_manager
    await pipeline_manager.remove_rule(rule_id, rule.camera_id)
    
    # Delete from database
    await db.delete(rule)
    await db.commit()
    
    return {"message": "Rule deleted", "id": rule_id}


@router.get("/{rule_id}/state")
async def get_rule_state(rule_id: str, request: Request):
    """Get the current state of a rule (alert status, etc.)."""
    pipeline_manager = request.app.state.pipeline_manager
    states = pipeline_manager.rule_engine.get_rule_states()
    
    if rule_id not in states:
        raise HTTPException(status_code=404, detail="Rule state not found")
    
    return states[rule_id]


# Preset rules for common scenarios
RULE_PRESETS = {
    "cat_on_counter": {
        "name": "Cat on Counter",
        "description": "Detect when a cat is on or over the counter",
        "primary_target": "cat",
        "secondary_target": "counter",
        "condition_type": "object_over_object",
        "condition_params": {"relationship": "over"},
        "alert_message": "🐱 Cat detected on counter!",
    },
    "cat_detected": {
        "name": "Cat Detected",
        "description": "Simple cat presence detection",
        "primary_target": "cat",
        "condition_type": "object_detected",
        "alert_message": "🐱 Cat spotted!",
    },
    "multiple_cats": {
        "name": "Multiple Cats",
        "description": "Detect when more than one cat is visible",
        "primary_target": "cat",
        "condition_type": "object_count",
        "condition_params": {"threshold": 2},
        "alert_message": "🐱🐱 Multiple cats detected!",
    },
    "cat_in_kitchen": {
        "name": "Cat in Kitchen Zone",
        "description": "Detect cat in a defined zone",
        "primary_target": "cat",
        "condition_type": "object_in_zone",
        "condition_params": {"zone": {"x1": 0, "y1": 0, "x2": 640, "y2": 480}},
        "alert_message": "🐱 Cat in kitchen zone!",
    },
}


@router.get("/presets/list")
async def list_rule_presets():
    """List available rule presets."""
    return [
        {"id": preset_id, **preset}
        for preset_id, preset in RULE_PRESETS.items()
    ]


@router.post("/presets/{preset_id}/apply")
async def apply_rule_preset(
    preset_id: str,
    camera_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Apply a rule preset to a camera."""
    if preset_id not in RULE_PRESETS:
        raise HTTPException(status_code=404, detail="Preset not found")
    
    preset = RULE_PRESETS[preset_id]
    
    # Create rule from preset
    rule_create = RuleCreate(
        camera_id=camera_id,
        **preset,
    )
    
    return await create_rule(rule_create, request, db)

