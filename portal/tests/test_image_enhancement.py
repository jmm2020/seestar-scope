"""Unit tests for portal/utils/image_enhancement.py"""

import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.image_enhancement import (
    balance_color,
    run_pipeline,
    stretch_arcsinh,
    stretch_ghs,
    stretch_histogram,
    stretch_stf,
)


def _rand_image(shape=(32, 32, 3), seed=0) -> np.ndarray:
    return np.random.default_rng(seed).uniform(0, 1, shape)


def _rand_pil(size=(16, 16), mode="RGB", seed=42) -> Image.Image:
    arr = (np.random.default_rng(seed).uniform(0, 1, (*size, 3)) * 255).astype(np.uint8)
    if mode == "L":
        arr = arr[:, :, 0]
    return Image.fromarray(arr, mode=mode)


# ---------------------------------------------------------------------------
# Output-range invariant: all stretch functions must stay in [0, 1]
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fn", [stretch_histogram, stretch_stf, stretch_arcsinh])
def test_stretch_output_range_rgb(fn):
    data = _rand_image()
    out = fn(data)
    assert out.min() >= 0.0
    assert out.max() <= 1.0


@pytest.mark.parametrize("fn", [stretch_histogram, stretch_stf, stretch_arcsinh])
def test_stretch_output_range_mono(fn):
    data = _rand_image((32, 32))
    out = fn(data)
    assert out.min() >= 0.0
    assert out.max() <= 1.0


# ---------------------------------------------------------------------------
# GHS-specific tests
# ---------------------------------------------------------------------------

def test_stretch_ghs_identity_when_D_zero():
    data = _rand_image(seed=1)
    np.testing.assert_array_equal(stretch_ghs(data, D=0), data)


def test_stretch_ghs_output_range():
    data = _rand_image()
    out = stretch_ghs(data, D=5.0, b=0.25, SP=0.0)
    assert out.min() >= 0.0
    assert out.max() <= 1.0


def test_stretch_ghs_symmetry_point_maps_to_zero():
    """At x=SP the GHS function should evaluate close to 0 (not 1)."""
    # Create a flat image at exactly SP=0.3
    SP = 0.3
    data = np.full((4, 4), SP, dtype=np.float64)
    out = stretch_ghs(data, D=5.0, b=0.25, SP=SP)
    # Result should be close to 0, not close to 1
    assert float(out.mean()) < 0.1, f"GHS at SP should be near 0, got {out.mean()}"


def test_stretch_ghs_mono_same_shape():
    data = _rand_image((16, 16))
    out = stretch_ghs(data, D=3.0)
    assert out.shape == data.shape


# ---------------------------------------------------------------------------
# balance_color
# ---------------------------------------------------------------------------

def test_balance_color_noop_for_mono():
    data = np.full((16, 16), 0.5, dtype=np.float64)
    np.testing.assert_array_equal(balance_color(data), data)


def test_balance_color_output_range():
    data = _rand_image()
    out = balance_color(data)
    assert out.min() >= 0.0
    assert out.max() <= 1.0


# ---------------------------------------------------------------------------
# run_pipeline
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("stretch_key", ["histogram", "stf", "ghs", "arcsinh", "none"])
def test_run_pipeline_all_stretch_modes(stretch_key):
    img = _rand_pil()
    out = run_pipeline(img, {"stretch": stretch_key})
    assert out.size == img.size
    assert out.mode == img.mode


def test_run_pipeline_unknown_stretch_does_not_raise():
    img = _rand_pil()
    out = run_pipeline(img, {"stretch": "does_not_exist"})
    assert out is not None


def test_run_pipeline_mono_image():
    img = _rand_pil(mode="L")
    out = run_pipeline(img, {"stretch": "stf"})
    assert out.size == img.size


def test_run_pipeline_preserves_mode():
    for mode in ("RGB", "L"):
        img = _rand_pil(mode=mode)
        out = run_pipeline(img, {})
        assert out.mode == mode


def test_run_pipeline_color_balance_flag():
    img = _rand_pil()
    out = run_pipeline(img, {"stretch": "none", "color_balance": True})
    assert out.size == img.size


def test_run_pipeline_missing_dep_skips_step(monkeypatch):
    """ImportError in a step should be swallowed with a warning, not raised."""
    import utils.image_enhancement as enh

    original = enh.subtract_background

    def _raise_import(*args, **kwargs):
        raise ImportError("sep not available")

    monkeypatch.setattr(enh, "subtract_background", _raise_import)
    img = _rand_pil()
    out = run_pipeline(img, {"stretch": "none", "background_sub": True})
    assert out is not None
    enh.subtract_background = original
