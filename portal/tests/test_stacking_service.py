"""Tests for StackingService — no hardware, no actual Siril invocation."""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import numpy as np
from PIL import Image


sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.services.stacking_service import (
    StackingConfig,
    StackingResult,
    StackingService,
)


# --- Config defaults --------------------------------------------------------


def test_stacking_config_defaults():
    cfg = StackingConfig()
    assert cfg.target_name == "target"
    assert cfg.exposure_time == 10.0
    assert cfg.gain == 80
    assert cfg.dark_path is None
    assert cfg.flat_path is None
    assert cfg.bias_path is None
    assert cfg.sigma_low == 3.0
    assert cfg.sigma_high == 3.0


# --- Service initial state --------------------------------------------------


def test_stacking_service_initial_state(tmp_path):
    service = StackingService(
        data_root=str(tmp_path / "seestar"),
        gallery_dir=str(tmp_path / "seestar" / "gallery"),
    )
    assert service.is_running is False
    assert service.current_result is None
    assert service.frame_count == 0
    assert service.session_id is None
    assert service.progress == 0.0


# --- Session lifecycle ------------------------------------------------------


def test_start_session_resets_state(tmp_path):
    service = StackingService(
        data_root=str(tmp_path / "seestar"),
        gallery_dir=str(tmp_path / "seestar" / "gallery"),
    )
    service._frame_paths = ["/old/frame1.png", "/old/frame2.png"]
    service._session_id = "old-session"

    new_id = service.start_session(StackingConfig(target_name="m31"))

    assert new_id != "old-session"
    assert service.session_id == new_id
    assert service.frame_count == 0
    assert service.config.target_name == "m31"


def test_add_frame_increments_count(tmp_path):
    service = StackingService(
        data_root=str(tmp_path / "seestar"),
        gallery_dir=str(tmp_path / "seestar" / "gallery"),
    )
    service.start_session()
    assert service.add_frame("/captures/frame1.png") is True
    assert service.add_frame("/captures/frame2.png") is True
    assert service.frame_count == 2


def test_add_frame_when_no_session(tmp_path):
    service = StackingService(
        data_root=str(tmp_path / "seestar"),
        gallery_dir=str(tmp_path / "seestar" / "gallery"),
    )
    assert service.add_frame("/captures/frame.png") is False
    assert service.frame_count == 0


# --- Script generation ------------------------------------------------------


def test_generate_stacking_script_no_calibration(tmp_path):
    service = StackingService(
        data_root=str(tmp_path / "seestar"),
        gallery_dir=str(tmp_path / "seestar" / "gallery"),
    )
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    script_path = session_dir / "stack.ssf"

    service._generate_stacking_script(
        script_path=script_path,
        session_dir=session_dir,
        num_files=5,
        config=StackingConfig(target_name="m42"),
    )

    contents = script_path.read_text()
    assert "convert" in contents
    assert "register" in contents
    assert "stack" in contents
    assert "calibrate" not in contents
    assert "m42_stacked" in contents


def test_generate_stacking_script_with_calibration(tmp_path):
    service = StackingService(
        data_root=str(tmp_path / "seestar"),
        gallery_dir=str(tmp_path / "seestar" / "gallery"),
    )
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    script_path = session_dir / "stack.ssf"

    service._generate_stacking_script(
        script_path=script_path,
        session_dir=session_dir,
        num_files=5,
        config=StackingConfig(
            target_name="m31",
            dark_path="/cal/dark.fit",
            flat_path="/cal/flat.fit",
        ),
    )

    contents = script_path.read_text()
    assert "calibrate" in contents
    assert "/cal/dark.fit" in contents
    assert "/cal/flat.fit" in contents


# --- run_stacking error path ------------------------------------------------


def test_run_stacking_no_frames(tmp_path):
    service = StackingService(
        data_root=str(tmp_path / "seestar"),
        gallery_dir=str(tmp_path / "seestar" / "gallery"),
    )
    service.start_session()
    result = asyncio.run(service.run_stacking())
    assert result.success is False
    assert "No frames" in (result.error_message or "")


def test_run_stacking_subprocess_failure(tmp_path, monkeypatch):
    """Mock asyncio.create_subprocess_exec to return nonzero exit; verify failure."""
    service = StackingService(
        data_root=str(tmp_path / "seestar"),
        gallery_dir=str(tmp_path / "seestar" / "gallery"),
    )

    # Pre-populate with a fake "frame" — bypass real PIL conversion by
    # monkeypatching _convert_frames_to_fits to return a dummy path.
    fake_session_dir = tmp_path / "seestar" / "processed" / "x"
    fake_session_dir.mkdir(parents=True, exist_ok=True)
    fake_fit = fake_session_dir / "light_0001.fit"
    fake_fit.write_bytes(b"dummy")

    monkeypatch.setattr(
        service,
        "_convert_frames_to_fits",
        lambda paths, session_dir: [fake_fit],
    )

    # Mock the subprocess to return an error code.
    fake_proc = MagicMock()
    fake_proc.communicate = AsyncMock(return_value=(b"out", b"siril boom"))
    fake_proc.returncode = 1
    fake_proc.kill = MagicMock()

    async def fake_create_subprocess_exec(*args, **kwargs):
        return fake_proc

    monkeypatch.setattr(
        "asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    service.start_session(StackingConfig(target_name="x"))
    service.add_frame(str(fake_fit))

    result = asyncio.run(service.run_stacking())

    assert result.success is False
    assert "siril-cli exited" in (result.error_message or "") or "code 1" in (result.error_message or "")
    assert service.is_running is False  # finally block resets it


# --- StackingResult dataclass ----------------------------------------------


def test_stacking_result_construction():
    r = StackingResult(success=True, session_id="abc", frame_count=10)
    assert r.success is True
    assert r.session_id == "abc"
    assert r.frame_count == 10
    assert r.output_fits is None
    assert r.duration_seconds == 0.0


# --- Happy-path run_stacking ------------------------------------------------


def test_run_stacking_happy_path(tmp_path, monkeypatch):
    """Mock Siril subprocess + pre-create output files; verify gallery move and result."""
    gallery = tmp_path / "gallery"
    gallery.mkdir()
    service = StackingService(
        data_root=str(tmp_path / "seestar"),
        gallery_dir=str(gallery),
    )
    session_id = service.start_session(StackingConfig(target_name="m42"))
    service.add_frame("/fake/frame.png")

    # Pre-create expected Siril output in session_dir
    session_dir = service._processed_dir / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "m42_stacked.fit").write_bytes(b"FITS")
    (session_dir / "m42_stacked.jpg").write_bytes(b"JPEG")

    fake_fit = session_dir / "light_0001.fit"
    fake_fit.write_bytes(b"FITS")
    monkeypatch.setattr(service, "_convert_frames_to_fits", lambda p, d: [fake_fit])

    fake_proc = MagicMock()
    fake_proc.communicate = AsyncMock(return_value=(b"done", b""))
    fake_proc.returncode = 0
    monkeypatch.setattr("asyncio.create_subprocess_exec", AsyncMock(return_value=fake_proc))

    result = asyncio.run(service.run_stacking())

    assert result.success is True
    assert result.output_fits == str(gallery / f"m42_{session_id}.fit")
    assert Path(result.output_fits).exists()
    assert service.is_running is False
    assert service.progress == 1.0


# --- _convert_frames_to_fits unit tests ------------------------------------


def test_convert_fits_passthrough(tmp_path):
    """Existing .fit files are copied as-is without conversion."""
    service = StackingService(
        data_root=str(tmp_path), gallery_dir=str(tmp_path / "gallery")
    )
    src = tmp_path / "frame.fit"
    src.write_bytes(b"FAKEFIT")
    session_dir = tmp_path / "session"
    session_dir.mkdir()

    result = service._convert_frames_to_fits([str(src)], session_dir)

    assert len(result) == 1
    assert result[0].name == "light_0001.fit"
    assert result[0].read_bytes() == b"FAKEFIT"


def test_convert_png_to_fits(tmp_path):
    """PNG frames are converted to FITS via PIL/astropy."""
    service = StackingService(
        data_root=str(tmp_path), gallery_dir=str(tmp_path / "gallery")
    )
    img = Image.fromarray(np.zeros((4, 4, 3), dtype=np.uint8))
    src = tmp_path / "frame.png"
    img.save(str(src))
    session_dir = tmp_path / "session"
    session_dir.mkdir()

    result = service._convert_frames_to_fits([str(src)], session_dir)

    assert len(result) == 1
    assert result[0].suffix == ".fit"
    assert result[0].exists()


def test_convert_skips_bad_frame(tmp_path):
    """A corrupt frame is skipped; valid frames still convert."""
    service = StackingService(
        data_root=str(tmp_path), gallery_dir=str(tmp_path / "gallery")
    )
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image")

    img = Image.fromarray(np.zeros((4, 4, 3), dtype=np.uint8))
    good = tmp_path / "good.png"
    img.save(str(good))

    session_dir = tmp_path / "session"
    session_dir.mkdir()

    result = service._convert_frames_to_fits([str(bad), str(good)], session_dir)

    assert len(result) == 1
    assert result[0].name == "light_0002.fit"


# --- abort() tests ---------------------------------------------------------


def test_abort_when_not_running(tmp_path):
    """abort() returns False when no stacking is in progress."""
    service = StackingService(
        data_root=str(tmp_path / "seestar"),
        gallery_dir=str(tmp_path / "gallery"),
    )
    assert service.abort() is False


def test_abort_requested_propagates_to_failure(tmp_path, monkeypatch):
    """Setting abort before stacking produces a failure result."""
    service = StackingService(
        data_root=str(tmp_path / "seestar"),
        gallery_dir=str(tmp_path / "gallery"),
    )
    service.start_session()
    service.add_frame("/fake/frame.fit")

    fake_fit = tmp_path / "light_0001.fit"
    fake_fit.write_bytes(b"FITS")
    monkeypatch.setattr(service, "_convert_frames_to_fits", lambda p, d: [fake_fit])

    original_generate = service._generate_stacking_script

    def abort_then_generate(*args, **kwargs):
        service._abort_requested = True
        return original_generate(*args, **kwargs)

    monkeypatch.setattr(service, "_generate_stacking_script", abort_then_generate)

    result = asyncio.run(service.run_stacking())

    assert result.success is False
    assert "Aborted" in (result.error_message or "")
    assert service.is_running is False


# --- asyncio.TimeoutError path test ----------------------------------------


def test_run_stacking_timeout(tmp_path, monkeypatch):
    """Timeout produces a failure result with is_running reset to False."""
    service = StackingService(
        data_root=str(tmp_path / "seestar"),
        gallery_dir=str(tmp_path / "gallery"),
    )
    service.start_session(StackingConfig(target_name="m31"))
    service.add_frame("/fake/frame.fit")

    fake_fit = tmp_path / "light_0001.fit"
    fake_fit.write_bytes(b"FITS")
    monkeypatch.setattr(service, "_convert_frames_to_fits", lambda p, d: [fake_fit])

    async def raise_timeout(*args, **kwargs):
        raise asyncio.TimeoutError()

    monkeypatch.setattr(service, "_run_siril_async", raise_timeout)

    result = asyncio.run(service.run_stacking())

    assert result.success is False
    assert "timed out" in (result.error_message or "").lower()
    assert service.is_running is False
