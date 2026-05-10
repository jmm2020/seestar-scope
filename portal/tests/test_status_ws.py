"""Tests for status_ws broadcaster and REST endpoint."""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.routers.status_ws import MessageType, router, stack_progress_broadcaster


def _make_endpoint_client(state_cls):
    app = FastAPI()
    app.include_router(router)
    app.state = state_cls()
    return TestClient(app)


def _make_view_data(count=5, lapse_ms=60000, stage="Stack", mode="star", target="M42"):
    return {
        "View": {
            "stage": stage,
            "Stack": {"count": count},
            "lapse_ms": lapse_ms,
            "mode": mode,
            "target_name": target,
        }
    }


# ---------------------------------------------------------------------------
# stack_progress_broadcaster tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_broadcaster_builds_correct_state():
    """State dict keys and computed values are correct on first broadcast."""
    alpaca = MagicMock()
    alpaca.get_view_state.return_value = _make_view_data(count=9, lapse_ms=90000, stage="Stack")

    app_state = MagicMock()
    app_state.alpaca = alpaca
    request = MagicMock()
    request.app.state = app_state

    broadcast_calls = []

    with patch("backend.routers.status_ws.manager") as mock_mgr, patch(
        "asyncio.sleep", new=AsyncMock(side_effect=StopAsyncIteration)
    ):
        mock_mgr.broadcast = AsyncMock(side_effect=lambda m: broadcast_calls.append(m))
        try:
            await stack_progress_broadcaster(request)
        except StopAsyncIteration:
            pass

    stack_msgs = [m for m in broadcast_calls if m["type"] == MessageType.STACK_PROGRESS]
    assert len(stack_msgs) == 1
    data = stack_msgs[0]["data"]
    assert data["frame_count"] == 9
    assert data["snr_estimate"] == 3.0  # sqrt(9)
    assert data["elapsed_s"] == 90.0  # 90000ms / 1000
    assert data["is_stacking"] is True
    assert data["target"] == "M42"
    assert "captured_at" in data
    assert app_state.live_stack_state == data


@pytest.mark.asyncio
async def test_broadcaster_suppresses_duplicate_broadcasts():
    """No second broadcast emitted when frame_count and is_stacking unchanged."""
    alpaca = MagicMock()
    alpaca.get_view_state.return_value = _make_view_data(count=5)

    request = MagicMock()
    request.app.state.alpaca = alpaca

    broadcast_calls = []
    call_count = 0

    async def mock_sleep(_):
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            raise StopAsyncIteration

    with patch("backend.routers.status_ws.manager") as mock_mgr, patch(
        "asyncio.sleep", new=AsyncMock(side_effect=mock_sleep)
    ):
        mock_mgr.broadcast = AsyncMock(side_effect=lambda m: broadcast_calls.append(m))
        try:
            await stack_progress_broadcaster(request)
        except StopAsyncIteration:
            pass

    # Two identical polls → only one STACK_PROGRESS broadcast
    stack_msgs = [m for m in broadcast_calls if m["type"] == MessageType.STACK_PROGRESS]
    assert len(stack_msgs) == 1


@pytest.mark.asyncio
async def test_broadcaster_handles_none_view_data():
    """No broadcast and no exception when get_view_state() returns None."""
    alpaca = MagicMock()
    alpaca.get_view_state.return_value = None

    request = MagicMock()
    request.app.state.alpaca = alpaca

    with patch("backend.routers.status_ws.manager") as mock_mgr, patch(
        "asyncio.sleep", new=AsyncMock(side_effect=StopAsyncIteration)
    ):
        mock_mgr.broadcast = AsyncMock()
        try:
            await stack_progress_broadcaster(request)
        except StopAsyncIteration:
            pass

    mock_mgr.broadcast.assert_not_called()


@pytest.mark.asyncio
async def test_broadcaster_continues_after_exception():
    """Exception from get_view_state() is caught; loop recovers on next iteration."""
    alpaca = MagicMock()
    call_count = 0

    def flaky_view():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ConnectionError("device offline")
        return _make_view_data(count=1)

    alpaca.get_view_state.side_effect = flaky_view
    request = MagicMock()
    request.app.state.alpaca = alpaca

    broadcast_calls = []
    sleep_count = 0

    async def mock_sleep(_):
        nonlocal sleep_count
        sleep_count += 1
        if sleep_count >= 2:
            raise StopAsyncIteration

    with patch("backend.routers.status_ws.manager") as mock_mgr, patch(
        "asyncio.sleep", new=AsyncMock(side_effect=mock_sleep)
    ):
        mock_mgr.broadcast = AsyncMock(side_effect=lambda m: broadcast_calls.append(m))
        try:
            await stack_progress_broadcaster(request)
        except StopAsyncIteration:
            pass

    # Cycle 1: error broadcast; Cycle 2: STACK_PROGRESS broadcast
    error_msgs = [m for m in broadcast_calls if m["type"] == MessageType.ERROR]
    stack_msgs = [m for m in broadcast_calls if m["type"] == MessageType.STACK_PROGRESS]
    assert len(error_msgs) == 1
    assert len(stack_msgs) == 1
    assert stack_msgs[0]["data"]["frame_count"] == 1


@pytest.mark.asyncio
async def test_broadcaster_handles_non_numeric_count():
    """Non-numeric count from firmware falls back gracefully without dropping broadcast."""
    alpaca = MagicMock()
    view = _make_view_data(count=3)
    # Corrupt the count field
    view["View"]["Stack"]["count"] = "N/A"
    alpaca.get_view_state.return_value = view

    request = MagicMock()
    request.app.state.alpaca = alpaca

    broadcast_calls = []

    with patch("backend.routers.status_ws.manager") as mock_mgr, patch(
        "asyncio.sleep", new=AsyncMock(side_effect=StopAsyncIteration)
    ):
        mock_mgr.broadcast = AsyncMock(side_effect=lambda m: broadcast_calls.append(m))
        try:
            await stack_progress_broadcaster(request)
        except StopAsyncIteration:
            pass

    # Should broadcast with frame_count=0 (fallback) rather than crashing
    stack_msgs = [m for m in broadcast_calls if m["type"] == MessageType.STACK_PROGRESS]
    assert len(stack_msgs) == 1
    assert stack_msgs[0]["data"]["frame_count"] == 0


# ---------------------------------------------------------------------------
# GET /api/status/live-stack endpoint tests
# ---------------------------------------------------------------------------


def test_live_stack_endpoint_empty_state():
    """Returns empty state dict when no broadcaster has run yet."""
    class FakeState:
        pass

    client = _make_endpoint_client(FakeState)
    resp = client.get("/api/status/live-stack")
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == {}
    assert "timestamp" in body


def test_live_stack_endpoint_returns_current_state():
    """Returns the last known state dict written by the broadcaster."""
    expected = {"frame_count": 42, "is_stacking": True, "snr_estimate": 6.48}

    class FakeState:
        live_stack_state = expected

    client = _make_endpoint_client(FakeState)
    resp = client.get("/api/status/live-stack")
    assert resp.status_code == 200
    assert resp.json()["state"] == expected
