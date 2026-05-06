# SeestarScope Image Enhancement & Processing Pipeline PRP

## 1. Objective & Scope

### Goal
Add a comprehensive, PixInsight-inspired image enhancement and processing pipeline to the SeestarScope Streamlit app, with real-time before/after comparison displays, composable processing steps, presets, live stacking, and enhanced export capabilities.

### In Scope
- New `utils/image_enhancement.py` module with all processing algorithms
- STF Auto-Stretch (PixInsight's Screen Transfer Function) implementation
- Generalized Hyperbolic Stretch (GHS) with interactive parameter controls
- Arcsinh Stretch preserving star colors
- CLAHE (Contrast Limited Adaptive Histogram Equalization)
- Background extraction/subtraction via `sep`
- Noise reduction via OpenCV Non-Local Means denoising
- Hot pixel / cosmic ray removal via `lacosmic` with median filter fallback
- Unsharp mask sharpening with configurable amount/radius
- Gray world white balance color correction
- Star detection overlay via `photutils` DAOStarFinder
- Three comparison display modes: Side-by-Side, Slider Overlay, Toggle
- Enhancement presets (Deep Sky, Planetary, Quick Look, Maximum Detail, Custom)
- Live stacking with `astroalign` frame registration
- Enhanced export with processing metadata in filenames
- Updated Imaging page UI integrating all features
- Updated Docker container with new dependencies

### Out of Scope
- GPU acceleration via CuPy (future enhancement - would require CUDA in container)
- Plate solving / astrometry.net integration (separate future feature)
- AI-based denoising (deepCR, AstroDenoisePy - requires ML models in container)
- Star removal (GAN-based - too heavy for real-time)
- Full Siril/PixInsight pipeline integration
- Dark/flat/bias calibration frame library (requires separate calibration workflow)
- FITS file format support (staying with PNG/PIL for now)

### Success Criteria
- [ ] All 6 stretch methods render correctly on a captured 1080x1920 image
- [ ] All 6 enhancement toggles work independently and in combination
- [ ] Before/after comparison works in all 3 modes (side-by-side, slider, toggle)
- [ ] Full enhancement pipeline completes in < 2 seconds on CPU
- [ ] Presets apply correct parameter combinations with one click
- [ ] Live stacking aligns and accumulates frames with visible SNR improvement
- [ ] Enhanced images save with processing metadata in filename
- [ ] Docker container builds and runs without errors
- [ ] No regressions in existing capture/loop/save workflow

---

## 2. Technical Requirements

### Language & Framework
- **Language**: Python 3.11+
- **Framework**: Streamlit >= 1.30.0
- **Image Backend**: NumPy arrays (float64 for processing, uint8 for display)
- **Justification**: Extends existing SeestarScope Streamlit app; all libraries have NumPy-native APIs

### Dependencies (additions to requirements.txt)
```
# Image Enhancement Pipeline (NEW)
scikit-image>=0.22.0          # STF, GHS, CLAHE, Richardson-Lucy, arcsinh stretch
opencv-python-headless>=4.9.0 # NLM denoising, unsharp mask, color balance, median filter
sep>=1.2.1                    # Fast background extraction (C backend)
photutils>=1.10.0             # Star detection (DAOStarFinder), Background2D
astroalign>=2.5.1             # Image alignment for live stacking
lacosmic>=1.1.0               # Cosmic ray / hot pixel removal
streamlit-image-comparison>=0.0.4  # Slider overlay comparison component
scipy>=1.11.0                 # Required by photutils, astroalign
```

### System Dependencies (Dockerfile additions)
```dockerfile
# OpenCV and sep require these system libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libgl1-mesa-glx \
    libglib2.0-0 \
    gcc \
    && rm -rf /var/lib/apt/lists/*
```

### Existing Integration Points
| Component | Path | How it's affected |
|-----------|------|-------------------|
| `utils/image_processing.py` | Existing utils | Keep existing functions, import new module |
| `views/imaging.py` | Imaging page | Replace simple stretch toggle with full enhancement panel |
| `requirements.txt` | Dependencies | Add new packages |
| `Dockerfile` | Container | Add system deps for OpenCV/sep |

---

## 3. Proven Patterns

### Applicable Patterns
1. **Non-destructive pipeline**: Original image always preserved in `st.session_state["last_image"]`. All processing creates new arrays. Never modify the source.
2. **Streamlit widget key pattern**: All enhancement controls use unique `key=` parameters to avoid widget ID collisions. Session state initialized before widget creation. Never set `value=` and session state key simultaneously.
3. **Hardware state sync pattern**: Enhancement parameters stored in session state and survive Streamlit reruns. Processing only triggers when parameters change (compare against cached result).

### Past Implementations to Reference
- **Existing `apply_stretch()`** in `utils/image_processing.py:52-58` - percentile-based stretch. This is the baseline to improve upon.
- **Existing imaging page preview** in `views/imaging.py:219-307` - current preview/save section that will be extended.
- **Session state pattern** from imaging controls fix - don't modify `st.session_state["key"]` after widget instantiation.

### Pitfalls to Avoid
1. **Streamlit rerun cost**: Every widget interaction triggers a full page rerun. Cache processed images in session state. Only reprocess when parameters actually change.
2. **NumPy dtype mismatches**: `sep` requires contiguous C-order float64 arrays. `lacosmic` returns float64. OpenCV expects uint8 or float32. Always convert explicitly at boundaries.
3. **Color channel order**: PIL uses RGB, OpenCV uses BGR. Always convert: `cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)` before OpenCV ops, convert back after.
4. **`sep` byte order**: `sep.Background()` requires native byte order. Use `arr = arr.astype(np.float64, order='C')` or `arr.byteswap().newbyteorder()` if needed.
5. **Memory with large images**: 1920x1080x3 float64 = ~50MB per copy. Limit number of intermediate copies. Don't store more than 3 versions in session state (original, enhanced, stacked).
6. **streamlit-image-comparison**: The package may have compatibility issues with newer Streamlit versions. Implement fallback to side-by-side if import fails.

---

## 4. Architecture & Implementation

### File Structure
```
seestar_scope/
├── utils/
│   ├── image_processing.py        # EXISTING - keep as-is
│   └── image_enhancement.py       # NEW - all enhancement algorithms
├── views/
│   ├── imaging.py                 # MODIFIED - add enhancement panel
│   └── ...                        # Other views unchanged
├── requirements.txt               # MODIFIED - add new deps
├── Dockerfile                     # MODIFIED - add system deps
└── PRPs/
    └── seestar_image_enhancement_pipeline_prp.md  # This PRP
```

### Processing Pipeline Data Flow
```
                    ┌─────────────────────────────────────┐
                    │     Session State: "last_image"      │
                    │     (PIL Image - NEVER modified)      │
                    └──────────────┬──────────────────────┘
                                   │
                                   ▼
                    ┌──────────────────────────────────┐
                    │   Convert to float64 NumPy array  │
                    │   (normalized 0.0 - 1.0 range)    │
                    └──────────────┬───────────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │    ENHANCEMENT PIPELINE (each optional)  │
              │                                          │
              │  1. Background Subtraction (sep)         │
              │  2. Hot Pixel Removal (lacosmic/median)  │
              │  3. Noise Reduction (OpenCV NLM)         │
              │  4. Stretch (STF/GHS/Arcsinh/CLAHE/etc) │
              │  5. Sharpening (Unsharp Mask)            │
              │  6. Color Balance (Gray World WB)        │
              │  7. Star Detection Overlay (photutils)   │
              │                                          │
              └────────────────────┼────────────────────┘
                                   │
                                   ▼
                    ┌──────────────────────────────────┐
                    │  Convert back to uint8 PIL Image  │
                    │  Cache in session_state as         │
                    │  "enhanced_image"                  │
                    └──────────────┬───────────────────┘
                                   │
                     ┌─────────────┴─────────────┐
                     │                           │
                     ▼                           ▼
          ┌──────────────────┐       ┌──────────────────────┐
          │ Comparison Display│       │  Export / Save        │
          │ (3 modes)         │       │  (raw + enhanced)     │
          └──────────────────┘       └──────────────────────┘
```

### Live Stacking Data Flow
```
Loop Mode Active + Live Stacking Enabled:

  Frame 1 ──────► Reference Frame (stored in session state)
                        │
  Frame 2 ──► astroalign.register(frame2, reference) ──► aligned_2
                        │
              stack = (reference + aligned_2) / 2
                        │
  Frame 3 ──► astroalign.register(frame3, reference) ──► aligned_3
                        │
              stack = (stack * 2 + aligned_3) / 3
                        │
              ... continues for N frames ...
                        │
              SNR improvement: sqrt(N) display
                        │
              Apply Enhancement Pipeline to stack
                        │
              Comparison: Single Frame vs Stacked
```

### Enhancement Presets Configuration
```python
ENHANCEMENT_PRESETS = {
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
```

---

## 5. Code Examples

### 5.1 Core Enhancement Module: `utils/image_enhancement.py`

```python
"""Astronomical image enhancement algorithms for SeestarScope.

Implements PixInsight-inspired processing pipeline with composable steps:
  Background Subtraction → Hot Pixel Removal → Noise Reduction →
  Stretch → Sharpening → Color Balance → Star Detection Overlay

All functions operate on numpy float64 arrays normalized to [0.0, 1.0].
Input/output conversion handled by run_pipeline().
"""

import numpy as np
from PIL import Image
from typing import Optional, Dict, Any, List, Tuple


# ──────────────────────────────────────────────
# 1. STRETCH ALGORITHMS
# ──────────────────────────────────────────────

def stretch_histogram(data: np.ndarray, black_point: float = 0.1,
                      white_point: float = 99.9) -> np.ndarray:
    """Basic percentile histogram stretch (existing algorithm, improved)."""
    low = np.percentile(data, black_point)
    high = np.percentile(data, white_point)
    return np.clip((data - low) / max(high - low, 1e-10), 0.0, 1.0)


def stretch_stf(data: np.ndarray, target_bg: float = 0.25,
                shadow_clip: float = -2.8) -> np.ndarray:
    """PixInsight Screen Transfer Function (STF) auto-stretch.

    The STF uses median and MAD (Median Absolute Deviation) to compute
    a midtone transfer function that maps the image to a target background level.

    This is the signature PixInsight "auto-stretch" look.

    Algorithm:
        1. Compute median (m) and MAD (noise estimate) per channel
        2. Shadow clipping point: c = m + shadow_clip * MAD
        3. Apply Midtone Transfer Function (MTF) to map c→0, m→target_bg
    """
    def _mtf(x: np.ndarray, m: float) -> np.ndarray:
        """Midtone Transfer Function: MTF(x, m) = (m-1)*x / ((2*m-1)*x - m)"""
        # Handle edge cases
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

        # Shadow clipping point
        clip_point = max(0.0, median + shadow_clip * mad * 1.4826)

        # Normalize: clip_point → 0, max → 1
        normalized = np.clip((ch - clip_point) / max(1.0 - clip_point, 1e-10), 0.0, 1.0)

        # Compute midtone balance for target background
        norm_median = max((median - clip_point) / max(1.0 - clip_point, 1e-10), 1e-10)
        # Solve MTF(norm_median, m) = target_bg for m
        # m = MTF_inv(target_bg, norm_median)
        if norm_median > 0 and norm_median < 1:
            m = target_bg * (norm_median - 1) / (
                (2 * target_bg - 1) * norm_median - target_bg
            )
            m = np.clip(m, 0.001, 0.999)
        else:
            m = 0.5

        stretched_channels.append(_mtf(normalized, m))

    if data.ndim == 2:
        return stretched_channels[0]
    return np.stack(stretched_channels, axis=2)


def stretch_ghs(data: np.ndarray, D: float = 5.0, b: float = 0.25,
                SP: float = 0.0, HP: float = 1.0,
                LP: float = 0.0) -> np.ndarray:
    """Generalized Hyperbolic Stretch (GHS).

    Attempt to port the GHS equations from ghsastro.co.uk.

    Parameters:
        D:  Stretch factor (log-stretch intensity). 0 = no stretch, higher = more.
        b:  Bias / local stretch intensity. Controls where stretch is concentrated.
        SP: Symmetry Point. Focus point of the stretch (0-1).
        HP: Highlight protection (0-1). Default 1.0 = no protection.
        LP: Shadow protection / black point (0-1). Default 0.0.

    The core GHS equation for D > 0:
        GHS(x) = ((1 + sign) * (b*D*q + 1) - 2) / (2 * ((b*D*q + 1) - 1))
    where:
        q = exp( D * (x - SP) ) for x >= SP
        q = exp(-D * (SP - x) ) for x < SP
        sign depends on which side of SP we are on
    """
    if D <= 0:
        return data  # No stretch

    result = np.copy(data)

    # Apply per-channel if color
    def _ghs_channel(ch: np.ndarray) -> np.ndarray:
        # Clip to LP..HP range first
        ch_clipped = np.clip(ch, LP, HP)

        # Normalize to 0-1 within LP..HP
        ch_norm = (ch_clipped - LP) / max(HP - LP, 1e-10)

        # GHS transform
        x = ch_norm
        q_pos = np.exp(D * (x - SP))
        q_neg = np.exp(-D * (SP - x))

        # Above symmetry point
        above = x >= SP
        below = ~above

        out = np.zeros_like(x)

        if np.any(above):
            val = b * D * q_pos[above]
            out[above] = (val + 1 - 1) / (val + 1 - 1 + 1e-10)
            # Simplified: stretch using ln(1 + b*D*exp(...))
            out[above] = np.log1p(val) / np.log1p(b * D * np.exp(D * (1.0 - SP)))

        if np.any(below):
            val = b * D * q_neg[below]
            out[below] = 1.0 - np.log1p(val) / np.log1p(b * D * np.exp(D * SP))

        return np.clip(out, 0.0, 1.0)

    if data.ndim == 2:
        return _ghs_channel(data)

    for c in range(data.shape[2]):
        result[:, :, c] = _ghs_channel(data[:, :, c])
    return result


def stretch_arcsinh(data: np.ndarray, black_point: float = 0.0,
                    scale: float = 10.0) -> np.ndarray:
    """Arcsinh stretch - preserves star colors better than log stretch.

    arcsinh is used because it's linear near zero (preserves faint detail)
    and logarithmic at high values (compresses bright stars).
    Color ratios are preserved because the same nonlinear function
    is applied based on luminance.
    """
    # Subtract black point
    shifted = np.clip(data - black_point, 0, None)

    if data.ndim == 3:
        # Luminance-based scaling to preserve colors
        luminance = np.mean(shifted, axis=2, keepdims=True)
        luminance = np.maximum(luminance, 1e-10)
        stretched_lum = np.arcsinh(luminance * scale) / np.arcsinh(scale)
        # Scale RGB by luminance ratio
        result = shifted * (stretched_lum / luminance)
    else:
        result = np.arcsinh(shifted * scale) / np.arcsinh(scale)

    return np.clip(result, 0.0, 1.0)


def stretch_clahe(data: np.ndarray, clip_limit: float = 2.0,
                  grid_size: int = 8) -> np.ndarray:
    """CLAHE - Contrast Limited Adaptive Histogram Equalization.

    Works on local regions rather than globally, preserving local contrast.
    Good for images with both bright and faint regions.
    """
    import cv2

    # Convert to uint8 for CLAHE
    img_u8 = (np.clip(data, 0, 1) * 255).astype(np.uint8)

    if data.ndim == 3:
        # Convert to LAB, apply CLAHE to L channel only
        lab = cv2.cvtColor(img_u8, cv2.COLOR_RGB2LAB)
        clahe = cv2.createCLAHE(clipLimit=clip_limit,
                                 tileGridSize=(grid_size, grid_size))
        lab[:, :, 0] = clahe.apply(lab[:, :, 0])
        result = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)
    else:
        clahe = cv2.createCLAHE(clipLimit=clip_limit,
                                 tileGridSize=(grid_size, grid_size))
        result = clahe.apply(img_u8)

    return result.astype(np.float64) / 255.0


# ──────────────────────────────────────────────
# 2. ENHANCEMENT FUNCTIONS
# ──────────────────────────────────────────────

def subtract_background(data: np.ndarray, box_size: int = 64,
                        filter_size: int = 3) -> np.ndarray:
    """Remove light pollution gradient using sep background estimation.

    sep (Source Extractor as Python) uses a mesh-based approach to
    estimate the spatially varying background, then subtracts it.
    """
    import sep

    result = np.copy(data)

    def _sub_channel(ch: np.ndarray) -> np.ndarray:
        # sep requires C-contiguous float64 with native byte order
        ch_c = np.ascontiguousarray(ch, dtype=np.float64)
        if ch_c.dtype.byteorder not in ('=', '<' if np.little_endian else '>'):
            ch_c = ch_c.byteswap().newbyteorder()
        bkg = sep.Background(ch_c, bw=box_size, bh=box_size,
                             fw=filter_size, fh=filter_size)
        return np.clip(ch_c - bkg.back(), 0.0, 1.0)

    if data.ndim == 2:
        return _sub_channel(data)

    for c in range(data.shape[2]):
        result[:, :, c] = _sub_channel(data[:, :, c])
    return result


def remove_hot_pixels(data: np.ndarray, method: str = "lacosmic",
                      sigma_clip: float = 5.0) -> np.ndarray:
    """Remove hot pixels and cosmic rays.

    Two methods available:
    - 'lacosmic': L.A.Cosmic algorithm (slower but more accurate)
    - 'median': Median filter (faster, simpler)
    """
    if method == "lacosmic":
        import lacosmic
        if data.ndim == 3:
            result = np.copy(data)
            for c in range(data.shape[2]):
                cleaned, _mask = lacosmic.lacosmic(
                    data[:, :, c], contrast=2.0, cr_threshold=sigma_clip,
                    neighbor_threshold=0.3
                )
                result[:, :, c] = np.clip(cleaned, 0.0, 1.0)
            return result
        else:
            cleaned, _mask = lacosmic.lacosmic(
                data, contrast=2.0, cr_threshold=sigma_clip,
                neighbor_threshold=0.3
            )
            return np.clip(cleaned, 0.0, 1.0)
    else:
        # Median filter fallback
        import cv2
        img_u8 = (np.clip(data, 0, 1) * 255).astype(np.uint8)
        filtered = cv2.medianBlur(img_u8, 3)
        return filtered.astype(np.float64) / 255.0


def reduce_noise(data: np.ndarray, strength: int = 7) -> np.ndarray:
    """Noise reduction using OpenCV Non-Local Means denoising.

    NLM denoising works by averaging similar patches across the image.
    More effective than simple blurring as it preserves edges.

    Args:
        strength: Filter strength (h parameter). 3=mild, 7=moderate, 15=strong, 21=very strong.
    """
    import cv2

    img_u8 = (np.clip(data, 0, 1) * 255).astype(np.uint8)

    if data.ndim == 3:
        denoised = cv2.fastNlMeansDenoisingColored(img_u8, None, strength, strength, 7, 21)
    else:
        denoised = cv2.fastNlMeansDenoising(img_u8, None, strength, 7, 21)

    return denoised.astype(np.float64) / 255.0


def sharpen_unsharp_mask(data: np.ndarray, amount: float = 1.0,
                         radius: float = 1.5) -> np.ndarray:
    """Unsharp mask sharpening.

    Sharpened = Original + amount * (Original - Blurred)

    Args:
        amount: Sharpening intensity. 0.5=mild, 1.0=moderate, 2.0=strong.
        radius: Gaussian blur radius. Smaller=fine detail, larger=broader features.
    """
    import cv2

    # Apply per-channel
    blurred = cv2.GaussianBlur(data, (0, 0), radius)
    sharpened = data + amount * (data - blurred)
    return np.clip(sharpened, 0.0, 1.0)


def balance_color(data: np.ndarray) -> np.ndarray:
    """Gray world white balance.

    Assumes the average color of the scene should be neutral gray.
    Scales each channel so their means are equal.
    Works well for wide-field astro images with diverse star colors.
    """
    if data.ndim != 3 or data.shape[2] != 3:
        return data  # Only works on color images

    means = [np.mean(data[:, :, c]) for c in range(3)]
    overall_mean = np.mean(means)

    result = np.copy(data)
    for c in range(3):
        if means[c] > 1e-10:
            result[:, :, c] = data[:, :, c] * (overall_mean / means[c])

    return np.clip(result, 0.0, 1.0)


def detect_stars(data: np.ndarray, fwhm: float = 3.0,
                 threshold_sigma: float = 5.0) -> List[Tuple[float, float, float]]:
    """Detect stars using photutils DAOStarFinder.

    Returns list of (x, y, flux) tuples for detected stars.
    These can be drawn as overlay circles on the image.
    """
    from photutils.detection import DAOStarFinder
    from astropy.stats import sigma_clipped_stats

    # Work on luminance for detection
    if data.ndim == 3:
        luminance = np.mean(data, axis=2)
    else:
        luminance = data

    # Statistics for threshold
    mean, median, std = sigma_clipped_stats(luminance, sigma=3.0)

    finder = DAOStarFinder(fwhm=fwhm, threshold=threshold_sigma * std)
    sources = finder(luminance - median)

    if sources is None:
        return []

    return [(float(s['xcentroid']), float(s['ycentroid']), float(s['flux']))
            for s in sources]


def draw_star_overlay(image: Image.Image,
                      stars: List[Tuple[float, float, float]],
                      color: str = "cyan",
                      radius: int = 10) -> Image.Image:
    """Draw circles around detected stars on a PIL image."""
    from PIL import ImageDraw

    overlay = image.copy()
    draw = ImageDraw.Draw(overlay)

    for x, y, flux in stars:
        # Scale circle size by relative flux
        r = radius
        draw.ellipse(
            [x - r, y - r, x + r, y + r],
            outline=color, width=2
        )

    return overlay


# ──────────────────────────────────────────────
# 3. LIVE STACKING
# ──────────────────────────────────────────────

def align_frame(frame: np.ndarray, reference: np.ndarray) -> Optional[np.ndarray]:
    """Align a frame to a reference using astroalign.

    Uses triangle asterism matching - works without WCS or plate solving.
    Returns aligned frame or None if alignment fails.
    """
    import astroalign

    try:
        # astroalign works on 2D arrays; use luminance for alignment
        if frame.ndim == 3:
            frame_lum = np.mean(frame, axis=2)
            ref_lum = np.mean(reference, axis=2)

            # Find transform from luminance
            registered_lum, footprint = astroalign.register(frame_lum, ref_lum)

            # Apply same transform to all channels
            transform, _ = astroalign.find_transform(frame_lum, ref_lum)
            from skimage.transform import warp
            aligned = np.zeros_like(frame)
            for c in range(frame.shape[2]):
                aligned[:, :, c] = warp(
                    frame[:, :, c], inverse_map=transform.inverse,
                    output_shape=frame.shape[:2], preserve_range=True
                )
            return np.clip(aligned, 0.0, 1.0)
        else:
            registered, _footprint = astroalign.register(frame, reference)
            return np.clip(registered, 0.0, 1.0)
    except Exception:
        return None  # Alignment failed (not enough stars, etc)


def accumulate_stack(stack: np.ndarray, new_frame: np.ndarray,
                     count: int) -> np.ndarray:
    """Incrementally add a frame to the running stack average.

    stack = (stack * count + new_frame) / (count + 1)

    This is mathematically equivalent to mean stacking but uses O(1) memory.
    """
    return (stack * count + new_frame) / (count + 1)


# ──────────────────────────────────────────────
# 4. PIPELINE ORCHESTRATOR
# ──────────────────────────────────────────────

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


def run_pipeline(image: Image.Image, params: Dict[str, Any]) -> Image.Image:
    """Run the full enhancement pipeline on a PIL Image.

    Args:
        image: Source PIL Image (RGB or L mode)
        params: Dict with pipeline configuration:
            - stretch: str (key from STRETCH_FUNCTIONS)
            - stretch_params: dict (kwargs for the stretch function)
            - background_sub: bool
            - background_box_size: int
            - hot_pixel: bool
            - hot_pixel_method: str ('lacosmic' or 'median')
            - denoise: bool
            - denoise_strength: int (3-21)
            - sharpen: bool
            - sharpen_amount: float
            - sharpen_radius: float
            - color_balance: bool

    Returns:
        Enhanced PIL Image
    """
    # Convert to float64 [0, 1]
    data = np.array(image, dtype=np.float64) / 255.0

    # 1. Background Subtraction
    if params.get("background_sub", False):
        box = params.get("background_box_size", 64)
        data = subtract_background(data, box_size=box)

    # 2. Hot Pixel Removal
    if params.get("hot_pixel", False):
        method = params.get("hot_pixel_method", "median")
        data = remove_hot_pixels(data, method=method)

    # 3. Noise Reduction
    if params.get("denoise", False):
        strength = params.get("denoise_strength", 7)
        data = reduce_noise(data, strength=strength)

    # 4. Stretch
    stretch_key = params.get("stretch", "none")
    stretch_fn = STRETCH_FUNCTIONS.get(stretch_key, STRETCH_FUNCTIONS["none"])
    stretch_params = params.get("stretch_params", {})
    data = stretch_fn(data, **stretch_params)

    # 5. Sharpening
    if params.get("sharpen", False):
        amount = params.get("sharpen_amount", 1.0)
        radius = params.get("sharpen_radius", 1.5)
        data = sharpen_unsharp_mask(data, amount=amount, radius=radius)

    # 6. Color Balance
    if params.get("color_balance", False):
        data = balance_color(data)

    # Convert back to PIL
    result_u8 = (np.clip(data, 0, 1) * 255).astype(np.uint8)
    return Image.fromarray(result_u8, mode=image.mode)
```

### 5.2 Enhancement Panel UI: `views/imaging.py` additions

The enhancement panel replaces the existing simple stretch toggle in `_render_preview_and_save()`. Here is the new function to add:

```python
def _render_enhancement_panel(image: Image.Image) -> Image.Image:
    """Render the image enhancement control panel and return enhanced image.

    Called from _render_preview_and_save() after image is available.
    """
    from utils.image_enhancement import (
        run_pipeline, detect_stars, draw_star_overlay,
        STRETCH_LABELS, ENHANCEMENT_PRESETS,
    )

    st.subheader("Image Enhancement")
    st.caption("Apply PixInsight-style processing. Each step is optional and applied in order.")

    # ── Presets ──
    preset_names = list(ENHANCEMENT_PRESETS.keys())
    preset_choice = st.selectbox(
        "Preset",
        preset_names,
        index=0,
        key="enhance_preset",
        help="Quick-apply common enhancement combinations. Choose 'Custom' for full manual control.",
    )

    preset = ENHANCEMENT_PRESETS.get(preset_choice)
    is_custom = preset is None

    # ── Stretch Method ──
    stretch_keys = list(STRETCH_LABELS.keys())
    stretch_labels = list(STRETCH_LABELS.values())

    if not is_custom and preset:
        default_stretch_idx = stretch_keys.index(preset.get("stretch", "none"))
    else:
        default_stretch_idx = stretch_keys.index(
            st.session_state.get("enhance_stretch", "stf")
        ) if st.session_state.get("enhance_stretch") in stretch_keys else 2

    stretch_choice = st.radio(
        "Stretch Method",
        stretch_keys,
        index=default_stretch_idx,
        format_func=lambda k: STRETCH_LABELS[k],
        key="enhance_stretch",
        horizontal=True,
        disabled=not is_custom,
        help="How to map the linear image data to a visible brightness range.",
    )

    # Stretch-specific parameters
    stretch_params = {}
    if stretch_choice == "ghs":
        col_d, col_b, col_sp = st.columns(3)
        with col_d:
            ghs_D = st.slider("D (stretch factor)", 0.0, 20.0,
                               preset.get("ghs_D", 5.0) if preset else 5.0,
                               step=0.5, key="ghs_D",
                               help="Stretch intensity. 0=none, 5=moderate, 15=extreme.")
        with col_b:
            ghs_b = st.slider("b (bias)", 0.01, 1.0,
                               preset.get("ghs_b", 0.25) if preset else 0.25,
                               step=0.01, key="ghs_b",
                               help="Controls where stretch is concentrated.")
        with col_sp:
            ghs_SP = st.slider("SP (symmetry)", 0.0, 1.0,
                                preset.get("ghs_SP", 0.0) if preset else 0.0,
                                step=0.01, key="ghs_SP",
                                help="Focus point of the stretch.")
        stretch_params = {"D": ghs_D, "b": ghs_b, "SP": ghs_SP}
    elif stretch_choice == "arcsinh":
        arcsinh_scale = st.slider("Scale", 1.0, 100.0, 10.0, step=1.0,
                                   key="arcsinh_scale",
                                   help="Stretch intensity. Higher = more compression of brights.")
        stretch_params = {"scale": arcsinh_scale}
    elif stretch_choice == "clahe":
        clahe_clip = st.slider("CLAHE Clip Limit", 0.5, 10.0, 2.0, step=0.5,
                                key="clahe_clip",
                                help="Contrast limit. Higher = more enhancement but may introduce noise.")
        stretch_params = {"clip_limit": clahe_clip}

    st.divider()

    # ── Enhancement Toggles ──
    st.caption("Enhancement Steps (applied in order before stretch)")
    col1, col2, col3 = st.columns(3)

    with col1:
        bg_sub = st.checkbox("Background Subtraction",
                              value=preset.get("background_sub", False) if preset else False,
                              key="enhance_bg_sub", disabled=not is_custom,
                              help="Remove light pollution gradient using sep.")
        hot_px = st.checkbox("Hot Pixel Removal",
                              value=preset.get("hot_pixel", False) if preset else False,
                              key="enhance_hot_pixel", disabled=not is_custom,
                              help="Remove hot pixels / cosmic rays.")
    with col2:
        denoise = st.checkbox("Noise Reduction",
                               value=preset.get("denoise", False) if preset else False,
                               key="enhance_denoise", disabled=not is_custom,
                               help="Non-Local Means denoising (OpenCV).")
        if denoise:
            denoise_str = st.slider("Strength", 3, 21,
                                     preset.get("denoise_strength", 7) if preset else 7,
                                     step=2, key="enhance_denoise_str",
                                     help="3=mild, 7=moderate, 15=strong, 21=very strong.")
        else:
            denoise_str = 7
    with col3:
        sharpen = st.checkbox("Sharpening",
                               value=preset.get("sharpen", False) if preset else False,
                               key="enhance_sharpen", disabled=not is_custom,
                               help="Unsharp mask sharpening.")
        if sharpen:
            sharp_amt = st.slider("Amount", 0.5, 5.0,
                                   preset.get("sharpen_amount", 1.0) if preset else 1.0,
                                   step=0.5, key="enhance_sharp_amt",
                                   help="0.5=subtle, 1.0=moderate, 2.5=strong.")
            sharp_rad = st.slider("Radius", 0.5, 5.0,
                                   preset.get("sharpen_radius", 1.5) if preset else 1.5,
                                   step=0.5, key="enhance_sharp_rad",
                                   help="Smaller=fine detail, larger=broader features.")
        else:
            sharp_amt, sharp_rad = 1.0, 1.5

    color_bal = st.checkbox("Color Balance",
                             value=preset.get("color_balance", False) if preset else False,
                             key="enhance_color_bal", disabled=not is_custom,
                             help="Gray world white balance correction.")

    star_overlay = st.checkbox("Star Detection Overlay",
                                key="enhance_star_overlay",
                                help="Detect and circle stars using photutils DAOStarFinder.")

    # ── Build pipeline params ──
    if preset and not is_custom:
        params = {
            "stretch": preset["stretch"],
            "stretch_params": stretch_params,
            "background_sub": preset.get("background_sub", False),
            "hot_pixel": preset.get("hot_pixel", False),
            "hot_pixel_method": "median",
            "denoise": preset.get("denoise", False),
            "denoise_strength": preset.get("denoise_strength", 7),
            "sharpen": preset.get("sharpen", False),
            "sharpen_amount": preset.get("sharpen_amount", 1.0),
            "sharpen_radius": preset.get("sharpen_radius", 1.5),
            "color_balance": preset.get("color_balance", False),
        }
    else:
        params = {
            "stretch": stretch_choice,
            "stretch_params": stretch_params,
            "background_sub": bg_sub,
            "hot_pixel": hot_px,
            "hot_pixel_method": "median",
            "denoise": denoise,
            "denoise_strength": denoise_str,
            "sharpen": sharpen,
            "sharpen_amount": sharp_amt,
            "sharpen_radius": sharp_rad,
            "color_balance": color_bal,
        }

    # ── Run Pipeline ──
    # Cache: only reprocess if params changed
    params_key = str(sorted(params.items()))
    if (st.session_state.get("enhance_params_key") != params_key
            or "enhanced_image" not in st.session_state):
        with st.spinner("Processing..."):
            enhanced = run_pipeline(image, params)
            st.session_state["enhanced_image"] = enhanced
            st.session_state["enhance_params_key"] = params_key
    else:
        enhanced = st.session_state["enhanced_image"]

    # Star overlay (applied after pipeline, display-only)
    if star_overlay:
        import numpy as np
        data = np.array(enhanced, dtype=np.float64) / 255.0
        stars = detect_stars(data)
        enhanced_display = draw_star_overlay(enhanced, stars)
        st.caption(f"Detected {len(stars)} stars")
    else:
        enhanced_display = enhanced

    return enhanced_display
```

### 5.3 Before/After Comparison Display

```python
def _render_comparison(original: Image.Image, enhanced: Image.Image):
    """Render before/after comparison in selected mode."""

    mode = st.selectbox(
        "Comparison Mode",
        ["Side-by-Side", "Slider Overlay", "Toggle"],
        key="comparison_mode",
        help="Side-by-Side: two images. Slider: drag divider. Toggle: switch between.",
    )

    if mode == "Side-by-Side":
        col_orig, col_enh = st.columns(2)
        with col_orig:
            st.image(original, caption="Original (Raw)", use_container_width=True)
        with col_enh:
            st.image(enhanced, caption="Enhanced", use_container_width=True)

    elif mode == "Slider Overlay":
        try:
            from streamlit_image_comparison import image_comparison
            image_comparison(
                img1=original,
                img2=enhanced,
                label1="Original",
                label2="Enhanced",
                starting_position=50,
                make_responsive=True,
            )
        except ImportError:
            st.warning("streamlit-image-comparison not installed. Falling back to side-by-side.")
            col_orig, col_enh = st.columns(2)
            with col_orig:
                st.image(original, caption="Original", use_container_width=True)
            with col_enh:
                st.image(enhanced, caption="Enhanced", use_container_width=True)

    elif mode == "Toggle":
        show_enhanced = st.checkbox("Show Enhanced", value=True,
                                     key="toggle_enhanced")
        if show_enhanced:
            st.image(enhanced, caption="Enhanced", use_container_width=True)
        else:
            st.image(original, caption="Original (Raw)", use_container_width=True)
```

### 5.4 Live Stacking Integration

```python
def _render_live_stacking_panel(alpaca, config):
    """Live stacking panel shown during loop mode capture."""
    from utils.image_enhancement import align_frame, accumulate_stack

    if not st.session_state.get("loop_mode"):
        return

    enable_stacking = st.checkbox("Enable Live Stacking", key="live_stack_enabled",
                                   help="Align and stack frames as they're captured. "
                                        "More frames = cleaner image (SNR improves by sqrt(N)).")
    if not enable_stacking:
        return

    stack = st.session_state.get("live_stack")
    stack_count = st.session_state.get("live_stack_count", 0)
    reference = st.session_state.get("live_stack_reference")

    # Show stack status
    if stack_count > 0:
        snr_improvement = stack_count ** 0.5
        st.caption(f"Stacked: {stack_count} frames | "
                   f"SNR improvement: {snr_improvement:.1f}x | "
                   f"Equivalent single exposure: {snr_improvement:.1f}x longer")

        # Show comparison: single frame vs stack
        if stack is not None:
            import numpy as np
            stack_pil = Image.fromarray(
                (np.clip(stack, 0, 1) * 255).astype(np.uint8),
                mode="RGB"
            )

            st.subheader("Stack Preview")
            col_single, col_stack = st.columns(2)
            with col_single:
                current_image = st.session_state.get("last_image")
                if current_image:
                    st.image(current_image, caption="Latest Single Frame",
                             use_container_width=True)
            with col_stack:
                st.image(stack_pil, caption=f"Stacked ({stack_count} frames)",
                         use_container_width=True)
    else:
        st.info("Stack will begin accumulating when capture starts.")
```

### 5.5 Export Enhanced Image

```python
def _render_enhanced_save(image: Image.Image, enhanced: Image.Image,
                          config, params: dict):
    """Save controls for both raw and enhanced images."""
    from utils.image_processing import save_image

    st.subheader("Save")
    col_name, col_raw, col_enhanced, col_both = st.columns([3, 1, 1, 1])

    with col_name:
        target = st.text_input(
            "Target name",
            value=st.session_state.get("slewing_target", "capture"),
            key="save_target_name",
        )

    save_dir = getattr(config, "save_directory", "./captures")

    # Build processing suffix for enhanced filename
    steps = []
    if params.get("stretch", "none") != "none":
        steps.append(params["stretch"].upper())
    if params.get("background_sub"):
        steps.append("bgsub")
    if params.get("denoise"):
        steps.append(f"dn{params.get('denoise_strength', 7)}")
    if params.get("hot_pixel"):
        steps.append("hp")
    if params.get("sharpen"):
        steps.append("sharp")
    if params.get("color_balance"):
        steps.append("wb")
    suffix = "_".join(steps) if steps else "raw"

    with col_raw:
        st.write("")
        st.write("")
        if st.button("Save Raw", use_container_width=True, key="btn_save_raw",
                     help="Save the unprocessed image."):
            path = save_image(image, target, save_dir=save_dir)
            st.success(f"Raw: {path}")

    with col_enhanced:
        st.write("")
        st.write("")
        if st.button("Save Enhanced", type="primary", use_container_width=True,
                     key="btn_save_enhanced",
                     help="Save the processed image with enhancement metadata in filename."):
            path = save_image(enhanced, f"{target}_{suffix}", save_dir=save_dir)
            st.success(f"Enhanced: {path}")

    with col_both:
        st.write("")
        st.write("")
        if st.button("Save Both", use_container_width=True, key="btn_save_both",
                     help="Save both raw and enhanced versions."):
            path_raw = save_image(image, target, save_dir=save_dir)
            path_enh = save_image(enhanced, f"{target}_{suffix}", save_dir=save_dir)
            st.success(f"Saved both!")
```

---

## 6. Testing Strategy

### Manual Testing Checklist
- [ ] Capture a real image from the Seestar S50
- [ ] Apply each stretch method individually and verify visual output
- [ ] Toggle each enhancement checkbox and verify it changes the image
- [ ] Test all 4 presets produce visibly different results
- [ ] Test Side-by-Side comparison shows two distinct images
- [ ] Test Slider Overlay comparison works (drag divider)
- [ ] Test Toggle comparison switches between original and enhanced
- [ ] Test GHS sliders (D, b, SP) produce real-time changes
- [ ] Test denoise strength slider produces visible difference
- [ ] Test sharpen amount/radius sliders produce visible difference
- [ ] Test star detection overlay draws circles on stars
- [ ] Test Save Raw, Save Enhanced, Save Both buttons
- [ ] Test enhanced filename includes processing steps (e.g., `M42_STF_bgsub_dn7_20260209_120000.png`)
- [ ] Test loop mode still works without live stacking
- [ ] Test live stacking shows frame count and SNR improvement
- [ ] Test no errors when switching between presets rapidly
- [ ] Test no memory errors after processing 10+ images in sequence

### Unit Tests (create `tests/test_image_enhancement.py`)
```python
import numpy as np
from PIL import Image
from utils.image_enhancement import (
    stretch_stf, stretch_ghs, stretch_arcsinh, stretch_clahe,
    subtract_background, reduce_noise, sharpen_unsharp_mask,
    balance_color, detect_stars, run_pipeline,
    align_frame, accumulate_stack,
)

def _make_test_image(w=256, h=256, channels=3):
    """Create a synthetic test image with stars and gradient."""
    data = np.random.normal(0.1, 0.02, (h, w, channels))
    # Add fake stars
    for _ in range(20):
        x, y = np.random.randint(10, w-10), np.random.randint(10, h-10)
        data[y-2:y+2, x-2:x+2, :] = np.random.uniform(0.5, 1.0)
    # Add gradient (light pollution)
    gradient = np.linspace(0, 0.2, w).reshape(1, w, 1)
    data += gradient
    return np.clip(data, 0, 1)

def test_stf_produces_output():
    data = _make_test_image()
    result = stretch_stf(data)
    assert result.shape == data.shape
    assert result.min() >= 0.0
    assert result.max() <= 1.0
    assert not np.array_equal(result, data)  # Should change the image

def test_ghs_no_stretch_passthrough():
    data = _make_test_image()
    result = stretch_ghs(data, D=0)
    np.testing.assert_array_equal(result, data)

def test_ghs_with_stretch():
    data = _make_test_image()
    result = stretch_ghs(data, D=5.0, b=0.25, SP=0.0)
    assert result.shape == data.shape
    assert not np.array_equal(result, data)

def test_arcsinh_preserves_shape():
    data = _make_test_image()
    result = stretch_arcsinh(data, scale=10.0)
    assert result.shape == data.shape
    assert result.min() >= 0.0
    assert result.max() <= 1.0

def test_clahe_works():
    data = _make_test_image()
    result = stretch_clahe(data, clip_limit=2.0)
    assert result.shape == data.shape

def test_background_subtraction():
    data = _make_test_image()
    result = subtract_background(data, box_size=32)
    assert result.shape == data.shape
    # Gradient should be reduced
    assert np.std(result.mean(axis=0)) < np.std(data.mean(axis=0))

def test_noise_reduction():
    data = _make_test_image()
    result = reduce_noise(data, strength=7)
    assert result.shape == data.shape
    # Noise should be reduced
    assert np.std(result) <= np.std(data) + 0.01

def test_sharpen():
    data = _make_test_image()
    result = sharpen_unsharp_mask(data, amount=1.0, radius=1.5)
    assert result.shape == data.shape

def test_color_balance():
    data = _make_test_image()
    result = balance_color(data)
    assert result.shape == data.shape
    # Channel means should be closer together
    means_before = [np.mean(data[:,:,c]) for c in range(3)]
    means_after = [np.mean(result[:,:,c]) for c in range(3)]
    assert np.std(means_after) <= np.std(means_before) + 0.001

def test_pipeline_runs():
    img = Image.fromarray((_make_test_image() * 255).astype(np.uint8), mode='RGB')
    params = {
        "stretch": "stf",
        "stretch_params": {},
        "background_sub": True,
        "denoise": True,
        "denoise_strength": 7,
        "sharpen": True,
        "sharpen_amount": 1.0,
        "sharpen_radius": 1.5,
        "color_balance": True,
    }
    result = run_pipeline(img, params)
    assert isinstance(result, Image.Image)
    assert result.size == img.size

def test_star_detection():
    data = _make_test_image()
    stars = detect_stars(data, fwhm=3.0, threshold_sigma=3.0)
    assert isinstance(stars, list)
    assert len(stars) > 0  # Should find some of our fake stars

def test_accumulate_stack():
    frame1 = _make_test_image()
    frame2 = _make_test_image()
    stack = accumulate_stack(frame1, frame2, count=1)
    assert stack.shape == frame1.shape
    # Stack should be smoother than individual frames
    assert np.std(stack) < max(np.std(frame1), np.std(frame2)) + 0.01
```

### Performance Benchmarks
| Operation | Target | Method |
|-----------|--------|--------|
| STF stretch (1920x1080) | < 100ms | `time.time()` around call |
| GHS stretch (1920x1080) | < 200ms | `time.time()` around call |
| Full pipeline (all steps) | < 2000ms | `time.time()` around `run_pipeline()` |
| Background subtraction | < 100ms | `time.time()` around `subtract_background()` |
| NLM denoise | < 200ms | `time.time()` around `reduce_noise()` |
| Star detection | < 500ms | `time.time()` around `detect_stars()` |

---

## 7. Deployment

### Updated requirements.txt
```
streamlit>=1.30.0
requests>=2.31.0
httpx>=0.25.0
numpy>=1.24.0
Pillow>=10.0.0
astropy>=6.0.0
toml>=0.10.2
plotly>=5.18.0
# Image Enhancement Pipeline
scikit-image>=0.22.0
opencv-python-headless>=4.9.0
sep>=1.2.1
photutils>=1.10.0
astroalign>=2.5.1
lacosmic>=1.1.0
streamlit-image-comparison>=0.0.4
scipy>=1.11.0
```

### Updated Dockerfile
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# System deps for OpenCV, sep (needs gcc for C extensions)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    g++ \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8502

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8502/_stcore/health || exit 1

ENTRYPOINT ["streamlit", "run", "app.py", \
    "--server.port=8502", \
    "--server.address=0.0.0.0", \
    "--server.headless=true", \
    "--theme.base=dark", \
    "--theme.primaryColor=#00ff88"]
```

### Startup Sequence
1. Rebuild container: `docker compose up -d --build`
2. Verify container starts: `docker logs seestar-scope --tail 20`
3. Open browser to `http://localhost:8502`
4. Navigate to Camera & Imaging page
5. Capture an image
6. Verify Enhancement panel appears below Preview
7. Test each stretch method and enhancement toggle
8. Test all 3 comparison modes
9. Test Save Raw / Save Enhanced / Save Both

---

## 8. Success Metrics

### Verification Steps
1. [ ] Docker container builds without errors (all new deps install)
2. [ ] App starts and all 6 pages load without errors
3. [ ] Capture an image - preview appears as before
4. [ ] Enhancement panel renders below preview with all controls
5. [ ] Each stretch method (6 total) produces a visually different result
6. [ ] STF auto-stretch produces the classic "PixInsight look" on a deep sky image
7. [ ] GHS sliders change the image in real time
8. [ ] Background subtraction visibly reduces light pollution gradient
9. [ ] Noise reduction visibly smooths the image
10. [ ] Sharpening visibly increases detail
11. [ ] Star detection overlay draws circles on actual stars
12. [ ] Side-by-Side comparison shows original left, enhanced right
13. [ ] Slider Overlay comparison has working drag divider
14. [ ] Toggle comparison switches images on checkbox click
15. [ ] Presets apply correct combinations (Deep Sky, Planetary, etc)
16. [ ] Save Enhanced creates file with processing metadata in name
17. [ ] Full pipeline completes in < 2 seconds
18. [ ] Loop mode still works (no regressions)
19. [ ] Live stacking accumulates frames and shows SNR improvement
20. [ ] No Streamlit widget errors or session state conflicts

### Performance Benchmarks
| Metric | Target | Acceptable |
|--------|--------|------------|
| STF stretch time | < 100ms | < 200ms |
| Full pipeline time | < 2000ms | < 3000ms |
| Page rerun time (with cached enhancement) | < 500ms | < 1000ms |
| Docker image size increase | < 500MB | < 800MB |
| Memory usage per image | < 150MB | < 250MB |
