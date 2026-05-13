"""Imager API Router — scope-direct stacked-frame poll endpoint.

Reads stacked frames straight from the scope's native :4800 channel via
SeestarImagerClient, bypassing the seestar_alp bridge. Designed for
poll-style use by the imaging page: GET /api/imager/stacked.jpg with a
cache-bust query param every 10-30 seconds.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import Response as FastAPIResponse

from clients.seestar_imager import SeestarImagerClient, SeestarImagerError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/imager", tags=["imager"])


_imager_client: Optional[SeestarImagerClient] = None


def get_imager_client() -> SeestarImagerClient:
    """Lazy singleton for the :4800 client. Settings imported here so module
    import does not require a fully-populated .env at test time."""
    global _imager_client
    if _imager_client is None:
        from backend.config import settings

        _imager_client = SeestarImagerClient(host=settings.seestar_ip)
    return _imager_client


@router.get(
    "/stacked.jpg",
    responses={
        200: {"content": {"image/jpeg": {}}, "description": "Latest stacked frame as JPEG"},
        204: {"description": "No stacked frame currently available"},
    },
)
def get_stacked_frame(quality: int = 90):
    """Return the scope's current stacked frame as JPEG.

    Returns 204 No Content when no stacking session is active or no frame is
    yet ready (the scope's empty-response case). Raises 502 if the :4800
    channel misbehaves so the UI can show a clear error.
    """
    client = get_imager_client()
    try:
        frame = client.request_stacked_frame()
    except SeestarImagerError as exc:
        logger.warning("imager :4800 fetch failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"imager channel error: {exc}") from exc

    if frame is None:
        return Response(status_code=204)

    try:
        jpeg = frame.to_jpeg(quality=quality)
    except SeestarImagerError as exc:
        logger.warning("imager jpeg encode failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"jpeg encode failed: {exc}") from exc

    headers = {
        "Cache-Control": "no-store, max-age=0",
        "X-Frame-Width": str(frame.width),
        "X-Frame-Height": str(frame.height),
        "X-Frame-Format": frame.frame_format,
    }
    return FastAPIResponse(content=jpeg, media_type="image/jpeg", headers=headers)
