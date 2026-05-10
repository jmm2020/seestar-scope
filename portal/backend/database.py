"""Database initialization and management

SQLite database for image gallery metadata.
Integrates with GalleryDatabase from models/gallery.py.
"""

import logging
from pathlib import Path
from backend.config import settings
from backend.models.gallery import GalleryDatabase

logger = logging.getLogger(__name__)

# Global database instance
_db_instance: GalleryDatabase = None


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
