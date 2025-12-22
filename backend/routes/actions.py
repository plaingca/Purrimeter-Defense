"""
Actions API routes for testing and managing actions.
"""

from typing import Dict, Any, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter()


class ActionTestRequest(BaseModel):
    """Schema for testing an action."""
    action_type: str = Field(..., description="Type of action to test")
    params: Dict[str, Any] = Field(default_factory=dict, description="Action parameters")


class ActionResult(BaseModel):
    """Schema for action result."""
    success: bool
    action_type: str
    message: str
    error: Optional[str] = None


@router.get("/available")
async def list_available_actions(request: Request):
    """List all available action types."""
    pipeline_manager = request.app.state.pipeline_manager
    action_service = pipeline_manager.action_service
    
    return action_service.get_available_actions()


@router.post("/test", response_model=ActionResult)
async def test_action(action: ActionTestRequest, request: Request):
    """
    Test an action without triggering a real alert.
    
    Useful for validating Discord webhooks, smart plugs, etc.
    """
    pipeline_manager = request.app.state.pipeline_manager
    action_service = pipeline_manager.action_service
    
    result = await action_service.execute_action(
        action.action_type,
        action.params,
    )
    
    return ActionResult(
        success=result.success,
        action_type=result.action_type,
        message=result.message,
        error=result.error,
    )


@router.post("/discord/test")
async def test_discord_webhook(
    request: Request,
    message: str = "🐱 Test alert from Purrimeter Defense!",
):
    """Quick test for Discord webhook."""
    pipeline_manager = request.app.state.pipeline_manager
    action_service = pipeline_manager.action_service
    
    result = await action_service.execute_action(
        "discord_webhook",
        {"message": message},
    )
    
    if not result.success:
        raise HTTPException(
            status_code=400,
            detail=f"Discord test failed: {result.error}",
        )
    
    return {"message": "Discord test sent successfully"}


@router.post("/kasa/test")
async def test_kasa_plug(
    request: Request,
    device_ip: str = None,
    action: str = "pulse",
):
    """Quick test for Kasa smart plug."""
    pipeline_manager = request.app.state.pipeline_manager
    action_service = pipeline_manager.action_service
    
    params = {"action": action}
    if device_ip:
        params["device_ip"] = device_ip
    
    result = await action_service.execute_action("kasa_smart_plug", params)
    
    if not result.success:
        raise HTTPException(
            status_code=400,
            detail=f"Kasa test failed: {result.error}",
        )
    
    return {"message": f"Kasa plug {action} executed successfully"}


class TapoTestRequest(BaseModel):
    """Schema for testing Tapo camera connection."""
    camera_ip: str = Field(..., description="Tapo camera IP address")
    camera_user: str = Field(..., description="Camera account username")
    camera_password: str = Field(..., description="Camera account password")


class TapoSaveRequest(BaseModel):
    """Schema for saving Tapo camera settings."""
    camera_ip: str = Field(..., description="Tapo camera IP address")
    camera_user: str = Field(..., description="Camera account username")
    camera_password: str = Field(..., description="Camera account password")


@router.post("/tapo/test-connection", response_model=ActionResult)
async def test_tapo_connection(
    tapo_config: TapoTestRequest,
    request: Request,
):
    """
    Test connection to a Tapo camera.
    
    This validates that the IP address and credentials are correct.
    """
    pipeline_manager = request.app.state.pipeline_manager
    action_service = pipeline_manager.action_service
    
    result = await action_service.execute_action(
        "tapo_test_connection",
        {
            "camera_ip": tapo_config.camera_ip,
            "camera_user": tapo_config.camera_user,
            "camera_password": tapo_config.camera_password,
        },
    )
    
    return ActionResult(
        success=result.success,
        action_type=result.action_type,
        message=result.message,
        error=result.error,
    )


class TapoSpeakerTestRequest(BaseModel):
    """Schema for testing Tapo camera speaker."""
    camera_ip: str = Field(..., description="Tapo camera IP address")
    camera_user: str = Field(..., description="Camera account username")
    camera_password: str = Field(..., description="Camera account password")
    sound_type: str = Field(default="alarm", description="Sound type: alarm or siren")
    duration: int = Field(default=2, description="Duration in seconds")


@router.post("/tapo/test-speaker", response_model=ActionResult)
async def test_tapo_speaker(
    tapo_config: TapoSpeakerTestRequest,
    request: Request,
):
    """
    Test the Tapo camera speaker by playing a sound.
    
    Sound types:
    - alarm: Triggers the camera's built-in alarm sound
    - siren: Manual siren control
    """
    pipeline_manager = request.app.state.pipeline_manager
    action_service = pipeline_manager.action_service
    
    params = {
        "camera_ip": tapo_config.camera_ip,
        "camera_user": tapo_config.camera_user,
        "camera_password": tapo_config.camera_password,
        "sound_type": tapo_config.sound_type,
        "duration": tapo_config.duration,
    }
    
    result = await action_service.execute_action("tapo_speaker", params)
    
    return ActionResult(
        success=result.success,
        action_type=result.action_type,
        message=result.message,
        error=result.error,
    )


@router.get("/tapo/status")
async def get_tapo_status(request: Request):
    """Get current Tapo camera configuration status."""
    from backend.config import settings
    
    return {
        "configured": bool(settings.TAPO_CAMERA_IP and settings.TAPO_CAMERA_USER and settings.TAPO_CAMERA_PASSWORD),
        "camera_ip": settings.TAPO_CAMERA_IP or "",
        "camera_user": settings.TAPO_CAMERA_USER or "",
        # Don't expose the password, just indicate if it's set
        "has_password": bool(settings.TAPO_CAMERA_PASSWORD),
    }


# Pre-configured action templates
ACTION_TEMPLATES = {
    "discord_alert": {
        "type": "discord_webhook",
        "name": "Discord Alert",
        "description": "Send alert message to Discord",
        "params": {
            "message": "🚨 Alert: {rule_name} triggered on {camera_name}!",
        },
    },
    "discord_with_embed": {
        "type": "discord_webhook",
        "name": "Discord Alert with Embed",
        "description": "Send rich alert to Discord",
        "params": {
            "message": "",
            "embed": {
                "title": "🐱 Purrimeter Alert!",
                "description": "{rule_name} triggered",
                "color": 16711680,  # Red
                "fields": [
                    {"name": "Camera", "value": "{camera_name}", "inline": True},
                    {"name": "Confidence", "value": "{confidence}%", "inline": True},
                ],
            },
        },
    },
    "kasa_deterrent_pulse": {
        "type": "kasa_smart_plug",
        "name": "Kasa Deterrent Pulse",
        "description": "Quick on-off pulse to scare cats",
        "params": {
            "action": "pulse",
        },
    },
    "kasa_deterrent_3sec": {
        "type": "kasa_smart_plug",
        "name": "Kasa Deterrent 3 Seconds",
        "description": "Turn on deterrent for 3 seconds",
        "params": {
            "action": "toggle",
            "duration": 3,
        },
    },
    "http_webhook": {
        "type": "http_request",
        "name": "HTTP Webhook",
        "description": "Send HTTP request to external service",
        "params": {
            "url": "https://example.com/webhook",
            "method": "POST",
            "body": {"event": "alert", "camera": "{camera_id}"},
        },
    },
    "play_deterrent_sound": {
        "type": "play_sound",
        "name": "Play Deterrent Sound",
        "description": "Play a sound to scare cats",
        "params": {
            "sound_file": "/app/sounds/hiss.wav",
        },
    },
    "tapo_alarm_short": {
        "type": "tapo_speaker",
        "name": "Tapo Alarm (Short)",
        "description": "Play 2-second alarm through Tapo camera speaker",
        "params": {
            "sound_type": "alarm",
            "duration": 2,
        },
    },
    "tapo_alarm_long": {
        "type": "tapo_speaker",
        "name": "Tapo Alarm (Long)",
        "description": "Play 5-second alarm through Tapo camera speaker",
        "params": {
            "sound_type": "alarm",
            "duration": 5,
        },
    },
    "tapo_siren": {
        "type": "tapo_speaker",
        "name": "Tapo Siren",
        "description": "Trigger manual siren on Tapo camera",
        "params": {
            "sound_type": "siren",
            "duration": 3,
        },
    },
}


@router.get("/templates")
async def list_action_templates():
    """List pre-configured action templates."""
    return [
        {"id": template_id, **template}
        for template_id, template in ACTION_TEMPLATES.items()
    ]


@router.get("/templates/{template_id}")
async def get_action_template(template_id: str):
    """Get a specific action template."""
    if template_id not in ACTION_TEMPLATES:
        raise HTTPException(status_code=404, detail="Template not found")
    
    return {"id": template_id, **ACTION_TEMPLATES[template_id]}

