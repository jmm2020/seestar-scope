"""
Session Data Model for Seestar Observation History
====================================================
Provides SQLite schema + Pydantic models for tracking observation sessions,
their frames, and resulting stacks.

A session represents a single target-night unit of work: started_at when stacking
begins, ended_at when stopped, with all captured frames and stacks linked to it.
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ============================================================================
# Pydantic Models (for API interaction)
# ============================================================================


class SessionRecord(BaseModel):
    """A single observation session — one target-night."""

    id: Optional[int] = Field(None, description="Auto-increment primary key")
    target_name: str = Field(..., description="Target object name (e.g., M31)")
    target_ra: Optional[float] = Field(None, description="Right ascension in hours")
    target_dec: Optional[float] = Field(None, description="Declination in degrees")
    started_at: datetime = Field(..., description="Session start time (UTC)")
    ended_at: Optional[datetime] = Field(None, description="Session end time (UTC)")
    site_location: Optional[Dict[str, Any]] = Field(None, description="{lat, lon, elevation}")
    conditions_snapshot: Optional[Dict[str, Any]] = Field(
        None, description="{seeing, transparency, temp}"
    )
    created_at: Optional[datetime] = Field(None, description="DB row creation time")
    frame_count: Optional[int] = Field(None, description="Frame count — set when include_frame_counts=true")
    total_exposure_s: Optional[float] = Field(None, description="Total exposure seconds — set when include_frame_counts=true")


class FrameRecord(BaseModel):
    """A single captured frame, linked to a session."""

    id: Optional[int] = Field(None, description="Auto-increment primary key")
    session_id: int = Field(..., description="Parent session ID")
    filename: str = Field(..., description="Path or basename of captured frame")
    exposure_s: float = Field(..., description="Exposure time in seconds")
    gain: int = Field(..., description="Sensor gain (0-400)")
    filter: str = Field(..., description="Filter name")
    captured_at: datetime = Field(..., description="When the frame was captured (UTC)")
    alpaca_metadata: Optional[Dict[str, Any]] = Field(None, description="Raw ALPACA response data")


class StackRecord(BaseModel):
    """A stacked output, linked to a session."""

    id: Optional[int] = Field(None, description="Auto-increment primary key")
    session_id: int = Field(..., description="Parent session ID")
    output_path: str = Field(..., description="Path to the stacked output image")
    frame_count: int = Field(..., description="Number of frames stacked")
    algorithm: str = Field(..., description="Stacking algorithm used (e.g., 'mean', 'siril')")
    applied_calibration_ids: Optional[List[int]] = Field(
        None, description="Calibration frame IDs used"
    )


class SessionFilter(BaseModel):
    """Filter criteria for session queries."""

    target: Optional[str] = Field(None, description="Target name (partial match)")
    start_date: Optional[datetime] = Field(None, description="Start of date range")
    end_date: Optional[datetime] = Field(None, description="End of date range")
    limit: int = Field(default=50, ge=1, le=500, description="Max results")
    offset: int = Field(default=0, ge=0, description="Pagination offset")


class SessionStats(BaseModel):
    """Summary statistics across all sessions."""

    total_sessions: int
    total_frames: int
    total_exposure_hours: float
    targets: Dict[str, int]


class StartSessionRequest(BaseModel):
    """POST body for starting a new session."""

    target_name: str = Field(..., description="Target object name")
    target_ra: Optional[float] = Field(None, description="RA in hours")
    target_dec: Optional[float] = Field(None, description="Dec in degrees")
    site_location: Optional[Dict[str, Any]] = Field(None, description="{lat, lon, elevation}")
    conditions_snapshot: Optional[Dict[str, Any]] = Field(
        None, description="{seeing, transparency, temp}"
    )


class EndSessionRequest(BaseModel):
    """POST body for ending an active session."""

    conditions_snapshot: Optional[Dict[str, Any]] = Field(
        None, description="Final conditions snapshot"
    )


class AddFrameRequest(BaseModel):
    """POST body for logging a captured frame."""

    filename: str = Field(..., description="Frame filename or path")
    exposure_s: float = Field(..., description="Exposure time in seconds")
    gain: int = Field(..., description="Sensor gain")
    filter: str = Field(default="L", description="Filter name")
    captured_at: Optional[datetime] = Field(None, description="Capture time (defaults to now UTC)")
    alpaca_metadata: Optional[Dict[str, Any]] = Field(None, description="Raw ALPACA response data")


class AddStackRequest(BaseModel):
    """POST body for logging a stack output."""

    output_path: str = Field(..., description="Path to the stacked image file")
    frame_count: int = Field(..., description="Number of frames stacked")
    algorithm: str = Field(default="mean", description="Stacking algorithm used")
    applied_calibration_ids: Optional[List[int]] = Field(None, description="Calibration frame IDs")


# ============================================================================
# SQLite Schema and Database Interface
# ============================================================================


class SessionDatabase:
    """SQLite database for observation sessions, frames, and stacks."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        target_name TEXT NOT NULL,
        target_ra REAL,
        target_dec REAL,
        started_at TEXT NOT NULL,
        ended_at TEXT,
        site_location TEXT,             -- JSON: {lat, lon, elevation}
        conditions_snapshot TEXT,       -- JSON: {seeing, transparency, temp}
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS frames (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL REFERENCES sessions(id),
        filename TEXT NOT NULL,
        exposure_s REAL NOT NULL,
        gain INTEGER NOT NULL,
        filter TEXT NOT NULL,
        captured_at TEXT NOT NULL,
        alpaca_metadata TEXT            -- JSON blob from ALPACA response
    );

    CREATE TABLE IF NOT EXISTS stacks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL REFERENCES sessions(id),
        output_path TEXT NOT NULL,
        frame_count INTEGER NOT NULL,
        algorithm TEXT NOT NULL,
        applied_calibration_ids TEXT    -- JSON array of calibration frame IDs
    );

    CREATE INDEX IF NOT EXISTS idx_sessions_target ON sessions(target_name);
    CREATE INDEX IF NOT EXISTS idx_sessions_started_at ON sessions(started_at);
    CREATE INDEX IF NOT EXISTS idx_frames_session ON frames(session_id);
    CREATE INDEX IF NOT EXISTS idx_stacks_session ON stacks(session_id);
    """

    def __init__(self, db_path: str = "data/seestar_gallery.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript(self.SCHEMA)
        # executescript() already commits; PRAGMA is a connection-level setting, not transactional
        self.conn.execute("PRAGMA foreign_keys = ON")

    @staticmethod
    def _safe_json(value: Optional[str], row_id: int = 0, field: str = "") -> Optional[dict]:
        if not value:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            logger.warning(f"Corrupt JSON in row {row_id} field {field!r} — skipping")
            return None

    def _row_to_session(self, row) -> SessionRecord:
        return SessionRecord(
            id=row["id"],
            target_name=row["target_name"],
            target_ra=row["target_ra"],
            target_dec=row["target_dec"],
            started_at=datetime.fromisoformat(row["started_at"]),
            ended_at=datetime.fromisoformat(row["ended_at"]) if row["ended_at"] else None,
            site_location=self._safe_json(row["site_location"], row["id"], "site_location"),
            conditions_snapshot=self._safe_json(
                row["conditions_snapshot"], row["id"], "conditions_snapshot"
            ),
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
        )

    def _row_to_frame(self, row) -> FrameRecord:
        return FrameRecord(
            id=row["id"],
            session_id=row["session_id"],
            filename=row["filename"],
            exposure_s=row["exposure_s"],
            gain=row["gain"],
            filter=row["filter"],
            captured_at=datetime.fromisoformat(row["captured_at"]),
            alpaca_metadata=self._safe_json(row["alpaca_metadata"], row["id"], "alpaca_metadata"),
        )

    def _row_to_stack(self, row) -> StackRecord:
        return StackRecord(
            id=row["id"],
            session_id=row["session_id"],
            output_path=row["output_path"],
            frame_count=row["frame_count"],
            algorithm=row["algorithm"],
            applied_calibration_ids=self._safe_json(
                row["applied_calibration_ids"], row["id"], "applied_calibration_ids"
            ),
        )

    def create_session(
        self,
        target_name: str,
        target_ra: Optional[float] = None,
        target_dec: Optional[float] = None,
        site_location: Optional[Dict[str, Any]] = None,
        conditions_snapshot: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Insert a new session row. Returns the new session ID."""
        started_at = datetime.now(timezone.utc).isoformat()
        cursor = self.conn.execute(
            """
            INSERT INTO sessions (
                target_name, target_ra, target_dec, started_at, ended_at,
                site_location, conditions_snapshot
            ) VALUES (?, ?, ?, ?, NULL, ?, ?)
            """,
            (
                target_name,
                target_ra,
                target_dec,
                started_at,
                json.dumps(site_location) if site_location else None,
                json.dumps(conditions_snapshot) if conditions_snapshot else None,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def end_session(
        self,
        session_id: int,
        conditions_snapshot: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Mark session as ended. Returns True if a row was updated."""
        ended_at = datetime.now(timezone.utc).isoformat()
        if conditions_snapshot is not None:
            cursor = self.conn.execute(
                "UPDATE sessions SET ended_at = ?, conditions_snapshot = ? WHERE id = ?",
                (ended_at, json.dumps(conditions_snapshot), session_id),
            )
        else:
            cursor = self.conn.execute(
                "UPDATE sessions SET ended_at = ? WHERE id = ?",
                (ended_at, session_id),
            )
        self.conn.commit()
        return cursor.rowcount > 0

    def add_frame(
        self,
        session_id: int,
        filename: str,
        exposure_s: float,
        gain: int,
        filter_name: str,
        captured_at: Optional[datetime] = None,
        alpaca_metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Insert a frame row. Returns the new frame ID."""
        if captured_at is None:
            captured_at = datetime.now(timezone.utc)
        cursor = self.conn.execute(
            """
            INSERT INTO frames (
                session_id, filename, exposure_s, gain, filter,
                captured_at, alpaca_metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                filename,
                exposure_s,
                gain,
                filter_name,
                captured_at.isoformat(),
                json.dumps(alpaca_metadata) if alpaca_metadata else None,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def add_stack(
        self,
        session_id: int,
        output_path: str,
        frame_count: int,
        algorithm: str = "mean",
        applied_calibration_ids: Optional[List[int]] = None,
    ) -> int:
        """Insert a stack row. Returns the new stack ID."""
        cursor = self.conn.execute(
            """
            INSERT INTO stacks (
                session_id, output_path, frame_count, algorithm,
                applied_calibration_ids
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                session_id,
                output_path,
                frame_count,
                algorithm,
                json.dumps(applied_calibration_ids) if applied_calibration_ids else None,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_by_id(self, session_id: int) -> Optional[SessionRecord]:
        """Fetch a single session record by primary key."""
        cursor = self.conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        return self._row_to_session(row)

    def list_sessions(self, limit: int = 50, offset: int = 0) -> List[SessionRecord]:
        """Return sessions newest-first."""
        cursor = self.conn.execute(
            "SELECT * FROM sessions ORDER BY started_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        return [self._row_to_session(row) for row in cursor.fetchall()]

    def get_frame_by_id(self, frame_id: int) -> Optional[FrameRecord]:
        """Fetch a single frame record by primary key."""
        cursor = self.conn.execute("SELECT * FROM frames WHERE id = ?", (frame_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        return self._row_to_frame(row)

    def get_frames(self, session_id: int) -> List[FrameRecord]:
        """Return all frames for a session, oldest-first."""
        cursor = self.conn.execute(
            "SELECT * FROM frames WHERE session_id = ? ORDER BY captured_at ASC",
            (session_id,),
        )
        return [self._row_to_frame(row) for row in cursor.fetchall()]

    def get_stacks(self, session_id: int) -> List[StackRecord]:
        """Return all stacks for a session, oldest-first."""
        cursor = self.conn.execute(
            "SELECT * FROM stacks WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        )
        return [self._row_to_stack(row) for row in cursor.fetchall()]

    def get_session_summaries(self, session_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        """Return per-session frame count and total exposure in one query."""
        if not session_ids:
            return {}
        placeholders = ",".join("?" * len(session_ids))
        cursor = self.conn.execute(
            f"SELECT session_id, COUNT(*) as frame_count, COALESCE(SUM(exposure_s), 0.0) as total_exposure_s "
            f"FROM frames WHERE session_id IN ({placeholders}) GROUP BY session_id",
            session_ids,
        )
        return {
            row["session_id"]: {
                "frame_count": row["frame_count"],
                "total_exposure_s": row["total_exposure_s"],
            }
            for row in cursor.fetchall()
        }

    def close(self):
        """Close database connection."""
        self.conn.close()
