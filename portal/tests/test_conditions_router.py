"""Tests for conditions REST router — _to_response mapping and endpoint behaviour."""

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.routers.conditions import router, _to_response  # noqa: E402
from backend.services.conditions_service import (  # noqa: E402
    AstroData,
    ConditionsData,
    WeatherData,
)

_app = FastAPI()
_app.include_router(router)
client = TestClient(_app)

_UTC = timezone.utc
_TS = datetime(2026, 5, 10, 2, 0, 0, tzinfo=_UTC)


def _make_conditions(weather_ok=True, cloud=25):
    return ConditionsData(
        site_name="Test Site",
        weather=WeatherData(
            cloud_cover_pct=cloud,
            wind_speed_ms=3.0,
            humidity_pct=55,
            temperature_c=12.0,
            weather_api_ok=weather_ok,
        ),
        astro=AstroData(
            sun_altitude_deg=-20.0,
            sun_azimuth_deg=270.0,
            moon_altitude_deg=35.0,
            moon_azimuth_deg=180.0,
            moon_illumination_pct=42.0,
            is_astronomical_night=True,
            is_nautical_twilight=False,
            is_civil_twilight=False,
            utc_time=_TS,
        ),
        timestamp=_TS,
    )


# --- _to_response unit tests -----------------------------------------------


def test_to_response_field_mapping():
    resp = _to_response(_make_conditions(weather_ok=True, cloud=25))
    assert resp.site_name == "Test Site"
    assert resp.weather.cloud_cover_pct == 25
    assert resp.weather.weather_api_ok is True
    assert resp.astro.is_astronomical_night is True
    assert resp.astro.sun_altitude_deg == -20.0
    # ISO timestamp must be parseable
    datetime.fromisoformat(resp.astro.utc_time)
    datetime.fromisoformat(resp.timestamp)


def test_to_response_weather_offline():
    resp = _to_response(_make_conditions(weather_ok=False, cloud=None))
    assert resp.weather.weather_api_ok is False
    assert resp.weather.cloud_cover_pct is None


# --- GET /api/conditions/current -------------------------------------------


def test_get_current_conditions_success():
    mock_svc = MagicMock()
    mock_svc.get_current.return_value = _make_conditions()
    with patch("backend.routers.conditions._conditions_service", mock_svc):
        resp = client.get("/api/conditions/current")
    assert resp.status_code == 200
    body = resp.json()
    assert body["weather"]["weather_api_ok"] is True
    assert "astro" in body
    assert body["site_name"] == "Test Site"


def test_get_current_conditions_offline():
    mock_svc = MagicMock()
    mock_svc.get_current.return_value = _make_conditions(weather_ok=False, cloud=None)
    with patch("backend.routers.conditions._conditions_service", mock_svc):
        resp = client.get("/api/conditions/current")
    assert resp.status_code == 200
    assert resp.json()["weather"]["weather_api_ok"] is False


def test_get_current_conditions_service_error():
    mock_svc = MagicMock()
    mock_svc.get_current.side_effect = RuntimeError("astropy error")
    with patch("backend.routers.conditions._conditions_service", mock_svc):
        resp = client.get("/api/conditions/current")
    assert resp.status_code == 500


# --- GET /api/conditions/forecast ------------------------------------------


def test_get_forecast_default_hours():
    mock_svc = MagicMock()
    mock_svc.get_forecast.return_value = [_make_conditions()] * 12
    with patch("backend.routers.conditions._conditions_service", mock_svc):
        resp = client.get("/api/conditions/forecast")
    assert resp.status_code == 200
    assert len(resp.json()) == 12
    mock_svc.get_forecast.assert_called_once_with(12)


def test_get_forecast_custom_hours():
    mock_svc = MagicMock()
    mock_svc.get_forecast.return_value = [_make_conditions()] * 6
    with patch("backend.routers.conditions._conditions_service", mock_svc):
        resp = client.get("/api/conditions/forecast?hours=6")
    assert resp.status_code == 200
    assert len(resp.json()) == 6
    mock_svc.get_forecast.assert_called_once_with(6)


def test_get_forecast_service_error():
    mock_svc = MagicMock()
    mock_svc.get_forecast.side_effect = RuntimeError("fail")
    with patch("backend.routers.conditions._conditions_service", mock_svc):
        resp = client.get("/api/conditions/forecast")
    assert resp.status_code == 500
