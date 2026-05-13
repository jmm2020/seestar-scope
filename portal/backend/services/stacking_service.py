"""
Siril Stacking Service — Session-Oriented Image Stacking
========================================================
Manages a stacking session lifecycle on top of the existing SirilService:

  configure → start_session → add_frame ... add_frame → run_stacking → result

Workflow inside run_stacking():
  1. Convert input PNG/JPG frames to FITS (so siril `convert` can ingest them
     reliably regardless of the source format)
  2. Generate an SSF (Siril Script File) with optional calibration commands
  3. Invoke `siril-cli` (or override via SIRIL_BIN env var) asynchronously
  4. Move the stacked FITS + JPEG into the gallery directory
  5. Return a StackingResult

This service mirrors the AutoFocusService class structure (dataclasses, is_running
property, async run method, _running flag in finally block) and wraps the existing
SirilService for directory layout and FITS validation utilities.
"""

import asyncio
import logging
import os
import shlex
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import numpy as np
from PIL import Image
from astropy.io import fits

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class StackingConfig:
    """Configuration for a Siril stacking session."""

    target_name: str = "target"
    exposure_time: float = 10.0  # seconds per frame (metadata only)
    gain: int = 80
    dark_path: Optional[str] = None
    flat_path: Optional[str] = None
    bias_path: Optional[str] = None
    sigma_low: float = 3.0
    sigma_high: float = 3.0


@dataclass
class StackingResult:
    """Complete stacking run result."""

    success: bool
    session_id: str
    frame_count: int
    output_fits: Optional[str] = None
    output_jpeg: Optional[str] = None
    error_message: Optional[str] = None
    duration_seconds: float = 0.0
    siril_output: Optional[str] = None


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class StackingService:
    """Session-oriented Siril stacking service."""

    def __init__(
        self,
        data_root: str = "/data/seestar",
        gallery_dir: str = "/data/seestar/gallery",
    ):
        self._running = False
        self._abort_requested = False
        self._current_result: Optional[StackingResult] = None
        self._frame_paths: List[str] = []
        self._session_id: Optional[str] = None
        self._config: StackingConfig = StackingConfig()
        self._progress: float = 0.0

        self._gallery_dir = Path(gallery_dir)
        self._processed_dir = Path(data_root) / "processed"

        # Configurable Siril CLI binary (so ARM64/Flatpak can override)
        self._siril_bin = os.environ.get("SIRIL_BIN", "siril-cli")
        try:
            self._siril_timeout = int(os.environ.get("SIRIL_TIMEOUT", "600"))
        except ValueError:
            self._siril_timeout = 600

    # --- Public properties -------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def current_result(self) -> Optional[StackingResult]:
        return self._current_result

    @property
    def frame_count(self) -> int:
        return len(self._frame_paths)

    @property
    def progress(self) -> float:
        return self._progress

    @property
    def session_id(self) -> Optional[str]:
        return self._session_id

    @property
    def config(self) -> StackingConfig:
        return self._config

    # --- Session management ------------------------------------------------

    def start_session(self, config: Optional[StackingConfig] = None) -> str:
        """Reset state and begin a new stacking session.

        Returns the new session_id.
        """
        self._frame_paths = []
        self._abort_requested = False
        self._progress = 0.0
        self._current_result = None
        if config is not None:
            self._config = config
        self._session_id = uuid.uuid4().hex
        logger.info(
            "Started stacking session %s (target=%s)",
            self._session_id,
            self._config.target_name,
        )
        return self._session_id

    def add_frame(self, path: str) -> bool:
        """Append a frame path to the active session.

        Returns False if no session active. Existence is NOT validated here —
        Siril/astropy will surface bad paths during run_stacking().
        """
        if not self._session_id:
            logger.warning("add_frame called with no active session")
            return False
        self._frame_paths.append(path)
        logger.debug("Added frame to session %s: %s", self._session_id, path)
        return True

    def abort(self) -> bool:
        """Request abort of the running stacking pipeline.

        The pipeline checks _abort_requested between long-running phases.
        """
        if not self._running:
            return False
        self._abort_requested = True
        logger.info("Abort requested for session %s", self._session_id)
        return True

    # --- Main pipeline -----------------------------------------------------

    async def run_stacking(
        self,
        config: Optional[StackingConfig] = None,
    ) -> StackingResult:
        """Execute full stacking pipeline.

        Phases:
          1. Convert input frames → FITS in session working dir
          2. Generate SSF script (with optional calibration)
          3. Invoke siril-cli asynchronously
          4. Move output into the gallery directory
        """
        if self._running:
            return StackingResult(
                success=False,
                session_id=self._session_id or "",
                frame_count=0,
                error_message="Stacking already running",
            )

        if not self._session_id:
            # Auto-start a session if none active
            self.start_session(config)

        if config is not None:
            self._config = config

        self._running = True
        self._abort_requested = False
        self._progress = 0.0
        start_time = datetime.now()

        session_id = self._session_id or uuid.uuid4().hex
        target = self._config.target_name
        frame_paths = list(self._frame_paths)

        try:
            if not frame_paths:
                raise ValueError("No frames added to session — nothing to stack")

            session_dir = self._processed_dir / session_id
            session_dir.mkdir(parents=True, exist_ok=True)
            lights_dir = self._processed_dir / "lights"
            lights_dir.mkdir(parents=True, exist_ok=True)

            # Phase 1: PNG/JPG → FITS conversion -----------------------------
            self._progress = 0.1
            converted_paths = self._convert_frames_to_fits(frame_paths, session_dir)
            if not converted_paths:
                raise ValueError("Failed to convert any input frames to FITS")
            if self._abort_requested:
                raise RuntimeError("Aborted")

            # Phase 2: SSF script generation --------------------------------
            self._progress = 0.3
            script_path = session_dir / "stack.ssf"
            self._generate_stacking_script(
                script_path=script_path,
                session_dir=session_dir,
                num_files=len(converted_paths),
                config=self._config,
            )
            if self._abort_requested:
                raise RuntimeError("Aborted")

            # Phase 3: invoke siril-cli -------------------------------------
            self._progress = 0.5
            stdout, stderr, returncode = await self._run_siril_async(
                script_path=script_path,
                working_dir=session_dir,
            )

            if returncode != 0:
                raise RuntimeError(
                    f"siril-cli exited with code {returncode}: {(stderr or stdout)[:500]}"
                )
            if self._abort_requested:
                raise RuntimeError("Aborted")

            # Phase 4: locate + move outputs --------------------------------
            self._progress = 0.9
            stacked_fits = session_dir / f"{target}_stacked.fit"
            stacked_jpeg = session_dir / f"{target}_stacked.jpg"

            final_fits: Optional[Path] = None
            final_jpeg: Optional[Path] = None

            self._gallery_dir.mkdir(parents=True, exist_ok=True)
            if stacked_fits.exists():
                final_fits = self._gallery_dir / f"{target}_{session_id}.fit"
                shutil.move(str(stacked_fits), str(final_fits))
            if stacked_jpeg.exists():
                final_jpeg = self._gallery_dir / f"{target}_{session_id}.jpg"
                shutil.move(str(stacked_jpeg), str(final_jpeg))

            if final_fits is None:
                raise RuntimeError("Siril completed without producing expected stacked FITS")

            self._progress = 1.0
            duration = (datetime.now() - start_time).total_seconds()

            result = StackingResult(
                success=True,
                session_id=session_id,
                frame_count=len(converted_paths),
                output_fits=str(final_fits),
                output_jpeg=str(final_jpeg) if final_jpeg else None,
                error_message=None,
                duration_seconds=duration,
                siril_output=stdout,
            )
            self._current_result = result
            logger.info(
                "Stacking session %s complete: %d frames → %s",
                session_id,
                len(converted_paths),
                final_fits,
            )
            return result

        except asyncio.TimeoutError:
            logger.error("Siril execution timed out after %ds", self._siril_timeout)
            duration = (datetime.now() - start_time).total_seconds()
            result = StackingResult(
                success=False,
                session_id=session_id,
                frame_count=len(frame_paths),
                error_message=f"Siril execution timed out (>{self._siril_timeout}s)",
                duration_seconds=duration,
            )
            self._current_result = result
            return result

        except Exception as exc:
            logger.error("Stacking session %s failed: %s", session_id, exc, exc_info=True)
            duration = (datetime.now() - start_time).total_seconds()
            result = StackingResult(
                success=False,
                session_id=session_id,
                frame_count=len(frame_paths),
                error_message=str(exc),
                duration_seconds=duration,
            )
            self._current_result = result
            return result

        finally:
            self._running = False

    # --- Helpers -----------------------------------------------------------

    def _convert_frames_to_fits(
        self,
        frame_paths: List[str],
        session_dir: Path,
    ) -> List[Path]:
        """Convert PNG/JPG frames to FITS files in session_dir.

        FITS files are named light_NNNN.fit so that Siril's `convert light`
        command picks them up as a sequence. PNGs from Seestar are 8-bit;
        the warning is logged once per session so users know FITS-direct
        capture is preferred for full dynamic range.
        """
        out: List[Path] = []
        warned_8bit = False

        for idx, src in enumerate(frame_paths, start=1):
            try:
                src_path = Path(src)
                # Pass-through if already FITS
                if src_path.suffix.lower() in (".fit", ".fits", ".fts"):
                    dest = session_dir / f"light_{idx:04d}.fit"
                    shutil.copy2(src_path, dest)
                    out.append(dest)
                    continue

                # Otherwise convert via PIL → numpy → astropy.io.fits
                with Image.open(src_path) as img:
                    if img.mode not in ("L", "I", "RGB", "RGBA"):
                        img = img.convert("RGB")
                    arr = np.asarray(img)

                if arr.dtype == np.uint8 and not warned_8bit:
                    logger.warning(
                        "Frame %s is 8-bit; for full dynamic range capture FITS directly",
                        src_path.name,
                    )
                    warned_8bit = True

                # Preserve source bit depth (uint8 for Seestar PNGs, uint16 for raw FITS pass-through)
                hdu = fits.PrimaryHDU(data=arr)
                dest = session_dir / f"light_{idx:04d}.fit"
                hdu.writeto(dest, overwrite=True)
                out.append(dest)

            except Exception as exc:
                logger.warning("Skipping frame %s: %s", src, exc, exc_info=True)

        return out

    def _generate_stacking_script(
        self,
        script_path: Path,
        session_dir: Path,
        num_files: int,
        config: StackingConfig,
    ) -> None:
        """Write the SSF script for the stacking pipeline.

        Adds calibration commands only when calibration paths are provided.
        """
        target = config.target_name
        sigma_low = config.sigma_low
        sigma_high = config.sigma_high

        lines: List[str] = [
            "# Seestar S50 Stacking Script (StackingService)",
            f"# Target: {target}",
            f"# Frames: {num_files}",
            "",
            f"cd {session_dir}",
            "",
            "# Convert input frames to Siril sequence",
            "convert light -out=../lights/light",
            "",
        ]

        # Calibration is optional. SirilService does color preprocessing for
        # OSC sensors (`preprocess light -debayer`), but if explicit dark/flat/bias
        # paths are provided we use the `calibrate` command instead.
        has_cal = bool(config.dark_path or config.flat_path or config.bias_path)
        if has_cal:
            cal_args: List[str] = ["calibrate light"]
            if config.dark_path:
                cal_args.append(f"-dark={config.dark_path}")
            if config.flat_path:
                cal_args.append(f"-flat={config.flat_path}")
            if config.bias_path:
                cal_args.append(f"-bias={config.bias_path}")
            cal_args.append("-cfa")
            lines.append("# Calibration (dark/flat/bias)")
            lines.append(" ".join(cal_args))
            lines.append("")
        else:
            lines.append("# Debayer for color sensor (Bayer RGGB) — no calibration provided")
            lines.append("preprocess light -debayer")
            lines.append("")

        lines.extend(
            [
                "# Register frames (star alignment)",
                "register pp_light -drizzle",
                "",
                "# Stack with sigma-clipping rejection",
                f"stack r_pp_light rej {sigma_low} {sigma_high} -norm=addscale -out=stacked",
                "",
                "# AutoStretch for visibility",
                "load stacked",
                "autostretch -sc -targetbg 0.25",
                f"save {target}_stacked",
                "",
                "# Export JPEG for gallery",
                f"savejpg {target}_stacked -quality=95",
                "",
                "close",
            ]
        )

        script_path.write_text("\n".join(lines))
        logger.info("Generated stacking SSF: %s", script_path)

    async def _run_siril_async(
        self,
        script_path: Path,
        working_dir: Path,
    ) -> tuple:
        """Run siril-cli via asyncio.create_subprocess_exec.

        SIRIL_BIN env var is honored. Returns (stdout, stderr, returncode).
        Raises asyncio.TimeoutError if Siril runs past SIRIL_TIMEOUT.
        """
        # SIRIL_BIN may include flags ("flatpak run ..."), so split via shlex
        cmd = shlex.split(self._siril_bin) + [
            "-d",
            str(working_dir),
            "-s",
            str(script_path),
        ]

        logger.info("Invoking siril: %s", " ".join(cmd))

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=self._siril_timeout,
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except ProcessLookupError:
                pass
            raise

        return stdout.decode(errors="replace"), stderr.decode(errors="replace"), proc.returncode
