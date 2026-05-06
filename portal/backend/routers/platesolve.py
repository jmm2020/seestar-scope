"""
Plate Solving Router

REST API endpoints for astrometric plate solving via ASTAP.
"""

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pathlib import Path
from pydantic import BaseModel, Field
from typing import Optional, List
import shutil

from backend.services.platesolve_service import (
    ASTAPService,
    PlatesolvingResult,
    SolveStatus,
    SolveMode,
    WCSSolution,
)
from backend.config import settings

router = APIRouter()

# Initialize ASTAP service
astap_service = ASTAPService(
    astap_bin="astap",
    data_root=str(settings.data_dir),
    timeout_sec=120,
)


# --- Request/Response Models ---

class SolveRequest(BaseModel):
    """Plate solve request"""
    mode: str = Field(..., description="Solving mode: 'blind' or 'hint'")
    image_path: str = Field(..., description="Path to FITS/image file")
    expected_ra_hours: Optional[float] = Field(None, description="Expected RA in hours (0-24)")
    expected_dec_degrees: Optional[float] = Field(None, description="Expected Dec in degrees (-90 to +90)")
    search_radius_deg: Optional[float] = Field(5.0, description="Search radius in degrees (hint mode)")
    fov_deg: Optional[float] = Field(None, description="Field of view estimate in degrees")
    downsample: Optional[int] = Field(0, description="Downsample factor (0=auto)")


class WCSSolutionResponse(BaseModel):
    ra_hours: float
    dec_degrees: float
    rotation_deg: float
    pixel_scale: float
    fov_width: float
    fov_height: float
    num_stars: int
    residual_arcsec: float


class SolveResponse(BaseModel):
    session_id: str
    status: str
    mode: str
    image_path: str
    solution: Optional[WCSSolutionResponse] = None
    expected_ra_hours: Optional[float] = None
    expected_dec_degrees: Optional[float] = None
    offset_arcsec: Optional[float] = None
    offset_ra_arcsec: Optional[float] = None
    offset_dec_arcsec: Optional[float] = None
    solve_time_sec: Optional[float] = None
    error_message: Optional[str] = None
    timestamp: str


class SessionListResponse(BaseModel):
    sessions: List[str]
    count: int


def _result_to_response(result: PlatesolvingResult) -> SolveResponse:
    solution_resp = None
    if result.solution:
        solution_resp = WCSSolutionResponse(
            ra_hours=result.solution.ra_hours,
            dec_degrees=result.solution.dec_degrees,
            rotation_deg=result.solution.rotation_deg,
            pixel_scale=result.solution.pixel_scale,
            fov_width=result.solution.fov_width,
            fov_height=result.solution.fov_height,
            num_stars=result.solution.num_stars,
            residual_arcsec=result.solution.residual_arcsec,
        )
    return SolveResponse(
        session_id=result.session_id,
        status=result.status.value,
        mode=result.mode.value,
        image_path=result.image_path,
        solution=solution_resp,
        expected_ra_hours=result.expected_ra_hours,
        expected_dec_degrees=result.expected_dec_degrees,
        offset_arcsec=result.offset_arcsec,
        offset_ra_arcsec=result.offset_ra_arcsec,
        offset_dec_arcsec=result.offset_dec_arcsec,
        solve_time_sec=result.solve_time_sec,
        error_message=result.error_message,
        timestamp=result.timestamp.isoformat(),
    )


# --- Endpoints ---

@router.post("/solve", response_model=SolveResponse)
async def solve_image(request: SolveRequest):
    """Plate solve an image (blind or hint mode)."""
    image_path = Path(request.image_path)
    if not image_path.exists():
        raise HTTPException(status_code=404, detail=f"Image not found: {request.image_path}")

    if request.mode not in ["blind", "hint"]:
        raise HTTPException(status_code=400, detail=f"Invalid mode: {request.mode}")

    if request.mode == "hint":
        if request.expected_ra_hours is None or request.expected_dec_degrees is None:
            raise HTTPException(status_code=400, detail="Hint mode requires expected_ra_hours and expected_dec_degrees")

    try:
        if request.mode == "blind":
            result = await astap_service.solve_blind(
                image_path=image_path,
                fov_deg=request.fov_deg,
                downsample=request.downsample or 0,
            )
        else:
            result = await astap_service.solve_hint(
                image_path=image_path,
                ra_hours=request.expected_ra_hours,
                dec_degrees=request.expected_dec_degrees,
                search_radius_deg=request.search_radius_deg or 5.0,
                fov_deg=request.fov_deg,
                downsample=request.downsample or 0,
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Plate solve error: {str(e)}")

    return _result_to_response(result)


@router.get("/result/{session_id}", response_model=SolveResponse)
async def get_solve_result(session_id: str):
    """Get plate solving result by session ID."""
    result = astap_service.get_result(session_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    return _result_to_response(result)


@router.get("/sessions", response_model=SessionListResponse)
async def list_solve_sessions():
    """List all plate solving session IDs."""
    sessions = astap_service.list_sessions()
    return SessionListResponse(sessions=sessions, count=len(sessions))


@router.post("/solve/upload", response_model=SolveResponse)
async def solve_uploaded_image(
    file: UploadFile = File(...),
    mode: str = Form(...),
    expected_ra_hours: Optional[float] = Form(None),
    expected_dec_degrees: Optional[float] = Form(None),
    search_radius_deg: Optional[float] = Form(5.0),
    fov_deg: Optional[float] = Form(None),
    downsample: Optional[int] = Form(0),
):
    """Upload an image and plate solve it."""
    if mode not in ["blind", "hint"]:
        raise HTTPException(status_code=400, detail=f"Invalid mode: {mode}")
    if mode == "hint" and (expected_ra_hours is None or expected_dec_degrees is None):
        raise HTTPException(status_code=400, detail="Hint mode requires RA/Dec")

    platesolve_dir = settings.data_dir / "platesolve"
    platesolve_dir.mkdir(parents=True, exist_ok=True)
    file_path = platesolve_dir / file.filename
    with file_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    request = SolveRequest(
        mode=mode, image_path=str(file_path),
        expected_ra_hours=expected_ra_hours,
        expected_dec_degrees=expected_dec_degrees,
        search_radius_deg=search_radius_deg,
        fov_deg=fov_deg, downsample=downsample,
    )
    return await solve_image(request)
