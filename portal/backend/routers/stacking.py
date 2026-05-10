"""
Stacking API Router
===================
REST endpoints for the Siril session-oriented stacking pipeline.

Mirrors the autofocus router pattern exactly: prefix is defined in the router,
service is lazily instantiated on first request, and the long-running
run_stacking() pipeline is dispatched via FastAPI BackgroundTasks.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel, Field

from ..services.stacking_service import (
    StackingConfig,
    StackingResult,
    StackingService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stacking", tags=["stacking"])

# Global lazy-initialized service instance (matches autofocus pattern)
_stacking_service: Optional[StackingService] = None


def get_stacking_service(request: Request) -> StackingService:
    """Return the singleton StackingService, creating it on first use."""
    global _stacking_service
    if _stacking_service is None:
        _stacking_service = StackingService()
    return _stacking_service


# ============================================================================
# Pydantic models
# ============================================================================


class StackingConfigRequest(BaseModel):
    """Stacking session configuration."""
    target_name: str = Field("target", description="Target object name (used in output filenames)")
    exposure_time: float = Field(10.0, ge=0.1, le=300.0, description="Exposure per frame (metadata only)")
    gain: int = Field(80, ge=0, le=400, description="Sensor gain metadata")
    dark_path: Optional[str] = Field(None, description="Path to master dark frame")
    flat_path: Optional[str] = Field(None, description="Path to master flat frame")
    bias_path: Optional[str] = Field(None, description="Path to master bias frame")
    sigma_low: float = Field(3.0, ge=0.5, le=10.0, description="Lower sigma rejection threshold")
    sigma_high: float = Field(3.0, ge=0.5, le=10.0, description="Upper sigma rejection threshold")


class AddFrameRequest(BaseModel):
    """Request body for /add-frame."""
    path: str = Field(..., description="Filesystem path to a captured frame")


class StackingResultResponse(BaseModel):
    """Stacking pipeline result."""
    success: bool
    session_id: str
    frame_count: int
    output_fits: Optional[str] = None
    output_jpeg: Optional[str] = None
    error_message: Optional[str] = None
    duration_seconds: float = 0.0
    siril_output: Optional[str] = None


class StackingStatusResponse(BaseModel):
    """Current stacking service status."""
    running: bool
    session_id: Optional[str] = None
    frame_count: int = 0
    progress: float = 0.0
    latest_result: Optional[StackingResultResponse] = None


# ============================================================================
# Endpoints
# ============================================================================


def _result_to_response(result: StackingResult) -> StackingResultResponse:
    return StackingResultResponse(
        success=result.success,
        session_id=result.session_id,
        frame_count=result.frame_count,
        output_fits=result.output_fits,
        output_jpeg=result.output_jpeg,
        error_message=result.error_message,
        duration_seconds=result.duration_seconds,
        siril_output=result.siril_output,
    )


@router.post("/start", response_model=dict)
async def start_stacking(
    config: Optional[StackingConfigRequest] = None,
    request: Request = None,
):
    """Start a new stacking session.

    Returns 409 if a stacking run is already in progress. The session_id is
    generated server-side and returned so the frontend can correlate
    /add-frame and /process calls with the active session.
    """
    service = get_stacking_service(request)

    if service.is_running:
        raise HTTPException(status_code=409, detail="Stacking already running")

    if config is not None:
        service_config = StackingConfig(
            target_name=config.target_name,
            exposure_time=config.exposure_time,
            gain=config.gain,
            dark_path=config.dark_path,
            flat_path=config.flat_path,
            bias_path=config.bias_path,
            sigma_low=config.sigma_low,
            sigma_high=config.sigma_high,
        )
    else:
        service_config = None

    session_id = service.start_session(service_config)

    return {
        "status": "started",
        "session_id": session_id,
        "message": "Stacking session started — use /add-frame and /process",
        "config": (config.model_dump() if config else StackingConfigRequest().model_dump()),
    }


@router.get("/status", response_model=StackingStatusResponse)
async def get_stacking_status(request: Request):
    """Return current running state and the latest result."""
    service = get_stacking_service(request)

    latest = None
    if service.current_result is not None:
        latest = _result_to_response(service.current_result)

    return StackingStatusResponse(
        running=service.is_running,
        session_id=service.session_id,
        frame_count=service.frame_count,
        progress=service.progress,
        latest_result=latest,
    )


@router.post("/add-frame", response_model=dict)
async def add_frame(payload: AddFrameRequest, request: Request):
    """Append a captured-frame path to the active stacking session."""
    service = get_stacking_service(request)

    if not service.session_id:
        raise HTTPException(status_code=404, detail="No active stacking session — call /start first")

    appended = service.add_frame(payload.path)
    if not appended:
        raise HTTPException(status_code=400, detail="Failed to append frame")

    return {
        "status": "added",
        "session_id": service.session_id,
        "frame_count": service.frame_count,
    }


@router.post("/process", response_model=dict)
async def process_stack(
    background_tasks: BackgroundTasks = None,
    request: Request = None,
):
    """Dispatch the stacking pipeline as a background task.

    Returns 409 if already running, 400 if there are no frames or no session.
    """
    service = get_stacking_service(request)

    if service.is_running:
        raise HTTPException(status_code=409, detail="Stacking already running")
    if not service.session_id:
        raise HTTPException(status_code=400, detail="No active session — call /start first")
    if service.frame_count == 0:
        raise HTTPException(status_code=400, detail="No frames added — call /add-frame first")

    async def run_stacking_task():
        logger.info("Starting Siril stacking session")
        result = await service.run_stacking()
        if result.success:
            logger.info("Stacking complete: %s", result.output_jpeg or result.output_fits)
        else:
            logger.error("Stacking failed: %s", result.error_message)

    background_tasks.add_task(run_stacking_task)

    return {
        "status": "processing",
        "session_id": service.session_id,
        "frame_count": service.frame_count,
        "message": "Stacking dispatched in background — poll /status",
    }


@router.post("/abort", response_model=dict)
async def abort_stacking(request: Request):
    """Request abort of an in-progress stacking pipeline."""
    service = get_stacking_service(request)

    if not service.is_running:
        raise HTTPException(status_code=404, detail="No stacking running")

    service.abort()
    return {
        "status": "abort_requested",
        "message": "Stacking will abort at the next checkpoint",
    }


@router.get("/config", response_model=StackingConfigRequest)
async def get_default_config():
    """Return default stacking configuration."""
    cfg = StackingConfig()
    return StackingConfigRequest(
        target_name=cfg.target_name,
        exposure_time=cfg.exposure_time,
        gain=cfg.gain,
        dark_path=cfg.dark_path,
        flat_path=cfg.flat_path,
        bias_path=cfg.bias_path,
        sigma_low=cfg.sigma_low,
        sigma_high=cfg.sigma_high,
    )
