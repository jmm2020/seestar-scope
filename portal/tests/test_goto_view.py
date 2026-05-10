"""Tests for goto view helper functions."""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
from views.goto import _check_alp_reachable, _poll_state_transition


def test_alp_reachable_when_200():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    with patch("views.goto.requests.get", return_value=mock_resp):
        assert _check_alp_reachable() is True


def test_alp_unreachable_on_connection_error():
    with patch("views.goto.requests.get",
               side_effect=requests.exceptions.ConnectionError("refused")):
        assert _check_alp_reachable() is False


def test_alp_unreachable_on_timeout():
    with patch("views.goto.requests.get",
               side_effect=requests.exceptions.Timeout("timed out")):
        assert _check_alp_reachable() is False


def test_alp_unreachable_on_non_200():
    mock_resp = MagicMock()
    mock_resp.status_code = 503
    with patch("views.goto.requests.get", return_value=mock_resp):
        assert _check_alp_reachable() is False


# --- _poll_state_transition tests ---

def _make_alpaca(statuses):
    mock = MagicMock()
    mock.get_telescope_status.side_effect = statuses
    return mock


def test_poll_returns_true_when_predicate_satisfied_immediately():
    alpaca = _make_alpaca([{"at_park": True}])
    with patch("views.goto.time.sleep"):
        result = _poll_state_transition(alpaca, lambda s: s.get("at_park"), timeout_s=5)
    assert result is True


def test_poll_returns_true_after_n_polls():
    alpaca = _make_alpaca([{"at_park": False}, {"at_park": False}, {"at_park": True}])
    times = iter([0, 1, 2, 3])
    with patch("views.goto.time.time", side_effect=times), \
         patch("views.goto.time.sleep"):
        result = _poll_state_transition(alpaca, lambda s: s.get("at_park"), timeout_s=10)
    assert result is True


def test_poll_returns_false_on_timeout():
    alpaca = _make_alpaca([{"at_park": False}] * 100)
    times = iter([0, 20])
    with patch("views.goto.time.time", side_effect=times), \
         patch("views.goto.time.sleep"):
        result = _poll_state_transition(alpaca, lambda s: s.get("at_park"), timeout_s=5)
    assert result is False


def test_poll_swallows_exceptions_and_retries():
    alpaca = _make_alpaca([Exception("network error"), {"at_park": True}])
    times = iter([0, 1, 2])
    with patch("views.goto.time.time", side_effect=times), \
         patch("views.goto.time.sleep"):
        result = _poll_state_transition(alpaca, lambda s: s.get("at_park"), timeout_s=10)
    assert result is True


def test_poll_returns_false_when_all_calls_raise():
    alpaca = _make_alpaca([Exception("refused")] * 100)
    times = iter([0, 20])
    with patch("views.goto.time.time", side_effect=times), \
         patch("views.goto.time.sleep"):
        result = _poll_state_transition(alpaca, lambda s: s.get("at_park"), timeout_s=5)
    assert result is False


def test_poll_fail_closed_on_absent_keys():
    # When status keys are absent, predicates must not give false positives
    alpaca = _make_alpaca([{}, {"at_park": True}])
    times = iter([0, 1, 2])
    with patch("views.goto.time.time", side_effect=times), \
         patch("views.goto.time.sleep"):
        result = _poll_state_transition(
            alpaca, lambda s: s.get("at_park", False) is True, timeout_s=10
        )
    assert result is True
