"""Tests for imaging view service-down banner and disabled controls."""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from clients.alpaca_client import AlpacaClient


def _expander_mock():
    """Mock for st.expander that supports `with` block."""
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=None)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


def test_is_alp_available_called_in_render(monkeypatch):
    """render_imaging() must call is_alp_available() once."""
    import streamlit as st

    client = AlpacaClient()
    monkeypatch.setattr(client, "is_alp_available", MagicMock(return_value=True))

    with (
        patch.object(st, "header"),
        patch.object(st, "error"),
        patch.object(st, "divider"),
        patch("views.imaging._render_live_view"),
        patch("views.imaging._render_session_status", return_value=(None, False)),
        patch("views.imaging._render_stacking_controls"),
        patch("views.imaging._render_stack_settings"),
        patch("views.imaging._render_camera_status"),
        patch("views.imaging._render_exposure_controls", return_value=(1000, 80)),
        patch("views.imaging._render_capture_controls"),
        patch("views.imaging._poll_exposure"),
        patch("views.imaging._render_preview_and_save"),
        patch.object(st, "expander", side_effect=lambda *a, **kw: _expander_mock()),
    ):
        from views.imaging import render_imaging

        render_imaging(client, MagicMock())

    client.is_alp_available.assert_called_once()


def test_banner_shown_when_alp_down(monkeypatch):
    """st.error() must be called when is_alp_available() returns False."""
    import streamlit as st

    client = AlpacaClient()
    monkeypatch.setattr(client, "is_alp_available", MagicMock(return_value=False))

    error_calls = []
    with (
        patch.object(st, "header"),
        patch.object(st, "error", side_effect=lambda msg: error_calls.append(msg)),
        patch.object(st, "divider"),
        patch("views.imaging._render_live_view"),
        patch("views.imaging._render_session_status", return_value=(None, False)),
        patch("views.imaging._render_stacking_controls"),
        patch("views.imaging._render_stack_settings"),
        patch("views.imaging._render_camera_status"),
        patch("views.imaging._render_exposure_controls", return_value=(1000, 80)),
        patch("views.imaging._render_capture_controls"),
        patch("views.imaging._poll_exposure"),
        patch("views.imaging._render_preview_and_save"),
        patch.object(st, "expander", side_effect=lambda *a, **kw: _expander_mock()),
    ):
        from views.imaging import render_imaging

        render_imaging(client, MagicMock())

    assert len(error_calls) == 1
    assert "seestar_alp" in error_calls[0]
    assert client.alp_base_url in error_calls[0]


def test_no_banner_when_alp_up(monkeypatch):
    """st.error() must NOT be called when is_alp_available() returns True."""
    import streamlit as st

    client = AlpacaClient()
    monkeypatch.setattr(client, "is_alp_available", MagicMock(return_value=True))

    error_calls = []
    with (
        patch.object(st, "header"),
        patch.object(st, "error", side_effect=lambda msg: error_calls.append(msg)),
        patch.object(st, "divider"),
        patch("views.imaging._render_live_view"),
        patch("views.imaging._render_session_status", return_value=(None, False)),
        patch("views.imaging._render_stacking_controls"),
        patch("views.imaging._render_stack_settings"),
        patch("views.imaging._render_camera_status"),
        patch("views.imaging._render_exposure_controls", return_value=(1000, 80)),
        patch("views.imaging._render_capture_controls"),
        patch("views.imaging._poll_exposure"),
        patch("views.imaging._render_preview_and_save"),
        patch.object(st, "expander", side_effect=lambda *a, **kw: _expander_mock()),
    ):
        from views.imaging import render_imaging

        render_imaging(client, MagicMock())

    assert len(error_calls) == 0


def test_stacking_controls_receive_alp_available_flag(monkeypatch):
    """render_imaging() must pass alp_available into _render_stacking_controls()."""
    import streamlit as st

    client = AlpacaClient()
    monkeypatch.setattr(client, "is_alp_available", MagicMock(return_value=False))

    captured_args = {}

    def capture(*args, **kwargs):
        captured_args["args"] = args
        captured_args["kwargs"] = kwargs

    with (
        patch.object(st, "header"),
        patch.object(st, "error"),
        patch.object(st, "divider"),
        patch("views.imaging._render_live_view"),
        patch("views.imaging._render_session_status", return_value=(None, False)),
        patch("views.imaging._render_stacking_controls", side_effect=capture),
        patch("views.imaging._render_stack_settings"),
        patch("views.imaging._render_camera_status"),
        patch("views.imaging._render_exposure_controls", return_value=(1000, 80)),
        patch("views.imaging._render_capture_controls"),
        patch("views.imaging._poll_exposure"),
        patch("views.imaging._render_preview_and_save"),
        patch.object(st, "expander", side_effect=lambda *a, **kw: _expander_mock()),
    ):
        from views.imaging import render_imaging

        render_imaging(client, MagicMock())

    assert captured_args["args"][3] is False  # alp_available is the 4th positional arg


def test_live_stack_panel_shown_when_stacking(monkeypatch):
    """_render_live_stack_panel() must be called when is_stacking is True."""
    import streamlit as st

    client = AlpacaClient()
    monkeypatch.setattr(client, "is_alp_available", MagicMock(return_value=True))

    panel_calls = []

    with patch.object(st, "header"), \
         patch.object(st, "divider"), \
         patch.object(st, "error"), \
         patch("views.imaging._render_live_view"), \
         patch("views.imaging._render_session_status", return_value=({}, True)), \
         patch("views.imaging._render_live_stack_panel", side_effect=lambda: panel_calls.append(1)), \
         patch("views.imaging._render_stacking_controls"), \
         patch("views.imaging._render_stack_settings"), \
         patch("views.imaging._render_camera_status"), \
         patch("views.imaging._render_exposure_controls", return_value=(1000, 80)), \
         patch("views.imaging._render_capture_controls"), \
         patch("views.imaging._poll_exposure"), \
         patch("views.imaging._render_preview_and_save"), \
         patch.object(st, "expander", side_effect=lambda *a, **kw: _expander_mock()):
        from views.imaging import render_imaging
        render_imaging(client, MagicMock())

    assert len(panel_calls) == 1


def test_live_stack_panel_hidden_when_not_stacking(monkeypatch):
    """_render_live_stack_panel() must NOT be called when is_stacking is False."""
    import streamlit as st

    client = AlpacaClient()
    monkeypatch.setattr(client, "is_alp_available", MagicMock(return_value=True))

    panel_calls = []

    with patch.object(st, "header"), \
         patch.object(st, "divider"), \
         patch.object(st, "error"), \
         patch("views.imaging._render_live_view"), \
         patch("views.imaging._render_session_status", return_value=(None, False)), \
         patch("views.imaging._render_live_stack_panel", side_effect=lambda: panel_calls.append(1)), \
         patch("views.imaging._render_stacking_controls"), \
         patch("views.imaging._render_stack_settings"), \
         patch("views.imaging._render_camera_status"), \
         patch("views.imaging._render_exposure_controls", return_value=(1000, 80)), \
         patch("views.imaging._render_capture_controls"), \
         patch("views.imaging._poll_exposure"), \
         patch("views.imaging._render_preview_and_save"), \
         patch.object(st, "expander", side_effect=lambda *a, **kw: _expander_mock()):
        from views.imaging import render_imaging
        render_imaging(client, MagicMock())

    assert len(panel_calls) == 0
