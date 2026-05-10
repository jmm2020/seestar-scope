"""Integration tests for the sessions API router — FastAPI TestClient with in-memory DB."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

# Stub module-level service singletons to avoid filesystem side-effects in tests
for _mod in ("backend.app.services.siril_service", "backend.services.platesolve_service"):
    _stub = MagicMock()
    _stub.SirilService.return_value = MagicMock()
    _stub.ASTAPService.return_value = MagicMock()
    sys.modules.setdefault(_mod, _stub)

from backend.main import app  # noqa: E402
from backend.database import get_sessions_db  # noqa: E402
from backend.models.sessions import SessionDatabase  # noqa: E402


@pytest.fixture
def client():
    db = SessionDatabase(db_path=":memory:")
    app.dependency_overrides[get_sessions_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_start_session_returns_200_with_id(client):
    resp = client.post("/api/sessions/", json={"target_name": "M31"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] is not None
    assert data["target_name"] == "M31"
    assert data["ended_at"] is None


def test_end_session_sets_ended_at(client):
    sid = client.post("/api/sessions/", json={"target_name": "M42"}).json()["id"]
    resp = client.post(f"/api/sessions/{sid}/end", json={})
    assert resp.status_code == 200
    assert resp.json()["ended_at"] is not None


def test_end_session_404_on_missing(client):
    resp = client.post("/api/sessions/999/end", json={})
    assert resp.status_code == 404


def test_get_session_404_on_missing(client):
    resp = client.get("/api/sessions/999")
    assert resp.status_code == 404


def test_get_session_returns_record(client):
    sid = client.post("/api/sessions/", json={"target_name": "NGC7000"}).json()["id"]
    resp = client.get(f"/api/sessions/{sid}")
    assert resp.status_code == 200
    assert resp.json()["target_name"] == "NGC7000"


def test_list_sessions_returns_newest_first(client):
    client.post("/api/sessions/", json={"target_name": "A"})
    client.post("/api/sessions/", json={"target_name": "B"})
    sessions = client.get("/api/sessions/").json()
    assert len(sessions) == 2
    assert sessions[0]["started_at"] >= sessions[1]["started_at"]


def test_list_sessions_include_frame_counts(client):
    sid = client.post("/api/sessions/", json={"target_name": "M31"}).json()["id"]
    client.post(
        f"/api/sessions/{sid}/frames",
        json={"filename": "f.fits", "exposure_s": 10.0, "gain": 80, "filter": "L"},
    )
    sessions = client.get("/api/sessions/?include_frame_counts=true").json()
    assert len(sessions) == 1
    assert sessions[0]["frame_count"] == 1
    assert sessions[0]["total_exposure_s"] == 10.0


def test_add_frame_404_on_missing_session(client):
    resp = client.post(
        "/api/sessions/999/frames",
        json={"filename": "f.fits", "exposure_s": 10.0, "gain": 80, "filter": "L"},
    )
    assert resp.status_code == 404


def test_get_frames_404_on_missing_session(client):
    resp = client.get("/api/sessions/999/frames")
    assert resp.status_code == 404


def test_add_and_get_frame_roundtrip(client):
    sid = client.post("/api/sessions/", json={"target_name": "M31"}).json()["id"]
    client.post(
        f"/api/sessions/{sid}/frames",
        json={"filename": "f.fits", "exposure_s": 10.0, "gain": 80, "filter": "L"},
    )
    frames = client.get(f"/api/sessions/{sid}/frames").json()
    assert len(frames) == 1
    assert frames[0]["filename"] == "f.fits"
    assert frames[0]["exposure_s"] == 10.0
