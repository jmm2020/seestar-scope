"""Stellarium Remote Control API Client."""

import requests
from dataclasses import dataclass
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class StellariumObject:
    """A celestial object selected in Stellarium."""

    name: str
    object_type: str
    ra_j2000_hours: float  # RA in hours (converted from Stellarium degrees)
    dec_j2000_degrees: float  # Dec in degrees
    altitude: float  # Current altitude above horizon
    azimuth: float  # Current azimuth
    magnitude: float  # Visual magnitude
    above_horizon: bool  # Whether currently visible
    constellation: str  # IAU constellation abbreviation
    rise: str  # Rise time string
    set_time: str  # Set time string


class StellariumClient:
    """Client for Stellarium Remote Control plugin."""

    def __init__(self, host: str = "localhost", port: int = 8090, timeout: int = 5):
        self.base_url = f"http://{host}:{port}"
        self.timeout = timeout
        self.session = requests.Session()

    def is_available(self) -> bool:
        """Check if Stellarium Remote Control is responding."""
        try:
            resp = self.session.get(f"{self.base_url}/api/main/status", timeout=self.timeout)
            return resp.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def get_status(self) -> Optional[dict]:
        """Get Stellarium status (location, time, FOV)."""
        try:
            resp = self.session.get(f"{self.base_url}/api/main/status", timeout=self.timeout)
            return resp.json() if resp.status_code == 200 else None
        except requests.exceptions.RequestException:
            return None

    def get_selected_object(self) -> Optional[StellariumObject]:
        """Get the currently selected object in Stellarium."""
        try:
            resp = self.session.get(
                f"{self.base_url}/api/objects/info?format=json",
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                return None

            text = resp.text
            if "no current selection" in text:
                return None

            data = resp.json()

            # Convert RA from degrees to hours
            ra_deg = data.get("raJ2000", 0)
            if ra_deg < 0:
                ra_deg += 360
            ra_hours = ra_deg / 15.0

            return StellariumObject(
                name=data.get("name", data.get("localized-name", "Unknown")),
                object_type=data.get("object-type", "unknown"),
                ra_j2000_hours=ra_hours,
                dec_j2000_degrees=data.get("decJ2000", 0),
                altitude=data.get("altitude", 0),
                azimuth=data.get("azimuth", 0),
                magnitude=data.get("vmag", 99),
                above_horizon=data.get("above-horizon", False),
                constellation=data.get("iauConstellation", ""),
                rise=data.get("rise", ""),
                set_time=data.get("set", ""),
            )
        except (requests.exceptions.RequestException, ValueError) as e:
            logger.error(f"Stellarium query failed: {e}")
            return None

    def lookup_object(self, name: str) -> Optional[StellariumObject]:
        """Look up a named object (e.g., 'M42', 'NGC 7000', 'Jupiter')."""
        try:
            resp = self.session.get(
                f"{self.base_url}/api/objects/info",
                params={"name": name, "format": "json"},
                timeout=self.timeout,
            )
            if resp.status_code != 200 or "not found" in resp.text.lower():
                return None

            data = resp.json()
            ra_deg = data.get("raJ2000", 0)
            if ra_deg < 0:
                ra_deg += 360
            ra_hours = ra_deg / 15.0

            return StellariumObject(
                name=data.get("name", name),
                object_type=data.get("object-type", "unknown"),
                ra_j2000_hours=ra_hours,
                dec_j2000_degrees=data.get("decJ2000", 0),
                altitude=data.get("altitude", 0),
                azimuth=data.get("azimuth", 0),
                magnitude=data.get("vmag", 99),
                above_horizon=data.get("above-horizon", False),
                constellation=data.get("iauConstellation", ""),
                rise=data.get("rise", ""),
                set_time=data.get("set", ""),
            )
        except (requests.exceptions.RequestException, ValueError):
            return None
