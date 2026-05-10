"""
Observing Conditions API Router
===============================
REST endpoints for current and forecast observing conditions:
- Astronomical: sun/moon altitude, twilight, moon phase (always available)
- Weather: cloud cover, wind, humidity, temp (degrades when Open-Meteo unreachable)
"""

import asyncio

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
import logging

from ..services.conditions_service import ConditionsService, SiteLocation
from ..config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/conditions", tags=["conditions"])

# Global service instance (initialized on first use)
_conditions_service: ConditionsService | None = None


def get_conditions_service() -> ConditionsService:
    """Get conditions service instance, building it from settings on first use."""
    global _conditions_service
    if _conditions_service is None:
        site = SiteLocation(
            latitude=settings.site_latitude,
            longitude=settings.site_longitude,
            elevation_m=settings.site_elevation_m,
            name=settings.site_name,
        )
        _conditions_service = ConditionsService(site)
    return _conditions_service


class WeatherResponse(BaseModel):
    cloud_cover_pct: int | None
    wind_speed_ms: float | None
    humidity_pct: int | None
    temperature_c: float | None
    weather_api_ok: bool


class AstroResponse(BaseModel):
    sun_altitude_deg: float
    sun_azimuth_deg: float
    moon_altitude_deg: float
    moon_azimuth_deg: float
    moon_illumination_pct: float
    is_astronomical_night: bool
    is_nautical_twilight: bool
    is_civil_twilight: bool
    utc_time: str  # ISO 8601


class ConditionsResponse(BaseModel):
    site_name: str
    weather: WeatherResponse
    astro: AstroResponse
    timestamp: str  # ISO 8601


def _to_response(data) -> ConditionsResponse:
    return ConditionsResponse(
        site_name=data.site_name,
        weather=WeatherResponse(
            cloud_cover_pct=data.weather.cloud_cover_pct,
            wind_speed_ms=data.weather.wind_speed_ms,
            humidity_pct=data.weather.humidity_pct,
            temperature_c=data.weather.temperature_c,
            weather_api_ok=data.weather.weather_api_ok,
        ),
        astro=AstroResponse(
            sun_altitude_deg=data.astro.sun_altitude_deg,
            sun_azimuth_deg=data.astro.sun_azimuth_deg,
            moon_altitude_deg=data.astro.moon_altitude_deg,
            moon_azimuth_deg=data.astro.moon_azimuth_deg,
            moon_illumination_pct=data.astro.moon_illumination_pct,
            is_astronomical_night=data.astro.is_astronomical_night,
            is_nautical_twilight=data.astro.is_nautical_twilight,
            is_civil_twilight=data.astro.is_civil_twilight,
            utc_time=data.astro.utc_time.isoformat(),
        ),
        timestamp=data.timestamp.isoformat(),
    )


@router.get("/current", response_model=ConditionsResponse)
async def get_current_conditions():
    """Return current observing conditions (astro + weather)."""
    try:
        service = get_conditions_service()
        data = await asyncio.to_thread(service.get_current)
        return _to_response(data)
    except Exception as e:
        logger.error(f"Failed to get current conditions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/forecast", response_model=list[ConditionsResponse])
async def get_forecast(
    hours: int = Query(12, ge=1, le=48, description="Forecast horizon in hours (1-48)"),
):
    """Return per-hour conditions for the next N hours (default 12)."""
    try:
        service = get_conditions_service()
        forecast = await asyncio.to_thread(service.get_forecast, hours)
        return [_to_response(d) for d in forecast]
    except Exception as e:
        logger.error(f"Failed to get forecast: {e}")
        raise HTTPException(status_code=500, detail=str(e))
