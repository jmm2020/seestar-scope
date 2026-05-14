"""SeestarScope Backend - Unified FastAPI Service

REST API for telescope control, image gallery, image processing,
autofocus, plate solving, and observing conditions.
Runs on port 8503 alongside the Streamlit UI (8502).
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from backend.routers import (
    telescope,
    gallery,
    processing,
    status_ws,
    autofocus,
    platesolve,
    postprocessing,
    sessions,
    conditions,
    stacking,
    imager,
)
from backend.config import settings
from backend.database import (
    init_database,
    close_database,
    init_sessions_database,
    close_sessions_database,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    logger.info("SeestarScope Backend starting up...")

    # Initialize SQLite database for gallery
    db_path = init_database()
    app.state.db_path = db_path
    logger.info(f"Gallery database ready at {db_path}")

    # Initialize sessions database (same file, separate connection)
    init_sessions_database()
    logger.info("Sessions database ready")

    # Initialize shared ALPACA client
    from backend.clients import get_alpaca_client, get_stellarium_client

    alpaca = get_alpaca_client()
    stellarium = get_stellarium_client()

    # Store in app state
    app.state.alpaca = alpaca
    app.state.stellarium = stellarium

    # Connect to telescope
    if settings.auto_connect:
        results = alpaca.connect_all()
        logger.info(f"ALPACA connection: {results}")

    yield

    logger.info("SeestarScope Backend shutting down...")
    alpaca.disconnect_all()
    close_database()
    close_sessions_database()

    if conditions._conditions_service is not None:
        conditions._conditions_service.close()


# Initialize FastAPI app
app = FastAPI(
    title="SeestarScope Backend API",
    description="REST API for Seestar S50 telescope control, gallery, and processing",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(telescope.router, prefix="/api/telescope", tags=["telescope"])
app.include_router(gallery.router, prefix="/api/gallery", tags=["gallery"])
app.include_router(processing.router, prefix="/api/processing", tags=["processing"])
app.include_router(autofocus.router)  # prefix="/api/autofocus" defined in router
app.include_router(platesolve.router)  # prefix="/api/platesolve" defined in router
app.include_router(postprocessing.router)  # prefix="/api/postprocessing" defined in router
app.include_router(sessions.router, prefix="/api/sessions", tags=["sessions"])
app.include_router(conditions.router)  # prefix="/api/conditions" defined in router
app.include_router(stacking.router)  # prefix="/api/stacking" defined in router
app.include_router(imager.router)  # prefix="/api/imager" defined in router
app.include_router(status_ws.router)  # WebSocket: live telescope status stream


@app.get("/")
async def root():
    """API root"""
    return {
        "service": "SeestarScope Backend",
        "version": "0.1.0",
        "endpoints": {
            "telescope": "/api/telescope/*",
            "gallery": "/api/gallery/*",
            "processing": "/api/processing/*",
            "autofocus": "/api/autofocus/*",
            "platesolve": "/api/platesolve/*",
            "postprocessing": "/api/postprocessing/*",
            "sessions": "/api/sessions/*",
            "conditions": "/api/conditions/*",
            "stacking": "/api/stacking/*",
            "status_ws": "ws://<host>:8503/api/status/ws",
            "status_connections": "/api/status/connections",
            "docs": "/docs",
            "health": "/health",
        },
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "seestar-backend"}
