"""
Rule engine for evaluating detection rules and triggering alerts.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Callable
import uuid
import structlog

from backend.database import Rule, RuleConditionType, Alert, AlertState
from backend.services.sam3_service import SAM3Service, Detection
from backend.config import settings
from backend.utils import to_utc_isoformat

logger = structlog.get_logger()


@dataclass
class RuleEvaluation:
    """Result of evaluating a rule."""
    rule_id: str
    triggered: bool
    confidence: float
    detected_objects: List[Dict[str, Any]]
    message: str


@dataclass
class RuleState:
    """State tracking for a rule."""
    rule: Rule
    last_triggered: Optional[datetime] = None
    current_alert_id: Optional[str] = None
    is_in_alert: bool = False
    consecutive_detections: int = 0
    required_consecutive: int = 1  # Require N consecutive detections to trigger (1 = instant)


class RuleEngine:
    """
    Engine for evaluating detection rules against SAM3 results.
    
    Supports various condition types:
    - Object detected: Simple presence detection
    - Object in zone: Object within defined screen region
    - Object over object: Spatial relationship (e.g., cat over counter)
    - Object count: Number of objects exceeds threshold
    """
    
    def __init__(self, sam3_service: SAM3Service):
        self.sam3_service = sam3_service
        self._rule_states: Dict[str, RuleState] = {}
        self._on_alert_callbacks: List[Callable] = []
        self._on_alert_end_callbacks: List[Callable] = []
    
    def register_rule(self, rule: Rule):
        """Register a rule for evaluation."""
        self._rule_states[rule.id] = RuleState(
            rule=rule,
            required_consecutive=settings.DETECTION_CONSECUTIVE_FRAMES,
        )
        logger.info("Rule registered", rule_id=rule.id, name=rule.name, required_consecutive=settings.DETECTION_CONSECUTIVE_FRAMES)
    
    def unregister_rule(self, rule_id: str):
        """Unregister a rule and clear any active alert."""
        if rule_id in self._rule_states:
            state = self._rule_states[rule_id]
            # Clear any active alert state
            if state.is_in_alert:
                logger.info("Clearing active alert on rule unregister", rule_id=rule_id, alert_id=state.current_alert_id)
                state.is_in_alert = False
                state.current_alert_id = None
                state.consecutive_detections = 0
            del self._rule_states[rule_id]
            logger.info("Rule unregistered", rule_id=rule_id)
    
    def update_rule(self, rule: Rule):
        """Update an existing rule and reset its alert state."""
        if rule.id in self._rule_states:
            old_state = self._rule_states[rule.id]
            old_rule = old_state.rule  # Keep reference to old rule for callbacks
            # If there was an active alert, we need to end it
            was_in_alert = old_state.is_in_alert
            old_alert_id = old_state.current_alert_id
            
            # Create new state with fresh rule but preserve cooldown
            self._rule_states[rule.id] = RuleState(
                rule=rule,
                last_triggered=old_state.last_triggered,
                is_in_alert=False,  # Reset alert state
                current_alert_id=None,
                consecutive_detections=0,
            )
            
            logger.info(
                "Rule updated", 
                rule_id=rule.id, 
                name=rule.name,
                was_in_alert=was_in_alert,
                primary_target=rule.primary_target,
            )
            
            return was_in_alert, old_alert_id, old_rule
        else:
            # Rule not registered, just register it
            self.register_rule(rule)
            return False, None, None
    
    async def fire_alert_end(self, alert_id: str, rule: Rule):
        """Manually fire alert end callbacks (for rule updates)."""
        logger.info(
            "Firing alert end event",
            alert_id=alert_id,
            rule_id=rule.id,
        )
        
        for callback in self._on_alert_end_callbacks:
            try:
                await callback(alert_id=alert_id, rule=rule)
            except Exception as e:
                logger.error("Alert end callback error", error=str(e))
    
    def on_alert(self, callback: Callable):
        """Register callback for alert start."""
        self._on_alert_callbacks.append(callback)
    
    def on_alert_end(self, callback: Callable):
        """Register callback for alert end."""
        self._on_alert_end_callbacks.append(callback)
    
    async def evaluate_rules(
        self,
        camera_id: str,
        detections: Dict[str, List[Detection]],
    ) -> List[RuleEvaluation]:
        """
        Evaluate all rules for a camera against detected objects.
        
        Args:
            camera_id: Camera the detections are from
            detections: Dict mapping label to list of Detection objects
            
        Returns:
            List of RuleEvaluation results
        """
        results = []
        
        for rule_id, state in self._rule_states.items():
            rule = state.rule
            
            # Skip if not for this camera or disabled
            if rule.camera_id != camera_id or not rule.enabled:
                continue
            
            # Check cooldown
            if state.last_triggered:
                cooldown_end = state.last_triggered + timedelta(seconds=rule.cooldown_seconds)
                if datetime.utcnow() < cooldown_end and not state.is_in_alert:
                    continue
            
            # Evaluate the rule
            evaluation = await self._evaluate_single_rule(rule, state, detections)
            results.append(evaluation)
            
            # Handle alert state transitions
            await self._handle_state_transition(state, evaluation)
        
        return results
    
    async def _evaluate_single_rule(
        self,
        rule: Rule,
        state: RuleState,
        detections: Dict[str, List[Detection]],
    ) -> RuleEvaluation:
        """Evaluate a single rule against detections."""
        
        primary_detections = detections.get(rule.primary_target, [])
        secondary_detections = detections.get(rule.secondary_target, []) if rule.secondary_target else []
        
        triggered = False
        confidence = 0.0
        detected_objects = []
        message = ""
        
        if rule.condition_type == RuleConditionType.OBJECT_DETECTED:
            # Simple object presence
            if primary_detections:
                triggered = True
                confidence = max(d.confidence for d in primary_detections)
                detected_objects = [
                    {"label": d.label, "confidence": d.confidence, "bbox": d.bbox}
                    for d in primary_detections
                ]
                message = f"🚨 {rule.primary_target} detected!"
        
        elif rule.condition_type == RuleConditionType.OBJECT_IN_ZONE:
            # Object within defined zone
            zone = rule.condition_params.get("zone", {})
            x1 = zone.get("x1", 0)
            y1 = zone.get("y1", 0)
            x2 = zone.get("x2", 9999)
            y2 = zone.get("y2", 9999)
            
            for detection in primary_detections:
                cx, cy = detection.center
                if x1 <= cx <= x2 and y1 <= cy <= y2:
                    triggered = True
                    confidence = max(confidence, detection.confidence)
                    detected_objects.append({
                        "label": detection.label,
                        "confidence": detection.confidence,
                        "bbox": detection.bbox,
                        "in_zone": True,
                    })
            
            if triggered:
                message = f"🚨 {rule.primary_target} in restricted zone!"
        
        elif rule.condition_type == RuleConditionType.OBJECT_OVER_OBJECT:
            # Spatial relationship between objects
            relationship = rule.condition_params.get("relationship", "over")
            
            logger.debug(
                "Evaluating object_over_object rule",
                rule_name=rule.name,
                primary_target=rule.primary_target,
                secondary_target=rule.secondary_target,
                primary_count=len(primary_detections),
                secondary_count=len(secondary_detections),
                relationship=relationship,
            )
            
            for primary in primary_detections:
                for secondary in secondary_detections:
                    is_related = self.sam3_service.check_spatial_relationship(
                        primary, secondary, relationship
                    )
                    
                    logger.debug(
                        "Checking spatial relationship",
                        primary_bbox=primary.bbox,
                        secondary_bbox=secondary.bbox,
                        relationship=relationship,
                        result=is_related,
                    )
                    
                    if is_related:
                        triggered = True
                        confidence = max(confidence, primary.confidence, secondary.confidence)
                        detected_objects.append({
                            "primary": {
                                "label": primary.label,
                                "confidence": primary.confidence,
                                "bbox": primary.bbox,
                            },
                            "secondary": {
                                "label": secondary.label,
                                "confidence": secondary.confidence,
                                "bbox": secondary.bbox,
                            },
                            "relationship": relationship,
                        })
            
            if triggered:
                message = f"🚨 {rule.primary_target} {relationship} {rule.secondary_target}!"
            else:
                logger.debug(
                    "Object over object rule not triggered",
                    rule_name=rule.name,
                    primary_found=len(primary_detections) > 0,
                    secondary_found=len(secondary_detections) > 0,
                )
        
        elif rule.condition_type == RuleConditionType.OBJECT_COUNT:
            # Count exceeds threshold
            threshold = rule.condition_params.get("threshold", 1)
            count = len(primary_detections)
            
            if count >= threshold:
                triggered = True
                confidence = sum(d.confidence for d in primary_detections) / count if count > 0 else 0
                detected_objects = [
                    {"label": d.label, "confidence": d.confidence, "bbox": d.bbox}
                    for d in primary_detections
                ]
                message = f"🚨 {count} {rule.primary_target}(s) detected (threshold: {threshold})!"
        
        return RuleEvaluation(
            rule_id=rule.id,
            triggered=triggered,
            confidence=confidence,
            detected_objects=detected_objects,
            message=message or rule.alert_message,
        )
    
    async def _handle_state_transition(
        self,
        state: RuleState,
        evaluation: RuleEvaluation,
    ):
        """Handle alert state transitions based on rule evaluation."""
        
        if evaluation.triggered:
            state.consecutive_detections += 1
            
            if not state.is_in_alert:
                # Check if we have enough consecutive detections
                if state.consecutive_detections >= state.required_consecutive:
                    # Transition to alert state
                    state.is_in_alert = True
                    state.last_triggered = datetime.utcnow()
                    state.current_alert_id = str(uuid.uuid4())
                    
                    logger.info(
                        "Alert triggered",
                        rule_id=evaluation.rule_id,
                        alert_id=state.current_alert_id,
                        message=evaluation.message,
                    )
                    
                    # Notify callbacks
                    for callback in self._on_alert_callbacks:
                        try:
                            await callback(
                                alert_id=state.current_alert_id,
                                rule=state.rule,
                                evaluation=evaluation,
                            )
                        except Exception as e:
                            logger.error("Alert callback error", error=str(e))
        else:
            state.consecutive_detections = 0
            
            if state.is_in_alert:
                # Transition out of alert state
                logger.info(
                    "Alert ended",
                    rule_id=evaluation.rule_id,
                    alert_id=state.current_alert_id,
                )
                
                alert_id = state.current_alert_id
                state.is_in_alert = False
                state.current_alert_id = None
                
                # Notify callbacks
                for callback in self._on_alert_end_callbacks:
                    try:
                        await callback(
                            alert_id=alert_id,
                            rule=state.rule,
                        )
                    except Exception as e:
                        logger.error("Alert end callback error", error=str(e))
    
    def get_rule_states(self) -> Dict[str, dict]:
        """Get current state of all rules."""
        return {
            rule_id: {
                "rule_id": rule_id,
                "rule_name": state.rule.name,
                "is_in_alert": state.is_in_alert,
                "current_alert_id": state.current_alert_id,
                "last_triggered": to_utc_isoformat(state.last_triggered),
                "consecutive_detections": state.consecutive_detections,
            }
            for rule_id, state in self._rule_states.items()
        }

