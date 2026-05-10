"""Unit tests for sessions view utility functions — no Streamlit required."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from views.sessions import _parse_dt, _session_duration_minutes


def test_parse_dt_valid_iso():
    dt = _parse_dt("2026-01-01T12:00:00")
    assert dt is not None
    assert dt.hour == 12


def test_parse_dt_none_input():
    assert _parse_dt(None) is None


def test_parse_dt_empty_string():
    assert _parse_dt("") is None


def test_parse_dt_invalid_string():
    assert _parse_dt("not-a-date") is None


def test_parse_dt_tz_aware_iso():
    dt = _parse_dt("2026-01-01T12:00:00+00:00")
    assert dt is not None
    assert dt.hour == 12


def test_session_duration_with_both_dates():
    session = {"started_at": "2026-01-01T00:00:00", "ended_at": "2026-01-01T01:30:00"}
    assert _session_duration_minutes(session) == 90.0


def test_session_duration_open_session_returns_none():
    session = {"started_at": "2026-01-01T00:00:00", "ended_at": None}
    assert _session_duration_minutes(session) is None


def test_session_duration_missing_started_at():
    session = {"ended_at": "2026-01-01T01:00:00"}
    assert _session_duration_minutes(session) is None
