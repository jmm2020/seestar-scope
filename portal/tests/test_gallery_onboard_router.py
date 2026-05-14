"""Tests for the /api/gallery/onboard router."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.routers import gallery as gallery_router  # noqa: E402
from backend.routers.gallery_onboard import router  # noqa: E402
from clients.seestar_archive import OnboardItem, SeestarArchiveError  # noqa: E402


def _app_with_router() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_list_onboard_items_returns_200_with_items():
    stub = MagicMock()
    stub.list_items.return_value = [
        OnboardItem(
            name="img",
            thumb_url="http://scope/t_thn.jpg",
            full_url="http://scope/t.jpg",
            is_video=False,
        ),
        OnboardItem(
            name="vid",
            thumb_url="http://scope/v_thn.jpg",
            full_url="http://scope/v.mp4",
            is_video=True,
        ),
    ]

    with patch(
        "backend.routers.gallery_onboard.get_archive_client", return_value=stub
    ):
        resp = _app_with_router().get("/api/gallery/onboard/")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert body[0]["name"] == "img"
    assert body[0]["is_video"] is False
    assert body[1]["full_url"].endswith(".mp4")


def test_list_onboard_items_empty_returns_200_empty_list():
    stub = MagicMock()
    stub.list_items.return_value = []

    with patch(
        "backend.routers.gallery_onboard.get_archive_client", return_value=stub
    ):
        resp = _app_with_router().get("/api/gallery/onboard/")

    assert resp.status_code == 200
    assert resp.json() == []


def test_list_onboard_items_client_error_returns_502():
    stub = MagicMock()
    stub.list_items.side_effect = SeestarArchiveError("scope offline")

    with patch(
        "backend.routers.gallery_onboard.get_archive_client", return_value=stub
    ):
        resp = _app_with_router().get("/api/gallery/onboard/")

    assert resp.status_code == 502
    assert "scope offline" in resp.json()["detail"]


def test_thumbnail_proxy_returns_200_with_jpeg():
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.content = b"\xff\xd8\xff\xe0fakejpeg"

    stub = MagicMock()
    stub.host = "192.168.0.132"
    stub.http_port = 80

    with patch("backend.routers.gallery_onboard.get_archive_client", return_value=stub):
        with patch("backend.routers.gallery_onboard.requests.get", return_value=fake_resp):
            resp = _app_with_router().get(
                "/api/gallery/onboard/thumbnail",
                params={"path": "MyWorks/x_thn.jpg"},
            )

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
    assert resp.headers["cache-control"] == "public, max-age=3600"
    assert resp.content == b"\xff\xd8\xff\xe0fakejpeg"


def test_thumbnail_proxy_constructs_url_from_client_host():
    """Backend must build the scope URL from client.host/http_port, not the caller."""
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.content = b"jpeg"

    stub = MagicMock()
    stub.host = "10.0.0.1"
    stub.http_port = 80

    captured = {}

    def fake_get(url, **kwargs):
        captured["url"] = url
        return fake_resp

    with patch("backend.routers.gallery_onboard.get_archive_client", return_value=stub):
        with patch("backend.routers.gallery_onboard.requests.get", side_effect=fake_get):
            _app_with_router().get(
                "/api/gallery/onboard/thumbnail",
                params={"path": "MyWorks/img_thn.jpg"},
            )

    assert captured["url"] == "http://10.0.0.1:80/MyWorks/img_thn.jpg"


def test_thumbnail_proxy_scope_unreachable_returns_502():
    stub = MagicMock()
    stub.host = "192.168.0.132"
    stub.http_port = 80

    with patch("backend.routers.gallery_onboard.get_archive_client", return_value=stub):
        with patch(
            "backend.routers.gallery_onboard.requests.get",
            side_effect=requests.ConnectionError("connection refused"),
        ):
            resp = _app_with_router().get(
                "/api/gallery/onboard/thumbnail",
                params={"path": "MyWorks/x_thn.jpg"},
            )

    assert resp.status_code == 502
    assert "connection refused" in resp.json()["detail"]


def test_thumbnail_proxy_non_200_returns_502():
    fake_resp = MagicMock()
    fake_resp.status_code = 404
    fake_resp.content = b""

    stub = MagicMock()
    stub.host = "192.168.0.132"
    stub.http_port = 80

    with patch("backend.routers.gallery_onboard.get_archive_client", return_value=stub):
        with patch("backend.routers.gallery_onboard.requests.get", return_value=fake_resp):
            resp = _app_with_router().get(
                "/api/gallery/onboard/thumbnail",
                params={"path": "MyWorks/missing_thn.jpg"},
            )

    assert resp.status_code == 502
    assert "HTTP 404" in resp.json()["detail"]


def test_thumbnail_proxy_rejects_oversized_response():
    """Responses larger than 5 MB must return 502 (size guard)."""
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.content = b"x" * (5 * 1024 * 1024 + 1)

    stub = MagicMock()
    stub.host = "192.168.0.132"
    stub.http_port = 80

    with patch("backend.routers.gallery_onboard.get_archive_client", return_value=stub):
        with patch("backend.routers.gallery_onboard.requests.get", return_value=fake_resp):
            resp = _app_with_router().get(
                "/api/gallery/onboard/thumbnail",
                params={"path": "MyWorks/huge.jpg"},
            )

    assert resp.status_code == 502
    assert "too large" in resp.json()["detail"]


def test_health_returns_ok_when_client_reachable():
    stub = MagicMock()
    stub.is_reachable.return_value = True
    with patch(
        "backend.routers.gallery_onboard.get_archive_client", return_value=stub
    ):
        resp = _app_with_router().get("/api/gallery/onboard/health")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_health_returns_unreachable_when_client_offline():
    stub = MagicMock()
    stub.is_reachable.return_value = False
    with patch(
        "backend.routers.gallery_onboard.get_archive_client", return_value=stub
    ):
        resp = _app_with_router().get("/api/gallery/onboard/health")

    assert resp.status_code == 200
    assert resp.json() == {"status": "unreachable"}


# ── Integration tests: both routers mounted together ──────────────────────────
#
# These tests catch routing collisions that are invisible when each router is
# tested in isolation.  The dual-router app mirrors the registration order in
# main.py: onboard router first, then the local gallery router.


def _dual_router_app() -> TestClient:
    """Minimal app with both gallery routers mounted in production order."""
    app = FastAPI()
    app.include_router(router)  # gallery_onboard: prefix="/api/gallery/onboard"
    app.include_router(gallery_router.router, prefix="/api/gallery")
    return TestClient(app)


def test_onboard_thumbnail_not_intercepted_by_local_gallery_wildcard():
    """Regression: /api/gallery/onboard/thumbnail must not return 422.

    Before the fix, gallery.router's /{image_id}/thumbnail route matched
    'onboard' and returned 422 int-parsing error.
    """
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.content = b"\xff\xd8\xff\xe0fakejpeg"

    stub = MagicMock()
    stub.host = "192.168.0.132"
    stub.http_port = 80

    with patch("backend.routers.gallery_onboard.get_archive_client", return_value=stub):
        with patch("backend.routers.gallery_onboard.requests.get", return_value=fake_resp):
            resp = _dual_router_app().get(
                "/api/gallery/onboard/thumbnail",
                params={"path": "Solar_video/2024-04-08-141802-Solar-timelapse_thn.jpg"},
            )

    assert resp.status_code == 200, f"Expected 200 but got {resp.status_code}: {resp.text}"
    assert resp.headers["content-type"] == "image/jpeg"


def test_onboard_list_not_intercepted_by_local_gallery_wildcard():
    """Regression: /api/gallery/onboard/ list must still work with both routers mounted."""
    stub = MagicMock()
    stub.list_items.return_value = [
        OnboardItem(
            name="img",
            thumb_url="http://scope/t_thn.jpg",
            full_url="http://scope/t.jpg",
            is_video=False,
        ),
    ]

    with patch("backend.routers.gallery_onboard.get_archive_client", return_value=stub):
        resp = _dual_router_app().get("/api/gallery/onboard/")

    assert resp.status_code == 200
    assert len(resp.json()) == 1
