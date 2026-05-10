"""HTTP client for the SeestarScope sessions REST API.

Used by Streamlit views to log captures to the active session and to fetch
history without sharing in-process state with the FastAPI backend.

Network failures are caught and logged — methods return None / [] so that
Streamlit callers don't crash when the backend is offline.
"""
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


class SessionsClient:
    """Thin wrapper around POST/GET /api/sessions/* endpoints."""

    def __init__(self, backend_url: Optional[str] = None, timeout: int = 10):
        self.backend_url = (
            backend_url
            or os.environ.get("BACKEND_URL")
            or "http://localhost:8503"
        )
        self.timeout = timeout
        self.session = requests.Session()

    def _post(self, path: str, payload: Dict[str, Any]) -> Optional[requests.Response]:
        url = f"{self.backend_url}{path}"
        try:
            resp = self.session.post(url, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as e:
            logger.warning(f"Sessions POST {url} failed: {e}")
            return None

    def _get(self, path: str) -> Optional[requests.Response]:
        url = f"{self.backend_url}{path}"
        try:
            resp = self.session.get(url, timeout=self.timeout)
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as e:
            logger.warning(f"Sessions GET {url} failed: {e}")
            return None

    def start_session(
        self,
        target_name: str,
        target_ra: Optional[float] = None,
        target_dec: Optional[float] = None,
        site_location: Optional[Dict[str, Any]] = None,
        conditions_snapshot: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Create a new session. Returns the session dict, or None on failure.

        Verifies persistence with a follow-up GET (verify-after-dispatch).
        """
        payload = {
            "target_name": target_name,
            "target_ra": target_ra,
            "target_dec": target_dec,
            "site_location": site_location,
            "conditions_snapshot": conditions_snapshot,
        }
        resp = self._post("/api/sessions/", payload)
        if resp is None:
            return None
        session = resp.json()

        verify = self._get(f"/api/sessions/{session['id']}")
        if verify is None or verify.status_code != 200:
            logger.error(f"Session start verification failed for id={session.get('id')}")
            return None
        return session

    def end_session(
        self,
        session_id: int,
        conditions_snapshot: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Mark a session ended. Verifies ended_at is set on round-trip."""
        payload = {"conditions_snapshot": conditions_snapshot}
        resp = self._post(f"/api/sessions/{session_id}/end", payload)
        if resp is None:
            return None
        session = resp.json()

        verify = self._get(f"/api/sessions/{session_id}")
        if verify is None or verify.status_code != 200:
            logger.error(f"Session end verification failed for id={session_id}")
            return None
        verified = verify.json()
        if verified.get("ended_at") is None:
            logger.error(f"Session {session_id} ended_at was not persisted")
            return None
        return session

    def add_frame(
        self,
        session_id: int,
        filename: str,
        exposure_s: float,
        gain: int,
        filter_name: str = "L",
        captured_at: Optional[datetime] = None,
        alpaca_metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Log a frame to a session. No verify (called per-frame, may be high-frequency)."""
        payload = {
            "filename": filename,
            "exposure_s": exposure_s,
            "gain": gain,
            "filter": filter_name,
            "captured_at": captured_at.isoformat() if captured_at else None,
            "alpaca_metadata": alpaca_metadata,
        }
        resp = self._post(f"/api/sessions/{session_id}/frames", payload)
        if resp is None:
            return None
        return resp.json()

    def list_sessions(self, limit: int = 50, offset: int = 0) -> Optional[List[Dict[str, Any]]]:
        """Get session list, newest-first."""
        resp = self._get(f"/api/sessions/?limit={limit}&offset={offset}")
        if resp is None:
            return None
        return resp.json()

    def get_session(self, session_id: int) -> Optional[Dict[str, Any]]:
        """Get a single session detail."""
        resp = self._get(f"/api/sessions/{session_id}")
        if resp is None:
            return None
        return resp.json()

    def get_frames(self, session_id: int) -> Optional[List[Dict[str, Any]]]:
        """Get all frames for a session."""
        resp = self._get(f"/api/sessions/{session_id}/frames")
        if resp is None:
            return None
        return resp.json()
