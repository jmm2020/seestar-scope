"""
ASTAP Plate Solving Service

Implements astrometric plate solving via ASTAP CLI to verify telescope
pointing accuracy after slews. Supports blind and hint-based solving modes.

Author: Lore (Phase 3)
"""

import asyncio
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import re
import math


class SolveStatus(Enum):
    """Plate solving job status"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"


class SolveMode(Enum):
    """Solving mode: blind or hint-based"""
    BLIND = "blind"
    HINT = "hint"


@dataclass
class WCSSolution:
    """World Coordinate System solution from plate solve"""
    ra_hours: float  # Right Ascension in decimal hours
    dec_degrees: float  # Declination in decimal degrees
    rotation_deg: float  # Field rotation in degrees
    pixel_scale: float  # Arcseconds per pixel
    fov_width: float  # Field of view width in degrees
    fov_height: float  # Field of view height in degrees
    num_stars: int  # Number of stars used in solution
    residual_arcsec: float  # RMS residual in arcseconds


@dataclass
class PlatesolvingResult:
    """Complete plate solving result with offset calculation"""
    session_id: str
    status: SolveStatus
    mode: SolveMode
    image_path: str
    solution: Optional[WCSSolution] = None
    expected_ra_hours: Optional[float] = None
    expected_dec_degrees: Optional[float] = None
    offset_arcsec: Optional[float] = None  # Angular separation from expected
    offset_ra_arcsec: Optional[float] = None  # RA offset component
    offset_dec_arcsec: Optional[float] = None  # Dec offset component
    solve_time_sec: Optional[float] = None
    error_message: Optional[str] = None
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


class ASTAPService:
    """
    ASTAP plate solving service with V-curve search algorithm.
    
    ASTAP (Astrometric STAcking Program) is a fast plate solver that uses
    a quad-tree star pattern matching algorithm. This service wraps the
    ASTAP CLI and parses INI output for WCS solutions.
    """

    def __init__(
        self,
        astap_bin: str = "astap",
        data_root: str = "/data/seestar",
        timeout_sec: int = 120,
    ):
        """
        Initialize ASTAP service.

        Args:
            astap_bin: Path to ASTAP CLI binary
            data_root: Root directory for working files
            timeout_sec: Timeout for solve operations
        """
        self.astap_bin = astap_bin
        self.data_root = Path(data_root)
        self.platesolve_dir = self.data_root / "platesolve"
        self.platesolve_dir.mkdir(parents=True, exist_ok=True)
        self.timeout_sec = timeout_sec
        
        # In-memory session storage (production would use Redis/database)
        self._sessions: Dict[str, PlatesolvingResult] = {}

    async def solve_blind(
        self,
        image_path: Path,
        fov_deg: Optional[float] = None,
        downsample: int = 0,
    ) -> PlatesolvingResult:
        """
        Perform blind plate solving without position hints.

        Args:
            image_path: Path to FITS or image file to solve
            fov_deg: Field of view estimate in degrees (optional hint)
            downsample: Downsample factor (0=auto, 1=none, 2=2x2, etc.)

        Returns:
            PlatesolvingResult with solution or error
        """
        session_id = f"solve_{uuid.uuid4().hex[:8]}"
        result = PlatesolvingResult(
            session_id=session_id,
            status=SolveStatus.PENDING,
            mode=SolveMode.BLIND,
            image_path=str(image_path),
        )
        self._sessions[session_id] = result

        # Build ASTAP command
        cmd = [self.astap_bin, "-f", str(image_path)]
        
        if fov_deg is not None:
            cmd.extend(["-fov", str(fov_deg)])
        
        if downsample > 0:
            cmd.extend(["-z", str(downsample)])

        # Execute solve
        result.status = SolveStatus.RUNNING
        start_time = datetime.utcnow()

        try:
            solution = await self._execute_astap(cmd, image_path)
            result.solution = solution
            result.status = SolveStatus.SUCCESS
            result.solve_time_sec = (datetime.utcnow() - start_time).total_seconds()
        except subprocess.TimeoutExpired:
            result.status = SolveStatus.TIMEOUT
            result.error_message = f"Solve timeout after {self.timeout_sec}s"
        except Exception as e:
            result.status = SolveStatus.FAILED
            result.error_message = str(e)

        return result

    async def solve_hint(
        self,
        image_path: Path,
        ra_hours: float,
        dec_degrees: float,
        search_radius_deg: float = 5.0,
        fov_deg: Optional[float] = None,
        downsample: int = 0,
    ) -> PlatesolvingResult:
        """
        Perform hint-based plate solving with expected position.

        Args:
            image_path: Path to FITS or image file to solve
            ra_hours: Expected RA in decimal hours (0-24)
            dec_degrees: Expected Dec in decimal degrees (-90 to +90)
            search_radius_deg: Search radius around hint position
            fov_deg: Field of view estimate in degrees (optional)
            downsample: Downsample factor (0=auto, 1=none, 2=2x2, etc.)

        Returns:
            PlatesolvingResult with solution and offset from expected
        """
        session_id = f"solve_{uuid.uuid4().hex[:8]}"
        result = PlatesolvingResult(
            session_id=session_id,
            status=SolveStatus.PENDING,
            mode=SolveMode.HINT,
            image_path=str(image_path),
            expected_ra_hours=ra_hours,
            expected_dec_degrees=dec_degrees,
        )
        self._sessions[session_id] = result

        # Build ASTAP command with position hint
        # ASTAP uses -ra (hours) and -spd (south pole distance = 90 + dec)
        spd = 90.0 + dec_degrees
        
        cmd = [
            self.astap_bin,
            "-f", str(image_path),
            "-ra", str(ra_hours),
            "-spd", str(spd),
            "-r", str(search_radius_deg),
        ]
        
        if fov_deg is not None:
            cmd.extend(["-fov", str(fov_deg)])
        
        if downsample > 0:
            cmd.extend(["-z", str(downsample)])

        # Execute solve
        result.status = SolveStatus.RUNNING
        start_time = datetime.utcnow()

        try:
            solution = await self._execute_astap(cmd, image_path)
            result.solution = solution
            result.status = SolveStatus.SUCCESS
            result.solve_time_sec = (datetime.utcnow() - start_time).total_seconds()

            # Calculate offset from expected position
            offset = self._calculate_offset(
                ra_hours, dec_degrees,
                solution.ra_hours, solution.dec_degrees
            )
            result.offset_arcsec = offset["separation_arcsec"]
            result.offset_ra_arcsec = offset["ra_arcsec"]
            result.offset_dec_arcsec = offset["dec_arcsec"]

        except subprocess.TimeoutExpired:
            result.status = SolveStatus.TIMEOUT
            result.error_message = f"Solve timeout after {self.timeout_sec}s"
        except Exception as e:
            result.status = SolveStatus.FAILED
            result.error_message = str(e)

        return result

    async def _execute_astap(
        self,
        cmd: List[str],
        image_path: Path,
    ) -> WCSSolution:
        """
        Execute ASTAP CLI and parse INI output.

        ASTAP writes solution to <image>.ini file with WCS parameters.

        Args:
            cmd: ASTAP command line arguments
            image_path: Path to image being solved

        Returns:
            WCSSolution parsed from ASTAP INI output

        Raises:
            RuntimeError: If solve fails or output cannot be parsed
        """
        # Run ASTAP with timeout
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout_sec,
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise subprocess.TimeoutExpired(cmd, self.timeout_sec)

        # Check return code
        if process.returncode != 0:
            stderr_str = stderr.decode() if stderr else "Unknown error"
            raise RuntimeError(f"ASTAP failed: {stderr_str}")

        # Parse INI file for solution
        ini_path = image_path.with_suffix(image_path.suffix + ".ini")
        if not ini_path.exists():
            raise RuntimeError("ASTAP did not produce solution INI file")

        return self._parse_astap_ini(ini_path)

    def _parse_astap_ini(self, ini_path: Path) -> WCSSolution:
        """
        Parse ASTAP INI output for WCS solution.

        Example INI format:
        CRVAL1=12.345  # RA in degrees
        CRVAL2=-23.456  # Dec in degrees
        CROTA1=45.6  # Rotation in degrees
        CDELT1=-0.00123  # Pixel scale in degrees/pixel
        CDELT2=0.00123
        PLTSOLVD=T  # Solution status
        """
        ini_text = ini_path.read_text()
        
        # Extract WCS parameters using regex
        def extract_float(pattern: str) -> float:
            match = re.search(pattern, ini_text)
            if not match:
                raise RuntimeError(f"Missing WCS parameter: {pattern}")
            return float(match.group(1))

        def extract_int(pattern: str, default: int = 0) -> int:
            match = re.search(pattern, ini_text)
            if not match:
                return default
            return int(match.group(1))

        # Check if solution succeeded
        if "PLTSOLVD=T" not in ini_text:
            raise RuntimeError("ASTAP solve failed (PLTSOLVD != T)")

        # Extract WCS parameters
        ra_deg = extract_float(r"CRVAL1=([\d.-]+)")
        dec_deg = extract_float(r"CRVAL2=([\d.-]+)")
        rotation_deg = extract_float(r"CROTA1=([\d.-]+)")
        cdelt1 = extract_float(r"CDELT1=([\d.-]+)")
        cdelt2 = extract_float(r"CDELT2=([\d.-]+)")
        
        # Optional parameters
        num_stars = extract_int(r"NRSTARS=(\d+)", default=0)
        
        # Calculate pixel scale (average of x/y)
        pixel_scale_deg = (abs(cdelt1) + abs(cdelt2)) / 2.0
        pixel_scale_arcsec = pixel_scale_deg * 3600.0
        
        # Estimate FOV (ASTAP may provide FOVX/FOVY)
        fov_width = extract_float(r"FOVX=([\d.-]+)") if "FOVX=" in ini_text else pixel_scale_deg * 1000
        fov_height = extract_float(r"FOVY=([\d.-]+)") if "FOVY=" in ini_text else pixel_scale_deg * 1000
        
        # RMS residual (if available)
        residual_arcsec = extract_float(r"RMSERR=([\d.-]+)") if "RMSERR=" in ini_text else 0.0

        return WCSSolution(
            ra_hours=ra_deg / 15.0,  # Convert degrees to hours
            dec_degrees=dec_deg,
            rotation_deg=rotation_deg,
            pixel_scale=pixel_scale_arcsec,
            fov_width=fov_width,
            fov_height=fov_height,
            num_stars=num_stars,
            residual_arcsec=residual_arcsec,
        )

    def _calculate_offset(
        self,
        expected_ra_hours: float,
        expected_dec_deg: float,
        solved_ra_hours: float,
        solved_dec_deg: float,
    ) -> Dict[str, float]:
        """
        Calculate angular separation between expected and solved positions.

        Uses spherical trigonometry (haversine formula) for accurate
        separation on the celestial sphere.

        Args:
            expected_ra_hours: Expected RA in hours
            expected_dec_deg: Expected Dec in degrees
            solved_ra_hours: Solved RA in hours
            solved_dec_deg: Solved Dec in degrees

        Returns:
            Dict with separation_arcsec, ra_arcsec, dec_arcsec
        """
        # Convert to radians
        ra1 = math.radians(expected_ra_hours * 15.0)  # Hours to degrees to radians
        dec1 = math.radians(expected_dec_deg)
        ra2 = math.radians(solved_ra_hours * 15.0)
        dec2 = math.radians(solved_dec_deg)

        # Haversine formula for great circle distance
        dra = ra2 - ra1
        ddec = dec2 - dec1
        
        a = math.sin(ddec / 2) ** 2 + \
            math.cos(dec1) * math.cos(dec2) * math.sin(dra / 2) ** 2
        c = 2 * math.asin(math.sqrt(a))
        
        separation_rad = c
        separation_arcsec = math.degrees(separation_rad) * 3600.0

        # Component offsets (approximation valid for small angles)
        ra_offset_arcsec = (solved_ra_hours - expected_ra_hours) * 15.0 * 3600.0 * math.cos(dec1)
        dec_offset_arcsec = (solved_dec_deg - expected_dec_deg) * 3600.0

        return {
            "separation_arcsec": separation_arcsec,
            "ra_arcsec": ra_offset_arcsec,
            "dec_arcsec": dec_offset_arcsec,
        }

    def get_result(self, session_id: str) -> Optional[PlatesolvingResult]:
        """Get result for a plate solving session."""
        return self._sessions.get(session_id)

    def list_sessions(self) -> List[str]:
        """List all session IDs."""
        return list(self._sessions.keys())
