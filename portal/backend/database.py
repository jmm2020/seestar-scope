"""Database initialization and management

SQLite database for image gallery metadata.
Integrates with GalleryDatabase from models/gallery.py.
Also manages SessionDatabase from models/sessions.py (same DB file, separate connection).
"""

import logging
from pathlib import Path
from backend.config import settings
from backend.models.gallery import GalleryDatabase
from backend.models.sessions import SessionDatabase

logger = logging.getLogger(__name__)

# Global database instance
_db_instance: GalleryDatabase = None
_sessions_db_instance: SessionDatabase = None


def init_database() -> str:
    """Initialize SQLite database for gallery.

    Creates database file and tables via GalleryDatabase class.
    Called during FastAPI lifespan startup.

    Returns:
        str: Path to database file
    """
    global _db_instance

    db_path = Path(settings.data_dir) / "seestar_gallery.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Initializing gallery database at {db_path}")

    # Initialize GalleryDatabase (creates schema automatically)
    _db_instance = GalleryDatabase(db_path=str(db_path))

    logger.info("Gallery database initialization complete")
    return str(db_path)


def close_database():
    """Close database connection.

    Called during FastAPI lifespan shutdown.
    """
    global _db_instance

    if _db_instance is not None:
        _db_instance.close()
        logger.info("Gallery database connection closed")


def get_db() -> GalleryDatabase:
    """Get global database instance.

    Returns:
        GalleryDatabase: Active database instance

    Raises:
        RuntimeError: If database not initialized
    """
    if _db_instance is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    return _db_instance


def init_sessions_database() -> str:
    """Initialize SQLite database for sessions.

    Opens a second connection to the same gallery DB file and creates
    sessions/frames/stacks tables via SessionDatabase._init_schema().
    Called during FastAPI lifespan startup.

    Returns:
        str: Path to database file
    """
    global _sessions_db_instance

    db_path = Path(settings.data_dir) / "seestar_gallery.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Initializing sessions database at {db_path}")

    _sessions_db_instance = SessionDatabase(db_path=str(db_path))

    logger.info("Sessions database initialization complete")
    return str(db_path)


def close_sessions_database():
    """Close sessions database connection.

    Called during FastAPI lifespan shutdown.
    """
    global _sessions_db_instance

    if _sessions_db_instance is not None:
        _sessions_db_instance.close()
        logger.info("Sessions database connection closed")


def get_sessions_db() -> SessionDatabase:
    """Get global sessions database instance.

    Returns:
        SessionDatabase: Active sessions database instance

    Raises:
        RuntimeError: If sessions database not initialized
    """
    if _sessions_db_instance is None:
        raise RuntimeError(
            "Sessions database not initialized. Call init_sessions_database() first."
        )
    return _sessions_db_instance
