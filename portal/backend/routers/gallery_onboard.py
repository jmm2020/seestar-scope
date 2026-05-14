"""Gallery Onboard Router — read-through view of the scope's onboard archive.

Lists images and videos served by the Seestar S50's built-in HTTP server,
discovered via ``get_albums`` on the :4701 guest JSON-RPC channel. The list
endpoint returns metadata; the thumbnail endpoint proxies the JPEG so the
browser caches it under the backend's origin (avoids mixed-origin cache misses
and lets us add a ``Cache-Control`` header).
"""

from __future__ import annotations

import logging
from typing import Optional

import requests
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from clients.seestar_archive import SeestarArchiveClient, SeestarArchiveError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/gallery/onboard", tags=["gallery"])


_archive_client: Optional[SeestarArchiveClient] = None


def get_archive_client() -> SeestarArchiveClient:
    """Lazy singleton for the :4701 archive client. Settings imported here so
    module import does not require a fully-populated .env at test time."""
    global _archive_client
    if _archive_client is None:
        from backend.config import settings

        _archive_client = SeestarArchiveClient(host=settings.seestar_ip)
    return _archive_client


@router.get("/")
def list_onboard_items():
    """Return all images and videos currently on the scope's onboard storage."""
    client = get_archive_client()
    try:
        items = client.list_items()
    except SeestarArchiveError as exc:
        logger.warning("archive :4701 fetch failed: %s", exc)
        raise HTTPException(
            status_code=502, detail=f"archive channel error: {exc}"
        ) from exc
    return [item.to_dict() for item in items]


@router.get("/thumbnail")
def proxy_thumbnail(url: str = Query(..., description="Absolute scope thumbnail URL")):
    """Proxy-fetch a scope thumbnail so the browser caches it under our origin."""
    try:
        resp = requests.get(url, timeout=10, stream=False)
    except requests.RequestException as exc:
        logger.warning("thumbnail proxy fetch failed for %s: %s", url, exc)
        raise HTTPException(
            status_code=502, detail=f"thumbnail fetch failed: {exc}"
        ) from exc
    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"scope returned HTTP {resp.status_code} for thumbnail",
        )
    return Response(
        content=resp.content,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/health")
def health():
    """Return ``ok`` if the scope archive channel responds, ``unreachable`` otherwise."""
    client = get_archive_client()
    return {"status": "ok" if client.is_reachable() else "unreachable"}
