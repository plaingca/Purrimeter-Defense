"""
Pipeline manager for orchestrating camera streams, detection, and alerts.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any
import uuid
import structlog
from PIL import Image

from backend.config import settings
from backend.services.sam3_service import SAM3Service, Detection
from backend.services.camera_stream import CameraStream, TimestampedFrame
from backend.services.recording_service import RecordingService
from backend.services.rule_engine import RuleEngine, RuleEvaluation
from backend.services.action_service import ActionService
from backend.database import Rule, Camera, Alert, AlertState, Recording, AsyncSessionLocal

logger = structlog.get_logger()


@dataclass
class PipelineState:
    """State of a camera pipeline."""
    camera_id: str
    camera_stream: CameraStream
    rules: List[Rule] = field(default_factory=list)
    is_running: bool = False
    last_detection_time: Optional[datetime] = None
    last_detections: Dict[str, List[Detection]] = field(default_factory=dict)
    active_alerts: Dict[str, str] = field(default_factory=dict)  # alert_id -> recording_id
    processing_task: Optional[asyncio.Task] = None


class PipelineManager:
    """
    Manages detection pipelines for all cameras.
    
    Each camera has its own pipeline that:
    1. Captures frames from RTSP stream
    2. Samples frames for SAM3 detection
    3. Evaluates rules against detections
    4. Triggers alerts and recordings
    5. Executes configured actions
    """
    
    def __init__(self, sam3_service: SAM3Service):
        self.sam3_service = sam3_service
        self.recording_service = RecordingService()
        self.action_service = ActionService()
        self.rule_engine = RuleEngine(sam3_service)
        
        self._pipelines: Dict[str, PipelineState] = {}
        self._lock = asyncio.Lock()
        self._running = False
        
        # Wire up alert callbacks
        self.rule_engine.on_alert(self._on_alert_triggered)
        self.rule_engine.on_alert_end(self._on_alert_ended)
    
    async def start(self):
        """Start the pipeline manager."""
        self._running = True
        logger.info("Pipeline manager started")
    
    async def stop(self):
        """Stop all pipelines."""
        self._running = False
        
        async with self._lock:
            for pipeline in self._pipelines.values():
                await self._stop_pipeline(pipeline)
        
        logger.info("Pipeline manager stopped")
    
    async def add_camera(self, camera: Camera) -> bool:
        """
        Add a camera and start its pipeline.
        
        Args:
            camera: Camera configuration
            
        Returns:
            True if camera was added successfully
        """
        async with self._lock:
            if camera.id in self._pipelines:
                logger.warning("Camera already exists", camera_id=camera.id)
                return False
            
            # Create camera stream
            stream = CameraStream(
                camera_id=camera.id,
                rtsp_url=camera.rtsp_url,
                name=camera.name,
                fps=camera.fps,
                width=camera.width,
                height=camera.height,
            )
            
            # Start the stream
            if not await stream.start():
                logger.error("Failed to start camera stream", camera_id=camera.id)
                return False
            
            # Create pipeline state
            pipeline = PipelineState(
                camera_id=camera.id,
                camera_stream=stream,
            )
            
            self._pipelines[camera.id] = pipeline
            
            # Start processing task
            pipeline.processing_task = asyncio.create_task(
                self._process_pipeline(pipeline)
            )
            pipeline.is_running = True
            
            logger.info("Camera added to pipeline", camera_id=camera.id, name=camera.name)
            return True
    
    async def remove_camera(self, camera_id: str):
        """Remove a camera and stop its pipeline."""
        async with self._lock:
            if camera_id not in self._pipelines:
                return
            
            pipeline = self._pipelines[camera_id]
            await self._stop_pipeline(pipeline)
            del self._pipelines[camera_id]
            
            logger.info("Camera removed from pipeline", camera_id=camera_id)
    
    async def _stop_pipeline(self, pipeline: PipelineState):
        """Stop a single pipeline."""
        pipeline.is_running = False
        
        if pipeline.processing_task:
            pipeline.processing_task.cancel()
            try:
                await pipeline.processing_task
            except asyncio.CancelledError:
                pass
        
        await pipeline.camera_stream.stop()
    
    async def add_rule(self, rule: Rule):
        """Add a rule to its camera's pipeline."""
        self.rule_engine.register_rule(rule)
        
        async with self._lock:
            if rule.camera_id in self._pipelines:
                self._pipelines[rule.camera_id].rules.append(rule)
        
        logger.info("Rule added", rule_id=rule.id, camera_id=rule.camera_id)
    
    async def remove_rule(self, rule_id: str, camera_id: str):
        """Remove a rule from its camera's pipeline."""
        self.rule_engine.unregister_rule(rule_id)
        
        async with self._lock:
            if camera_id in self._pipelines:
                pipeline = self._pipelines[camera_id]
                pipeline.rules = [r for r in pipeline.rules if r.id != rule_id]
                # Also clear detections cache to force fresh detection with new rules
                pipeline.last_detections = {}
        
        logger.info("Rule removed", rule_id=rule_id)
    
    async def update_rule(self, rule: Rule):
        """Update an existing rule in its camera's pipeline."""
        # Update in rule engine (this resets alert state)
        was_in_alert, old_alert_id, old_rule = self.rule_engine.update_rule(rule)
        
        # If there was an active alert, end it properly and notify websocket clients
        if was_in_alert and old_alert_id and old_rule:
            # Fire the alert end through the rule engine to notify websocket clients
            await self.rule_engine.fire_alert_end(old_alert_id, old_rule)
            # Also run our internal alert end handler (for recordings, actions, etc.)
            await self._on_alert_ended(old_alert_id, old_rule)
        
        async with self._lock:
            if rule.camera_id in self._pipelines:
                pipeline = self._pipelines[rule.camera_id]
                # Replace rule in pipeline's rule list
                pipeline.rules = [r if r.id != rule.id else rule for r in pipeline.rules]
                # If rule wasn't in list, add it
                if not any(r.id == rule.id for r in pipeline.rules):
                    pipeline.rules.append(rule)
                # Clear detections cache to force fresh detection with new targets
                pipeline.last_detections = {}
        
        logger.info("Rule updated in pipeline", rule_id=rule.id, camera_id=rule.camera_id)
    
    async def _process_pipeline(self, pipeline: PipelineState):
        """
        Main processing loop for a camera pipeline.
        
        Continuously samples frames and runs detection.
        """
        logger.info("Starting pipeline processing", camera_id=pipeline.camera_id)
        
        sample_interval = 1.0 / settings.DETECTION_SAMPLE_RATE
        
        while pipeline.is_running and self._running:
            try:
                # Get current frame
                pil_image = pipeline.camera_stream.get_frame_as_pil()
                
                if pil_image is None:
                    await asyncio.sleep(0.1)
                    continue
                
                # Collect all detection targets from rules
                targets = set()
                for rule in pipeline.rules:
                    if rule.enabled:
                        targets.add(rule.primary_target)
                        if rule.secondary_target:
                            targets.add(rule.secondary_target)
                
                if not targets:
                    await asyncio.sleep(sample_interval)
                    continue
                
                # Run detection
                detections = await self.sam3_service.detect_objects(
                    pil_image,
                    list(targets),
                    confidence_threshold=settings.DETECTION_CONFIDENCE_THRESHOLD,
                )
                
                pipeline.last_detection_time = datetime.utcnow()
                pipeline.last_detections = detections
                
                # Evaluate rules
                evaluations = await self.rule_engine.evaluate_rules(
                    pipeline.camera_id,
                    detections,
                )
                
                # Log any triggered rules
                for eval in evaluations:
                    if eval.triggered:
                        logger.debug(
                            "Rule triggered",
                            rule_id=eval.rule_id,
                            confidence=eval.confidence,
                        )
                
                await asyncio.sleep(sample_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    "Pipeline processing error",
                    camera_id=pipeline.camera_id,
                    error=str(e),
                )
                await asyncio.sleep(1.0)
        
        logger.info("Pipeline processing stopped", camera_id=pipeline.camera_id)
    
    async def _on_alert_triggered(
        self,
        alert_id: str,
        rule: Rule,
        evaluation: RuleEvaluation,
    ):
        """Handle alert triggered event."""
        logger.info(
            "Alert triggered - starting recording",
            alert_id=alert_id,
            rule_id=rule.id,
            message=evaluation.message,
        )
        
        pipeline = self._pipelines.get(rule.camera_id)
        if not pipeline:
            return
        
        # Save alert to database
        try:
            async with AsyncSessionLocal() as session:
                alert = Alert(
                    id=alert_id,
                    camera_id=rule.camera_id,
                    rule_id=rule.id,
                    state=AlertState.TRIGGERED,
                    message=evaluation.message,
                    detected_objects=evaluation.detected_objects,
                    detection_confidence=evaluation.confidence,
                    triggered_at=datetime.utcnow(),
                )
                session.add(alert)
                await session.commit()
                logger.info("Alert saved to database", alert_id=alert_id)
        except Exception as e:
            logger.error("Failed to save alert to database", error=str(e))
        
        # Start recording
        try:
            recording_id = await self.recording_service.start_recording(
                pipeline.camera_stream,
                alert_id,
            )
            pipeline.active_alerts[alert_id] = recording_id
            
            # Update alert state to recording
            try:
                async with AsyncSessionLocal() as session:
                    from sqlalchemy import select
                    result = await session.execute(select(Alert).where(Alert.id == alert_id))
                    alert = result.scalar_one_or_none()
                    if alert:
                        alert.state = AlertState.RECORDING
                        await session.commit()
            except Exception as e:
                logger.error("Failed to update alert state", error=str(e))
            
            logger.info(
                "Recording started",
                alert_id=alert_id,
                recording_id=recording_id,
            )
        except Exception as e:
            logger.error("Failed to start recording", error=str(e))
        
        # Execute on_alert_start actions
        if rule.on_alert_start_actions:
            results = await self.action_service.execute_actions(
                rule.on_alert_start_actions
            )
            for result in results:
                if not result.success:
                    logger.warning(
                        "Alert start action failed",
                        action_type=result.action_type,
                        error=result.error,
                    )
    
    async def _on_alert_ended(self, alert_id: str, rule: Rule):
        """Handle alert ended event."""
        logger.info(
            "Alert ended - stopping recording",
            alert_id=alert_id,
            rule_id=rule.id,
        )
        
        pipeline = self._pipelines.get(rule.camera_id)
        if not pipeline:
            return
        
        # Stop recording
        recording_id = pipeline.active_alerts.pop(alert_id, None)
        discord_sent = False
        
        if recording_id:
            try:
                recording_info = await self.recording_service.stop_recording(
                    recording_id
                )
                
                if recording_info:
                    logger.info(
                        "Recording stopped",
                        recording_id=recording_id,
                        duration=recording_info.get("duration_seconds"),
                    )
                    
                    # Send to Discord
                    discord_result = await self.action_service.execute_action(
                        "discord_video_upload",
                        {
                            "video_path": recording_info["filepath"],
                            "message": f"🎬 Recording from alert: {rule.name}",
                        },
                    )
                    discord_sent = discord_result.success if discord_result else False
                    
                    # Save recording to database
                    try:
                        async with AsyncSessionLocal() as session:
                            from pathlib import Path
                            recording = Recording(
                                id=recording_id,
                                camera_id=rule.camera_id,
                                alert_id=alert_id,
                                filename=recording_info.get("filename", ""),
                                filepath=recording_info.get("filepath", ""),
                                duration_seconds=recording_info.get("duration_seconds"),
                                file_size_bytes=recording_info.get("file_size_bytes"),
                                thumbnail_path=recording_info.get("thumbnail_path"),
                                started_at=datetime.fromisoformat(recording_info.get("started_at", datetime.utcnow().isoformat())),
                                ended_at=datetime.fromisoformat(recording_info.get("ended_at", datetime.utcnow().isoformat())),
                                discord_sent=discord_sent,
                            )
                            session.add(recording)
                            await session.commit()
                            logger.info("Recording saved to database", recording_id=recording_id)
                    except Exception as e:
                        logger.error("Failed to save recording to database", error=str(e))
                    
            except Exception as e:
                logger.error("Failed to stop recording", error=str(e))
        
        # Update alert state to cooldown/idle and set ended_at
        try:
            async with AsyncSessionLocal() as session:
                from sqlalchemy import select
                result = await session.execute(select(Alert).where(Alert.id == alert_id))
                alert = result.scalar_one_or_none()
                if alert:
                    alert.state = AlertState.COOLDOWN
                    alert.ended_at = datetime.utcnow()
                    await session.commit()
                    logger.info("Alert updated in database", alert_id=alert_id, state="cooldown")
        except Exception as e:
            logger.error("Failed to update alert in database", error=str(e))
        
        # Execute on_alert_end actions
        if rule.on_alert_end_actions:
            results = await self.action_service.execute_actions(
                rule.on_alert_end_actions
            )
            for result in results:
                if not result.success:
                    logger.warning(
                        "Alert end action failed",
                        action_type=result.action_type,
                        error=result.error,
                    )
    
    def get_pipeline_status(self, camera_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a camera pipeline."""
        pipeline = self._pipelines.get(camera_id)
        if not pipeline:
            return None
        
        return {
            "camera_id": camera_id,
            "is_running": pipeline.is_running,
            "stream_running": pipeline.camera_stream.is_running,
            "frame_count": pipeline.camera_stream.frame_count,
            "last_detection_time": (
                pipeline.last_detection_time.isoformat()
                if pipeline.last_detection_time else None
            ),
            "rules_count": len(pipeline.rules),
            "active_alerts": list(pipeline.active_alerts.keys()),
        }
    
    def get_all_pipeline_status(self) -> List[Dict[str, Any]]:
        """Get status of all pipelines."""
        return [
            self.get_pipeline_status(camera_id)
            for camera_id in self._pipelines.keys()
        ]
    
    def get_current_frame_jpeg(self, camera_id: str, quality: int = 80) -> Optional[bytes]:
        """Get current frame as JPEG for streaming."""
        pipeline = self._pipelines.get(camera_id)
        if not pipeline:
            return None
        
        return pipeline.camera_stream.get_jpeg_frame(quality)
    
    def get_current_detections(self, camera_id: str) -> Dict[str, List[dict]]:
        """Get current detections for a camera."""
        pipeline = self._pipelines.get(camera_id)
        if not pipeline:
            return {}
        
        return {
            label: [
                {
                    "label": d.label,
                    "confidence": d.confidence,
                    "bbox": d.bbox,
                    "center": d.center,
                    "area": d.area,
                }
                for d in detections
            ]
            for label, detections in pipeline.last_detections.items()
        }
    
    def get_pipeline(self, camera_id: str) -> Optional[PipelineState]:
        """Get a pipeline by camera ID."""
        return self._pipelines.get(camera_id)
    
    def get_camera_stream(self, camera_id: str) -> Optional[CameraStream]:
        """Get the camera stream for a camera."""
        pipeline = self._pipelines.get(camera_id)
        if not pipeline:
            return None
        return pipeline.camera_stream

