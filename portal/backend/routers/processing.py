"""
Processing Router for Seestar FastAPI Backend

Exposes Siril processing pipeline via REST API.
Handles image stacking, registration, and enhancement for multi-frame sequences.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from pathlib import Path
import asyncio
import json
from datetime import datetime
import httpx

from backend.services.siril_service import SirilService, ProcessingStatus, ProcessingResult
from backend.config import settings

router = APIRouter()

# Initialize Siril service
siril_service = SirilService(
    data_root=str(settings.data_dir),
    gallery_dir=str(settings.gallery_dir)
)


# --- Request/Response Models ---

class ProcessSessionRequest(BaseModel):
    """Request to process a session of FITS files"""
    session_id: str = Field(..., description="Unique session identifier")
    fits_files: List[str] = Field(..., description="List of FITS file paths")
    target_name: str = Field(default="target", description="Target object name")
    metadata: Optional[Dict] = Field(default=None, description="Optional metadata (exposure, gain, etc.)")


class ProcessSessionResponse(BaseModel):
    """Response from processing session"""
    success: bool
    status: str
    session_id: str
    output_fits: Optional[str] = None
    output_jpeg: Optional[str] = None
    error_message: Optional[str] = None
    stats: Optional[Dict] = None


class ProcessingStatusResponse(BaseModel):
    """Status of a processing session"""
    session_id: str
    status: str
    progress: Optional[float] = None
    output_files: Optional[List[str]] = None
    error_message: Optional[str] = None


# --- Background Task Store ---
processing_tasks: Dict[str, ProcessingResult] = {}


# --- API Endpoints ---

@router.post("/sessions", response_model=ProcessSessionResponse)
async def process_session(
    request: ProcessSessionRequest,
    background_tasks: BackgroundTasks
):
    """Start Siril processing for a session of FITS files."""
    try:
        fits_paths = [Path(f) for f in request.fits_files]
        missing = [str(f) for f in fits_paths if not f.exists()]

        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"FITS files not found: {missing}"
            )

        if request.session_id in processing_tasks:
            existing = processing_tasks[request.session_id]
            if existing.status in [ProcessingStatus.PENDING, ProcessingStatus.CONVERTING,
                                   ProcessingStatus.REGISTERING, ProcessingStatus.STACKING]:
                raise HTTPException(
                    status_code=409,
                    detail=f"Session {request.session_id} is already processing"
                )

        background_tasks.add_task(
            _process_session_task,
            session_id=request.session_id,
            fits_files=fits_paths,
            target_name=request.target_name,
            metadata=request.metadata
        )

        return ProcessSessionResponse(
            success=True,
            status="queued",
            session_id=request.session_id
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}/status", response_model=ProcessingStatusResponse)
async def get_session_status(session_id: str):
    """Get processing status for a session."""
    if session_id in processing_tasks:
        result = processing_tasks[session_id]
        return ProcessingStatusResponse(
            session_id=session_id,
            status=result.status.value,
            output_files=[
                str(result.output_path) if result.output_path else None,
                str(result.jpeg_path) if result.jpeg_path else None
            ],
            error_message=result.error_message
        )

    status = siril_service.get_processing_status(session_id)
    return ProcessingStatusResponse(
        session_id=session_id,
        status=status.get("status", "not_found"),
        output_files=status.get("output_files")
    )


@router.get("/sessions/{session_id}/stream")
async def stream_session_status(session_id: str):
    """Server-Sent Events (SSE) stream for real-time processing updates."""
    async def event_generator():
        while True:
            if session_id in processing_tasks:
                result = processing_tasks[session_id]
                event_data = {
                    "session_id": session_id,
                    "status": result.status.value,
                    "timestamp": datetime.now().isoformat()
                }

                if result.status == ProcessingStatus.COMPLETE:
                    event_data["output_fits"] = str(result.output_path) if result.output_path else None
                    event_data["output_jpeg"] = str(result.jpeg_path) if result.jpeg_path else None
                    event_data["stats"] = result.stats
                    yield f"data: {json.dumps(event_data)}\n\n"
                    break
                elif result.status == ProcessingStatus.FAILED:
                    event_data["error"] = result.error_message
                    yield f"data: {json.dumps(event_data)}\n\n"
                    break
                else:
                    yield f"data: {json.dumps(event_data)}\n\n"
            else:
                yield f"data: {json.dumps({'status': 'waiting', 'session_id': session_id})}\n\n"

            await asyncio.sleep(2)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )


@router.delete("/sessions/{session_id}")
async def cancel_session(session_id: str):
    """Cancel a processing session (if still running)."""
    if session_id not in processing_tasks:
        raise HTTPException(status_code=404, detail="Session not found")

    result = processing_tasks[session_id]
    if result.status in [ProcessingStatus.COMPLETE, ProcessingStatus.FAILED]:
        raise HTTPException(
            status_code=400,
            detail=f"Session already {result.status.value}"
        )

    processing_tasks[session_id] = ProcessingResult(
        success=False,
        status=ProcessingStatus.FAILED,
        error_message="Cancelled by user"
    )
    return {"message": f"Session {session_id} cancelled"}


# --- AUTO-TRIGGER HELPER (for Streamlit integration) ---

def auto_trigger_processing(
    session_id: str,
    fits_files: List[Path],
    target_name: str,
    metadata: Optional[Dict] = None,
    backend_url: str = "http://localhost:8503"
) -> Dict:
    """Auto-trigger Siril processing after a capture sequence completes."""
    try:
        payload = {
            "session_id": session_id,
            "fits_files": [str(f) for f in fits_files],
            "target_name": target_name,
            "metadata": metadata or {}
        }
        response = httpx.post(
            f"{backend_url}/api/processing/sessions",
            json=payload,
            timeout=10.0
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"success": False, "error": str(e)}


# --- Background Task ---

async def _process_session_task(
    session_id: str,
    fits_files: List[Path],
    target_name: str,
    metadata: Optional[Dict]
):
    """Background task for Siril processing."""
    processing_tasks[session_id] = ProcessingResult(
        success=False,
        status=ProcessingStatus.PENDING
    )

    result = await asyncio.to_thread(
        siril_service.process_session,
        session_id=session_id,
        fits_files=fits_files,
        target_name=target_name,
        metadata=metadata
    )

    processing_tasks[session_id] = result


# --- Health Check ---

@router.get("/health")
async def health_check():
    """Check if Siril CLI is available."""
    try:
        import subprocess
        result = subprocess.run(
            [siril_service.siril_bin, "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return {
                "status": "healthy",
                "siril_version": result.stdout.strip(),
                "data_root": str(siril_service.data_root),
                "gallery_dir": str(siril_service.gallery_dir)
            }
        else:
            return {"status": "degraded", "error": "Siril CLI not responding correctly"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
