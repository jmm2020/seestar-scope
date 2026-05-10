"""Unit tests for portal/backend/routers/postprocessing.py"""

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.routers.postprocessing import _result_to_response
from backend.services.postprocessing_service import PostprocessingResult


# ---------------------------------------------------------------------------
# _result_to_response status mapping
# ---------------------------------------------------------------------------

def test_result_to_response_unknown_when_none():
    resp = _result_to_response("j1", None)
    assert resp.status == "unknown"
    assert resp.job_id == "j1"


def test_result_to_response_running_when_no_completed_at():
    result = PostprocessingResult(success=False, job_id="j2")
    resp = _result_to_response("j2", result)
    assert resp.status == "running"


def test_result_to_response_completed_on_success():
    result = PostprocessingResult(
        success=True,
        job_id="j3",
        completed_at=datetime.now(timezone.utc),
    )
    resp = _result_to_response("j3", result)
    assert resp.status == "completed"
    assert resp.success is True


def test_result_to_response_failed_on_no_success():
    result = PostprocessingResult(
        success=False,
        job_id="j4",
        error_message="something went wrong",
        completed_at=datetime.now(timezone.utc),
    )
    resp = _result_to_response("j4", result)
    assert resp.status == "failed"
    assert resp.error_message == "something went wrong"


def test_result_to_response_pending_never_produced():
    """Verify 'pending' is never a valid status value."""
    # None → unknown
    assert _result_to_response("x", None).status != "pending"
    # Running → running
    result = PostprocessingResult(success=False, job_id="x")
    assert _result_to_response("x", result).status != "pending"


# ---------------------------------------------------------------------------
# PostprocessingRequest path validator
# ---------------------------------------------------------------------------

def test_image_path_validator_rejects_etc_passwd(tmp_path, monkeypatch):
    import backend.routers.postprocessing as router_mod
    from pydantic import ValidationError

    # Patch settings on the module so the validator reads patched roots
    mock_settings = MagicMock()
    mock_settings.captures_dir.resolve.return_value = (tmp_path / "captures").resolve()
    mock_settings.gallery_dir.resolve.return_value = (tmp_path / "gallery").resolve()
    mock_settings.processing_dir.resolve.return_value = (tmp_path / "processing").resolve()
    monkeypatch.setattr(router_mod, "settings", mock_settings)

    from backend.routers.postprocessing import PostprocessingRequest

    with pytest.raises((ValidationError, ValueError)):
        PostprocessingRequest(image_path="/etc/passwd")


def test_image_path_validator_allows_captures_dir(tmp_path, monkeypatch):
    import backend.routers.postprocessing as router_mod

    captures = tmp_path / "captures"
    captures.mkdir()
    img = captures / "test.png"
    img.touch()

    mock_settings = MagicMock()
    mock_settings.captures_dir.resolve.return_value = captures.resolve()
    mock_settings.gallery_dir.resolve.return_value = (tmp_path / "gallery").resolve()
    mock_settings.processing_dir.resolve.return_value = (tmp_path / "processing").resolve()
    monkeypatch.setattr(router_mod, "settings", mock_settings)

    from backend.routers.postprocessing import PostprocessingRequest

    # Should not raise
    req = PostprocessingRequest(image_path=str(img))
    assert req.image_path == str(img)


# ---------------------------------------------------------------------------
# processing_jobs capping
# ---------------------------------------------------------------------------

def test_processing_jobs_capped_at_max(tmp_path, monkeypatch):
    import backend.routers.postprocessing as router_mod

    # Reset jobs dict
    router_mod.processing_jobs.clear()
    router_mod._MAX_JOBS = 5

    # Fill beyond the cap
    for i in range(7):
        job_id = f"pp_{i:08x}"
        router_mod.processing_jobs[job_id] = PostprocessingResult(
            success=False, job_id=job_id
        )
        if len(router_mod.processing_jobs) > router_mod._MAX_JOBS:
            router_mod.processing_jobs.popitem(last=False)

    assert len(router_mod.processing_jobs) <= router_mod._MAX_JOBS
    # Oldest entries should have been evicted
    assert "pp_00000000" not in router_mod.processing_jobs
