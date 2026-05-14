"""Tests for gallery view layer — fetch_onboard_items and render_onboard_card."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests

# Stub heavy/unavailable packages before project imports.
for _mod in (
    "streamlit",
    "numpy",
    "PIL",
    "PIL.Image",
    "scipy",
    "skimage",
    "cv2",
    "sep",
    "photutils",
    "astroalign",
    "lacosmic",
    "utils.image_processing",
):
    sys.modules.setdefault(_mod, MagicMock())

sys.path.insert(0, str(Path(__file__).parent.parent))

from views.gallery import fetch_onboard_items, render_onboard_card  # noqa: E402


def test_render_onboard_card_encodes_spaces_in_thumb_url(monkeypatch):
    """requests.get must be called with a percent-encoded proxy URL; st.image receives bytes."""
    st_mock = MagicMock()
    monkeypatch.setattr("views.gallery.st", st_mock)

    fake_resp = MagicMock()
    fake_resp.content = b"fake-jpeg-bytes"

    item = {
        "name": "M 13",
        "is_video": False,
        "thumb_url": "http://10.0.0.1/MyWorks/M 13/img_thn.jpg",
        "full_url": "http://10.0.0.1/MyWorks/M 13/img.jpg",
    }
    with patch("views.gallery.requests.get", return_value=fake_resp) as mock_get:
        render_onboard_card(item)

    called_url = mock_get.call_args[0][0]
    assert " " not in called_url, "Spaces must be percent-encoded in the proxy URL"
    assert "%20" in called_url, "Space must be encoded as %20"
    assert "path=" in called_url, "Proxy URL must use path= param, not url="
    assert mock_get.call_args[1].get("timeout") == 10, (
        "requests.get must use timeout=10 to prevent UI hangs"
    )

    assert st_mock.image.called, "st.image must be called for a non-video item"
    image_arg = st_mock.image.call_args[0][0]
    assert image_arg == b"fake-jpeg-bytes", "st.image must receive bytes, not a URL string"


def test_render_onboard_card_thumbnail_http_error(monkeypatch):
    """HTTP 4xx/5xx from backend (raise_for_status) triggers st.error, not an unhandled exception."""
    st_mock = MagicMock()
    monkeypatch.setattr("views.gallery.st", st_mock)

    fake_resp = MagicMock()
    fake_resp.raise_for_status.side_effect = requests.exceptions.HTTPError("404 Not Found")

    item = {
        "name": "M 82",
        "is_video": False,
        "thumb_url": "http://10.0.0.1/MyWorks/M 82/img_thn.jpg",
        "full_url": "http://10.0.0.1/MyWorks/M 82/img.jpg",
    }
    with patch("views.gallery.requests.get", return_value=fake_resp):
        render_onboard_card(item)

    assert st_mock.error.called, "st.error must be called when raise_for_status raises HTTPError"
    assert not st_mock.image.called, "st.image must not be called on fetch failure"


def test_render_onboard_card_thumbnail_network_error(monkeypatch):
    """Network failure during thumbnail fetch triggers st.error, not an unhandled exception."""
    st_mock = MagicMock()
    monkeypatch.setattr("views.gallery.st", st_mock)

    item = {
        "name": "M 82",
        "is_video": False,
        "thumb_url": "http://10.0.0.1/MyWorks/M 82/img_thn.jpg",
        "full_url": "http://10.0.0.1/MyWorks/M 82/img.jpg",
    }
    with patch("views.gallery.requests.get", side_effect=Exception("connection refused")):
        render_onboard_card(item)

    assert st_mock.error.called, "st.error must be called when thumbnail fetch fails"
    assert not st_mock.image.called, "st.image must not be called on fetch failure"


def test_render_onboard_card_video_no_try_except(monkeypatch):
    """st.video is called directly for video items; no misleading try/except."""
    st_mock = MagicMock()
    monkeypatch.setattr("views.gallery.st", st_mock)

    item = {
        "name": "Solar_video",
        "is_video": True,
        "thumb_url": "http://10.0.0.1/MyWorks/Solar_video/thn.jpg",
        "full_url": "http://10.0.0.1/MyWorks/Solar_video/timelapse.mp4",
    }
    render_onboard_card(item)

    assert st_mock.video.called, "st.video must be called for a video item"
    video_url = st_mock.video.call_args[0][0]
    assert video_url == item["full_url"]
    # The LAN-access caption must be present.
    caption_calls = [str(c) for c in st_mock.caption.call_args_list]
    assert any("LAN" in c for c in caption_calls), "Video card must include LAN access caption"


def test_fetch_onboard_items_returns_list_on_200(monkeypatch):
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = [
        {
            "name": "img",
            "thumb_url": "http://s/t_thn.jpg",
            "full_url": "http://s/t.jpg",
            "is_video": False,
        }
    ]

    with patch("views.gallery.requests.get", return_value=fake_response):
        result = fetch_onboard_items()

    assert len(result) == 1
    assert result[0]["name"] == "img"


def test_fetch_onboard_items_returns_empty_on_error(monkeypatch):
    with patch("views.gallery.requests.get", side_effect=Exception("boom")):
        result = fetch_onboard_items()
    assert result == []


def test_fetch_onboard_items_returns_empty_on_non_200(monkeypatch):
    fake_response = MagicMock()
    fake_response.status_code = 502
    fake_response.text = "scope offline"

    with patch("views.gallery.requests.get", return_value=fake_response):
        result = fetch_onboard_items()

    assert result == []
