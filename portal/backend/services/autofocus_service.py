"""
Auto-Focus Service -- V-Curve Algorithm with HFR Metric
======================================================
Implements automated focusing for Seestar S50 using:
- V-curve sweep across focuser positions
- Half-Flux Radius (HFR) as focus quality metric
- Parabola fitting to find optimal focus position
- Star detection via thresholding + connected components
"""

import numpy as np
from scipy import ndimage
from typing import Optional, Dict, Any, List, Tuple
import logging
from dataclasses import dataclass
from datetime import datetime
import asyncio

logger = logging.getLogger(__name__)


@dataclass
class AutoFocusConfig:
    """Configuration for autofocus routine."""
    exposure_time: float = 2.0
    gain: int = 100
    step_size: int = 200
    num_steps: int = 11
    detection_threshold: float = 3.0
    min_stars: int = 5
    max_stars: int = 50


@dataclass
class FocusPosition:
    """Single focus measurement."""
    position: int
    hfr: float
    num_stars: int
    timestamp: datetime


@dataclass
class AutoFocusResult:
    """Complete autofocus run result."""
    success: bool
    optimal_position: Optional[int]
    initial_position: int
    final_position: int
    measurements: List[FocusPosition]
    v_curve_fit: Optional[Dict[str, float]]
    error_message: Optional[str]
    duration_seconds: float


class AutoFocusService:
    """V-curve autofocus with HFR metric."""

    def __init__(self, alpaca_client):
        self.alpaca = alpaca_client
        self.config = AutoFocusConfig()
        self._running = False
        self._current_result: Optional[AutoFocusResult] = None

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def current_result(self) -> Optional[AutoFocusResult]:
        return self._current_result

    async def run_autofocus(
        self,
        config: Optional[AutoFocusConfig] = None
    ) -> AutoFocusResult:
        """Execute complete V-curve autofocus routine."""
        if self._running:
            return AutoFocusResult(
                success=False, optimal_position=None,
                initial_position=0, final_position=0,
                measurements=[], v_curve_fit=None,
                error_message="Autofocus already running",
                duration_seconds=0.0
            )

        self._running = True
        start_time = datetime.now()
        if config:
            self.config = config

        try:
            focuser_status = self.alpaca.get_focuser_status()
            initial_position = focuser_status.get('position', 5000)
            logger.info(f"Starting autofocus from position {initial_position}")

            total_range = self.config.step_size * (self.config.num_steps - 1)
            start_position = max(0, initial_position - total_range // 2)

            measurements = []
            positions = [
                start_position + i * self.config.step_size
                for i in range(self.config.num_steps)
            ]

            for position in positions:
                logger.info(f"Measuring HFR at position {position}")
                self.alpaca.move_focuser(position)
                await self._wait_for_focuser_settled()
                image_data = await self._capture_frame()
                hfr, num_stars = self._calculate_hfr(image_data)

                if hfr is None:
                    logger.warning(f"Failed to calculate HFR at position {position}")
                    continue

                measurement = FocusPosition(
                    position=position, hfr=hfr,
                    num_stars=num_stars, timestamp=datetime.now()
                )
                measurements.append(measurement)
                logger.info(f"Position {position}: HFR={hfr:.2f}, Stars={num_stars}")

            if len(measurements) < 5:
                raise ValueError(f"Insufficient measurements: {len(measurements)} < 5")

            optimal_position, fit_params = self._fit_v_curve(measurements)
            if optimal_position is None:
                raise ValueError("Failed to fit V-curve")

            logger.info(f"Moving to optimal focus position: {optimal_position}")
            self.alpaca.move_focuser(optimal_position)
            await self._wait_for_focuser_settled()

            verify_image = await self._capture_frame()
            verify_hfr, verify_stars = self._calculate_hfr(verify_image)
            if verify_hfr:
                logger.info(f"Verification: HFR={verify_hfr:.2f}, Stars={verify_stars}")

            duration = (datetime.now() - start_time).total_seconds()
            result = AutoFocusResult(
                success=True, optimal_position=optimal_position,
                initial_position=initial_position,
                final_position=optimal_position,
                measurements=measurements, v_curve_fit=fit_params,
                error_message=None, duration_seconds=duration
            )
            self._current_result = result
            return result

        except Exception as e:
            logger.error(f"Autofocus failed: {e}")
            duration = (datetime.now() - start_time).total_seconds()
            result = AutoFocusResult(
                success=False, optimal_position=None,
                initial_position=initial_position if 'initial_position' in locals() else 0,
                final_position=initial_position if 'initial_position' in locals() else 0,
                measurements=measurements if 'measurements' in locals() else [],
                v_curve_fit=None, error_message=str(e),
                duration_seconds=duration
            )
            self._current_result = result
            return result
        finally:
            self._running = False

    async def _wait_for_focuser_settled(self, timeout: float = 10.0):
        """Wait for focuser to stop moving."""
        start = datetime.now()
        while (datetime.now() - start).total_seconds() < timeout:
            status = self.alpaca.get_focuser_status()
            if not status.get('ismoving', False):
                await asyncio.sleep(0.5)
                return
            await asyncio.sleep(0.1)
        logger.warning("Focuser settle timeout")

    async def _capture_frame(self) -> np.ndarray:
        """Capture single frame for HFR measurement."""
        self.alpaca.start_exposure(duration=self.config.exposure_time, light=True)
        await asyncio.sleep(self.config.exposure_time + 0.5)
        for _ in range(50):
            status = self.alpaca.get_camera_status()
            if status.get('imageready', False):
                break
            await asyncio.sleep(0.1)
        image_data = self.alpaca.get_imagearray()
        if not image_data:
            raise ValueError("Failed to capture image")
        return np.array(image_data, dtype=np.float32)

    def _calculate_hfr(self, image_data: np.ndarray) -> Tuple[Optional[float], int]:
        """Calculate Half-Flux Radius from image."""
        try:
            if image_data.ndim == 3:
                image_data = np.mean(image_data, axis=2)

            background = np.median(image_data)
            noise = np.std(image_data[image_data < np.percentile(image_data, 50)])
            threshold = background + self.config.detection_threshold * noise
            star_mask = image_data > threshold
            labeled, num_features = ndimage.label(star_mask)

            if num_features == 0:
                logger.warning("No stars detected")
                return None, 0

            hfr_values = []
            for star_id in range(1, num_features + 1):
                star_pixels = labeled == star_id
                if np.sum(star_pixels) < 5:
                    continue
                y_coords, x_coords = np.where(star_pixels)
                total_flux = np.sum(image_data[star_pixels])
                if total_flux == 0:
                    continue
                centroid_x = np.sum(x_coords * image_data[star_pixels]) / total_flux
                centroid_y = np.sum(y_coords * image_data[star_pixels]) / total_flux
                hfr = self._compute_hfr_for_star(
                    image_data, star_pixels, centroid_x, centroid_y, total_flux
                )
                if hfr:
                    hfr_values.append(hfr)

            if len(hfr_values) < self.config.min_stars:
                logger.warning(f"Insufficient stars: {len(hfr_values)} < {self.config.min_stars}")
                return None, 0

            hfr_values = sorted(hfr_values)[:self.config.max_stars]
            return float(np.mean(hfr_values)), len(hfr_values)
        except Exception as e:
            logger.error(f"HFR calculation failed: {e}")
            return None, 0

    def _compute_hfr_for_star(
        self, image_data, star_pixels, centroid_x, centroid_y, total_flux
    ) -> Optional[float]:
        """Compute HFR for a single star."""
        try:
            y_coords, x_coords = np.where(star_pixels)
            distances = np.sqrt((x_coords - centroid_x)**2 + (y_coords - centroid_y)**2)
            sort_indices = np.argsort(distances)
            sorted_distances = distances[sort_indices]
            sorted_fluxes = image_data[y_coords[sort_indices], x_coords[sort_indices]]
            cumulative_flux = np.cumsum(sorted_fluxes)
            half_flux = total_flux / 2.0
            half_flux_idx = np.searchsorted(cumulative_flux, half_flux)
            if half_flux_idx >= len(sorted_distances):
                half_flux_idx = len(sorted_distances) - 1
            hfr = sorted_distances[half_flux_idx]
            if hfr < 0.5 or hfr > 50:
                return None
            return float(hfr)
        except Exception as e:
            logger.error(f"Star HFR computation failed: {e}")
            return None

    def _fit_v_curve(self, measurements: List[FocusPosition]) -> Tuple[Optional[int], Optional[Dict[str, float]]]:
        """Fit parabola to V-curve and find optimal focus."""
        try:
            positions = np.array([m.position for m in measurements])
            hfrs = np.array([m.hfr for m in measurements])
            coeffs = np.polyfit(positions, hfrs, deg=2)
            a, b, c = coeffs

            if a <= 0:
                logger.warning("Invalid V-curve: parabola opens downward")
                min_idx = np.argmin(hfrs)
                return int(positions[min_idx]), None

            optimal_position = -b / (2 * a)
            optimal_position = int(np.clip(optimal_position, 0, 10000))
            min_pos, max_pos = min(positions), max(positions)
            optimal_position = int(np.clip(optimal_position, min_pos, max_pos))

            y_pred = np.polyval(coeffs, positions)
            ss_res = np.sum((hfrs - y_pred) ** 2)
            ss_tot = np.sum((hfrs - np.mean(hfrs)) ** 2)
            r_squared = float(1 - (ss_res / ss_tot)) if ss_tot > 0 else 0.0

            fit_params = {'a': float(a), 'b': float(b), 'c': float(c), 'r_squared': r_squared}
            logger.info(f"V-curve fit: a={a:.6f}, b={b:.4f}, c={c:.2f}, R2={r_squared:.3f}")
            return optimal_position, fit_params
        except Exception as e:
            logger.error(f"V-curve fitting failed: {e}")
            return None, None
