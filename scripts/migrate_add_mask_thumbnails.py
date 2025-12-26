#!/usr/bin/env python3
"""
Migration script to:
1. Add mask_thumbnail_path column to recordings table
2. Generate mask thumbnails for existing recordings using stored detection data
"""

import asyncio
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np
from pathlib import Path
from sqlalchemy import text, select
from sqlalchemy.orm import selectinload

from backend.database import engine, AsyncSessionLocal, Recording, Alert
from backend.config import settings


async def add_column():
    """Add mask_thumbnail_path column if it doesn't exist."""
    print("Adding mask_thumbnail_path column to recordings table...")
    
    async with engine.begin() as conn:
        # Check if column exists
        result = await conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='recordings' AND column_name='mask_thumbnail_path'
        """))
        
        if result.fetchone() is None:
            await conn.execute(text(
                'ALTER TABLE recordings ADD COLUMN mask_thumbnail_path VARCHAR'
            ))
            print("✓ Column added successfully")
        else:
            print("✓ Column already exists")


async def generate_mask_thumbnail_for_recording(recording: Recording, alert: Alert) -> str:
    """
    Generate a mask thumbnail for an existing recording using stored detection data.
    
    Since we don't have the original segmentation masks, we draw bounding boxes
    from the stored detected_objects data.
    """
    # Check if thumbnail exists to use as base image
    if not recording.thumbnail_path or not Path(recording.thumbnail_path).exists():
        # Try to extract frame from video
        video_path = Path(recording.filepath)
        if not video_path.exists():
            return None
        
        cap = cv2.VideoCapture(str(video_path))
        fps = cap.get(cv2.CAP_PROP_FPS)
        # Seek to ~1 second in
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(fps))
        ret, frame = cap.read()
        if not ret:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = cap.read()
        cap.release()
        
        if not ret:
            return None
    else:
        # Read existing thumbnail
        frame = cv2.imread(str(recording.thumbnail_path))
        if frame is None:
            return None
    
    height, width = frame.shape[:2]
    overlay = frame.copy()
    
    # Color scheme
    primary_color = (0, 100, 255)  # Orange-red in BGR
    secondary_color = (255, 150, 0)  # Blue in BGR
    
    detected_objects = alert.detected_objects or []
    
    for obj in detected_objects:
        # Handle spatial relationship objects (primary/secondary structure)
        if 'primary' in obj and 'secondary' in obj:
            # Draw primary
            primary = obj['primary']
            if 'bbox' in primary:
                x1, y1, x2, y2 = primary['bbox']
                # Scale bbox if needed (thumbnail might be resized)
                cv2.rectangle(overlay, (x1, y1), (x2, y2), primary_color, 3)
                label = f"{primary.get('label', 'object')}: {primary.get('confidence', 0):.0%}"
                label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
                cv2.rectangle(overlay, (x1, y1 - label_size[1] - 10), (x1 + label_size[0] + 10, y1), primary_color, -1)
                cv2.putText(overlay, label, (x1 + 5, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            
            # Draw secondary
            secondary = obj['secondary']
            if 'bbox' in secondary:
                x1, y1, x2, y2 = secondary['bbox']
                cv2.rectangle(overlay, (x1, y1), (x2, y2), secondary_color, 3)
                label = f"{secondary.get('label', 'object')}: {secondary.get('confidence', 0):.0%}"
                label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
                cv2.rectangle(overlay, (x1, y2), (x1 + label_size[0] + 10, y2 + label_size[1] + 10), secondary_color, -1)
                cv2.putText(overlay, label, (x1 + 5, y2 + label_size[1] + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        # Handle simple detection objects
        elif 'bbox' in obj:
            x1, y1, x2, y2 = obj['bbox']
            cv2.rectangle(overlay, (x1, y1), (x2, y2), primary_color, 3)
            label = f"{obj.get('label', 'object')}: {obj.get('confidence', 0):.0%}"
            label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.rectangle(overlay, (x1, y1 - label_size[1] - 10), (x1 + label_size[0] + 10, y1), primary_color, -1)
            cv2.putText(overlay, label, (x1 + 5, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    
    # Blend overlay
    result = cv2.addWeighted(frame, 0.4, overlay, 0.6, 0)
    
    # Add header info
    rule_name = alert.rule.name if alert.rule else "Unknown Rule"
    cv2.putText(result, f"Rule: {rule_name}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    
    timestamp = alert.triggered_at.strftime("%Y-%m-%d %H:%M:%S UTC") if alert.triggered_at else ""
    cv2.putText(result, timestamp, (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
    
    # Add "Backfilled" indicator
    cv2.putText(result, "[Backfilled - Bounding Boxes Only]", (10, height - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 255), 1)
    
    # Save mask thumbnail
    video_path = Path(recording.filepath)
    mask_filename = video_path.stem + "_mask.jpg"
    mask_path = settings.RECORDINGS_PATH / mask_filename
    
    cv2.imwrite(str(mask_path), result)
    
    return str(mask_path)


async def backfill_mask_thumbnails():
    """Generate mask thumbnails for all existing recordings that don't have them."""
    print("\nBackfilling mask thumbnails for existing recordings...")
    
    async with AsyncSessionLocal() as session:
        # Get all recordings without mask thumbnails, with their alerts
        query = (
            select(Recording)
            .options(selectinload(Recording.alert).selectinload(Alert.rule))
            .where(Recording.mask_thumbnail_path == None)
        )
        
        result = await session.execute(query)
        recordings = result.unique().scalars().all()
        
        print(f"Found {len(recordings)} recordings without mask thumbnails")
        
        success_count = 0
        skip_count = 0
        error_count = 0
        
        for i, recording in enumerate(recordings):
            try:
                if not recording.alert:
                    print(f"  [{i+1}/{len(recordings)}] {recording.filename}: No alert data, skipping")
                    skip_count += 1
                    continue
                
                if not recording.alert.detected_objects:
                    print(f"  [{i+1}/{len(recordings)}] {recording.filename}: No detection data, skipping")
                    skip_count += 1
                    continue
                
                mask_path = await generate_mask_thumbnail_for_recording(recording, recording.alert)
                
                if mask_path:
                    recording.mask_thumbnail_path = mask_path
                    await session.commit()
                    print(f"  [{i+1}/{len(recordings)}] {recording.filename}: ✓ Generated mask thumbnail")
                    success_count += 1
                else:
                    print(f"  [{i+1}/{len(recordings)}] {recording.filename}: Failed to generate (no source image)")
                    skip_count += 1
                    
            except Exception as e:
                print(f"  [{i+1}/{len(recordings)}] {recording.filename}: Error - {e}")
                error_count += 1
        
        print(f"\nBackfill complete:")
        print(f"  ✓ Success: {success_count}")
        print(f"  ⊘ Skipped: {skip_count}")
        print(f"  ✗ Errors: {error_count}")


async def main():
    print("=" * 60)
    print("Mask Thumbnail Migration Script")
    print("=" * 60)
    
    await add_column()
    await backfill_mask_thumbnails()
    
    print("\n" + "=" * 60)
    print("Migration complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

