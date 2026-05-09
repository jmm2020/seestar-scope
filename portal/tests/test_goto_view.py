"""Tests for goto view helper functions."""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
from views.goto import _check_alp_reachable


def test_alp_reachable_when_200():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    with patch("views.goto.requests.get", return_value=mock_resp):
        assert _check_alp_reachable() is True


def test_alp_unreachable_on_connection_error():
    with patch("views.goto.requests.get",
               side_effect=requests.exceptions.ConnectionError("refused")):
        assert _check_alp_reachable() is False


def test_alp_unreachable_on_non_200():
    mock_resp = MagicMock()
    mock_resp.status_code = 503
    with patch("views.goto.requests.get", return_value=mock_resp):
        assert _check_alp_reachable() is False
