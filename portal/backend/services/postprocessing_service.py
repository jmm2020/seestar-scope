"""
Postprocessing Service - Image Enhancement Pipeline
====================================================
Wraps the algorithm library in `utils.image_enhancement` for server-side use.
Manages master calibration frames (dark/flat/bias) on disk and runs the
configurable enhancement pipeline asynchronously.
"""

from __future__ import annotations

import logging
import shutil
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
from PIL import Image

# Make `utils.image_enhancement` importable when uvicorn runs with cwd=portal/.
# In containers, copy portal/utils/ alongside backend/ in the Dockerfile.
_PORTAL_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PORTAL_ROOT) not in sys.path:
    sys.path.insert(0, str(_PORTAL_ROOT))

logger = logging.getLogger(__name__)

VALID_FRAME_TYPES = ("dark", "flat", "bias")


@dataclass
class CalibrationFrames:
    """Paths to master calibration frames on disk (None when not uploaded)."""

    dark_path: Optional[str] = None
    flat_path: Optional[str] = None
    bias_path: Optional[str] = None


@dataclass
class PostprocessingResult:
    """Result of one apply_pipeline() invocation."""

    success: bool
    output_path: Optional[str] = None
    error_message: Optional[str] = None
    stats: Optional[Dict[str, Any]] = None
    duration_seconds: float = 0.0
    job_id: Optional[str] = None
    completed_at: Optional[datetime] = None


class PostprocessingService:
    """Server-side image enhancement service."""

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.calibration_dir = self.data_dir / "calibration"
        self.processed_dir = self.data_dir / "processed"
        self.calibration_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

        self._calibration = CalibrationFrames()
        self._discover_existing_masters()
        self._current_result: Optional[PostprocessingResult] = None

    def _discover_existing_masters(self) -> None:
        """Populate _calibration with masters already on disk at startup."""
        for frame_type in VALID_FRAME_TYPES:
            path = self._find_master(frame_type)
            if path is not None:
                setattr(self._calibration, f"{frame_type}_path", str(path))

    def _find_master(self, frame_type: str) -> Optional[Path]:
        """Locate an existing master file by stem (any extension)."""
        for candidate in self.calibration_dir.glob(f"master_{frame_type}.*"):
            if candidate.is_file():
                return candidate
        return None

    @property
    def current_result(self) -> Optional[PostprocessingResult]:
        return self._current_result

    # ------------------------------------------------------------------
    # Calibration frame management
    # ------------------------------------------------------------------

    def store_calibration_frame(self, frame_type: str, source_path: str) -> bool:
        """Copy a source file to calibration_dir/master_<frame_type>.<ext>."""
        if frame_type not in VALID_FRAME_TYPES:
            logger.error("Invalid calibration frame_type: %s", frame_type)
            return False

        src = Path(source_path)
        if not src.exists():
            logger.error("Calibration source missing: %s", source_path)
            return False

        ext = src.suffix.lower() or ".png"
        # Remove any prior master with a different extension so glob stays unique.
        for old in self.calibration_dir.glob(f"master_{frame_type}.*"):
            try:
                old.unlink()
            except OSError as exc:
                logger.warning("Failed to remove old master %s: %s", old, exc)

        dest = self.calibration_dir / f"master_{frame_type}{ext}"
        try:
            shutil.copy2(src, dest)
        except OSError as exc:
            logger.error(
                "Failed to copy calibration frame %s from %s to %s: %s",
                frame_type,
                src,
                dest,
                exc,
            )
            return False
        setattr(self._calibration, f"{frame_type}_path", str(dest))
        logger.info("Stored master %s at %s", frame_type, dest)
        return True

    def delete_calibration_frame(self, frame_type: str) -> bool:
        """Remove a master calibration frame."""
        if frame_type not in VALID_FRAME_TYPES:
            return False
        existing = self._find_master(frame_type)
        if existing is None:
            return False
        try:
            existing.unlink()
        except OSError as exc:
            logger.error("Failed to delete master %s: %s", frame_type, exc)
            return False
        setattr(self._calibration, f"{frame_type}_path", None)
        return True

    def get_calibration_info(self) -> Dict[str, Any]:
        """Return current calibration frame paths and existence flags."""
        info: Dict[str, Any] = {}
        for frame_type in VALID_FRAME_TYPES:
            path = getattr(self._calibration, f"{frame_type}_path")
            info[frame_type] = {
                "path": path,
                "exists": bool(path) and Path(path).exists(),
            }
        return info

    # ------------------------------------------------------------------
    # Pipeline execution
    # ------------------------------------------------------------------

    def apply_pipeline(
        self, image_path: str, params: Dict[str, Any], job_id: Optional[str] = None
    ) -> PostprocessingResult:
        """Run the enhancement pipeline against ``image_path`` and persist output."""
        start = datetime.now(timezone.utc)
        job_id = job_id or f"pp_{uuid.uuid4().hex[:8]}"

        try:
            from utils.image_enhancement import run_pipeline
        except ImportError as exc:
            logger.error("PostprocessingService: import failed: %s", exc, exc_info=True)
            result = PostprocessingResult(
                success=False,
                error_message=f"image_enhancement import failed: {exc}",
                job_id=job_id,
                completed_at=datetime.now(timezone.utc),
            )
            self._current_result = result
            return result

        src = Path(image_path)
        if not src.exists():
            result = PostprocessingResult(
                success=False,
                error_message=f"Source image not found: {image_path}",
                job_id=job_id,
                completed_at=datetime.now(timezone.utc),
            )
            self._current_result = result
            return result

        try:
            logger.info("PostprocessingService: applying pipeline to %s", image_path)
            image = Image.open(src)
            image.load()

            if params.get("apply_calibration"):
                arr = np.array(image, dtype=np.float64) / 255.0
                arr = self._apply_calibration(arr)
                u8 = (np.clip(arr, 0, 1) * 255).astype(np.uint8)
                image = Image.fromarray(u8, mode=image.mode)

            enhanced = run_pipeline(image, params)

            output_dir = self.processed_dir
            output_dir.mkdir(parents=True, exist_ok=True)
            output_name = f"{src.stem}_processed_{job_id}{src.suffix or '.png'}"
            output_path = output_dir / output_name
            enhanced.save(str(output_path))

            arr_out = np.array(enhanced)
            stats = {
                "min": int(arr_out.min()),
                "max": int(arr_out.max()),
                "mean": float(arr_out.mean()),
                "std": float(arr_out.std()),
            }

            duration = (datetime.now(timezone.utc) - start).total_seconds()

            if stats["max"] == 0:
                result = PostprocessingResult(
                    success=False,
                    output_path=str(output_path),
                    error_message="Output image is all black (verify-after-dispatch)",
                    stats=stats,
                    duration_seconds=duration,
                    job_id=job_id,
                    completed_at=datetime.now(timezone.utc),
                )
            else:
                result = PostprocessingResult(
                    success=True,
                    output_path=str(output_path),
                    stats=stats,
                    duration_seconds=duration,
                    job_id=job_id,
                    completed_at=datetime.now(timezone.utc),
                )
        except Exception as exc:
            logger.error("PostprocessingService: pipeline failed: %s", exc, exc_info=True)
            duration = (datetime.now(timezone.utc) - start).total_seconds()
            result = PostprocessingResult(
                success=False,
                error_message=str(exc),
                duration_seconds=duration,
                job_id=job_id,
                completed_at=datetime.now(timezone.utc),
            )

        self._current_result = result
        return result

    def _apply_calibration(self, arr: np.ndarray) -> np.ndarray:
        """Subtract dark/bias and divide by flat. All work happens in [0,1] float.

        Calibration only applies to mono (2D) data here. The Seestar S50 delivers
        already-debayered RGB to ALPACA, so for 3-channel input we skip the
        Bayer-aware steps and operate per-channel as a best-effort.
        """
        result = arr.astype(np.float64, copy=True)

        bias = self._load_master_array("bias")
        dark = self._load_master_array("dark")
        flat = self._load_master_array("flat")

        if bias is not None and bias.shape == result.shape:
            result = result - bias
        elif bias is not None:
            logger.warning("Bias frame shape %s != image %s; skipping", bias.shape, result.shape)

        if dark is not None and dark.shape == result.shape:
            result = result - dark
        elif dark is not None:
            logger.warning("Dark frame shape %s != image %s; skipping", dark.shape, result.shape)

        if flat is not None and flat.shape == result.shape:
            flat_norm = flat / max(float(np.mean(flat)), 1e-10)
            flat_norm = np.where(flat_norm < 1e-3, 1.0, flat_norm)
            result = result / flat_norm
        elif flat is not None:
            logger.warning("Flat frame shape %s != image %s; skipping", flat.shape, result.shape)

        return np.clip(result, 0.0, 1.0)

    def _load_master_array(self, frame_type: str) -> Optional[np.ndarray]:
        """Load a master frame as float64 [0,1]. Returns None if missing."""
        path_str = getattr(self._calibration, f"{frame_type}_path")
        if not path_str:
            return None
        path = Path(path_str)
        if not path.exists():
            return None

        suffix = path.suffix.lower()
        try:
            if suffix in (".fits", ".fit", ".fts"):
                from astropy.io import fits  # local import - heavy dep

                with fits.open(str(path)) as hdul:
                    data = np.asarray(hdul[0].data, dtype=np.float64)
                if data.size == 0:
                    return None
                # Normalize FITS data to [0,1] using observed range
                lo, hi = float(data.min()), float(data.max())
                if hi > lo:
                    data = (data - lo) / (hi - lo)
                else:
                    data = np.zeros_like(data)
                return data
            else:
                img = Image.open(path)
                img.load()
                return np.array(img, dtype=np.float64) / 255.0
        except Exception as exc:
            logger.error("Failed to load master %s at %s: %s", frame_type, path, exc, exc_info=True)
            return None

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health_check(self) -> Dict[str, Any]:
        """Report whether all required dependencies are importable."""
        missing = []
        for module_name in ("numpy", "cv2", "PIL"):
            try:
                __import__(module_name)
            except ImportError:
                missing.append(module_name)

        # Verify the algorithm module itself is importable.
        try:
            from utils.image_enhancement import run_pipeline  # noqa: F401
        except ImportError as exc:
            return {
                "status": "degraded",
                "service": "postprocessing",
                "error": f"image_enhancement import failed: {exc}",
            }

        if missing:
            return {
                "status": "degraded",
                "service": "postprocessing",
                "missing": missing,
            }

        return {"status": "healthy", "service": "postprocessing"}
