"""Tests for SessionsClient - mocked HTTP, no live backend required."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

from clients.sessions_client import SessionsClient


def _ok(json_payload):
    r = MagicMock()
    r.status_code = 200
    r.json.return_value = json_payload
    r.raise_for_status = MagicMock()
    return r


def test_default_backend_url():
    c = SessionsClient()
    assert c.backend_url == "http://localhost:8503"


def test_explicit_backend_url():
    c = SessionsClient(backend_url="http://other:9999")
    assert c.backend_url == "http://other:9999"


def test_start_session_verify_after_dispatch():
    c = SessionsClient()
    payload = {"id": 1, "target_name": "M31", "started_at": "2026-01-01T00:00:00", "ended_at": None}
    with (
        patch.object(c.session, "post", return_value=_ok(payload)) as p,
        patch.object(c.session, "get", return_value=_ok(payload)) as g,
    ):
        result = c.start_session("M31", target_ra=0.7, target_dec=41.0)
    assert result == payload
    p.assert_called_once()
    g.assert_called_once()  # verify-after-dispatch


def test_start_session_returns_none_on_post_failure():
    c = SessionsClient()
    with patch.object(
        c.session, "post", side_effect=requests.exceptions.ConnectionError("refused")
    ):
        assert c.start_session("M31") is None


def test_end_session_verify_ended_at_set():
    c = SessionsClient()
    end_payload = {
        "id": 1,
        "target_name": "M31",
        "started_at": "x",
        "ended_at": "2026-01-01T01:00:00",
    }
    with (
        patch.object(c.session, "post", return_value=_ok(end_payload)),
        patch.object(c.session, "get", return_value=_ok(end_payload)),
    ):
        result = c.end_session(1)
    assert result is not None
    assert isinstance(result.get("ended_at"), str) and result["ended_at"] is not None


def test_end_session_returns_none_when_ended_at_missing():
    c = SessionsClient()
    end_payload = {"id": 1, "target_name": "M31", "started_at": "x", "ended_at": None}
    with (
        patch.object(c.session, "post", return_value=_ok(end_payload)),
        patch.object(c.session, "get", return_value=_ok(end_payload)),
    ):
        assert c.end_session(1) is None


def test_add_frame_no_verify():
    c = SessionsClient()
    frame_payload = {"id": 1, "session_id": 1, "filename": "f.fits"}
    with (
        patch.object(c.session, "post", return_value=_ok(frame_payload)) as p,
        patch.object(c.session, "get") as g,
    ):
        result = c.add_frame(1, "f.fits", 10.0, 80, "L")
    assert result == frame_payload
    p.assert_called_once()
    g.assert_not_called()  # No verify on per-frame writes


def test_add_frame_returns_none_on_failure():
    c = SessionsClient()
    with patch.object(c.session, "post", side_effect=requests.exceptions.Timeout()):
        assert c.add_frame(1, "f.fits", 10.0, 80, "L") is None


def test_list_sessions_returns_list():
    c = SessionsClient()
    payload = [{"id": 1, "target_name": "M31"}]
    with patch.object(c.session, "get", return_value=_ok(payload)):
        assert c.list_sessions() == payload


def test_list_sessions_returns_none_on_failure():
    c = SessionsClient()
    with patch.object(c.session, "get", side_effect=requests.exceptions.ConnectionError()):
        assert c.list_sessions() is None


def test_get_frames_returns_list():
    c = SessionsClient()
    payload = [{"id": 1, "session_id": 1, "filename": "f.fits"}]
    with patch.object(c.session, "get", return_value=_ok(payload)):
        assert c.get_frames(1) == payload


def test_backend_url_env_var(monkeypatch):
    monkeypatch.setenv("BACKEND_URL", "http://docker-host:8503")
    c = SessionsClient()
    assert c.backend_url == "http://docker-host:8503"


def test_get_session_returns_dict():
    c = SessionsClient()
    payload = {"id": 5, "target_name": "M31", "started_at": "2026-01-01T00:00:00", "ended_at": None}
    with patch.object(c.session, "get", return_value=_ok(payload)):
        result = c.get_session(5)
    assert result == payload


def test_get_session_returns_none_on_failure():
    c = SessionsClient()
    with patch.object(c.session, "get", side_effect=requests.exceptions.ConnectionError()):
        assert c.get_session(5) is None


def test_post_returns_none_on_non_json_response():
    c = SessionsClient()
    bad_resp = _ok({})
    bad_resp.json.side_effect = ValueError("not json")
    with patch.object(c.session, "post", return_value=bad_resp):
        assert c.start_session("M31") is None


def test_get_returns_none_on_non_json_response():
    c = SessionsClient()
    bad_resp = _ok({})
    bad_resp.json.side_effect = ValueError("not json")
    with patch.object(c.session, "get", return_value=bad_resp):
        assert c.list_sessions() is None
