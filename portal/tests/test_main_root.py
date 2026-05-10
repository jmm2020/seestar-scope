"""Tests for the root GET / endpoint in main.py."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

for _mod in ("backend.app.services.siril_service", "backend.services.platesolve_service"):
    sys.modules.setdefault(_mod, MagicMock())

from backend.main import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(app)


def test_root_returns_ok():
    resp = client.get("/")
    assert resp.status_code == 200


def test_root_status_ws_has_no_hardcoded_ip():
    body = client.get("/").json()
    assert "192.168" not in body["endpoints"]["status_ws"]
    assert "<host>" in body["endpoints"]["status_ws"]
