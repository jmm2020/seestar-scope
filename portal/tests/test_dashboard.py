"""Tests for dashboard isinstance guards — no live Streamlit session required."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

# Stub heavy/unavailable packages before any project imports resolve them.
# dashboard.py → utils.coordinates (via utils/__init__ → utils.image_processing → numpy)
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

import pytest  # noqa: E402

from views.dashboard import _render_device_health, _render_view_state  # noqa: E402


@pytest.fixture()
def mock_st(monkeypatch):
    """Patch the streamlit module used inside dashboard after import."""
    st = MagicMock()
    monkeypatch.setattr("views.dashboard.st", st)
    return st


def test_render_device_health_string_state_shows_warning(mock_st):
    """Non-dict state (error string) must show a warning — not crash on .get()."""
    alpaca = MagicMock()
    alpaca.get_device_state.return_value = "Error: Exceeded allotted wait time"

    _render_device_health(alpaca)

    mock_st.warning.assert_called_once()
    mock_st.metric.assert_not_called()


def test_render_device_health_none_state_shows_warning(mock_st):
    """None return (normal timeout/error path) also shows warning and exits cleanly."""
    alpaca = MagicMock()
    alpaca.get_device_state.return_value = None

    _render_device_health(alpaca)

    mock_st.warning.assert_called_once()
    mock_st.metric.assert_not_called()


def test_render_view_state_none_shows_info(mock_st):
    """None view_data shows info message and does not crash."""
    alpaca = MagicMock()
    alpaca.get_view_state.return_value = None

    _render_view_state(alpaca)

    mock_st.info.assert_called_once()


def test_render_view_state_string_shows_info(mock_st):
    """Non-dict view_data (error string) shows info message and does not crash."""
    alpaca = MagicMock()
    alpaca.get_view_state.return_value = "Error: Exceeded allotted wait time"

    _render_view_state(alpaca)

    mock_st.info.assert_called_once()
    mock_st.metric.assert_not_called()
