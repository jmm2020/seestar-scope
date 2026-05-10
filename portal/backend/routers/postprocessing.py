"""
Postprocessing API Router
=========================
REST endpoints for the image enhancement pipeline:
  GET    /api/postprocessing/health
  POST   /api/postprocessing/apply
  GET    /api/postprocessing/jobs/{job_id}
  GET    /api/postprocessing/calibration
  POST   /api/postprocessing/calibration/{frame_type}
  DELETE /api/postprocessing/calibration/{frame_type}
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    HTTPException,
    UploadFile,
)
from pydantic import BaseModel, Field

from backend.config import settings
from backend.services.postprocessing_service import (
    PostprocessingResult,
    PostprocessingService,
    VALID_FRAME_TYPES,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/postprocessing", tags=["postprocessing"])

# Singleton service instance (lazy-init via getter)
_service: Optional[PostprocessingService] = None


def get_service() -> PostprocessingService:
    global _service
    if _service is None:
        _service = PostprocessingService(settings.data_dir)
    return _service


# In-memory job store. Survives until backend restart.
processing_jobs: Dict[str, PostprocessingResult] = {}


# --------------------------------------------------------------------------
# Pydantic models
# --------------------------------------------------------------------------

class PostprocessingRequest(BaseModel):
    """Pipeline parameters for a single apply call."""
    image_path: str = Field(..., description="Path to source image (PNG or FITS)")
    stretch: str = Field("stf", description="Stretch algorithm key")
    stretch_params: Dict[str, Any] = Field(default_factory=dict)
    background_sub: bool = False
    hot_pixel: bool = False
    hot_pixel_method: str = Field("median", description="'median' or 'lacosmic'")
    denoise: bool = False
    denoise_strength: int = Field(7, ge=3, le=21)
    sharpen: bool = False
    sharpen_amount: float = Field(1.0, ge=0.5, le=5.0)
    sharpen_radius: float = Field(1.5, ge=0.5, le=5.0)
    color_balance: bool = False
    apply_calibration: bool = False
    output_dir: Optional[str] = None


class PostprocessingJobResponse(BaseModel):
    """Status snapshot of a processing job."""
    job_id: str
    status: str  # "pending" | "running" | "completed" | "failed"
    success: Optional[bool] = None
    output_path: Optional[str] = None
    error_message: Optional[str] = None
    stats: Optional[Dict[str, Any]] = None
    duration_seconds: Optional[float] = None
    completed_at: Optional[datetime] = None


class CalibrationFrameStatus(BaseModel):
    path: Optional[str] = None
    exists: bool = False


class CalibrationInfoResponse(BaseModel):
    dark: CalibrationFrameStatus
    flat: CalibrationFrameStatus
    bias: CalibrationFrameStatus


# --------------------------------------------------------------------------
# Background task helpers
# --------------------------------------------------------------------------

def _request_to_params(req: PostprocessingRequest) -> Dict[str, Any]:
    return {
        "stretch": req.stretch,
        "stretch_params": req.stretch_params,
        "background_sub": req.background_sub,
        "hot_pixel": req.hot_pixel,
        "hot_pixel_method": req.hot_pixel_method,
        "denoise": req.denoise,
        "denoise_strength": req.denoise_strength,
        "sharpen": req.sharpen,
        "sharpen_amount": req.sharpen_amount,
        "sharpen_radius": req.sharpen_radius,
        "color_balance": req.color_balance,
        "apply_calibration": req.apply_calibration,
        "output_dir": req.output_dir,
    }


async def _run_pipeline_task(job_id: str, image_path: str,
                             params: Dict[str, Any]) -> None:
    """Background runner. Stores PostprocessingResult in processing_jobs."""
    service = get_service()
    processing_jobs[job_id] = PostprocessingResult(
        success=False, error_message=None, job_id=job_id,
    )
    try:
        result = await asyncio.to_thread(
            service.apply_pipeline, image_path, params, job_id,
        )
    except Exception as exc:  # safety net
        logger.error("Postprocessing background task failed: %s", exc, exc_info=True)
        result = PostprocessingResult(
            success=False,
            error_message=str(exc),
            job_id=job_id,
            completed_at=datetime.utcnow(),
        )
    processing_jobs[job_id] = result


def _result_to_response(job_id: str,
                        result: Optional[PostprocessingResult]) -> PostprocessingJobResponse:
    if result is None:
        return PostprocessingJobResponse(job_id=job_id, status="unknown")
    if result.completed_at is None:
        status = "running"
    elif result.success:
        status = "completed"
    else:
        status = "failed"
    return PostprocessingJobResponse(
        job_id=job_id,
        status=status,
        success=result.success,
        output_path=result.output_path,
        error_message=result.error_message,
        stats=result.stats,
        duration_seconds=result.duration_seconds,
        completed_at=result.completed_at,
    )


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------

@router.get("/health")
async def health_check():
    """Report health of the postprocessing service and its deps."""
    return get_service().health_check()


@router.post("/apply")
async def apply_postprocessing(
    req: PostprocessingRequest,
    background_tasks: BackgroundTasks,
):
    """Kick off a pipeline run; returns a job id for polling."""
    if not Path(req.image_path).exists():
        raise HTTPException(
            status_code=404,
            detail=f"image_path not found: {req.image_path}",
        )

    job_id = f"pp_{uuid.uuid4().hex[:8]}"
    params = _request_to_params(req)
    processing_jobs[job_id] = PostprocessingResult(
        success=False, error_message=None, job_id=job_id,
    )
    background_tasks.add_task(_run_pipeline_task, job_id, req.image_path, params)
    return {"job_id": job_id, "status": "started"}


@router.get("/jobs/{job_id}", response_model=PostprocessingJobResponse)
async def get_job_status(job_id: str):
    if job_id not in processing_jobs:
        raise HTTPException(status_code=404, detail=f"Unknown job_id: {job_id}")
    return _result_to_response(job_id, processing_jobs[job_id])


@router.get("/calibration", response_model=CalibrationInfoResponse)
async def get_calibration_info():
    info = get_service().get_calibration_info()
    return CalibrationInfoResponse(
        dark=CalibrationFrameStatus(**info["dark"]),
        flat=CalibrationFrameStatus(**info["flat"]),
        bias=CalibrationFrameStatus(**info["bias"]),
    )


@router.post("/calibration/{frame_type}")
async def upload_calibration_frame(frame_type: str, file: UploadFile = File(...)):
    if frame_type not in VALID_FRAME_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"frame_type must be one of {VALID_FRAME_TYPES}",
        )

    suffix = Path(file.filename or "upload").suffix or ".png"
    tmp_dir = Path(tempfile.mkdtemp(prefix="cal_upload_"))
    tmp_path = tmp_dir / f"upload{suffix}"
    try:
        with tmp_path.open("wb") as out:
            shutil.copyfileobj(file.file, out)
        ok = get_service().store_calibration_frame(frame_type, str(tmp_path))
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
            tmp_dir.rmdir()
        except OSError:
            pass

    if not ok:
        raise HTTPException(status_code=500, detail="Failed to store calibration frame")
    return {"status": "stored", "frame_type": frame_type}


@router.delete("/calibration/{frame_type}")
async def delete_calibration_frame(frame_type: str):
    if frame_type not in VALID_FRAME_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"frame_type must be one of {VALID_FRAME_TYPES}",
        )
    if not get_service().delete_calibration_frame(frame_type):
        raise HTTPException(
            status_code=404,
            detail=f"No master {frame_type} frame to delete",
        )
    return {"status": "deleted", "frame_type": frame_type}
