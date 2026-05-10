"""
Sessions API Router for Seestar Observation History
=====================================================
REST endpoints for creating, ending, listing, and inspecting observation sessions.
Per-frame logging endpoint allows imaging/sequence views to record captures.
"""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query

from ..database import get_sessions_db
from ..models.sessions import (
    AddFrameRequest,
    EndSessionRequest,
    FrameRecord,
    SessionDatabase,
    SessionRecord,
    StartSessionRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sessions"])


@router.post("/", response_model=SessionRecord)
async def start_session(
    request: StartSessionRequest,
    db: SessionDatabase = Depends(get_sessions_db),
):
    """Start a new observation session.

    Creates a session row with started_at = now (UTC) and ended_at = NULL.
    Returns the full session record (verify-after-dispatch at DB layer).
    """
    try:
        session_id = db.create_session(
            target_name=request.target_name,
            target_ra=request.target_ra,
            target_dec=request.target_dec,
            site_location=request.site_location,
            conditions_snapshot=request.conditions_snapshot,
        )
        record = db.get_by_id(session_id)
        if record is None:
            raise HTTPException(
                status_code=500,
                detail=f"Session {session_id} not found after creation",
            )
        logger.info(f"Session {session_id} started for target {request.target_name}")
        return record

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{session_id}/end", response_model=SessionRecord)
async def end_session(
    session_id: int,
    request: EndSessionRequest,
    db: SessionDatabase = Depends(get_sessions_db),
):
    """End an active session — sets ended_at to now (UTC).

    Idempotent: calling on an already-ended session just overwrites ended_at.
    """
    try:
        existing = db.get_by_id(session_id)
        if existing is None:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

        db.end_session(session_id, conditions_snapshot=request.conditions_snapshot)
        record = db.get_by_id(session_id)
        logger.info(f"Session {session_id} ended")
        return record

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to end session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=List[SessionRecord])
async def list_sessions(
    limit: int = Query(50, ge=1, le=500, description="Max results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: SessionDatabase = Depends(get_sessions_db),
):
    """List sessions, newest-first."""
    try:
        records = db.list_sessions(limit=limit, offset=offset)
        logger.info(f"Sessions query returned {len(records)} sessions")
        return records

    except Exception as e:
        logger.error(f"Sessions list failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_id}", response_model=SessionRecord)
async def get_session(
    session_id: int,
    db: SessionDatabase = Depends(get_sessions_db),
):
    """Get session detail by ID."""
    try:
        record = db.get_by_id(session_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
        return record

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_id}/frames", response_model=List[FrameRecord])
async def get_session_frames(
    session_id: int,
    db: SessionDatabase = Depends(get_sessions_db),
):
    """Return all frames for a session, oldest-first."""
    try:
        existing = db.get_by_id(session_id)
        if existing is None:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

        frames = db.get_frames(session_id)
        return frames

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get frames for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{session_id}/frames", response_model=FrameRecord)
async def add_frame(
    session_id: int,
    request: AddFrameRequest,
    db: SessionDatabase = Depends(get_sessions_db),
):
    """Log a captured frame to an active session."""
    try:
        existing = db.get_by_id(session_id)
        if existing is None:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

        frame_id = db.add_frame(
            session_id=session_id,
            filename=request.filename,
            exposure_s=request.exposure_s,
            gain=request.gain,
            filter=request.filter,
            captured_at=request.captured_at,
            alpaca_metadata=request.alpaca_metadata,
        )
        frames = db.get_frames(session_id)
        record = next((f for f in frames if f.id == frame_id), None)
        if record is None:
            raise HTTPException(
                status_code=500,
                detail=f"Frame {frame_id} not found after creation",
            )
        return record

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add frame to session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
