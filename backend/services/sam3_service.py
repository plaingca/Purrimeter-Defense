"""
SAM3 Model Service for object detection and segmentation.

Uses a dedicated thread pool to keep the HTTP interface responsive
during AI inference operations.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
import structlog
import numpy as np
from PIL import Image
import torch
import threading

from backend.config import settings

logger = structlog.get_logger()

# Dedicated thread pool for inference - isolated from the main async pool
# Using 2 workers to allow some parallelism while avoiding GPU memory issues
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


class SAM3Service:
    """
    Service for running SAM3 (Segment Anything Model 3) inference.
    
    SAM3 is a unified foundation model for promptable segmentation.
    It can detect and segment objects using text prompts.
    
    Uses a dedicated thread pool to keep the HTTP interface responsive.
    """
    
    def __init__(self):
        self.model = None
        self.processor = None
        self.device = settings.SAM3_DEVICE
        self._lock = asyncio.Lock()
        self._initialized = False
        self._inference_lock = threading.Lock()  # For thread-safe GPU access
        
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
                
                logger.info("SAM3 model loaded via official sam3 package", device=self.device)
                return
                
            except ImportError:
                logger.info("Official sam3 package not found, trying transformers...")
            
            try:
                # Try transformers (for when it's supported)
                from transformers import Sam3Processor, Sam3Model
                
                self.processor = Sam3Processor.from_pretrained(
                    settings.SAM3_MODEL_ID,
                    token=settings.HF_TOKEN,
                )
                
                # Load model without specific dtype (let it use default float32)
                # Per HuggingFace reference: https://huggingface.co/facebook/sam3
                self.model = Sam3Model.from_pretrained(
                    settings.SAM3_MODEL_ID,
                    token=settings.HF_TOKEN,
                ).to(self.device)
                
                self.model.eval()
                self._use_official_sam3 = False
                self._initialized = True
                
                logger.info("SAM3 model loaded via transformers", device=self.device)
                
            except Exception as e:
                logger.error("Failed to load SAM3 model", error=str(e))
                logger.warning("Running in mock mode - no actual detection will occur")
                logger.warning("To enable detection, install sam3: pip install sam3")
                self._initialized = True
                self.model = None
                self._use_official_sam3 = False
    
    async def detect_objects(
        self,
        image: Image.Image,
        text_prompts: List[str],
        confidence_threshold: float = 0.5,
    ) -> Dict[str, List[Detection]]:
        """
        Detect objects in an image using text prompts.
        
        Args:
            image: PIL Image to process
            text_prompts: List of text prompts describing objects to detect
            confidence_threshold: Minimum confidence for detection
            
        Returns:
            Dictionary mapping prompt text to list of Detection objects
        """
        if not self._initialized:
            await self.initialize()
        
        if self.model is None:
            # Mock mode - return empty detections
            return {prompt: [] for prompt in text_prompts}
        
        # Run inference in dedicated thread pool to keep async loop responsive
        loop = asyncio.get_running_loop()
        
        # Process all prompts together for efficiency
        results = await loop.run_in_executor(
            _inference_executor,
            self._detect_all_prompts,
            image,
            text_prompts,
            confidence_threshold,
        )
        
        return results
    
    def _detect_all_prompts(
        self,
        image: Image.Image,
        text_prompts: List[str],
        confidence_threshold: float,
    ) -> Dict[str, List[Detection]]:
        """
        Run detection for all prompts (synchronous, runs in thread pool).
        Uses a semaphore to serialize GPU access.
        """
        results = {}
        
        # Acquire semaphore to limit concurrent GPU access
        with _inference_semaphore:
            for prompt in text_prompts:
                results[prompt] = self._detect_single_prompt(
                    image, prompt, confidence_threshold
                )
        
        return results
    
    def _detect_single_prompt(
        self,
        image: Image.Image,
        text_prompt: str,
        confidence_threshold: float,
    ) -> List[Detection]:
        """Run detection for a single text prompt (synchronous)."""
        try:
            # Thread-safe GPU access
            with self._inference_lock:
                # Process inputs
                inputs = self.processor(
                    images=image,
                    text=text_prompt,
                    return_tensors="pt",
                ).to(self.device)
                
                # Run inference with inference mode for better performance
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
            
            # Log what we got
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
                        # Calculate center and area
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
            # Check if A's center is horizontally aligned with B
            # and A is above or overlapping B
            a_center_x, a_center_y = object_a.center
            
            # A should be within B's horizontal span
            horizontal_overlap = b_x1 <= a_center_x <= b_x2
            
            # A should be above or at B (y increases downward)
            # Check if bottom of A is near or above top of B, or overlapping
            vertical_position = a_y2 >= b_y1 - 50  # Allow 50px tolerance
            
            # Check mask overlap
            mask_overlap = np.sum(object_a.mask & object_b.mask) > 0
            
            return horizontal_overlap and (vertical_position or mask_overlap)
            
        elif relationship == "on":
            # Check if masks overlap at all
            return np.sum(object_a.mask & object_b.mask) > 0
            
        elif relationship == "inside":
            # Check if A is fully contained within B
            return (
                a_x1 >= b_x1 and a_y1 >= b_y1 and
                a_x2 <= b_x2 and a_y2 <= b_y2
            )
            
        elif relationship == "near":
            # Check proximity (within 100 pixels)
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
        """
        Create a visualization of detections overlaid on the image.
        
        Args:
            image: Original image
            detections: List of detections to visualize
            alpha: Transparency of mask overlay
            
        Returns:
            Image with masks overlaid
        """
        import matplotlib
        
        result = image.convert("RGBA")
        
        n_masks = len(detections)
        if n_masks == 0:
            return result
        
        # Get colormap
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
