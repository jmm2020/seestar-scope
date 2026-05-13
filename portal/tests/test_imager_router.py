"""Tests for the /api/imager REST router — covers the 200/204/502 cases."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.routers.imager import router  # noqa: E402
from clients.seestar_imager import SeestarImagerError, StackedFrame  # noqa: E402


def _app_with_router() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_stacked_jpg_returns_204_when_no_frame_ready():
    stub = MagicMock()
    stub.request_stacked_frame.return_value = None

    with patch("backend.routers.imager.get_imager_client", return_value=stub):
        resp = _app_with_router().get("/api/imager/stacked.jpg")

    assert resp.status_code == 204
    assert resp.content == b""


def test_stacked_jpg_returns_jpeg_when_frame_available():
    fake_frame = MagicMock(spec=StackedFrame)
    fake_frame.width = 1080
    fake_frame.height = 1920
    fake_frame.frame_format = "bayer16"
    fake_frame.to_jpeg.return_value = b"\xff\xd8\xff\xe0fakejpeg"

    stub = MagicMock()
    stub.request_stacked_frame.return_value = fake_frame

    with patch("backend.routers.imager.get_imager_client", return_value=stub):
        resp = _app_with_router().get("/api/imager/stacked.jpg")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
    assert resp.headers["x-frame-width"] == "1080"
    assert resp.headers["x-frame-height"] == "1920"
    assert resp.headers["x-frame-format"] == "bayer16"
    assert resp.headers["cache-control"] == "no-store, max-age=0"
    assert resp.content == b"\xff\xd8\xff\xe0fakejpeg"
    fake_frame.to_jpeg.assert_called_once_with(quality=90)


def test_stacked_jpg_passes_quality_query_param():
    fake_frame = MagicMock(spec=StackedFrame)
    fake_frame.width = 64
    fake_frame.height = 64
    fake_frame.frame_format = "bayer16"
    fake_frame.to_jpeg.return_value = b"\xff\xd8\xffJ"

    stub = MagicMock()
    stub.request_stacked_frame.return_value = fake_frame

    with patch("backend.routers.imager.get_imager_client", return_value=stub):
        resp = _app_with_router().get("/api/imager/stacked.jpg?quality=60")

    assert resp.status_code == 200
    fake_frame.to_jpeg.assert_called_once_with(quality=60)


def test_stacked_jpg_returns_502_on_imager_error():
    stub = MagicMock()
    stub.request_stacked_frame.side_effect = SeestarImagerError("scope offline")

    with patch("backend.routers.imager.get_imager_client", return_value=stub):
        resp = _app_with_router().get("/api/imager/stacked.jpg")

    assert resp.status_code == 502
    assert "scope offline" in resp.json()["detail"]


def test_stacked_jpg_returns_502_on_jpeg_encode_failure():
    fake_frame = MagicMock(spec=StackedFrame)
    fake_frame.width = 1080
    fake_frame.height = 1920
    fake_frame.frame_format = "bayer16"
    fake_frame.to_jpeg.side_effect = SeestarImagerError("decode failed")

    stub = MagicMock()
    stub.request_stacked_frame.return_value = fake_frame

    with patch("backend.routers.imager.get_imager_client", return_value=stub):
        resp = _app_with_router().get("/api/imager/stacked.jpg")

    assert resp.status_code == 502
    assert "decode failed" in resp.json()["detail"]
