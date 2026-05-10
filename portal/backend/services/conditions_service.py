"""
Observing Conditions Service — astropy + Open-Meteo
====================================================
Computes astronomical data locally (sun/moon altitude, twilight, moon phase)
and fetches weather data from the free Open-Meteo API. Astronomical data is
always available; weather degrades gracefully to weather_api_ok=False when
the API is unreachable.
"""

import math
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, List

import httpx
from astropy.coordinates import EarthLocation, AltAz, get_body, get_sun, solar_system_ephemeris
from astropy.time import Time
import astropy.units as u

logger = logging.getLogger(__name__)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


@dataclass
class SiteLocation:
    """Observing site coordinates."""

    latitude: float  # degrees N (positive), S (negative)
    longitude: float  # degrees E (positive), W (negative)
    elevation_m: float = 0.0  # meters above sea level
    name: str = "My Observatory"


@dataclass
class WeatherData:
    """Weather snapshot. weather_api_ok=False indicates degraded mode."""

    cloud_cover_pct: Optional[int] = None
    wind_speed_ms: Optional[float] = None
    humidity_pct: Optional[int] = None
    temperature_c: Optional[float] = None
    weather_api_ok: bool = False


@dataclass
class AstroData:
    """Astronomical observing parameters at a given UTC time."""

    sun_altitude_deg: float
    sun_azimuth_deg: float
    moon_altitude_deg: float
    moon_azimuth_deg: float
    moon_illumination_pct: float
    is_astronomical_night: bool  # sun_alt < -18°
    is_nautical_twilight: bool  # -18° <= sun_alt < -12°
    is_civil_twilight: bool  # -12° <= sun_alt < -6°
    utc_time: datetime


@dataclass
class ConditionsData:
    """Combined snapshot for a site at a given time."""

    site_name: str
    weather: WeatherData
    astro: AstroData
    timestamp: datetime


class ConditionsService:
    """Computes astro data and fetches weather for an observing site."""

    def __init__(self, site: SiteLocation, http_timeout: float = 5.0):
        """Build EarthLocation and httpx client.

        Astropy's builtin ephemeris avoids the first-call download of JPL
        ephemeris data — sufficient accuracy for sun/moon position.
        """
        self.site = site
        self._location = EarthLocation(
            lat=site.latitude * u.deg,
            lon=site.longitude * u.deg,
            height=site.elevation_m * u.m,
        )
        self._http = httpx.Client(timeout=http_timeout)
        # Pin to builtin ephemeris so first call doesn't try to download JPL data
        solar_system_ephemeris.set("builtin")

    def close(self) -> None:
        """Close the underlying HTTP client."""
        try:
            self._http.close()
        except Exception:
            pass

    def get_current(self) -> ConditionsData:
        """Compute astro + fetch weather for the current moment."""
        now = Time.now()
        astro = self._compute_astro(now)
        weather = self._fetch_weather()
        return ConditionsData(
            site_name=self.site.name,
            weather=weather,
            astro=astro,
            timestamp=astro.utc_time,
        )

    def get_forecast(self, hours: int = 12) -> List[ConditionsData]:
        """Return per-hour conditions for the next N hours.

        Astro data is computed locally for each hour. Weather is fetched
        in a single Open-Meteo call and zipped to the hourly grid.
        """
        hours = max(1, min(int(hours), 48))  # clamp to 1..48
        weather_by_hour = self._fetch_hourly_weather(hours)

        results: List[ConditionsData] = []
        # Use UTC now floored to the hour as the forecast anchor so it lines up
        # with Open-Meteo's hourly grid.
        anchor = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        for i in range(hours):
            t = anchor + timedelta(hours=i)
            astro = self._compute_astro(Time(t))
            weather = weather_by_hour[i] if i < len(weather_by_hour) else WeatherData()
            results.append(
                ConditionsData(
                    site_name=self.site.name,
                    weather=weather,
                    astro=astro,
                    timestamp=t,
                )
            )
        return results

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _compute_astro(self, time: Time) -> AstroData:
        """Compute sun/moon position and twilight flags at `time`."""
        frame = AltAz(obstime=time, location=self._location)
        sun_altaz = get_sun(time).transform_to(frame)
        moon_altaz = get_body("moon", time).transform_to(frame)

        # Moon illumination from sun-moon elongation
        sun_coord = get_sun(time)
        moon_coord = get_body("moon", time)
        elongation = sun_coord.separation(moon_coord)
        illumination_pct = float((1 - math.cos(elongation.rad)) / 2 * 100)

        sun_alt = float(sun_altaz.alt.deg)
        is_astro_night = sun_alt < -18.0
        is_nautical = -18.0 <= sun_alt < -12.0
        is_civil = -12.0 <= sun_alt < -6.0

        return AstroData(
            sun_altitude_deg=sun_alt,
            sun_azimuth_deg=float(sun_altaz.az.deg),
            moon_altitude_deg=float(moon_altaz.alt.deg),
            moon_azimuth_deg=float(moon_altaz.az.deg),
            moon_illumination_pct=illumination_pct,
            is_astronomical_night=is_astro_night,
            is_nautical_twilight=is_nautical,
            is_civil_twilight=is_civil,
            utc_time=time.to_datetime(timezone=timezone.utc),
        )

    def _fetch_weather(self) -> WeatherData:
        """Fetch current weather from Open-Meteo. Returns weather_api_ok=False on any failure."""
        params = {
            "latitude": self.site.latitude,
            "longitude": self.site.longitude,
            "current": "cloud_cover,wind_speed_10m,relative_humidity_2m,temperature_2m",
            "wind_speed_unit": "ms",
            "timezone": "UTC",
        }
        try:
            resp = self._http.get(OPEN_METEO_URL, params=params)
            resp.raise_for_status()
            payload = resp.json()
            current = payload.get("current") or {}
            return WeatherData(
                cloud_cover_pct=_as_int(current.get("cloud_cover")),
                wind_speed_ms=_as_float(current.get("wind_speed_10m")),
                humidity_pct=_as_int(current.get("relative_humidity_2m")),
                temperature_c=_as_float(current.get("temperature_2m")),
                weather_api_ok=True,
            )
        except Exception as e:
            logger.warning(f"Open-Meteo current weather fetch failed: {e}")
            return WeatherData(weather_api_ok=False)

    def _fetch_hourly_weather(self, hours: int) -> List[WeatherData]:
        """Fetch hourly forecast. Returns empty list on failure."""
        params = {
            "latitude": self.site.latitude,
            "longitude": self.site.longitude,
            "hourly": "cloud_cover,wind_speed_10m,relative_humidity_2m,temperature_2m",
            "wind_speed_unit": "ms",
            "timezone": "UTC",
            "forecast_hours": hours,
        }
        try:
            resp = self._http.get(OPEN_METEO_URL, params=params)
            resp.raise_for_status()
            payload = resp.json()
            hourly = payload.get("hourly") or {}
            cloud = hourly.get("cloud_cover") or []
            wind = hourly.get("wind_speed_10m") or []
            humidity = hourly.get("relative_humidity_2m") or []
            temp = hourly.get("temperature_2m") or []
            n = min(len(cloud), len(wind), len(humidity), len(temp), hours)
            out: List[WeatherData] = []
            for i in range(n):
                out.append(
                    WeatherData(
                        cloud_cover_pct=_as_int(cloud[i]),
                        wind_speed_ms=_as_float(wind[i]),
                        humidity_pct=_as_int(humidity[i]),
                        temperature_c=_as_float(temp[i]),
                        weather_api_ok=True,
                    )
                )
            # Pad with degraded entries if API returned fewer points than requested
            while len(out) < hours:
                out.append(WeatherData(weather_api_ok=False))
            return out
        except Exception as e:
            logger.warning(f"Open-Meteo hourly forecast fetch failed: {e}")
            return [WeatherData(weather_api_ok=False) for _ in range(hours)]


def _as_int(value) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def _as_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
