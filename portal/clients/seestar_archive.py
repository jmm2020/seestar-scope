"""Direct guest-mode TCP client for the Seestar S50 onboard archive.

Uses port 4701 (guest JSON-RPC channel) for the ``get_albums`` method and
constructs direct HTTP URLs (port 80) for the scope's built-in static file
server. Mirrors the single-shot socket pattern of ``SeestarObserverClient``.

Verified live on firmware 7.34 (probe 2026-05-14):

    get_albums → code: 0, returns {path: "MyWorks", list: [{group_name, files: [{name, thn, count, type}]}]}
    HTTP :80/MyWorks/<thn> serves the thumbnail JPEG
    HTTP :80/MyWorks/<thn replaced _thn.jpg→.jpg> serves the full-resolution JPEG
    HTTP :80/MyWorks/<thn replaced _thn.jpg→.mp4> serves the timelapse MP4

The Seestar mobile app shows the same album list; this client gives the portal
read-through visibility into the scope's onboard storage without copying files
to the Jetson.
"""

from __future__ import annotations

import json
import logging
import socket
import threading
import time
from dataclasses import asdict, dataclass
from typing import Any, List

logger = logging.getLogger(__name__)


class SeestarArchiveError(Exception):
    """Raised when an archive request fails (timeout, socket error, code != 0)."""


@dataclass
class OnboardItem:
    """One image or video discovered on the scope's onboard archive."""

    name: str
    thumb_url: str
    full_url: str
    is_video: bool

    def to_dict(self) -> dict:
        return asdict(self)


class SeestarArchiveClient:
    """Single-shot JSON-RPC client for the Seestar guest channel (:4701).

    The ``get_albums`` method is on the guest whitelist on firmware 7.34, so
    this client does not depend on the seestar_alp bridge. URLs are constructed
    against the scope's HTTP server (default :80) and rendered directly by the
    browser; the backend only proxies thumbnails for caching.
    """

    def __init__(
        self,
        host: str,
        rpc_port: int = 4701,
        http_port: int = 80,
        timeout: float = 5.0,
    ):
        self.host = host
        self.rpc_port = rpc_port
        self.http_port = http_port
        self.timeout = timeout
        self._lock = threading.Lock()
        self._next_id = 1

    def _rpc_call(self, method: str, params: Any = None) -> Any:
        with self._lock:
            cid = self._next_id
            self._next_id += 1
        payload: dict = {"id": cid, "method": method}
        if params is not None:
            payload["params"] = params
        wire = (json.dumps(payload) + "\r\n").encode()
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(self.timeout)
        try:
            s.connect((self.host, self.rpc_port))
            s.sendall(wire)
            deadline = time.monotonic() + self.timeout
            buf = b""
            while time.monotonic() < deadline:
                s.settimeout(max(0.1, deadline - time.monotonic()))
                try:
                    chunk = s.recv(65536)
                except socket.timeout as exc:
                    raise SeestarArchiveError(
                        f"timed out after {self.timeout}s waiting for id={cid} ({method})"
                    ) from exc
                if not chunk:
                    raise SeestarArchiveError("socket closed before response")
                buf += chunk
                while b"\r\n" in buf:
                    line, buf = buf.split(b"\r\n", 1)
                    if not line:
                        continue
                    try:
                        obj = json.loads(line.decode("utf-8", errors="replace"))
                    except json.JSONDecodeError:
                        continue
                    if obj.get("id") != cid:
                        continue
                    code = obj.get("code", 0)
                    if code != 0:
                        raise SeestarArchiveError(
                            f"method '{method}' returned code={code}"
                        )
                    return obj.get("result")
            raise SeestarArchiveError(
                f"timed out after {self.timeout}s waiting for id={cid} ({method})"
            )
        except OSError as exc:
            raise SeestarArchiveError(f"socket error: {exc}") from exc
        finally:
            try:
                s.close()
            except OSError:
                pass

    def get_albums(self) -> dict:
        """Return the raw album listing from the scope.

        The structure on firmware 7.34 is::

            {"path": "MyWorks",
             "list": [{"group_name": "SolarSystem",
                       "files": [{"name": "Solar_video", "thn": "Solar_video/...thn.jpg", ...}]}]}
        """
        result = self._rpc_call("get_albums")
        return result if isinstance(result, dict) else {}

    def list_items(self) -> List[OnboardItem]:
        """Flatten every album group's files into a list of ``OnboardItem``."""
        albums = self.get_albums()
        parent_folder = albums.get("path", "")
        base = f"http://{self.host}:{self.http_port}"
        items: List[OnboardItem] = []
        for group in albums.get("list", []) or []:
            for entry in group.get("files", []) or []:
                thn = entry.get("thn") or ""
                name = entry.get("name") or ""
                if not thn:
                    continue
                # Video timelapses: name ends with "_video", thn is a _thn.jpg
                # poster, and the full asset is the same path with extension
                # swapped from "_thn.jpg" to ".mp4". Images use ".jpg".
                is_video = name.endswith("_video")
                ext = ".mp4" if is_video else ".jpg"
                stripped = thn.rpartition("_thn.jpg")[0] or thn
                thumb_url = f"{base}/{parent_folder}/{thn}"
                full_url = f"{base}/{parent_folder}/{stripped}{ext}"
                items.append(
                    OnboardItem(
                        name=name,
                        thumb_url=thumb_url,
                        full_url=full_url,
                        is_video=is_video,
                    )
                )
        return items

    def is_reachable(self) -> bool:
        try:
            self.get_albums()
            return True
        except SeestarArchiveError:
            return False
