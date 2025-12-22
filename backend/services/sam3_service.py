"""
SAM3 Model Service for object detection and segmentation.

Uses streaming video inference for real-time performance.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
import structlog
import numpy as np
from PIL import Image
import torch
import threading
import time

from backend.config import settings

logger = structlog.get_logger()

# Dedicated thread pool for inference - isolated from the main async pool
_inference_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="sam3-inference")

# Semaphore to limit concurrent GPU inference (prevents OOM)
_inference_semaphore = threading.Semaphore(1)


@dataclass
class Detection:
    """Represents a detected object with its mask and bounding box."""
    label: str
    confidence: float
    mask: np.ndarray  # Binary mask
    bbox: Tuple[int, int, int, int]  # x1, y1, x2, y2
    center: Tuple[int, int]  # Center point of bounding box
    area: int  # Pixel area of mask


@dataclass
class StreamingSession:
    """Holds state for a streaming inference session."""
    camera_id: str
    inference_session: Any  # The SAM3 streaming session object
    active_prompts: List[str] = field(default_factory=list)
    frame_count: int = 0
    last_update: float = 0


class SAM3Service:
    """
    Service for running SAM3 (Segment Anything Model 3) inference.
    
    Supports two modes:
    1. Single-frame inference (original) - for one-off detections
    2. Streaming video inference - for real-time video processing (faster)
    
    Streaming mode maintains state between frames and only encodes
    prompts once, resulting in significantly faster inference.
    """
    
    def __init__(self):
        self.model = None
        self.processor = None
        self.device = settings.SAM3_DEVICE
        self._lock = asyncio.Lock()
        self._initialized = False
        self._inference_lock = threading.Lock()
        self._use_streaming = False  # Will be set during init based on model capabilities
        
        # Streaming sessions per camera
        self._streaming_sessions: Dict[str, StreamingSession] = {}
        self._session_lock = threading.Lock()
        
    async def initialize(self):
        """Initialize the SAM3 model."""
        if self._initialized:
            return
            
        async with self._lock:
            if self._initialized:
                return
                
            logger.info("Loading SAM3 model...", model_id=settings.SAM3_MODEL_ID)
            
            # Try official sam3 package first, then transformers
            try:
                # Try official Meta sam3 package
                from sam3.model_builder import build_sam3_image_model
                from sam3.model.sam3_image_processor import Sam3Processor as OfficialSam3Processor
                
                self.model = build_sam3_image_model()
                self.processor = OfficialSam3Processor(self.model)
                self._use_official_sam3 = True
                self._initialized = True
                
                # Check if streaming is supported
                self._use_streaming = hasattr(self.processor, 'init_video_session')
                
                logger.info(
                    "SAM3 model loaded via official sam3 package", 
                    device=self.device,
                    streaming_supported=self._use_streaming,
                )
                return
                
            except ImportError:
                logger.info("Official sam3 package not found, trying transformers...")
            
            try:
                # Try transformers
                from transformers import Sam3Processor, Sam3Model
                
                self.processor = Sam3Processor.from_pretrained(
                    settings.SAM3_MODEL_ID,
                    token=settings.HF_TOKEN,
                )
                
                self.model = Sam3Model.from_pretrained(
                    settings.SAM3_MODEL_ID,
                    token=settings.HF_TOKEN,
                ).to(self.device)
                
                self.model.eval()
                self._use_official_sam3 = False
                self._initialized = True
                
                # Check if streaming is supported
                self._use_streaming = hasattr(self.processor, 'init_video_session')
                
                logger.info(
                    "SAM3 model loaded via transformers", 
                    device=self.device,
                    streaming_supported=self._use_streaming,
                )
                
            except Exception as e:
                logger.error("Failed to load SAM3 model", error=str(e))
                logger.warning("Running in mock mode - no actual detection will occur")
                self._initialized = True
                self.model = None
                self._use_official_sam3 = False
                self._use_streaming = False
    
    def _get_or_create_streaming_session(
        self,
        camera_id: str,
        prompts: List[str],
    ) -> Optional[StreamingSession]:
        """Get existing streaming session or create a new one."""
        if not self._use_streaming:
            return None
            
        with self._session_lock:
            session = self._streaming_sessions.get(camera_id)
            
            # Check if prompts changed - need to recreate session
            if session and set(session.active_prompts) != set(prompts):
                logger.info(
                    "Prompts changed, recreating streaming session",
                    camera_id=camera_id,
                    old_prompts=session.active_prompts,
                    new_prompts=prompts,
                )
                session = None
            
            if session is None:
                try:
                    # Initialize new streaming session
                    inference_session = self.processor.init_video_session(
                        inference_device=self.device,
                        processing_device="cpu",
                        video_storage_device="cpu",
                        dtype=torch.bfloat16 if self.device == "cuda" else torch.float32,
                    )
                    
                    # Add all text prompts
                    for prompt in prompts:
                        inference_session = self.processor.add_text_prompt(
                            inference_session=inference_session,
                            text=prompt,
                        )
                    
                    session = StreamingSession(
                        camera_id=camera_id,
                        inference_session=inference_session,
                        active_prompts=list(prompts),
                        last_update=time.time(),
                    )
                    self._streaming_sessions[camera_id] = session
                    
                    logger.info(
                        "Created streaming session",
                        camera_id=camera_id,
                        prompts=prompts,
                    )
                    
                except Exception as e:
                    logger.error(
                        "Failed to create streaming session, falling back to single-frame",
                        camera_id=camera_id,
                        error=str(e),
                    )
                    return None
            
            return session
    
    def _reset_streaming_session(self, camera_id: str):
        """Reset a streaming session (useful after long pauses)."""
        with self._session_lock:
            if camera_id in self._streaming_sessions:
                del self._streaming_sessions[camera_id]
                logger.info("Reset streaming session", camera_id=camera_id)
    
    async def detect_objects(
        self,
        image: Image.Image,
        text_prompts: List[str],
        confidence_threshold: float = 0.5,
        camera_id: Optional[str] = None,
    ) -> Dict[str, List[Detection]]:
        """
        Detect objects in an image using text prompts.
        
        Args:
            image: PIL Image to process
            text_prompts: List of text prompts describing objects to detect
            confidence_threshold: Minimum confidence for detection
            camera_id: Optional camera ID for streaming session (enables faster inference)
            
        Returns:
            Dictionary mapping prompt text to list of Detection objects
        """
        if not self._initialized:
            await self.initialize()
        
        if self.model is None:
            return {prompt: [] for prompt in text_prompts}
        
        loop = asyncio.get_running_loop()
        
        # Use streaming mode if available and camera_id provided
        if self._use_streaming and camera_id:
            results = await loop.run_in_executor(
                _inference_executor,
                self._detect_streaming,
                image,
                text_prompts,
                confidence_threshold,
                camera_id,
            )
        else:
            # Use single-frame mode with caching for static objects
            results = await loop.run_in_executor(
                _inference_executor,
                self._detect_all_prompts,
                image,
                text_prompts,
                confidence_threshold,
                camera_id,
            )
        
        return results
    
    def _detect_streaming(
        self,
        image: Image.Image,
        text_prompts: List[str],
        confidence_threshold: float,
        camera_id: str,
    ) -> Dict[str, List[Detection]]:
        """
        Run detection using streaming video inference.
        Much faster for continuous video as prompts are encoded once.
        """
        start_time = time.time()
        
        with _inference_semaphore:
            session = self._get_or_create_streaming_session(camera_id, text_prompts)
            
            if session is None:
                # Fall back to single-frame mode
                return self._detect_all_prompts(image, text_prompts, confidence_threshold)
            
            try:
                with self._inference_lock:
                    # Process the frame
                    inputs = self.processor(
                        images=image,
                        device=self.device,
                        return_tensors="pt",
                    )
                    
                    # Run streaming inference
                    with torch.inference_mode():
                        model_outputs = self.model(
                            inference_session=session.inference_session,
                            frame=inputs.pixel_values[0],
                            reverse=False,
                        )
                    
                    # Post-process outputs
                    processed_outputs = self.processor.postprocess_outputs(
                        session.inference_session,
                        model_outputs,
                        original_sizes=inputs.original_sizes,
                    )
                
                session.frame_count += 1
                session.last_update = time.time()
                
                # Convert to our Detection format
                results = self._outputs_to_detections(
                    processed_outputs,
                    text_prompts,
                    confidence_threshold,
                )
                
                elapsed = time.time() - start_time
                logger.debug(
                    "Streaming inference complete",
                    camera_id=camera_id,
                    frame_count=session.frame_count,
                    elapsed_ms=int(elapsed * 1000),
                )
                
                return results
                
            except Exception as e:
                logger.error(
                    "Streaming inference failed, resetting session",
                    camera_id=camera_id,
                    error=str(e),
                )
                self._reset_streaming_session(camera_id)
                # Fall back to single-frame
                return self._detect_all_prompts(image, text_prompts, confidence_threshold)
    
    def _outputs_to_detections(
        self,
        outputs: Dict,
        prompts: List[str],
        confidence_threshold: float,
    ) -> Dict[str, List[Detection]]:
        """Convert streaming outputs to Detection objects."""
        results = {prompt: [] for prompt in prompts}
        
        try:
            object_ids = outputs.get("object_ids", [])
            masks = outputs.get("masks", [])
            boxes = outputs.get("boxes", [])
            scores = outputs.get("scores", [])
            labels = outputs.get("labels", [])  # Text labels for each object
            
            if not object_ids:
                return results
            
            # Convert tensors to numpy
            if hasattr(masks, 'cpu'):
                masks = masks.cpu().numpy()
            if hasattr(boxes, 'cpu'):
                boxes = boxes.cpu().numpy()
            if hasattr(scores, 'cpu'):
                scores = scores.cpu().numpy()
            
            for i, obj_id in enumerate(object_ids):
                score = float(scores[i]) if i < len(scores) else 1.0
                if score < confidence_threshold:
                    continue
                
                mask = masks[i] if i < len(masks) else np.zeros((1, 1), dtype=np.uint8)
                box = boxes[i] if i < len(boxes) else [0, 0, 1, 1]
                
                # Get the label for this detection
                label = labels[i] if i < len(labels) else prompts[0] if prompts else "object"
                
                x1, y1, x2, y2 = map(int, box)
                center = ((x1 + x2) // 2, (y1 + y2) // 2)
                area = int(np.sum(mask)) if mask.size > 0 else 0
                
                detection = Detection(
                    label=label,
                    confidence=score,
                    mask=mask.astype(np.uint8) if mask.size > 0 else np.zeros((1, 1), dtype=np.uint8),
                    bbox=(x1, y1, x2, y2),
                    center=center,
                    area=area,
                )
                
                # Add to appropriate prompt results
                if label in results:
                    results[label].append(detection)
                elif prompts:
                    # If label doesn't match prompts exactly, try to match
                    for prompt in prompts:
                        if prompt.lower() in label.lower() or label.lower() in prompt.lower():
                            results[prompt].append(detection)
                            break
            
            # Log results
            for prompt, detections in results.items():
                if detections:
                    logger.info(
                        "SAM3 found objects (streaming)",
                        prompt=prompt,
                        count=len(detections),
                        scores=[d.confidence for d in detections],
                    )
                else:
                    logger.debug("SAM3 found no objects (streaming)", prompt=prompt)
            
        except Exception as e:
            logger.error("Failed to convert outputs to detections", error=str(e))
        
        return results
    
    def _detect_all_prompts(
        self,
        image: Image.Image,
        text_prompts: List[str],
        confidence_threshold: float,
        camera_id: Optional[str] = None,
    ) -> Dict[str, List[Detection]]:
        """
        Run detection for all prompts with SHARED VISION ENCODING.
        
        Vision encoder runs ONCE for all prompts (saves ~300ms per extra prompt).
        """
        with _inference_semaphore:
            return self._detect_with_shared_vision(
                image, text_prompts, confidence_threshold
            )
    
    def _detect_with_shared_vision(
        self,
        image: Image.Image,
        text_prompts: List[str],
        confidence_threshold: float,
    ) -> Dict[str, List[Detection]]:
        """
        Detect multiple prompts with shared vision encoding.
        Vision encoder runs ONCE, then each prompt uses the cached vision features.
        """
        results = {prompt: [] for prompt in text_prompts}
        
        if not text_prompts:
            return results
        
        try:
            start_time = time.time()
            
            with self._inference_lock:
                # Process image with first prompt to get pixel values
                first_inputs = self.processor(
                    images=image,
                    text=text_prompts[0],
                    return_tensors="pt",
                ).to(self.device)
                
                with torch.inference_mode():
                    # Run vision encoder ONCE
                    vision_start = time.time()
                    vision_embeds = self.model.vision_encoder(first_inputs['pixel_values'])
                    vision_time = (time.time() - vision_start) * 1000
                    
                    # Process each prompt with shared vision
                    for prompt in text_prompts:
                        prompt_start = time.time()
                        
                        # Get text inputs for this prompt
                        text_inputs = self.processor(
                            images=image,
                            text=prompt,
                            return_tensors="pt",
                        ).to(self.device)
                        
                        # Run model with pre-computed vision embeddings
                        outputs = self.model(
                            vision_embeds=vision_embeds,
                            input_ids=text_inputs['input_ids'],
                            attention_mask=text_inputs['attention_mask'],
                        )
                        
                        # Post-process results
                        processed = self.processor.post_process_instance_segmentation(
                            outputs,
                            threshold=confidence_threshold,
                            mask_threshold=0.5,
                            target_sizes=first_inputs.get("original_sizes").tolist(),
                        )[0]
                        
                        prompt_time = (time.time() - prompt_start) * 1000
                        
                        # Convert to Detection objects
                        detections = self._process_detection_results(processed, prompt, confidence_threshold)
                        results[prompt] = detections
                        
                        if detections:
                            logger.info(
                                "SAM3 found objects (shared vision)",
                                prompt=prompt,
                                count=len(detections),
                                prompt_ms=int(prompt_time),
                            )
                        else:
                            logger.debug(
                                "SAM3 found no objects",
                                prompt=prompt,
                                prompt_ms=int(prompt_time),
                            )
            
            total_time = (time.time() - start_time) * 1000
            logger.debug(
                "Shared vision detection complete",
                prompts=len(text_prompts),
                vision_ms=int(vision_time),
                total_ms=int(total_time),
            )
            
        except Exception as e:
            logger.error("Shared vision detection failed", error=str(e))
            import traceback
            traceback.print_exc()
            # Fall back to individual detection
            for prompt in text_prompts:
                results[prompt] = self._detect_single_prompt(image, prompt, confidence_threshold)
        
        return results
    
    def _process_detection_results(
        self,
        results: Dict,
        prompt: str,
        confidence_threshold: float,
    ) -> List[Detection]:
        """Convert post-processed results to Detection objects."""
        detections = []
        
        num_masks = len(results.get("masks", []))
        if "masks" not in results or num_masks == 0:
            return detections
        
        masks = results["masks"].cpu().numpy()
        boxes = results["boxes"].cpu().numpy() if "boxes" in results else []
        scores = results["scores"].cpu().numpy() if "scores" in results else []
        
        for i, (mask, box, score) in enumerate(zip(masks, boxes, scores)):
            if score >= confidence_threshold:
                x1, y1, x2, y2 = map(int, box)
                center = ((x1 + x2) // 2, (y1 + y2) // 2)
                area = int(np.sum(mask))
                
                detections.append(Detection(
                    label=prompt,
                    confidence=float(score),
                    mask=mask.astype(np.uint8),
                    bbox=(x1, y1, x2, y2),
                    center=center,
                    area=area,
                ))
        
        return detections
    
    def _detect_single_prompt(
        self,
        image: Image.Image,
        text_prompt: str,
        confidence_threshold: float,
    ) -> List[Detection]:
        """Run detection for a single text prompt (synchronous)."""
        try:
            with self._inference_lock:
                # Process inputs
                inputs = self.processor(
                    images=image,
                    text=text_prompt,
                    return_tensors="pt",
                ).to(self.device)
                
                # Run inference
                with torch.inference_mode():
                    outputs = self.model(**inputs)
                
                # Post-process results
                results = self.processor.post_process_instance_segmentation(
                    outputs,
                    threshold=confidence_threshold,
                    mask_threshold=0.5,
                    target_sizes=inputs.get("original_sizes").tolist(),
                )[0]
            
            detections = []
            
            num_masks = len(results.get("masks", []))
            logger.debug(
                "SAM3 detection result",
                prompt=text_prompt,
                num_masks=num_masks,
                has_boxes="boxes" in results,
                has_scores="scores" in results,
            )
            
            if "masks" in results and num_masks > 0:
                masks = results["masks"].cpu().numpy()
                boxes = results["boxes"].cpu().numpy() if "boxes" in results else []
                scores = results["scores"].cpu().numpy() if "scores" in results else []
                
                logger.info(
                    "SAM3 found objects",
                    prompt=text_prompt,
                    count=len(masks),
                    scores=[float(s) for s in scores],
                )
                
                for i, (mask, box, score) in enumerate(zip(masks, boxes, scores)):
                    if score >= confidence_threshold:
                        x1, y1, x2, y2 = map(int, box)
                        center = ((x1 + x2) // 2, (y1 + y2) // 2)
                        area = int(np.sum(mask))
                        
                        detections.append(Detection(
                            label=text_prompt,
                            confidence=float(score),
                            mask=mask.astype(np.uint8),
                            bbox=(x1, y1, x2, y2),
                            center=center,
                            area=area,
                        ))
            else:
                logger.debug("SAM3 found no objects", prompt=text_prompt)
            
            return detections
            
        except Exception as e:
            logger.error("Detection failed", prompt=text_prompt, error=str(e))
            import traceback
            traceback.print_exc()
            return []
    
    def check_spatial_relationship(
        self,
        object_a: Detection,
        object_b: Detection,
        relationship: str,
    ) -> bool:
        """
        Check if a spatial relationship exists between two detected objects.
        
        Args:
            object_a: First detection (e.g., cat)
            object_b: Second detection (e.g., counter)
            relationship: Type of relationship to check:
                - "over": object_a center is above object_b and masks overlap
                - "on": object_a overlaps with object_b (any part)
                - "inside": object_a is fully contained within object_b
                - "near": objects are within proximity
                
        Returns:
            True if relationship exists
        """
        a_x1, a_y1, a_x2, a_y2 = object_a.bbox
        b_x1, b_y1, b_x2, b_y2 = object_b.bbox
        
        if relationship == "over":
            a_center_x, a_center_y = object_a.center
            horizontal_overlap = b_x1 <= a_center_x <= b_x2
            vertical_position = a_y2 >= b_y1 - 50
            mask_overlap = np.sum(object_a.mask & object_b.mask) > 0
            return horizontal_overlap and (vertical_position or mask_overlap)
            
        elif relationship == "on":
            return np.sum(object_a.mask & object_b.mask) > 0
            
        elif relationship == "inside":
            return (
                a_x1 >= b_x1 and a_y1 >= b_y1 and
                a_x2 <= b_x2 and a_y2 <= b_y2
            )
            
        elif relationship == "near":
            a_cx, a_cy = object_a.center
            b_cx, b_cy = object_b.center
            distance = np.sqrt((a_cx - b_cx)**2 + (a_cy - b_cy)**2)
            return distance < 100
            
        return False
    
    def masks_to_visualization(
        self,
        image: Image.Image,
        detections: List[Detection],
        alpha: float = 0.5,
    ) -> Image.Image:
        """Create a visualization of detections overlaid on the image."""
        import matplotlib
        
        result = image.convert("RGBA")
        
        n_masks = len(detections)
        if n_masks == 0:
            return result
        
        cmap = matplotlib.colormaps.get_cmap("rainbow").resampled(n_masks)
        colors = [
            tuple(int(c * 255) for c in cmap(i)[:3])
            for i in range(n_masks)
        ]
        
        for detection, color in zip(detections, colors):
            mask = detection.mask * 255
            mask_img = Image.fromarray(mask.astype(np.uint8))
            
            overlay = Image.new("RGBA", result.size, color + (0,))
            alpha_mask = mask_img.point(lambda v: int(v * alpha))
            overlay.putalpha(alpha_mask)
            
            result = Image.alpha_composite(result, overlay)
        
        return result
