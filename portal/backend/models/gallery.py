"""
Gallery Data Model for Seestar Image Archive
============================================
Provides SQLite schema + Pydantic models for indexing captured images.
Supports filtering by target, date range, exposure, filter, session.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
import json
import sqlite3
from pydantic import BaseModel, Field


# ============================================================================
# Pydantic Models (for API interaction)
# ============================================================================

class ImageMetadata(BaseModel):
    """Metadata extracted from FITS header or imaging session."""
    target: str = Field(..., description="Target object name (e.g., M31, NGC7000)")
    exposure: float = Field(..., description="Exposure time in seconds")
    gain: int = Field(..., ge=0, le=400, description="Sensor gain (0-400)")
    filter: str = Field(default="L", description="Filter name (L, R, G, B, Ha, etc.)")
    ra: Optional[float] = Field(None, description="Right ascension in hours (J2000)")
    dec: Optional[float] = Field(None, description="Declination in degrees (J2000)")
    temperature: Optional[float] = Field(None, description="CCD temperature in Celsius")
    binning: str = Field(default="1x1", description="Binning mode")
    observer: Optional[str] = Field(None, description="Observer name")
    telescope: str = Field(default="Seestar S50", description="Telescope model")


class ImageRecord(BaseModel):
    """Complete record of a captured image in the gallery."""
    id: Optional[int] = Field(None, description="Auto-increment primary key")
    fits_path: str = Field(..., description="Path to FITS file")
    png_path: str = Field(..., description="Path to PNG preview")
    session_id: str = Field(..., description="Session identifier (YYYYMMDD_HHMMSS)")
    captured_at: datetime = Field(default_factory=datetime.utcnow, description="UTC timestamp")
    metadata: ImageMetadata = Field(..., description="Astronomical metadata")

    processed: bool = Field(default=False, description="Has been processed by Siril")
    processed_path: Optional[str] = Field(None, description="Path to processed image")
    stacked: bool = Field(default=False, description="Part of a stacked sequence")
    stack_id: Optional[str] = Field(None, description="Stack sequence identifier")

    tags: List[str] = Field(default_factory=list, description="User-defined tags")
    notes: Optional[str] = Field(None, description="User notes")
    quality_score: Optional[int] = Field(None, ge=1, le=5, description="Quality rating 1-5")


class GalleryFilter(BaseModel):
    """Filter criteria for gallery searches."""
    target: Optional[str] = Field(None, description="Target name (partial match)")
    session_id: Optional[str] = Field(None, description="Exact session ID")
    start_date: Optional[datetime] = Field(None, description="Start of date range")
    end_date: Optional[datetime] = Field(None, description="End of date range")
    filter: Optional[str] = Field(None, description="Filter name")
    min_exposure: Optional[float] = Field(None, description="Minimum exposure time")
    max_exposure: Optional[float] = Field(None, description="Maximum exposure time")
    processed_only: bool = Field(default=False, description="Only show processed images")
    stacked_only: bool = Field(default=False, description="Only show stacked images")
    tags: Optional[List[str]] = Field(None, description="Must have all these tags")
    limit: int = Field(default=50, ge=1, le=500, description="Max results")
    offset: int = Field(default=0, ge=0, description="Pagination offset")


class GalleryStats(BaseModel):
    """Gallery statistics summary."""
    total_images: int
    total_sessions: int
    targets: Dict[str, int]
    filters: Dict[str, int]
    total_exposure_hours: float
    date_range: Tuple[Optional[datetime], Optional[datetime]]
    processed_count: int
    stacked_count: int


# ============================================================================
# SQLite Schema and Database Interface
# ============================================================================

class GalleryDatabase:
    """SQLite database for image gallery indexing."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS images (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fits_path TEXT NOT NULL,
        png_path TEXT NOT NULL,
        session_id TEXT NOT NULL,
        captured_at TEXT NOT NULL,

        -- Metadata fields (denormalized for query performance)
        target TEXT NOT NULL,
        exposure REAL NOT NULL,
        gain INTEGER NOT NULL,
        filter TEXT DEFAULT 'L',
        ra REAL,
        dec REAL,
        temperature REAL,
        binning TEXT DEFAULT '1x1',
        observer TEXT,
        telescope TEXT DEFAULT 'Seestar S50',

        -- Processing status
        processed BOOLEAN DEFAULT 0,
        processed_path TEXT,
        stacked BOOLEAN DEFAULT 0,
        stack_id TEXT,

        -- User annotations
        tags TEXT,  -- JSON array
        notes TEXT,
        quality_score INTEGER CHECK(quality_score BETWEEN 1 AND 5),

        -- Timestamps
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_target ON images(target);
    CREATE INDEX IF NOT EXISTS idx_session ON images(session_id);
    CREATE INDEX IF NOT EXISTS idx_captured_at ON images(captured_at);
    CREATE INDEX IF NOT EXISTS idx_filter ON images(filter);
    CREATE INDEX IF NOT EXISTS idx_processed ON images(processed);
    CREATE INDEX IF NOT EXISTS idx_stacked ON images(stacked);
    """

    def __init__(self, db_path: str = "data/seestar_gallery.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript(self.SCHEMA)
        self.conn.commit()

    def _row_to_record(self, row) -> ImageRecord:
        metadata = ImageMetadata(
            target=row['target'],
            exposure=row['exposure'],
            gain=row['gain'],
            filter=row['filter'],
            ra=row['ra'],
            dec=row['dec'],
            temperature=row['temperature'],
            binning=row['binning'],
            observer=row['observer'],
            telescope=row['telescope']
        )
        return ImageRecord(
            id=row['id'],
            fits_path=row['fits_path'],
            png_path=row['png_path'],
            session_id=row['session_id'],
            captured_at=datetime.fromisoformat(row['captured_at']),
            metadata=metadata,
            processed=bool(row['processed']),
            processed_path=row['processed_path'],
            stacked=bool(row['stacked']),
            stack_id=row['stack_id'],
            tags=json.loads(row['tags']) if row['tags'] else [],
            notes=row['notes'],
            quality_score=row['quality_score']
        )

    def add_image(self, record: ImageRecord) -> int:
        """Insert new image record. Returns the new record ID."""
        cursor = self.conn.execute("""
            INSERT INTO images (
                fits_path, png_path, session_id, captured_at,
                target, exposure, gain, filter, ra, dec, temperature,
                binning, observer, telescope,
                processed, processed_path, stacked, stack_id,
                tags, notes, quality_score
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            record.fits_path, record.png_path, record.session_id,
            record.captured_at.isoformat(),
            record.metadata.target, record.metadata.exposure, record.metadata.gain,
            record.metadata.filter, record.metadata.ra, record.metadata.dec,
            record.metadata.temperature, record.metadata.binning,
            record.metadata.observer, record.metadata.telescope,
            record.processed, record.processed_path, record.stacked, record.stack_id,
            json.dumps(record.tags), record.notes, record.quality_score
        ))
        self.conn.commit()
        return cursor.lastrowid

    def search(self, filter_criteria: GalleryFilter) -> List[ImageRecord]:
        """Search images with flexible filtering."""
        query = "SELECT * FROM images WHERE 1=1"
        params = []

        if filter_criteria.target:
            query += " AND target LIKE ?"
            params.append(f"%{filter_criteria.target}%")

        if filter_criteria.session_id:
            query += " AND session_id = ?"
            params.append(filter_criteria.session_id)

        if filter_criteria.start_date:
            query += " AND captured_at >= ?"
            params.append(filter_criteria.start_date.isoformat())

        if filter_criteria.end_date:
            query += " AND captured_at <= ?"
            params.append(filter_criteria.end_date.isoformat())

        if filter_criteria.filter:
            query += " AND filter = ?"
            params.append(filter_criteria.filter)

        if filter_criteria.min_exposure is not None:
            query += " AND exposure >= ?"
            params.append(filter_criteria.min_exposure)

        if filter_criteria.max_exposure is not None:
            query += " AND exposure <= ?"
            params.append(filter_criteria.max_exposure)

        if filter_criteria.processed_only:
            query += " AND processed = 1"

        if filter_criteria.stacked_only:
            query += " AND stacked = 1"

        query += " ORDER BY captured_at DESC LIMIT ? OFFSET ?"
        params.extend([filter_criteria.limit, filter_criteria.offset])

        cursor = self.conn.execute(query, params)
        return [self._row_to_record(row) for row in cursor.fetchall()]

    def get_stats(self) -> GalleryStats:
        """Get gallery statistics summary."""
        cursor = self.conn.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(DISTINCT session_id) as sessions,
                COUNT(CASE WHEN processed = 1 THEN 1 END) as processed,
                COUNT(CASE WHEN stacked = 1 THEN 1 END) as stacked,
                SUM(exposure) as total_exposure_seconds,
                MIN(captured_at) as earliest,
                MAX(captured_at) as latest
            FROM images
        """)
        row = cursor.fetchone()

        cursor = self.conn.execute("SELECT target, COUNT(*) as cnt FROM images GROUP BY target")
        targets = {r['target']: r['cnt'] for r in cursor.fetchall()}

        cursor = self.conn.execute("SELECT filter, COUNT(*) as cnt FROM images GROUP BY filter")
        filters = {r['filter']: r['cnt'] for r in cursor.fetchall()}

        earliest = datetime.fromisoformat(row['earliest']) if row['earliest'] else None
        latest = datetime.fromisoformat(row['latest']) if row['latest'] else None

        return GalleryStats(
            total_images=row['total'],
            total_sessions=row['sessions'],
            targets=targets,
            filters=filters,
            total_exposure_hours=row['total_exposure_seconds'] / 3600.0 if row['total_exposure_seconds'] else 0.0,
            date_range=(earliest, latest),
            processed_count=row['processed'],
            stacked_count=row['stacked']
        )

    def get_by_id(self, image_id: int) -> Optional[ImageRecord]:
        """Fetch a single image record by primary key."""
        cursor = self.conn.execute("SELECT * FROM images WHERE id = ?", (image_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def update_processing_status(self, image_id: int, processed_path: str):
        """Mark image as processed and record output path."""
        self.conn.execute("""
            UPDATE images
            SET processed = 1, processed_path = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (processed_path, image_id))
        self.conn.commit()

    def add_tags(self, image_id: int, tags: List[str]):
        """Add tags to an image (merges with existing)."""
        cursor = self.conn.execute("SELECT tags FROM images WHERE id = ?", (image_id,))
        row = cursor.fetchone()
        if row:
            existing = json.loads(row['tags']) if row['tags'] else []
            merged = list(set(existing + tags))
            self.conn.execute(
                "UPDATE images SET tags = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (json.dumps(merged), image_id)
            )
            self.conn.commit()

    def close(self):
        """Close database connection."""
        self.conn.close()


# ============================================================================
# Helper Functions
# ============================================================================

def create_gallery_record_from_dual_save(
    fits_path: str,
    png_path: str,
    metadata: Dict[str, Any],
    session_id: str
) -> ImageRecord:
    """Create ImageRecord from the dual-format save output."""
    img_metadata = ImageMetadata(
        target=metadata['target'],
        exposure=metadata['exposure'],
        gain=metadata['gain'],
        filter=metadata.get('filter', 'L'),
        ra=metadata.get('ra'),
        dec=metadata.get('dec'),
        temperature=metadata.get('temperature'),
        binning=metadata.get('binning', '1x1'),
        observer=metadata.get('observer'),
        telescope=metadata.get('telescope', 'Seestar S50')
    )
    return ImageRecord(
        fits_path=fits_path,
        png_path=png_path,
        session_id=session_id,
        captured_at=datetime.utcnow(),
        metadata=img_metadata
    )
