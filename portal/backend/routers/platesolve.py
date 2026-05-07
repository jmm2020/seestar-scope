"""
Plate Solving Router

REST API endpoints for astrometric plate solving via ASTAP.
Verifies telescope pointing accuracy after slews.

Author: Lore (Phase 3)
"""

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pathlib import Path
from pydantic import BaseModel, Field
from typing import Optional, List
import shutil

from ..services.platesolve_service import (
    ASTAPService,
    PlatesolvingResult,
)


router = APIRouter(prefix="/api/platesolve", tags=["platesolve"])

# Initialize ASTAP service (singleton)
astap_service = ASTAPService(
    astap_bin="astap",
    data_root="/data/seestar",
    timeout_sec=120,
)


# ============================================================================
# Request/Response Models
# ============================================================================

class SolveRequest(BaseModel):
    """Plate solve request with mode selection"""
    mode: str = Field(..., description="Solving mode: 'blind' or 'hint'")
    image_path: str = Field(..., description="Path to FITS/image file")
    
    # Hint mode parameters
    expected_ra_hours: Optional[float] = Field(None, description="Expected RA in hours (0-24)")
    expected_dec_degrees: Optional[float] = Field(None, description="Expected Dec in degrees (-90 to +90)")
    search_radius_deg: Optional[float] = Field(5.0, description="Search radius in degrees (hint mode)")
    
    # Optional parameters
    fov_deg: Optional[float] = Field(None, description="Field of view estimate in degrees")
    downsample: Optional[int] = Field(0, description="Downsample factor (0=auto, 1=none, 2=2x2, etc.)")

    class Config:
        json_schema_extra = {
            "example": {
                "mode": "hint",
                "image_path": "/data/seestar/images/m31_001.fits",
                "expected_ra_hours": 0.712,
                "expected_dec_degrees": 41.269,
                "search_radius_deg": 5.0,
                "fov_deg": 1.2,
            }
        }


class WCSSolutionResponse(BaseModel):
    """WCS solution response model"""
    ra_hours: float = Field(..., description="Right Ascension in decimal hours")
    dec_degrees: float = Field(..., description="Declination in decimal degrees")
    rotation_deg: float = Field(..., description="Field rotation in degrees")
    pixel_scale: float = Field(..., description="Pixel scale in arcsec/pixel")
    fov_width: float = Field(..., description="Field of view width in degrees")
    fov_height: float = Field(..., description="Field of view height in degrees")
    num_stars: int = Field(..., description="Number of stars in solution")
    residual_arcsec: float = Field(..., description="RMS residual in arcseconds")


class SolveResponse(BaseModel):
    """Plate solving result response"""
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
    """List of plate solve sessions"""
    sessions: List[str]
    count: int


# ============================================================================
# Helper Functions
# ============================================================================

def _result_to_response(result: PlatesolvingResult) -> SolveResponse:
    """Convert PlatesolvingResult to API response model"""
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


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/solve", response_model=SolveResponse)
async def solve_image(request: SolveRequest):
    """
    Perform plate solving on an image.
    
    Supports two modes:
    - **blind**: No position hint, full-sky search (slower)
    - **hint**: Use expected position to constrain search (faster)
    
    For hint mode, provide expected_ra_hours and expected_dec_degrees.
    Result will include offset from expected position.
    
    **Example (hint mode):**
    ```json
    {
      "mode": "hint",
      "image_path": "/data/seestar/images/m31_001.fits",
      "expected_ra_hours": 0.712,
      "expected_dec_degrees": 41.269,
      "search_radius_deg": 5.0,
      "fov_deg": 1.2
    }
    ```
    
    **Example (blind mode):**
    ```json
    {
      "mode": "blind",
      "image_path": "/data/seestar/images/unknown.fits",
      "fov_deg": 1.2
    }
    ```
    """
    # Validate image path
    image_path = Path(request.image_path)
    if not image_path.exists():
        raise HTTPException(status_code=404, detail=f"Image not found: {request.image_path}")
    
    # Validate mode
    if request.mode not in ["blind", "hint"]:
        raise HTTPException(status_code=400, detail=f"Invalid mode: {request.mode}. Must be 'blind' or 'hint'")
    
    # Validate hint mode parameters
    if request.mode == "hint":
        if request.expected_ra_hours is None or request.expected_dec_degrees is None:
            raise HTTPException(
                status_code=400,
                detail="Hint mode requires expected_ra_hours and expected_dec_degrees"
            )
        if not (0 <= request.expected_ra_hours <= 24):
            raise HTTPException(status_code=400, detail="expected_ra_hours must be 0-24")
        if not (-90 <= request.expected_dec_degrees <= 90):
            raise HTTPException(status_code=400, detail="expected_dec_degrees must be -90 to +90")
    
    # Execute plate solve
    try:
        if request.mode == "blind":
            result = await astap_service.solve_blind(
                image_path=image_path,
                fov_deg=request.fov_deg,
                downsample=request.downsample or 0,
            )
        else:  # hint mode
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
    """
    Get plate solving result by session ID.
    
    Returns the complete result including WCS solution and offset calculations.
    Status can be: pending, running, success, failed, timeout.
    """
    result = astap_service.get_result(session_id)
    
    if result is None:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    
    return _result_to_response(result)


@router.get("/sessions", response_model=SessionListResponse)
async def list_solve_sessions():
    """
    List all plate solving session IDs.
    
    Useful for tracking active and completed solves.
    """
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
    """
    Upload an image and perform plate solving.
    
    Convenience endpoint for solving images not yet on disk.
    Saves uploaded file to /data/seestar/platesolve/ before solving.
    
    **Form Parameters:**
    - file: Image file (FITS, PNG, JPG)
    - mode: 'blind' or 'hint'
    - expected_ra_hours: Expected RA in hours (hint mode)
    - expected_dec_degrees: Expected Dec in degrees (hint mode)
    - search_radius_deg: Search radius in degrees (hint mode, default 5.0)
    - fov_deg: Field of view estimate (optional)
    - downsample: Downsample factor (optional, 0=auto)
    """
    # Validate mode
    if mode not in ["blind", "hint"]:
        raise HTTPException(status_code=400, detail=f"Invalid mode: {mode}")
    
    # Validate hint mode parameters
    if mode == "hint":
        if expected_ra_hours is None or expected_dec_degrees is None:
            raise HTTPException(
                status_code=400,
                detail="Hint mode requires expected_ra_hours and expected_dec_degrees"
            )
    
    # Save uploaded file
    platesolve_dir = Path("/data/seestar/platesolve")
    platesolve_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = platesolve_dir / file.filename
    with file_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # Create solve request
    request = SolveRequest(
        mode=mode,
        image_path=str(file_path),
        expected_ra_hours=expected_ra_hours,
        expected_dec_degrees=expected_dec_degrees,
        search_radius_deg=search_radius_deg,
        fov_deg=fov_deg,
        downsample=downsample,
    )
    
    # Execute solve via main endpoint logic
    return await solve_image(request)
