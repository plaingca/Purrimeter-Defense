"""
Action service for executing custom actions on alerts.
"""

import asyncio
from typing import Dict, Any, Optional, List
from abc import ABC, abstractmethod
from dataclasses import dataclass
import structlog
import aiohttp

from backend.config import settings

logger = structlog.get_logger()


@dataclass
class ActionResult:
    """Result of executing an action."""
    success: bool
    action_type: str
    message: str
    error: Optional[str] = None


class ActionHandler(ABC):
    """Base class for action handlers."""
    
    @property
    @abstractmethod
    def action_type(self) -> str:
        """Return the action type identifier."""
        pass
    
    @abstractmethod
    async def execute(self, params: Dict[str, Any]) -> ActionResult:
        """Execute the action with given parameters."""
        pass


class DiscordWebhookAction(ActionHandler):
    """Send alert notifications to Discord."""
    
    @property
    def action_type(self) -> str:
        return "discord_webhook"
    
    async def execute(self, params: Dict[str, Any]) -> ActionResult:
        webhook_url = params.get("webhook_url") or settings.DISCORD_WEBHOOK_URL
        
        if not webhook_url:
            return ActionResult(
                success=False,
                action_type=self.action_type,
                message="No Discord webhook URL configured",
                error="WEBHOOK_NOT_CONFIGURED",
            )
        
        message = params.get("message", "🚨 Alert triggered!")
        embed = params.get("embed", {})
        
        payload = {"content": message}
        
        if embed:
            payload["embeds"] = [embed]
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=payload) as response:
                    if response.status in (200, 204):
                        return ActionResult(
                            success=True,
                            action_type=self.action_type,
                            message="Discord notification sent",
                        )
                    else:
                        error_text = await response.text()
                        return ActionResult(
                            success=False,
                            action_type=self.action_type,
                            message="Failed to send Discord notification",
                            error=f"HTTP {response.status}: {error_text}",
                        )
        except Exception as e:
            return ActionResult(
                success=False,
                action_type=self.action_type,
                message="Discord webhook error",
                error=str(e),
            )


class DiscordVideoUploadAction(ActionHandler):
    """Upload recording video to Discord."""
    
    @property
    def action_type(self) -> str:
        return "discord_video_upload"
    
    async def execute(self, params: Dict[str, Any]) -> ActionResult:
        webhook_url = params.get("webhook_url") or settings.DISCORD_WEBHOOK_URL
        video_path = params.get("video_path")
        message = params.get("message", "🎬 Recording from alert")
        
        if not webhook_url:
            return ActionResult(
                success=False,
                action_type=self.action_type,
                message="No Discord webhook URL configured",
                error="WEBHOOK_NOT_CONFIGURED",
            )
        
        if not video_path:
            return ActionResult(
                success=False,
                action_type=self.action_type,
                message="No video path provided",
                error="NO_VIDEO_PATH",
            )
        
        try:
            from pathlib import Path
            video_file = Path(video_path)
            
            if not video_file.exists():
                return ActionResult(
                    success=False,
                    action_type=self.action_type,
                    message="Video file not found",
                    error="FILE_NOT_FOUND",
                )
            
            # Check file size (Discord limit is 25MB for free, 100MB for Nitro)
            file_size_mb = video_file.stat().st_size / (1024 * 1024)
            
            if file_size_mb > 25:
                logger.warning(
                    "Video too large for Discord",
                    size_mb=file_size_mb,
                    path=video_path,
                )
                return ActionResult(
                    success=False,
                    action_type=self.action_type,
                    message=f"Video too large ({file_size_mb:.1f}MB > 25MB limit)",
                    error="FILE_TOO_LARGE",
                )
            
            async with aiohttp.ClientSession() as session:
                data = aiohttp.FormData()
                data.add_field('content', message)
                data.add_field(
                    'file',
                    open(video_path, 'rb'),
                    filename=video_file.name,
                    content_type='video/mp4',
                )
                
                async with session.post(webhook_url, data=data) as response:
                    if response.status in (200, 204):
                        return ActionResult(
                            success=True,
                            action_type=self.action_type,
                            message="Video uploaded to Discord",
                        )
                    else:
                        error_text = await response.text()
                        return ActionResult(
                            success=False,
                            action_type=self.action_type,
                            message="Failed to upload video",
                            error=f"HTTP {response.status}: {error_text}",
                        )
                        
        except Exception as e:
            return ActionResult(
                success=False,
                action_type=self.action_type,
                message="Video upload error",
                error=str(e),
            )


class KasaSmartPlugAction(ActionHandler):
    """Control Kasa smart plugs (e.g., to trigger deterrent devices)."""
    
    @property
    def action_type(self) -> str:
        return "kasa_smart_plug"
    
    async def execute(self, params: Dict[str, Any]) -> ActionResult:
        device_ip = params.get("device_ip") or settings.KASA_DEVICE_IP
        action = params.get("action", "toggle")  # on, off, toggle
        duration = params.get("duration", 3)  # seconds to stay on
        
        if not device_ip:
            return ActionResult(
                success=False,
                action_type=self.action_type,
                message="No Kasa device IP configured",
                error="DEVICE_NOT_CONFIGURED",
            )
        
        try:
            from kasa import SmartPlug
            
            plug = SmartPlug(device_ip)
            await plug.update()
            
            if action == "on":
                await plug.turn_on()
            elif action == "off":
                await plug.turn_off()
            elif action == "toggle":
                await plug.turn_on()
                await asyncio.sleep(duration)
                await plug.turn_off()
            elif action == "pulse":
                # Quick on-off pulse
                await plug.turn_on()
                await asyncio.sleep(0.5)
                await plug.turn_off()
            
            return ActionResult(
                success=True,
                action_type=self.action_type,
                message=f"Kasa plug {action} executed",
            )
            
        except ImportError:
            return ActionResult(
                success=False,
                action_type=self.action_type,
                message="python-kasa not installed",
                error="DEPENDENCY_MISSING",
            )
        except Exception as e:
            return ActionResult(
                success=False,
                action_type=self.action_type,
                message="Kasa plug error",
                error=str(e),
            )


class HTTPRequestAction(ActionHandler):
    """Make HTTP requests to external services."""
    
    @property
    def action_type(self) -> str:
        return "http_request"
    
    async def execute(self, params: Dict[str, Any]) -> ActionResult:
        url = params.get("url")
        method = params.get("method", "POST").upper()
        headers = params.get("headers", {})
        body = params.get("body")
        
        if not url:
            return ActionResult(
                success=False,
                action_type=self.action_type,
                message="No URL provided",
                error="NO_URL",
            )
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method,
                    url,
                    headers=headers,
                    json=body if body else None,
                ) as response:
                    if 200 <= response.status < 300:
                        return ActionResult(
                            success=True,
                            action_type=self.action_type,
                            message=f"HTTP {method} {url} succeeded",
                        )
                    else:
                        error_text = await response.text()
                        return ActionResult(
                            success=False,
                            action_type=self.action_type,
                            message=f"HTTP request failed",
                            error=f"HTTP {response.status}: {error_text}",
                        )
                        
        except Exception as e:
            return ActionResult(
                success=False,
                action_type=self.action_type,
                message="HTTP request error",
                error=str(e),
            )


class PlaySoundAction(ActionHandler):
    """Play a sound file (for local alerts)."""
    
    @property
    def action_type(self) -> str:
        return "play_sound"
    
    async def execute(self, params: Dict[str, Any]) -> ActionResult:
        sound_file = params.get("sound_file")
        
        if not sound_file:
            return ActionResult(
                success=False,
                action_type=self.action_type,
                message="No sound file specified",
                error="NO_SOUND_FILE",
            )
        
        try:
            import simpleaudio as sa
            from pathlib import Path
            
            sound_path = Path(sound_file)
            if not sound_path.exists():
                return ActionResult(
                    success=False,
                    action_type=self.action_type,
                    message=f"Sound file not found: {sound_file}",
                    error="FILE_NOT_FOUND",
                )
            
            # Play sound asynchronously
            wave_obj = sa.WaveObject.from_wave_file(str(sound_path))
            play_obj = wave_obj.play()
            # Don't wait for completion
            
            return ActionResult(
                success=True,
                action_type=self.action_type,
                message=f"Playing sound: {sound_file}",
            )
            
        except ImportError:
            return ActionResult(
                success=False,
                action_type=self.action_type,
                message="simpleaudio not installed",
                error="DEPENDENCY_MISSING",
            )
        except Exception as e:
            return ActionResult(
                success=False,
                action_type=self.action_type,
                message="Sound playback error",
                error=str(e),
            )


class TapoSpeakerAction(ActionHandler):
    """Play sounds through Tapo camera's built-in speaker."""
    
    @property
    def action_type(self) -> str:
        return "tapo_speaker"
    
    def _play_alarm(self, camera_ip: str, camera_user: str, camera_password: str, duration: int):
        """Synchronous function to play alarm (runs in thread pool)."""
        import time
        from pytapo import Tapo
        
        tapo = Tapo(camera_ip, camera_user, camera_password)
        tapo.setAlarm(True, "sound")
        time.sleep(duration)
        tapo.setAlarm(False, "sound")
    
    def _play_siren(self, camera_ip: str, camera_user: str, camera_password: str, duration: int):
        """Synchronous function to play siren (runs in thread pool)."""
        import time
        from pytapo import Tapo
        
        tapo = Tapo(camera_ip, camera_user, camera_password)
        tapo.startManualAlarm()
        time.sleep(duration)
        tapo.stopManualAlarm()
    
    async def execute(self, params: Dict[str, Any]) -> ActionResult:
        camera_ip = params.get("camera_ip") or settings.TAPO_CAMERA_IP
        camera_user = params.get("camera_user") or settings.TAPO_CAMERA_USER
        camera_password = params.get("camera_password") or settings.TAPO_CAMERA_PASSWORD
        
        # Sound options
        sound_type = params.get("sound_type", "alarm")  # alarm, siren, or custom
        duration = params.get("duration", 3)  # seconds
        
        if not camera_ip:
            return ActionResult(
                success=False,
                action_type=self.action_type,
                message="No Tapo camera IP configured",
                error="CAMERA_NOT_CONFIGURED",
            )
        
        if not camera_user or not camera_password:
            return ActionResult(
                success=False,
                action_type=self.action_type,
                message="Tapo camera credentials not configured",
                error="CREDENTIALS_NOT_CONFIGURED",
            )
        
        try:
            if sound_type == "alarm":
                # Run blocking pytapo calls in thread pool
                await asyncio.to_thread(
                    self._play_alarm,
                    camera_ip, camera_user, camera_password, duration
                )
                logger.info(
                    "Tapo alarm triggered",
                    camera_ip=camera_ip,
                    duration=duration,
                )
                
                return ActionResult(
                    success=True,
                    action_type=self.action_type,
                    message=f"Tapo alarm played for {duration}s",
                )
            elif sound_type == "siren":
                # Run blocking pytapo calls in thread pool
                await asyncio.to_thread(
                    self._play_siren,
                    camera_ip, camera_user, camera_password, duration
                )
                logger.info(
                    "Tapo manual siren triggered",
                    camera_ip=camera_ip,
                    duration=duration,
                )
                
                return ActionResult(
                    success=True,
                    action_type=self.action_type,
                    message=f"Tapo siren played for {duration}s",
                )
            else:
                return ActionResult(
                    success=False,
                    action_type=self.action_type,
                    message=f"Unknown sound type: {sound_type}",
                    error="INVALID_SOUND_TYPE",
                )
                
        except ImportError:
            return ActionResult(
                success=False,
                action_type=self.action_type,
                message="pytapo not installed",
                error="DEPENDENCY_MISSING",
            )
        except Exception as e:
            logger.error("Tapo speaker error", error=str(e), camera_ip=camera_ip)
            return ActionResult(
                success=False,
                action_type=self.action_type,
                message="Tapo speaker error",
                error=str(e),
            )


class TapoConnectionTestAction(ActionHandler):
    """Test connection to Tapo camera (used for settings validation)."""
    
    @property
    def action_type(self) -> str:
        return "tapo_test_connection"
    
    def _test_connection(self, camera_ip: str, camera_user: str, camera_password: str) -> dict:
        """Synchronous function to test connection (runs in thread pool)."""
        from pytapo import Tapo
        
        tapo = Tapo(camera_ip, camera_user, camera_password)
        return tapo.getBasicInfo()
    
    async def execute(self, params: Dict[str, Any]) -> ActionResult:
        camera_ip = params.get("camera_ip") or settings.TAPO_CAMERA_IP
        camera_user = params.get("camera_user") or settings.TAPO_CAMERA_USER
        camera_password = params.get("camera_password") or settings.TAPO_CAMERA_PASSWORD
        
        if not camera_ip:
            return ActionResult(
                success=False,
                action_type=self.action_type,
                message="No Tapo camera IP provided",
                error="CAMERA_NOT_CONFIGURED",
            )
        
        if not camera_user or not camera_password:
            return ActionResult(
                success=False,
                action_type=self.action_type,
                message="Tapo camera credentials not provided",
                error="CREDENTIALS_NOT_CONFIGURED",
            )
        
        try:
            # Run blocking pytapo calls in thread pool
            info = await asyncio.to_thread(
                self._test_connection,
                camera_ip, camera_user, camera_password
            )
            
            device_info = info.get("device_info", {}).get("basic_info", {})
            device_model = device_info.get("device_model", "Unknown")
            device_name = device_info.get("device_alias", "Tapo Camera")
            
            logger.info(
                "Tapo connection test successful",
                camera_ip=camera_ip,
                device_model=device_model,
                device_name=device_name,
            )
            
            return ActionResult(
                success=True,
                action_type=self.action_type,
                message=f"Connected to {device_name} ({device_model})",
            )
                
        except ImportError:
            return ActionResult(
                success=False,
                action_type=self.action_type,
                message="pytapo not installed",
                error="DEPENDENCY_MISSING",
            )
        except Exception as e:
            error_msg = str(e)
            if "Invalid authentication" in error_msg:
                return ActionResult(
                    success=False,
                    action_type=self.action_type,
                    message="Invalid credentials - check username/password",
                    error="AUTHENTICATION_FAILED",
                )
            logger.error("Tapo connection test failed", error=error_msg, camera_ip=camera_ip)
            return ActionResult(
                success=False,
                action_type=self.action_type,
                message="Failed to connect to Tapo camera",
                error=error_msg,
            )


class ActionService:
    """
    Service for executing actions on alerts.
    
    Supports various action types:
    - Discord webhook notifications
    - Discord video uploads
    - Kasa smart plug control
    - HTTP requests
    - Sound playback
    """
    
    def __init__(self):
        self._handlers: Dict[str, ActionHandler] = {}
        self._register_default_handlers()
    
    def _register_default_handlers(self):
        """Register built-in action handlers."""
        handlers = [
            DiscordWebhookAction(),
            DiscordVideoUploadAction(),
            KasaSmartPlugAction(),
            HTTPRequestAction(),
            PlaySoundAction(),
            TapoSpeakerAction(),
            TapoConnectionTestAction(),
        ]
        
        for handler in handlers:
            self._handlers[handler.action_type] = handler
    
    def register_handler(self, handler: ActionHandler):
        """Register a custom action handler."""
        self._handlers[handler.action_type] = handler
    
    async def execute_action(
        self,
        action_type: str,
        params: Dict[str, Any],
    ) -> ActionResult:
        """Execute a single action."""
        if action_type not in self._handlers:
            return ActionResult(
                success=False,
                action_type=action_type,
                message=f"Unknown action type: {action_type}",
                error="UNKNOWN_ACTION_TYPE",
            )
        
        handler = self._handlers[action_type]
        
        try:
            result = await handler.execute(params)
            logger.info(
                "Action executed",
                action_type=action_type,
                success=result.success,
                message=result.message,
            )
            return result
        except Exception as e:
            logger.error("Action execution failed", action_type=action_type, error=str(e))
            return ActionResult(
                success=False,
                action_type=action_type,
                message="Action execution failed",
                error=str(e),
            )
    
    async def execute_actions(
        self,
        actions: List[Dict[str, Any]],
    ) -> List[ActionResult]:
        """Execute multiple actions."""
        results = []
        
        for action in actions:
            action_type = action.get("type")
            params = action.get("params", {})
            
            result = await self.execute_action(action_type, params)
            results.append(result)
        
        return results
    
    def get_available_actions(self) -> List[Dict[str, str]]:
        """Get list of available action types."""
        return [
            {"type": action_type, "name": handler.__class__.__name__}
            for action_type, handler in self._handlers.items()
        ]

