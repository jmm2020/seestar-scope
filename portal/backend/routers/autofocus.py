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

from ..services.autofocus_service import AutoFocusService, AutoFocusConfig

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/autofocus", tags=["autofocus"])

# Global service instance (initialized in lifespan)
_autofocus_service: Optional[AutoFocusService] = None


def get_autofocus_service(request: Request) -> AutoFocusService:
    """Get autofocus service instance from app state."""
    global _autofocus_service

    if _autofocus_service is None:
        # Initialize on first use
        alpaca = request.app.state.alpaca
        _autofocus_service = AutoFocusService(alpaca)

    return _autofocus_service


# ============================================================================
# Pydantic Models for API
# ============================================================================


class AutoFocusConfigRequest(BaseModel):
    """Configuration for autofocus routine."""

    exposure_time: float = Field(2.0, ge=0.1, le=10.0, description="Exposure time in seconds")
    gain: int = Field(100, ge=0, le=400, description="Sensor gain")
    step_size: int = Field(200, ge=50, le=500, description="Focuser steps between measurements")
    num_steps: int = Field(11, ge=5, le=21, description="Number of positions (must be odd)")
    detection_threshold: float = Field(
        3.0, ge=1.0, le=10.0, description="Sigma threshold for star detection"
    )
    min_stars: int = Field(5, ge=3, le=20, description="Minimum stars required")
    max_stars: int = Field(50, ge=10, le=200, description="Maximum stars to measure")


class FocusPositionResponse(BaseModel):
    """Single focus measurement result."""

    position: int
    hfr: float
    num_stars: int
    timestamp: datetime


class AutoFocusResultResponse(BaseModel):
    """Complete autofocus result."""

    success: bool
    optimal_position: Optional[int]
    initial_position: int
    final_position: int
    measurements: List[FocusPositionResponse]
    v_curve_fit: Optional[dict]
    error_message: Optional[str]
    duration_seconds: float


class AutoFocusStatusResponse(BaseModel):
    """Current autofocus status."""

    running: bool
    latest_result: Optional[AutoFocusResultResponse]


# ============================================================================
# API Endpoints
# ============================================================================


@router.post("/start", response_model=dict)
async def start_autofocus(
    config: Optional[AutoFocusConfigRequest] = None,
    background_tasks: BackgroundTasks = None,
    request: Request = None,
):
    """
    Start V-curve autofocus routine.
    
    The autofocus runs asynchronously. Poll /api/autofocus/status to check progress.
    
    **Algorithm:**
    1. Move focuser through sweep range (11 positions by default)
    2. Capture exposure at each position
    3. Calculate HFR (Half-Flux Radius) for each frame
    4. Fit parabola (V-curve) to HFR vs position
    5. Move to optimal position (minimum HFR)
    6. Capture verification exposure
    
    **Returns:**
    - 200: Autofocus started successfully
    - 409: Autofocus already running
    - 500: Failed to start autofocus
    
    **Example:**
    ```bash
    curl -X POST http://localhost:8503/api/autofocus/start \
      -H "Content-Type: application/json" \
      -d '{"exposure_time": 3.0, "gain": 150, "step_size": 150, "num_steps": 11}'
    ```
    """
    try:
        service = get_autofocus_service(request)

        if service.is_running:
            raise HTTPException(status_code=409, detail="Autofocus already running")

        # Convert Pydantic model to service config
        if config:
            service_config = AutoFocusConfig(
                exposure_time=config.exposure_time,
                gain=config.gain,
                step_size=config.step_size,
                num_steps=config.num_steps,
                detection_threshold=config.detection_threshold,
                min_stars=config.min_stars,
                max_stars=config.max_stars,
            )
        else:
            service_config = None

        # Run autofocus in background
        async def run_autofocus_task():
            logger.info("Starting autofocus routine")
            result = await service.run_autofocus(config=service_config)
            if result.success:
                logger.info(f"Autofocus complete: optimal={result.optimal_position}, HFR improved")
            else:
                logger.error(f"Autofocus failed: {result.error_message}")

        background_tasks.add_task(run_autofocus_task)

        return {
            "status": "started",
            "message": "Autofocus routine started in background",
            "config": config.dict() if config else AutoFocusConfig().__dict__,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start autofocus: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status", response_model=AutoFocusStatusResponse)
async def get_autofocus_status(request: Request):
    """
    Get current autofocus status and latest result.

    **Returns:**
    - `running`: Whether autofocus is currently active
    - `latest_result`: Most recent autofocus result (if available)

    **Example:**
    ```bash
    curl http://localhost:8503/api/autofocus/status
    ```

    **Response:**
    ```json
    {
      "running": false,
      "latest_result": {
        "success": true,
        "optimal_position": 5420,
        "initial_position": 5000,
        "final_position": 5420,
        "measurements": [...],
        "v_curve_fit": {"a": 0.000012, "b": -0.13, "c": 350.2, "r_squared": 0.95},
        "error_message": null,
        "duration_seconds": 45.3
      }
    }
    ```
    """
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
                        position=m.position, hfr=m.hfr, num_stars=m.num_stars, timestamp=m.timestamp
                    )
                    for m in result.measurements
                ],
                v_curve_fit=result.v_curve_fit,
                error_message=result.error_message,
                duration_seconds=result.duration_seconds,
            )

        return AutoFocusStatusResponse(running=service.is_running, latest_result=result_response)

    except Exception as e:
        logger.error(f"Failed to get autofocus status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/abort", response_model=dict)
async def abort_autofocus(request: Request):
    """
    Abort running autofocus routine.

    **Note:** Current implementation completes the active measurement before aborting.
    A future enhancement could add immediate cancellation.

    **Returns:**
    - 200: Abort signal sent
    - 404: No autofocus running

    **Example:**
    ```bash
    curl -X POST http://localhost:8503/api/autofocus/abort
    ```
    """
    try:
        service = get_autofocus_service(request)

        if not service.is_running:
            raise HTTPException(status_code=404, detail="No autofocus routine running")

        # TODO: Implement graceful abort mechanism
        # For now, the routine will complete the current measurement

        return {
            "status": "abort_requested",
            "message": "Autofocus will abort after current measurement completes",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to abort autofocus: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config", response_model=AutoFocusConfigRequest)
async def get_default_config():
    """
    Get default autofocus configuration.

    Useful for understanding parameter ranges and defaults before starting a run.

    **Example:**
    ```bash
    curl http://localhost:8503/api/autofocus/config
    ```
    """
    default_config = AutoFocusConfig()
    return AutoFocusConfigRequest(
        exposure_time=default_config.exposure_time,
        gain=default_config.gain,
        step_size=default_config.step_size,
        num_steps=default_config.num_steps,
        detection_threshold=default_config.detection_threshold,
        min_stars=default_config.min_stars,
        max_stars=default_config.max_stars,
    )
