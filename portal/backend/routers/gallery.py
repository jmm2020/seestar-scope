"""
Gallery API Router for Seestar Image Archive
============================================
Provides REST endpoints for browsing captured images.
Integrates with GalleryDatabase (SQLite) for filtering/searching.
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import FileResponse, StreamingResponse
from typing import Optional, List
from datetime import datetime
from pathlib import Path
import io
import logging

from PIL import Image

from ..models.gallery import (
    GalleryDatabase,
    GalleryFilter,
    ImageRecord,
    GalleryStats
)
from ..database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["gallery"])


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
    """
    List images with flexible filtering.
    
    Examples:
    - GET /api/gallery/?target=M31&limit=10
    - GET /api/gallery/?session_id=20260302_143052
    - GET /api/gallery/?processed_only=true&filter=Ha
    - GET /api/gallery/?start_date=2026-03-01T00:00:00Z&end_date=2026-03-02T23:59:59Z
    """
    try:
        # Build filter criteria
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
    """
    Get gallery statistics summary.
    
    Returns:
    - Total images/sessions
    - Target/filter breakdown
    - Total exposure hours
    - Date range
    - Processing counts
    """
    try:
        stats = db.get_stats()
        logger.info(f"Gallery stats: {stats.total_images} images, {stats.total_sessions} sessions")
        return stats
        
    except Exception as e:
        logger.error(f"Failed to get gallery stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{image_id}", response_model=ImageRecord)
async def get_image_detail(image_id: int, db: GalleryDatabase = Depends(get_db)):
    """
    Get full details for a specific image.
    
    Returns ImageRecord with all metadata, tags, notes, processing status.
    """
    try:
        record = db.get_by_id(image_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Image {image_id} not found")
        return record

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
    """
    Serve thumbnail for an image.

    Returns the PNG preview scaled to fit within size×size pixels (aspect ratio preserved).
    If the original is already smaller than size, it is returned as-is.

    Query params:
    - size: Max thumbnail dimension in pixels (default 256)
    """
    try:
        record = db.get_by_id(image_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Image {image_id} not found")

        png_path = Path(record.png_path)
        if not png_path.exists():
            raise HTTPException(status_code=404, detail=f"PNG file not found: {record.png_path}")

        cache_headers = {"Cache-Control": "public, max-age=3600"}
        with Image.open(png_path) as img:
            if img.width > size or img.height > size:
                img.thumbnail((size, size), Image.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                buf.seek(0)
                return StreamingResponse(buf, media_type="image/png", headers=cache_headers)

        return FileResponse(path=str(png_path), media_type="image/png", headers=cache_headers)

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
    """
    Add tags to an image (merges with existing tags).
    
    Request body: ["nebula", "narrowband", "featured"]
    """
    try:
        db.add_tags(image_id, tags)
        return {"status": "success", "image_id": image_id, "tags": tags}
        
    except Exception as e:
        logger.error(f"Failed to add tags to image {image_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
