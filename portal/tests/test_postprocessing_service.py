"""Unit tests for portal/backend/services/postprocessing_service.py"""

import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.services.postprocessing_service import PostprocessingService


def _write_png(path: Path, value: int = 128, size: tuple = (8, 8)) -> None:
    Image.fromarray(
        np.full((*size, 3), value, dtype=np.uint8), "RGB"
    ).save(str(path))


# ---------------------------------------------------------------------------
# Calibration frame lifecycle
# ---------------------------------------------------------------------------

def test_store_and_discover_calibration_frame(tmp_path):
    svc = PostprocessingService(tmp_path)
    src = tmp_path / "dark.png"
    _write_png(src)

    assert svc.store_calibration_frame("dark", str(src)) is True
    info = svc.get_calibration_info()
    assert info["dark"]["exists"] is True
    assert info["flat"]["exists"] is False
    assert info["bias"]["exists"] is False


def test_store_calibration_frame_invalid_type(tmp_path):
    svc = PostprocessingService(tmp_path)
    src = tmp_path / "x.png"
    _write_png(src)
    assert svc.store_calibration_frame("cosmic_ray", str(src)) is False


def test_store_calibration_frame_missing_source(tmp_path):
    svc = PostprocessingService(tmp_path)
    assert svc.store_calibration_frame("dark", str(tmp_path / "nonexistent.png")) is False


def test_delete_calibration_frame(tmp_path):
    svc = PostprocessingService(tmp_path)
    src = tmp_path / "flat.png"
    _write_png(src)
    svc.store_calibration_frame("flat", str(src))

    assert svc.delete_calibration_frame("flat") is True
    assert svc.get_calibration_info()["flat"]["exists"] is False


def test_delete_nonexistent_calibration_frame(tmp_path):
    svc = PostprocessingService(tmp_path)
    assert svc.delete_calibration_frame("dark") is False


def test_discover_existing_masters_on_restart(tmp_path):
    svc1 = PostprocessingService(tmp_path)
    src = tmp_path / "bias.png"
    _write_png(src)
    svc1.store_calibration_frame("bias", str(src))

    # New service instance should discover the stored master
    svc2 = PostprocessingService(tmp_path)
    assert svc2.get_calibration_info()["bias"]["exists"] is True


# ---------------------------------------------------------------------------
# apply_pipeline
# ---------------------------------------------------------------------------

def test_apply_pipeline_missing_source_returns_failure(tmp_path):
    svc = PostprocessingService(tmp_path)
    result = svc.apply_pipeline(str(tmp_path / "nonexistent.png"), {})
    assert result.success is False
    assert result.error_message is not None


def test_apply_pipeline_all_black_sets_failure(tmp_path):
    svc = PostprocessingService(tmp_path)
    src = tmp_path / "img.png"
    _write_png(src, value=100)

    black = Image.fromarray(np.zeros((8, 8, 3), dtype=np.uint8), "RGB")
    with patch("utils.image_enhancement.run_pipeline", return_value=black):
        result = svc.apply_pipeline(str(src), {"stretch": "none"})

    assert result.success is False
    assert result.error_message is not None
    assert "all black" in (result.error_message or "").lower()


def test_apply_pipeline_success(tmp_path):
    svc = PostprocessingService(tmp_path)
    src = tmp_path / "img.png"
    _write_png(src, value=128)

    result = svc.apply_pipeline(str(src), {"stretch": "none"})
    assert result.success is True
    assert result.output_path is not None
    assert Path(result.output_path).exists()


def test_apply_pipeline_output_always_in_processed_dir(tmp_path):
    svc = PostprocessingService(tmp_path)
    src = tmp_path / "img.png"
    _write_png(src, value=128)

    result = svc.apply_pipeline(str(src), {"stretch": "none"})
    assert result.success is True
    assert str(svc.processed_dir) in result.output_path


# ---------------------------------------------------------------------------
# Flat near-zero guard
# ---------------------------------------------------------------------------

def test_apply_calibration_skips_shape_mismatch(tmp_path):
    svc = PostprocessingService(tmp_path)
    # Store a flat with a different size
    flat_path = tmp_path / "calibration" / "master_flat.png"
    flat_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(
        np.full((4, 4, 3), 200, dtype=np.uint8), "RGB"
    ).save(str(flat_path))
    svc._calibration.flat_path = str(flat_path)

    # 8x8 image — shape mismatch → calibration skips, no crash
    arr = np.random.default_rng(0).uniform(0, 1, (8, 8, 3))
    result = svc._apply_calibration(arr)
    assert result.shape == (8, 8, 3)
