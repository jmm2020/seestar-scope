"""
Auto-Focus API Router
=====================
REST endpoints for V-curve autofocus with HFR metric.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Request
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import logging

from backend.services.autofocus_service import (
    AutoFocusService,
    AutoFocusConfig,
    AutoFocusResult,
    FocusPosition
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Global service instance (initialized on first use)
_autofocus_service: Optional[AutoFocusService] = None


def get_autofocus_service(request: Request) -> AutoFocusService:
    """Get autofocus service instance from app state."""
    global _autofocus_service
    if _autofocus_service is None:
        alpaca = request.app.state.alpaca
        _autofocus_service = AutoFocusService(alpaca)
    return _autofocus_service


# --- Pydantic Models ---

class AutoFocusConfigRequest(BaseModel):
    """Configuration for autofocus routine."""
    exposure_time: float = Field(2.0, ge=0.1, le=10.0, description="Exposure time in seconds")
    gain: int = Field(100, ge=0, le=400, description="Sensor gain")
    step_size: int = Field(200, ge=50, le=500, description="Focuser steps between measurements")
    num_steps: int = Field(11, ge=5, le=21, description="Number of positions")
    detection_threshold: float = Field(3.0, ge=1.0, le=10.0, description="Sigma threshold for star detection")
    min_stars: int = Field(5, ge=3, le=20, description="Minimum stars required")
    max_stars: int = Field(50, ge=10, le=200, description="Maximum stars to measure")


class FocusPositionResponse(BaseModel):
    position: int
    hfr: float
    num_stars: int
    timestamp: datetime


class AutoFocusResultResponse(BaseModel):
    success: bool
    optimal_position: Optional[int]
    initial_position: int
    final_position: int
    measurements: List[FocusPositionResponse]
    v_curve_fit: Optional[dict]
    error_message: Optional[str]
    duration_seconds: float


class AutoFocusStatusResponse(BaseModel):
    running: bool
    latest_result: Optional[AutoFocusResultResponse]


# --- Endpoints ---

@router.post("/start")
async def start_autofocus(
    config: Optional[AutoFocusConfigRequest] = None,
    background_tasks: BackgroundTasks = None,
    request: Request = None
):
    """Start V-curve autofocus routine (runs in background)."""
    try:
        service = get_autofocus_service(request)
        if service.is_running:
            raise HTTPException(status_code=409, detail="Autofocus already running")

        service_config = None
        if config:
            service_config = AutoFocusConfig(
                exposure_time=config.exposure_time,
                gain=config.gain,
                step_size=config.step_size,
                num_steps=config.num_steps,
                detection_threshold=config.detection_threshold,
                min_stars=config.min_stars,
                max_stars=config.max_stars
            )

        async def run_autofocus_task():
            result = await service.run_autofocus(config=service_config)
            if result.success:
                logger.info(f"Autofocus complete: optimal={result.optimal_position}")
            else:
                logger.error(f"Autofocus failed: {result.error_message}")

        background_tasks.add_task(run_autofocus_task)
        return {
            "status": "started",
            "message": "Autofocus routine started in background",
            "config": config.dict() if config else AutoFocusConfig().__dict__
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status", response_model=AutoFocusStatusResponse)
async def get_autofocus_status(request: Request):
    """Get current autofocus status and latest result."""
    try:
        service = get_autofocus_service(request)
        result_response = None
        if service.current_result:
            result = service.current_result
            result_response = AutoFocusResultResponse(
                success=result.success,
                optimal_position=result.optimal_position,
                initial_position=result.initial_position,
                final_position=result.final_position,
                measurements=[
                    FocusPositionResponse(
                        position=m.position, hfr=m.hfr,
                        num_stars=m.num_stars, timestamp=m.timestamp
                    ) for m in result.measurements
                ],
                v_curve_fit=result.v_curve_fit,
                error_message=result.error_message,
                duration_seconds=result.duration_seconds
            )
        return AutoFocusStatusResponse(running=service.is_running, latest_result=result_response)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/abort")
async def abort_autofocus(request: Request):
    """Abort running autofocus routine."""
    try:
        service = get_autofocus_service(request)
        if not service.is_running:
            raise HTTPException(status_code=404, detail="No autofocus routine running")
        return {"status": "abort_requested", "message": "Autofocus will abort after current measurement"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config", response_model=AutoFocusConfigRequest)
async def get_default_config():
    """Get default autofocus configuration."""
    c = AutoFocusConfig()
    return AutoFocusConfigRequest(
        exposure_time=c.exposure_time, gain=c.gain,
        step_size=c.step_size, num_steps=c.num_steps,
        detection_threshold=c.detection_threshold,
        min_stars=c.min_stars, max_stars=c.max_stars
    )
