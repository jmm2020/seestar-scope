"""Astronomical image enhancement algorithms for SeestarScope.

Implements PixInsight-inspired processing pipeline with composable steps:
  Background Subtraction -> Hot Pixel Removal -> Noise Reduction ->
  Stretch -> Sharpening -> Color Balance

  Note: Star detection/overlay (detect_stars, draw_star_overlay) is provided
  as a separate utility called by the view layer, not by run_pipeline().

All functions operate on numpy float64 arrays normalized to [0.0, 1.0].
Input/output conversion handled by run_pipeline().
"""

import logging
import numpy as np
from PIL import Image
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# 1. STRETCH ALGORITHMS
# --------------------------------------------------------------------------


def stretch_histogram(
    data: np.ndarray, black_point: float = 0.1, white_point: float = 99.9
) -> np.ndarray:
    """Basic percentile histogram stretch."""
    low = np.percentile(data, black_point)
    high = np.percentile(data, white_point)
    return np.clip((data - low) / max(high - low, 1e-10), 0.0, 1.0)


def stretch_stf(data: np.ndarray, target_bg: float = 0.25, shadow_clip: float = -2.8) -> np.ndarray:
    """PixInsight Screen Transfer Function (STF) auto-stretch.

    The STF uses median and MAD (Median Absolute Deviation) to compute
    a midtone transfer function that maps the image to a target background level.
    """

    def _mtf(x: np.ndarray, m: float) -> np.ndarray:
        result = np.zeros_like(x)
        mask = x > 0
        result[mask] = (m - 1.0) * x[mask] / ((2.0 * m - 1.0) * x[mask] - m)
        result[x >= 1.0] = 1.0
        return np.clip(result, 0.0, 1.0)

    if data.ndim == 2:
        channels = [data]
    else:
        channels = [data[:, :, c] for c in range(data.shape[2])]

    stretched_channels = []
    for ch in channels:
        median = np.median(ch)
        mad = np.median(np.abs(ch - median))
        if mad < 1e-10:
            mad = 1e-10

        clip_point = max(0.0, median + shadow_clip * mad * 1.4826)
        normalized = np.clip((ch - clip_point) / max(1.0 - clip_point, 1e-10), 0.0, 1.0)
        norm_median = max((median - clip_point) / max(1.0 - clip_point, 1e-10), 1e-10)
        if 0 < norm_median < 1:
            m = target_bg * (norm_median - 1) / ((2 * target_bg - 1) * norm_median - target_bg)
            m = float(np.clip(m, 0.001, 0.999))
        else:
            m = 0.5

        stretched_channels.append(_mtf(normalized, m))

    if data.ndim == 2:
        return stretched_channels[0]
    return np.stack(stretched_channels, axis=2)


def stretch_ghs(
    data: np.ndarray,
    D: float = 5.0,
    b: float = 0.25,
    SP: float = 0.0,
    HP: float = 1.0,
    LP: float = 0.0,
) -> np.ndarray:
    """Generalized Hyperbolic Stretch (GHS).

    Parameters:
        D:  Stretch factor (log-stretch intensity). 0 = no stretch.
        b:  Bias / local stretch intensity.
        SP: Symmetry Point (0-1).
        HP: Highlight protection (0-1). Default 1.0 = no protection.
        LP: Shadow protection / black point (0-1). Default 0.0.
    """
    if D <= 0:
        return data  # No stretch

    result = np.copy(data)

    def _ghs_channel(ch: np.ndarray) -> np.ndarray:
        ch_clipped = np.clip(ch, LP, HP)
        ch_norm = (ch_clipped - LP) / max(HP - LP, 1e-10)

        x = ch_norm
        q_pos = np.exp(D * (x - SP))
        q_neg = np.exp(-D * (SP - x))

        above = x >= SP
        below = ~above

        out = np.zeros_like(x)

        if np.any(above):
            val = b * D * (q_pos[above] - 1)
            denom = np.log1p(b * D * (np.exp(D * (1.0 - SP)) - 1))
            out[above] = np.log1p(val) / max(denom, 1e-10)

        if np.any(below):
            val = b * D * (q_neg[below] - 1)
            denom = np.log1p(b * D * (np.exp(D * SP) - 1))
            out[below] = 1.0 - np.log1p(val) / max(denom, 1e-10)

        return np.clip(out, 0.0, 1.0)

    if data.ndim == 2:
        return _ghs_channel(data)

    for c in range(data.shape[2]):
        result[:, :, c] = _ghs_channel(data[:, :, c])
    return result


def stretch_arcsinh(data: np.ndarray, black_point: float = 0.0, scale: float = 10.0) -> np.ndarray:
    """Arcsinh stretch - preserves star colors better than log stretch."""
    shifted = np.clip(data - black_point, 0, None)

    if data.ndim == 3:
        luminance = np.mean(shifted, axis=2, keepdims=True)
        luminance = np.maximum(luminance, 1e-10)
        stretched_lum = np.arcsinh(luminance * scale) / np.arcsinh(scale)
        result = shifted * (stretched_lum / luminance)
    else:
        result = np.arcsinh(shifted * scale) / np.arcsinh(scale)

    return np.clip(result, 0.0, 1.0)


def stretch_clahe(data: np.ndarray, clip_limit: float = 2.0, grid_size: int = 8) -> np.ndarray:
    """CLAHE - Contrast Limited Adaptive Histogram Equalization."""
    import cv2

    img_u8 = (np.clip(data, 0, 1) * 255).astype(np.uint8)

    if data.ndim == 3:
        lab = cv2.cvtColor(img_u8, cv2.COLOR_RGB2LAB)
        clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(grid_size, grid_size))
        lab[:, :, 0] = clahe.apply(lab[:, :, 0])
        result = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)
    else:
        clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(grid_size, grid_size))
        result = clahe.apply(img_u8)

    return result.astype(np.float64) / 255.0


# --------------------------------------------------------------------------
# 2. ENHANCEMENT FUNCTIONS
# --------------------------------------------------------------------------


def subtract_background(data: np.ndarray, box_size: int = 64, filter_size: int = 3) -> np.ndarray:
    """Remove light pollution gradient using sep background estimation."""
    import sep

    result = np.copy(data)

    def _sub_channel(ch: np.ndarray) -> np.ndarray:
        # sep requires C-contiguous float64 with native byte order
        ch_c = np.ascontiguousarray(ch, dtype=np.float64)
        if ch_c.dtype.byteorder not in ("=", "<" if np.little_endian else ">"):
            ch_c = ch_c.byteswap().newbyteorder()
        bkg = sep.Background(ch_c, bw=box_size, bh=box_size, fw=filter_size, fh=filter_size)
        return np.clip(ch_c - bkg.back(), 0.0, 1.0)

    if data.ndim == 2:
        return _sub_channel(data)

    for c in range(data.shape[2]):
        result[:, :, c] = _sub_channel(data[:, :, c])
    return result


def remove_hot_pixels(
    data: np.ndarray, method: str = "median", sigma_clip: float = 5.0
) -> np.ndarray:
    """Remove hot pixels and cosmic rays.

    Two methods available:
    - 'lacosmic': L.A.Cosmic algorithm (slower but more accurate)
    - 'median': Median filter (faster, simpler) - DEFAULT
    """
    if method == "lacosmic":
        try:
            import lacosmic
        except ImportError:
            logger.warning("lacosmic not installed; falling back to median filter")
            method = "median"
        else:
            if data.ndim == 3:
                result = np.copy(data)
                for c in range(data.shape[2]):
                    cleaned, _mask = lacosmic.lacosmic(
                        data[:, :, c], contrast=2.0, cr_threshold=sigma_clip, neighbor_threshold=0.3
                    )
                    result[:, :, c] = np.clip(cleaned, 0.0, 1.0)
                return result
            cleaned, _mask = lacosmic.lacosmic(
                data, contrast=2.0, cr_threshold=sigma_clip, neighbor_threshold=0.3
            )
            return np.clip(cleaned, 0.0, 1.0)

    # Median filter path (default method, also used as lacosmic fallback)
    import cv2

    img_u8 = (np.clip(data, 0, 1) * 255).astype(np.uint8)
    filtered = cv2.medianBlur(img_u8, 3)
    return filtered.astype(np.float64) / 255.0


def reduce_noise(data: np.ndarray, strength: int = 7) -> np.ndarray:
    """Noise reduction using OpenCV Non-Local Means denoising.

    strength: 3=mild, 7=moderate, 15=strong, 21=very strong.
    """
    import cv2

    img_u8 = (np.clip(data, 0, 1) * 255).astype(np.uint8)

    if data.ndim == 3:
        denoised = cv2.fastNlMeansDenoisingColored(img_u8, None, strength, strength, 7, 21)
    else:
        denoised = cv2.fastNlMeansDenoising(img_u8, None, strength, 7, 21)

    return denoised.astype(np.float64) / 255.0


def sharpen_unsharp_mask(data: np.ndarray, amount: float = 1.0, radius: float = 1.5) -> np.ndarray:
    """Unsharp mask sharpening: Sharpened = Original + amount * (Original - Blurred)."""
    import cv2

    blurred = cv2.GaussianBlur(data, (0, 0), radius)
    sharpened = data + amount * (data - blurred)
    return np.clip(sharpened, 0.0, 1.0)


def balance_color(data: np.ndarray) -> np.ndarray:
    """Gray world white balance.

    Scales each channel so their means are equal.
    No-op for mono (2D) images.
    """
    if data.ndim != 3 or data.shape[2] != 3:
        return data

    means = [np.mean(data[:, :, c]) for c in range(3)]
    overall_mean = float(np.mean(means))

    result = np.copy(data)
    for c in range(3):
        if means[c] > 1e-10:
            result[:, :, c] = data[:, :, c] * (overall_mean / means[c])

    return np.clip(result, 0.0, 1.0)


def detect_stars(
    data: np.ndarray, fwhm: float = 3.0, threshold_sigma: float = 5.0
) -> List[Tuple[float, float, float]]:
    """Detect stars using photutils DAOStarFinder.

    Returns list of (x, y, flux) tuples for detected stars.
    """
    from photutils.detection import DAOStarFinder
    from astropy.stats import sigma_clipped_stats

    if data.ndim == 3:
        luminance = np.mean(data, axis=2)
    else:
        luminance = data

    _mean, median, std = sigma_clipped_stats(luminance, sigma=3.0)

    finder = DAOStarFinder(fwhm=fwhm, threshold=threshold_sigma * std)
    sources = finder(luminance - median)

    if sources is None:
        return []

    return [(float(s["xcentroid"]), float(s["ycentroid"]), float(s["flux"])) for s in sources]


def draw_star_overlay(
    image: Image.Image,
    stars: List[Tuple[float, float, float]],
    color: str = "cyan",
    radius: int = 10,
) -> Image.Image:
    """Draw circles around detected stars on a PIL image."""
    from PIL import ImageDraw

    overlay = image.copy()
    draw = ImageDraw.Draw(overlay)

    for x, y, _flux in stars:
        r = radius
        draw.ellipse(
            [x - r, y - r, x + r, y + r],
            outline=color,
            width=2,
        )

    return overlay


# --------------------------------------------------------------------------
# 3. PIPELINE ORCHESTRATOR
# --------------------------------------------------------------------------

STRETCH_FUNCTIONS = {
    "none": lambda data, **kw: data,
    "histogram": stretch_histogram,
    "stf": stretch_stf,
    "ghs": stretch_ghs,
    "arcsinh": stretch_arcsinh,
    "clahe": stretch_clahe,
}

STRETCH_LABELS = {
    "none": "None (Linear/Raw)",
    "histogram": "Basic Histogram Stretch",
    "stf": "STF Auto-Stretch (PixInsight)",
    "ghs": "Generalized Hyperbolic Stretch",
    "arcsinh": "Arcsinh Stretch",
    "clahe": "CLAHE (Adaptive)",
}

ENHANCEMENT_PRESETS: Dict[str, Optional[Dict[str, Any]]] = {
    "Quick Look": {
        "stretch": "stf",
        "background_sub": False,
        "denoise": False,
        "hot_pixel": False,
        "sharpen": False,
        "color_balance": False,
    },
    "Deep Sky": {
        "stretch": "stf",
        "background_sub": True,
        "denoise": True,
        "denoise_strength": 7,
        "hot_pixel": True,
        "sharpen": True,
        "sharpen_amount": 1.0,
        "sharpen_radius": 1.5,
        "color_balance": True,
    },
    "Planetary": {
        "stretch": "none",
        "background_sub": False,
        "denoise": True,
        "denoise_strength": 15,
        "hot_pixel": True,
        "sharpen": True,
        "sharpen_amount": 2.5,
        "sharpen_radius": 0.8,
        "color_balance": True,
    },
    "Maximum Detail": {
        "stretch": "ghs",
        "ghs_D": 5.0,
        "ghs_b": 0.25,
        "ghs_SP": 0.0,
        "background_sub": True,
        "denoise": True,
        "denoise_strength": 5,
        "hot_pixel": True,
        "sharpen": True,
        "sharpen_amount": 2.0,
        "sharpen_radius": 1.2,
        "color_balance": True,
    },
    "Custom": None,  # sentinel - use manual controls
}


def run_pipeline(image: Image.Image, params: Dict[str, Any]) -> Image.Image:
    """Run the full enhancement pipeline on a PIL Image.

    Args:
        image: Source PIL Image (RGB or L mode)
        params: Pipeline configuration. Recognized keys include:
            stretch, stretch_params, background_sub, background_box_size,
            hot_pixel, hot_pixel_method, denoise, denoise_strength,
            sharpen, sharpen_amount, sharpen_radius, color_balance.

    Returns:
        Enhanced PIL Image (same mode as input).
    """
    data = np.array(image, dtype=np.float64) / 255.0

    if params.get("background_sub", False):
        try:
            box = params.get("background_box_size", 64)
            data = subtract_background(data, box_size=box)
        except ImportError:
            logger.warning("run_pipeline: sep not available, skipping background_sub")
        except Exception as exc:
            raise RuntimeError(f"background_sub step failed: {exc}") from exc

    if params.get("hot_pixel", False):
        try:
            method = params.get("hot_pixel_method", "median")
            data = remove_hot_pixels(data, method=method)
        except ImportError:
            logger.warning("run_pipeline: cv2 not available, skipping hot_pixel")
        except Exception as exc:
            raise RuntimeError(f"hot_pixel step failed: {exc}") from exc

    if params.get("denoise", False):
        try:
            strength = params.get("denoise_strength", 7)
            data = reduce_noise(data, strength=strength)
        except ImportError:
            logger.warning("run_pipeline: cv2 not available, skipping denoise")
        except Exception as exc:
            raise RuntimeError(f"denoise step failed: {exc}") from exc

    stretch_key = params.get("stretch", "none")
    stretch_fn = STRETCH_FUNCTIONS.get(stretch_key, STRETCH_FUNCTIONS["none"])
    stretch_params = params.get("stretch_params", {})
    try:
        data = stretch_fn(data, **stretch_params)
    except Exception as exc:
        raise RuntimeError(f"stretch step ({stretch_key}) failed: {exc}") from exc

    if params.get("sharpen", False):
        try:
            amount = params.get("sharpen_amount", 1.0)
            radius = params.get("sharpen_radius", 1.5)
            data = sharpen_unsharp_mask(data, amount=amount, radius=radius)
        except ImportError:
            logger.warning("run_pipeline: cv2 not available, skipping sharpen")
        except Exception as exc:
            raise RuntimeError(f"sharpen step failed: {exc}") from exc

    if params.get("color_balance", False):
        try:
            data = balance_color(data)
        except Exception as exc:
            raise RuntimeError(f"color_balance step failed: {exc}") from exc

    result_u8 = (np.clip(data, 0, 1) * 255).astype(np.uint8)
    return Image.fromarray(result_u8, mode=image.mode)
