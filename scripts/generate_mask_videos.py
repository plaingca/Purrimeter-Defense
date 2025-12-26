#!/usr/bin/env python3
"""
Batch script to generate mask videos for all existing recordings.

This processes each recording through SAM3 and generates a video
with detection masks overlaid on every frame.

Usage:
    python scripts/generate_mask_videos.py [--recording-id ID] [--limit N]
"""

import asyncio
import argparse
import sys
import os
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from backend.database import engine, AsyncSessionLocal, Recording, Alert
from backend.config import settings
from backend.services.sam3_service import SAM3Service
from backend.services.mask_video_service import MaskVideoService

import structlog
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer()
    ]
)
logger = structlog.get_logger()


async def add_mask_video_column():
    """Add mask_video_path column if it doesn't exist."""
    async with engine.begin() as conn:
        result = await conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='recordings' AND column_name='mask_video_path'
        """))
        
        if result.fetchone() is None:
            await conn.execute(text(
                'ALTER TABLE recordings ADD COLUMN mask_video_path VARCHAR'
            ))
            logger.info("Added mask_video_path column")
        else:
            logger.info("mask_video_path column already exists")


async def get_recordings_to_process(recording_id: str = None, limit: int = None):
    """Get recordings that need mask video generation."""
    async with AsyncSessionLocal() as session:
        query = (
            select(Recording)
            .options(
                selectinload(Recording.alert).selectinload(Alert.rule)
            )
            .where(Recording.mask_video_path == None)
        )
        
        if recording_id:
            query = query.where(Recording.id == recording_id)
        
        if limit:
            query = query.limit(limit)
        
        result = await session.execute(query)
        recordings = result.unique().scalars().all()
        
        # Detach from session so we can use them later
        return [
            {
                "id": r.id,
                "filepath": r.filepath,
                "filename": r.filename,
                "alert_id": r.alert_id,
                "rule_name": r.alert.rule.name if r.alert and r.alert.rule else "Unknown",
                "primary_target": r.alert.rule.primary_target if r.alert and r.alert.rule else "cat",
                "secondary_target": r.alert.rule.secondary_target if r.alert and r.alert.rule else None,
            }
            for r in recordings
            if r.filepath and Path(r.filepath).exists()
        ]


async def update_recording_mask_path(recording_id: str, mask_video_path: str):
    """Update the recording with the mask video path."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Recording).where(Recording.id == recording_id)
        )
        recording = result.scalar_one_or_none()
        if recording:
            recording.mask_video_path = mask_video_path
            await session.commit()
            logger.info("Updated recording", recording_id=recording_id, mask_video_path=mask_video_path)


async def process_recording(
    mask_service: MaskVideoService,
    recording: dict,
    index: int,
    total: int,
):
    """Process a single recording to generate mask video."""
    video_path = Path(recording["filepath"])
    output_path = video_path.with_stem(video_path.stem + "_mask")
    
    logger.info(
        f"\n{'='*60}\n"
        f"Processing recording {index}/{total}\n"
        f"{'='*60}",
        filename=recording["filename"],
        rule=recording["rule_name"],
        primary=recording["primary_target"],
        secondary=recording["secondary_target"],
    )
    
    start_time = datetime.now()
    
    result = await mask_service.generate_mask_video(
        video_path=video_path,
        output_path=output_path,
        primary_target=recording["primary_target"],
        secondary_target=recording["secondary_target"],
        rule_name=recording["rule_name"],
    )
    
    elapsed = (datetime.now() - start_time).total_seconds()
    
    if result:
        await update_recording_mask_path(recording["id"], result)
        logger.info(
            "Recording processed successfully",
            recording_id=recording["id"],
            time_seconds=f"{elapsed:.1f}",
            output=result,
        )
        return True
    else:
        logger.error(
            "Failed to process recording",
            recording_id=recording["id"],
        )
        return False


async def main(recording_id: str = None, limit: int = None):
    """Main entry point for batch processing."""
    
    print("=" * 70)
    print("Mask Video Generation - Batch Processor")
    print("=" * 70)
    print()
    
    # Ensure database column exists
    await add_mask_video_column()
    
    # Initialize SAM3 service
    logger.info("Initializing SAM3 model...")
    sam3_service = SAM3Service()
    await sam3_service.initialize()
    
    mask_service = MaskVideoService(sam3_service)
    
    # Get recordings to process
    logger.info("Fetching recordings to process...")
    recordings = await get_recordings_to_process(recording_id, limit)
    
    if not recordings:
        logger.info("No recordings found that need mask video generation")
        return
    
    logger.info(f"Found {len(recordings)} recordings to process")
    
    # Process each recording
    success_count = 0
    error_count = 0
    total_start = datetime.now()
    
    for i, recording in enumerate(recordings, 1):
        try:
            success = await process_recording(mask_service, recording, i, len(recordings))
            if success:
                success_count += 1
            else:
                error_count += 1
        except Exception as e:
            logger.error(f"Error processing recording: {e}")
            error_count += 1
    
    total_elapsed = (datetime.now() - total_start).total_seconds()
    
    print()
    print("=" * 70)
    print("Batch Processing Complete")
    print("=" * 70)
    print(f"  Total recordings: {len(recordings)}")
    print(f"  Successful: {success_count}")
    print(f"  Failed: {error_count}")
    print(f"  Total time: {total_elapsed/60:.1f} minutes")
    if success_count > 0:
        print(f"  Average time per video: {total_elapsed/success_count:.1f} seconds")
    print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate mask videos for recordings")
    parser.add_argument(
        "--recording-id",
        type=str,
        help="Process a specific recording by ID"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit the number of recordings to process"
    )
    
    args = parser.parse_args()
    
    asyncio.run(main(recording_id=args.recording_id, limit=args.limit))

