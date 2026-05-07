"""Telescope control REST API

Provides RESTful endpoints for controlling the Seestar S50 via ALPACA protocol.
Mirrors the functionality available in the Streamlit UI but as a programmable API.
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Optional

router = APIRouter()

# --- Request/Response Models ---

class SlewRequest(BaseModel):
    """Request to slew telescope to coordinates"""
    ra_hours: float = Field(..., description="Right Ascension in hours (0-24)")
    dec_degrees: float = Field(..., description="Declination in degrees (-90 to +90)")

class TrackingRequest(BaseModel):
    """Request to enable/disable tracking"""
    enabled: bool = Field(..., description="True to enable sidereal tracking, False to disable")

class PulseGuideRequest(BaseModel):
    """Request to pulse guide"""
    direction: int = Field(..., ge=0, le=3, description="Direction: 0=N, 1=S, 2=E, 3=W")
    duration_ms: int = Field(..., gt=0, description="Duration in milliseconds")

class ExposureRequest(BaseModel):
    """Request to start camera exposure"""
    duration_seconds: float = Field(..., gt=0, description="Exposure duration in seconds")
    light: bool = Field(True, description="True for light frame, False for dark frame")

class GainRequest(BaseModel):
    """Request to set camera gain"""
    gain: int = Field(..., ge=0, le=400, description="Gain value (0-400)")

class FilterRequest(BaseModel):
    """Request to change filter"""
    position: int = Field(..., ge=0, le=2, description="Filter position: 0=Dark, 1=IR, 2=LP")

class FocuserRequest(BaseModel):
    """Request to move focuser"""
    position: int = Field(..., gt=0, description="Target focuser position")

class DewHeaterRequest(BaseModel):
    """Request to control dew heater"""
    on: bool = Field(..., description="True to turn on, False to turn off")

# --- Telescope Endpoints ---

@router.get("/status")
async def get_telescope_status(request: Request):
    """Get complete telescope status"""
    alpaca = request.app.state.alpaca
    try:
        status = alpaca.get_telescope_status()
        return {
            "success": True,
            "data": status
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/slew")
async def slew_telescope(req: SlewRequest, request: Request):
    """Slew telescope to RA/Dec coordinates (async)"""
    alpaca = request.app.state.alpaca
    try:
        resp = alpaca.slew_to(req.ra_hours, req.dec_degrees)
        if resp.success:
            return {"success": True, "message": "Slew command sent"}
        else:
            raise HTTPException(status_code=400, detail=resp.error_message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/tracking")
async def set_tracking(req: TrackingRequest, request: Request):
    """Enable or disable sidereal tracking"""
    alpaca = request.app.state.alpaca
    try:
        resp = alpaca.set_tracking(req.enabled)
        if resp.success:
            return {"success": True, "tracking": req.enabled}
        else:
            raise HTTPException(status_code=400, detail=resp.error_message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/park")
async def park_telescope(request: Request):
    """Park the telescope"""
    alpaca = request.app.state.alpaca
    try:
        resp = alpaca.park()
        if resp.success:
            return {"success": True, "message": "Telescope parked"}
        else:
            raise HTTPException(status_code=400, detail=resp.error_message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/unpark")
async def unpark_telescope(request: Request):
    """Unpark the telescope"""
    alpaca = request.app.state.alpaca
    try:
        resp = alpaca.unpark()
        if resp.success:
            return {"success": True, "message": "Telescope unparked"}
        else:
            raise HTTPException(status_code=400, detail=resp.error_message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/home")
async def find_home(request: Request):
    """Move telescope to home position"""
    alpaca = request.app.state.alpaca
    try:
        resp = alpaca.find_home()
        if resp.success:
            return {"success": True, "message": "Finding home position"}
        else:
            raise HTTPException(status_code=400, detail=resp.error_message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/pulse-guide")
async def pulse_guide(req: PulseGuideRequest, request: Request):
    """Pulse guide telescope in specified direction"""
    alpaca = request.app.state.alpaca
    try:
        resp = alpaca.pulse_guide(req.direction, req.duration_ms)
        if resp.success:
            return {"success": True, "message": "Pulse guide executed"}
        else:
            raise HTTPException(status_code=400, detail=resp.error_message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Camera Endpoints ---

@router.get("/camera/status")
async def get_camera_status(request: Request):
    """Get camera status"""
    alpaca = request.app.state.alpaca
    try:
        status = alpaca.get_camera_status()
        return {"success": True, "data": status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/camera/expose")
async def start_exposure(req: ExposureRequest, request: Request):
    """Start camera exposure"""
    alpaca = request.app.state.alpaca
    try:
        resp = alpaca.start_exposure(req.duration_seconds, req.light)
        if resp.success:
            return {"success": True, "message": "Exposure started"}
        else:
            raise HTTPException(status_code=400, detail=resp.error_message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/camera/abort")
async def abort_exposure(request: Request):
    """Abort current exposure"""
    alpaca = request.app.state.alpaca
    try:
        resp = alpaca.abort_exposure()
        if resp.success:
            return {"success": True, "message": "Exposure aborted"}
        else:
            raise HTTPException(status_code=400, detail=resp.error_message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/camera/image-ready")
async def check_image_ready(request: Request):
    """Check if image is ready for download"""
    alpaca = request.app.state.alpaca
    try:
        ready = alpaca.is_image_ready()
        return {"success": True, "image_ready": ready}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/camera/gain")
async def set_gain(req: GainRequest, request: Request):
    """Set camera gain"""
    alpaca = request.app.state.alpaca
    try:
        resp = alpaca.set_gain(req.gain)
        if resp.success:
            return {"success": True, "gain": req.gain}
        else:
            raise HTTPException(status_code=400, detail=resp.error_message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Focuser Endpoints ---

@router.get("/focuser/status")
async def get_focuser_status(request: Request):
    """Get focuser status"""
    alpaca = request.app.state.alpaca
    try:
        status = alpaca.get_focuser_status()
        return {"success": True, "data": status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/focuser/move")
async def move_focuser(req: FocuserRequest, request: Request):
    """Move focuser to position"""
    alpaca = request.app.state.alpaca
    try:
        resp = alpaca.move_focuser(req.position)
        if resp.success:
            return {"success": True, "message": "Focuser moving"}
        else:
            raise HTTPException(status_code=400, detail=resp.error_message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Filter Wheel Endpoints ---

@router.get("/filter/names")
async def get_filter_names(request: Request):
    """Get available filter names"""
    alpaca = request.app.state.alpaca
    try:
        names = alpaca.get_filter_names()
        return {"success": True, "filters": names}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/filter/position")
async def get_filter_position(request: Request):
    """Get current filter position"""
    alpaca = request.app.state.alpaca
    try:
        pos = alpaca.get_filter_position()
        return {"success": True, "position": pos}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/filter/set")
async def set_filter(req: FilterRequest, request: Request):
    """Set filter position"""
    alpaca = request.app.state.alpaca
    try:
        resp = alpaca.set_filter(req.position)
        if resp.success:
            return {"success": True, "position": req.position}
        else:
            raise HTTPException(status_code=400, detail=resp.error_message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Switch (Dew Heater) Endpoints ---

@router.get("/dew-heater/status")
async def get_dew_heater_status(request: Request):
    """Get dew heater status"""
    alpaca = request.app.state.alpaca
    try:
        status = alpaca.get_dew_heater()
        return {"success": True, "on": status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/dew-heater/set")
async def set_dew_heater(req: DewHeaterRequest, request: Request):
    """Control dew heater"""
    alpaca = request.app.state.alpaca
    try:
        resp = alpaca.set_dew_heater(req.on)
        if resp.success:
            return {"success": True, "on": req.on}
        else:
            raise HTTPException(status_code=400, detail=resp.error_message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Stellarium Integration ---

@router.get("/stellarium/status")
async def get_stellarium_status(request: Request):
    """Check Stellarium availability"""
    stellarium = request.app.state.stellarium
    try:
        available = stellarium.is_available()
        status = stellarium.get_status() if available else None
        return {
            "success": True,
            "available": available,
            "status": status
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stellarium/selected")
async def get_selected_object(request: Request):
    """Get currently selected object in Stellarium"""
    stellarium = request.app.state.stellarium
    try:
        obj = stellarium.get_selected_object()
        if obj:
            return {
                "success": True,
                "object": {
                    "name": obj.name,
                    "type": obj.object_type,
                    "ra_hours": obj.ra_j2000_hours,
                    "dec_degrees": obj.dec_j2000_degrees,
                    "altitude": obj.altitude,
                    "azimuth": obj.azimuth,
                    "magnitude": obj.magnitude,
                    "above_horizon": obj.above_horizon,
                    "constellation": obj.constellation
                }
            }
        else:
            return {"success": True, "object": None, "message": "No object selected"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/stellarium/slew-to-selected")
async def slew_to_stellarium_object(request: Request):
    """Slew telescope to Stellarium-selected object"""
    alpaca = request.app.state.alpaca
    stellarium = request.app.state.stellarium
    try:
        obj = stellarium.get_selected_object()
        if not obj:
            raise HTTPException(status_code=400, detail="No object selected in Stellarium")
        
        if not obj.above_horizon:
            raise HTTPException(status_code=400, detail=f"{obj.name} is below horizon")
        
        resp = alpaca.slew_to(obj.ra_j2000_hours, obj.dec_j2000_degrees)
        if resp.success:
            return {
                "success": True,
                "message": f"Slewing to {obj.name}",
                "target": obj.name,
                "ra": obj.ra_j2000_hours,
                "dec": obj.dec_j2000_degrees
            }
        else:
            raise HTTPException(status_code=400, detail=resp.error_message)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
