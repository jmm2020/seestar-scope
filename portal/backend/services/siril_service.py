"""
Siril Processing Service for Seestar S50 Astrophotography Pipeline

Automates Siril CLI for image stacking, registration, and enhancement.
Optimized for Seestar S50 (Sony IMX462 color sensor, Bayer RGGB pattern).
"""

import subprocess
import shutil
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass
from enum import Enum
import json
import logging

logger = logging.getLogger(__name__)


class ProcessingStatus(Enum):
    """Processing pipeline status codes"""
    PENDING = "pending"
    CONVERTING = "converting"
    REGISTERING = "registering"
    STACKING = "stacking"
    STRETCHING = "stretching"
    EXPORTING = "exporting"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class ProcessingResult:
    """Result of Siril processing pipeline"""
    success: bool
    status: ProcessingStatus
    output_path: Optional[Path] = None
    jpeg_path: Optional[Path] = None
    error_message: Optional[str] = None
    siril_output: Optional[str] = None
    stats: Optional[Dict] = None


class SirilService:
    """Siril automation service for Seestar S50 image processing."""

    def __init__(
        self,
        data_root: str = "data",
        siril_bin: str = "siril-cli",
        gallery_dir: Optional[str] = None
    ):
        self.data_root = Path(data_root)
        self.siril_bin = siril_bin
        self.gallery_dir = Path(gallery_dir) if gallery_dir else self.data_root / "gallery"

        self.lights_dir = self.data_root / "lights"
        self.processed_dir = self.data_root / "processed"
        self.stacked_dir = self.gallery_dir

        for d in [self.lights_dir, self.processed_dir, self.stacked_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def process_session(
        self,
        session_id: str,
        fits_files: List[Path],
        target_name: str = "target",
        metadata: Optional[Dict] = None
    ) -> ProcessingResult:
        """Process a session of FITS files through the Siril pipeline."""
        try:
            logger.info(f"Starting Siril processing for session {session_id}")

            if not fits_files:
                return ProcessingResult(
                    success=False,
                    status=ProcessingStatus.FAILED,
                    error_message="No FITS files provided"
                )

            if not self._validate_fits_files(fits_files):
                return ProcessingResult(
                    success=False,
                    status=ProcessingStatus.FAILED,
                    error_message="FITS file validation failed"
                )

            session_dir = self.processed_dir / session_id
            session_dir.mkdir(exist_ok=True)

            logger.info(f"Copying {len(fits_files)} FITS files to {session_dir}")
            for fits_file in fits_files:
                shutil.copy2(fits_file, session_dir / fits_file.name)

            script_path = session_dir / "process.ssf"
            self._generate_seestar_script(
                script_path=script_path,
                session_dir=session_dir,
                num_files=len(fits_files),
                target_name=target_name,
                metadata=metadata
            )

            result = self._execute_siril_script(script_path, session_dir)
            if not result.success:
                return result

            stacked_fits = session_dir / f"stacked_{target_name}.fit"
            jpeg_path = session_dir / f"stacked_{target_name}.jpg"

            if not stacked_fits.exists():
                return ProcessingResult(
                    success=False,
                    status=ProcessingStatus.FAILED,
                    error_message="Stacked FITS not found after processing",
                    siril_output=result.siril_output
                )

            final_fits = self.stacked_dir / f"{target_name}_{session_id}.fit"
            final_jpeg = self.stacked_dir / f"{target_name}_{session_id}.jpg"

            shutil.move(str(stacked_fits), str(final_fits))
            if jpeg_path.exists():
                shutil.move(str(jpeg_path), str(final_jpeg))

            logger.info(f"Processing complete: {final_fits}")

            return ProcessingResult(
                success=True,
                status=ProcessingStatus.COMPLETE,
                output_path=final_fits,
                jpeg_path=final_jpeg if final_jpeg.exists() else None,
                siril_output=result.siril_output,
                stats={
                    "input_frames": len(fits_files),
                    "output_fits": str(final_fits),
                    "output_jpeg": str(final_jpeg) if final_jpeg.exists() else None
                }
            )

        except Exception as e:
            logger.error(f"Processing failed: {e}", exc_info=True)
            return ProcessingResult(
                success=False,
                status=ProcessingStatus.FAILED,
                error_message=str(e)
            )

    def _generate_seestar_script(
        self,
        script_path: Path,
        session_dir: Path,
        num_files: int,
        target_name: str,
        metadata: Optional[Dict] = None
    ):
        """Generate Siril .ssf script optimized for Seestar S50."""
        script = [
            "# Seestar S50 Processing Script",
            "# Generated by UCIS SirilService",
            f"# Target: {target_name}",
            f"# Frames: {num_files}",
            "",
            f"cd {session_dir}",
            "",
            "# Convert FITS -> Siril format",
            "convert light -out=../lights/light",
            "",
            "# Debayer for color sensor (Bayer RGGB)",
            "preprocess light -debayer",
            "",
            "# Register frames (star alignment)",
            "register light -drizzle",
            "",
            "# Stack with sigma-clipping rejection",
            "stack r_light rej 3 3 -norm=addscale -out=stacked",
            "",
            "# AutoStretch for deep-sky visibility",
            "load stacked",
            "autostretch -sc -targetbg 0.25",
            f"save {target_name}_stacked",
            "",
            "# Export JPEG for gallery",
            f"savejpg {target_name}_stacked -quality=95",
            "",
            "close"
        ]

        with open(script_path, 'w') as f:
            f.write('\n'.join(script))

        logger.info(f"Generated Siril script: {script_path}")

    def _execute_siril_script(
        self,
        script_path: Path,
        working_dir: Path
    ) -> ProcessingResult:
        """Execute Siril script via CLI subprocess."""
        try:
            logger.info(f"Executing Siril script: {script_path}")

            result = subprocess.run(
                [self.siril_bin, "-s", str(script_path)],
                cwd=str(working_dir),
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout
            )

            if result.returncode != 0:
                logger.error(f"Siril failed with code {result.returncode}")
                logger.error(f"stderr: {result.stderr}")
                return ProcessingResult(
                    success=False,
                    status=ProcessingStatus.FAILED,
                    error_message=f"Siril exited with code {result.returncode}",
                    siril_output=result.stderr
                )

            logger.info("Siril execution successful")
            return ProcessingResult(
                success=True,
                status=ProcessingStatus.COMPLETE,
                siril_output=result.stdout
            )

        except subprocess.TimeoutExpired:
            logger.error("Siril execution timed out")
            return ProcessingResult(
                success=False,
                status=ProcessingStatus.FAILED,
                error_message="Siril execution timed out (>10 minutes)"
            )
        except Exception as e:
            logger.error(f"Siril execution error: {e}", exc_info=True)
            return ProcessingResult(
                success=False,
                status=ProcessingStatus.FAILED,
                error_message=str(e)
            )

    def _validate_fits_files(self, fits_files: List[Path]) -> bool:
        """Validate that all files exist and are FITS format"""
        for f in fits_files:
            if not f.exists():
                logger.error(f"FITS file not found: {f}")
                return False
            if f.suffix.lower() not in ['.fits', '.fit', '.fts']:
                logger.error(f"Not a FITS file: {f}")
                return False
        return True

    def get_processing_status(self, session_id: str) -> Dict:
        """Get status of a processing session."""
        session_dir = self.processed_dir / session_id
        if not session_dir.exists():
            return {"status": "not_found", "session_id": session_id}

        stacked_files = list(self.stacked_dir.glob(f"*{session_id}*"))
        if stacked_files:
            return {
                "status": "complete",
                "session_id": session_id,
                "output_files": [str(f) for f in stacked_files]
            }
        else:
            return {
                "status": "processing",
                "session_id": session_id,
                "working_dir": str(session_dir)
            }
