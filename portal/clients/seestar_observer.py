"""Direct guest-mode TCP client for Seestar S50 port 4701.

The S50 firmware accepts up to 8 simultaneous clients (1 host + 7 guests).
Port 4700 is the host channel (held by seestar_alp); port 4701 is the guest
JSON-RPC channel for state reads. This client uses 4701 to bypass the bridge
for methods whose ``method_sync`` round-trip hangs 10s on firmware 7.34.

Verified whitelist on firmware 7.34 (others return JSON-RPC code 103 or, in
the case of ``get_device_state``, briefly crash the firmware listener):

    test_connection, get_view_state, get_setting,
    iscope_get_app_state, get_focuser_position, pi_is_verified

Calling methods outside the whitelist is refused client-side.
"""

import json
import logging
import socket
import threading
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

SUPPORTED_METHODS = frozenset(
    {
        "test_connection",
        "get_view_state",
        "get_setting",
        "iscope_get_app_state",
        "get_focuser_position",
        "pi_is_verified",
    }
)


class SeestarObserverError(Exception):
    """Raised when a request fails (timeout, socket error, code != 0, unsupported)."""


class SeestarObserverClient:
    """Single-shot JSON-RPC client for Seestar guest channel (:4701)."""

    def __init__(self, host: str, port: int = 4701, timeout: float = 3.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._lock = threading.Lock()
        self._next_id = 1

    def call(self, method: str, params: Optional[dict] = None) -> Any:
        if method not in SUPPORTED_METHODS:
            raise SeestarObserverError(
                f"method '{method}' is not on the :{self.port} guest whitelist"
            )
        with self._lock:
            cid = self._next_id
            self._next_id += 1
        return self._send(cid, method, params)

    def _send(self, cid: int, method: str, params: Optional[dict]) -> Any:
        payload = {"id": cid, "method": method}
        if params is not None:
            payload["params"] = params
        wire = (json.dumps(payload) + "\r\n").encode()
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(self.timeout)
        try:
            s.connect((self.host, self.port))
            s.sendall(wire)
            deadline = time.monotonic() + self.timeout
            buf = b""
            while time.monotonic() < deadline:
                s.settimeout(max(0.1, deadline - time.monotonic()))
                try:
                    chunk = s.recv(65536)
                except socket.timeout as exc:
                    raise SeestarObserverError(
                        f"timed out after {self.timeout}s waiting for id={cid} ({method})"
                    ) from exc
                if not chunk:
                    raise SeestarObserverError("socket closed before response")
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
                        raise SeestarObserverError(
                            f"method '{method}' returned code={code}"
                        )
                    return obj.get("result")
            raise SeestarObserverError(
                f"timed out after {self.timeout}s waiting for id={cid} ({method})"
            )
        except OSError as exc:
            raise SeestarObserverError(f"socket error: {exc}") from exc
        finally:
            try:
                s.close()
            except OSError:
                pass

    def is_reachable(self) -> bool:
        try:
            self.call("test_connection")
            return True
        except SeestarObserverError:
            return False

    def get_view_state(self) -> dict:
        result = self.call("get_view_state")
        return result if isinstance(result, dict) else {}

    def get_setting(self) -> dict:
        result = self.call("get_setting")
        return result if isinstance(result, dict) else {}

    def get_focuser_position(self) -> Optional[int]:
        result = self.call("get_focuser_position")
        return result if isinstance(result, int) else None

    def get_app_state(self) -> dict:
        result = self.call("iscope_get_app_state")
        return result if isinstance(result, dict) else {}
