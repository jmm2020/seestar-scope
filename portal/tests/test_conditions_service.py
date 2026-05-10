"""Tests for ConditionsService — astropy + Open-Meteo."""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.services.conditions_service import (  # noqa: E402
    ConditionsService,
    SiteLocation,
    AstroData,
)


# --- Helpers ---------------------------------------------------------------

def _mock_current_response(cloud=25, wind=5.0, humidity=60, temp=15.0):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "current": {
            "cloud_cover": cloud,
            "wind_speed_10m": wind,
            "relative_humidity_2m": humidity,
            "temperature_2m": temp,
        }
    }
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def _mock_hourly_response(hours=12, cloud_value=30):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "hourly": {
            "cloud_cover": [cloud_value] * hours,
            "wind_speed_10m": [4.0] * hours,
            "relative_humidity_2m": [55] * hours,
            "temperature_2m": [10.0] * hours,
        }
    }
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


@pytest.fixture
def service():
    svc = ConditionsService(SiteLocation(37.12, -123.45, name="Test Site"))
    yield svc
    svc.close()


# --- Construction ----------------------------------------------------------

def test_site_location_construction(service):
    assert service.site.latitude == 37.12
    assert service.site.longitude == -123.45
    assert service.site.name == "Test Site"


# --- Astro computation -----------------------------------------------------

def test_compute_astro_returns_valid_altitudes(service):
    from astropy.time import Time
    astro = service._compute_astro(Time.now())
    assert isinstance(astro, AstroData)
    assert -90.0 <= astro.sun_altitude_deg <= 90.0
    assert -90.0 <= astro.moon_altitude_deg <= 90.0
    assert 0.0 <= astro.moon_illumination_pct <= 100.0


def test_twilight_flags_mutually_exclusive(service):
    """At any sun altitude, at most one twilight flag is True."""
    from astropy.time import Time
    astro = service._compute_astro(Time.now())
    flags = [
        astro.is_astronomical_night,
        astro.is_nautical_twilight,
        astro.is_civil_twilight,
    ]
    assert sum(flags) <= 1


# --- Weather fetch ---------------------------------------------------------

def test_fetch_weather_success(service):
    with patch.object(service._http, "get", return_value=_mock_current_response()):
        weather = service._fetch_weather()
    assert weather.weather_api_ok is True
    assert weather.cloud_cover_pct == 25
    assert weather.wind_speed_ms == 5.0
    assert weather.humidity_pct == 60
    assert weather.temperature_c == 15.0


def test_fetch_weather_unreachable(service):
    """ConnectError / network failure should yield weather_api_ok=False."""
    with patch.object(service._http, "get",
                      side_effect=httpx.ConnectError("refused")):
        weather = service._fetch_weather()
    assert weather.weather_api_ok is False
    assert weather.cloud_cover_pct is None
    assert weather.wind_speed_ms is None


def test_fetch_weather_5xx(service):
    """A 5xx response should also degrade gracefully."""
    bad_resp = MagicMock()
    bad_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "503", request=MagicMock(), response=MagicMock()
    )
    with patch.object(service._http, "get", return_value=bad_resp):
        weather = service._fetch_weather()
    assert weather.weather_api_ok is False


# --- get_current integration ----------------------------------------------

def test_get_current_returns_conditions_data(service):
    with patch.object(service._http, "get", return_value=_mock_current_response(
            cloud=10, wind=2.5, humidity=40, temp=18.0)):
        data = service.get_current()
    assert data.site_name == "Test Site"
    assert data.weather.weather_api_ok is True
    assert data.weather.cloud_cover_pct == 10
    # Astro fields populated regardless of weather
    assert isinstance(data.astro, AstroData)


def test_get_current_works_when_weather_down(service):
    """Astro must render even if weather API is unreachable."""
    with patch.object(service._http, "get",
                      side_effect=httpx.ConnectError("offline")):
        data = service.get_current()
    assert data.weather.weather_api_ok is False
    assert isinstance(data.astro, AstroData)
    assert -90.0 <= data.astro.sun_altitude_deg <= 90.0


# --- Forecast --------------------------------------------------------------

def test_get_forecast_returns_n_hours(service):
    with patch.object(service._http, "get", return_value=_mock_hourly_response(hours=12)):
        forecast = service.get_forecast(hours=12)
    assert len(forecast) == 12
    assert all(p.weather.weather_api_ok for p in forecast)
    assert all(p.weather.cloud_cover_pct == 30 for p in forecast)


def test_get_forecast_clamps_hours(service):
    with patch.object(service._http, "get", return_value=_mock_hourly_response(hours=48)):
        forecast = service.get_forecast(hours=999)
    assert len(forecast) == 48


def test_get_forecast_degrades_on_failure(service):
    with patch.object(service._http, "get",
                      side_effect=httpx.ConnectError("offline")):
        forecast = service.get_forecast(hours=6)
    assert len(forecast) == 6
    assert all(p.weather.weather_api_ok is False for p in forecast)
    # Astro still populated
    assert all(isinstance(p.astro, AstroData) for p in forecast)
