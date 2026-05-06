"""
Gallery API Router for Seestar Image Archive
============================================
Provides REST endpoints for browsing captured images.
Integrates with GalleryDatabase (SQLite) for filtering/searching.
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import FileResponse
from typing import Optional, List
from datetime import datetime
from pathlib import Path
import logging

from backend.models.gallery import (
    GalleryDatabase,
    GalleryFilter,
    ImageRecord,
    GalleryStats
)
from backend.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/", response_model=List[ImageRecord])
async def list_images(
    target: Optional[str] = Query(None, description="Target name (partial match)"),
    session_id: Optional[str] = Query(None, description="Session ID"),
    start_date: Optional[datetime] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[datetime] = Query(None, description="End date (ISO format)"),
    filter: Optional[str] = Query(None, description="Filter name (L, R, G, B, Ha, etc.)"),
    min_exposure: Optional[float] = Query(None, description="Minimum exposure time (seconds)"),
    max_exposure: Optional[float] = Query(None, description="Maximum exposure time (seconds)"),
    processed_only: bool = Query(False, description="Only show processed images"),
    stacked_only: bool = Query(False, description="Only show stacked images"),
    limit: int = Query(50, ge=1, le=500, description="Max results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: GalleryDatabase = Depends(get_db)
):
    """List images with flexible filtering."""
    try:
        filter_criteria = GalleryFilter(
            target=target,
            session_id=session_id,
            start_date=start_date,
            end_date=end_date,
            filter=filter,
            min_exposure=min_exposure,
            max_exposure=max_exposure,
            processed_only=processed_only,
            stacked_only=stacked_only,
            limit=limit,
            offset=offset
        )
        records = db.search(filter_criteria)
        logger.info(f"Gallery query returned {len(records)} images")
        return records
    except Exception as e:
        logger.error(f"Gallery search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats", response_model=GalleryStats)
async def get_gallery_stats(db: GalleryDatabase = Depends(get_db)):
    """Get gallery statistics summary."""
    try:
        stats = db.get_stats()
        logger.info(f"Gallery stats: {stats.total_images} images, {stats.total_sessions} sessions")
        return stats
    except Exception as e:
        logger.error(f"Failed to get gallery stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{image_id}", response_model=ImageRecord)
async def get_image_detail(image_id: int, db: GalleryDatabase = Depends(get_db)):
    """Get full details for a specific image."""
    try:
        filter_criteria = GalleryFilter(limit=1000, offset=0)
        records = db.search(filter_criteria)
        matching = [r for r in records if r.id == image_id]
        if not matching:
            raise HTTPException(status_code=404, detail=f"Image {image_id} not found")
        return matching[0]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get image {image_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{image_id}/thumbnail")
async def get_thumbnail(
    image_id: int,
    size: int = Query(256, ge=64, le=1024),
    db: GalleryDatabase = Depends(get_db)
):
    """Serve thumbnail for an image."""
    try:
        filter_criteria = GalleryFilter(limit=1000, offset=0)
        records = db.search(filter_criteria)
        matching = [r for r in records if r.id == image_id]
        if not matching:
            raise HTTPException(status_code=404, detail=f"Image {image_id} not found")
        record = matching[0]
        png_path = Path(record.png_path)
        if not png_path.exists():
            raise HTTPException(status_code=404, detail=f"PNG file not found: {record.png_path}")
        return FileResponse(
            path=str(png_path),
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=3600"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to serve thumbnail for image {image_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{image_id}/tags")
async def add_tags(
    image_id: int,
    tags: List[str],
    db: GalleryDatabase = Depends(get_db)
):
    """Add tags to an image (merges with existing tags)."""
    try:
        db.add_tags(image_id, tags)
        return {"status": "success", "image_id": image_id, "tags": tags}
    except Exception as e:
        logger.error(f"Failed to add tags to image {image_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
