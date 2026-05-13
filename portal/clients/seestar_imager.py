"""Direct client for the Seestar S50's native imaging channel on TCP :4800.

Bypasses the seestar_alp bridge entirely. The scope's :4800 port runs an
unauthenticated binary JSON-RPC protocol that delivers stacked frames and
preview frames straight from the firmware:

    request:    JSON-RPC line, e.g. {"id": 23, "method": "get_stacked_img"}
    response:   80-byte header (parse with ">HHHIHHBBHH" — first 20 bytes used)
                followed by `size` bytes of payload.

For id=23 (stacked frame) the payload is a zip archive containing a
single file named "raw_data" whose bytes are either:

    - uint16 RGB (size == width * height * 6) — already demosaiced by the scope
    - uint16 Bayer GRBG (size == width * height * 2) — needs demosaic

A "no stack ready yet" response is just a header with size < 1000 and width=0
height=0. We return None in that case.

Verified live against firmware 7.34 at 192.168.0.132:4800 on 2026-05-13.
Wire format reference: vendor/seestar_alp/device/protocols/binary.py:116 and
vendor/seestar_alp/device/protocols/imager.py:263.
"""
from __future__ import annotations

import io
import json
import logging
import socket
import struct
import threading
import zipfile
from dataclasses import dataclass
from typing import Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)


HEADER_SIZE = 80
HEADER_FMT = ">HHHIHHBBHH"  # 20 bytes; rest of the 80-byte header is padding
HEADER_FMT_SIZE = struct.calcsize(HEADER_FMT)
EMPTY_PAYLOAD_THRESHOLD = 1000  # size < this means "no frame ready"

REQUEST_STACK = {"id": 23, "method": "get_stacked_img"}
REQUEST_STREAM_START = {"id": 21, "method": "begin_streaming"}


class SeestarImagerError(Exception):
    """Raised when the :4800 imaging channel misbehaves (socket / protocol / decode)."""


@dataclass
class StackedFrame:
    """A single stacked frame pulled directly off :4800."""

    width: int
    height: int
    raw_data: bytes
    frame_format: str  # "rgb16" or "bayer16"

    def to_jpeg(self, quality: int = 90) -> bytes:
        """Demosaic (if needed) and encode as JPEG for browser delivery."""
        img = _decode_raw_to_bgr(self.raw_data, self.width, self.height, self.frame_format)
        if img is None:
            raise SeestarImagerError(
                f"failed to decode {self.frame_format} frame ({self.width}x{self.height},"
                f" {len(self.raw_data)} bytes)"
            )
        ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
        if not ok:
            raise SeestarImagerError("cv2.imencode returned failure")
        return bytes(buf)


def _decode_raw_to_bgr(
    raw: bytes, width: int, height: int, fmt: str
) -> Optional[np.ndarray]:
    if fmt == "rgb16":
        expected = width * height * 6
        if len(raw) != expected:
            return None
        img = np.frombuffer(raw, dtype=np.uint16).reshape(height, width, 3)
        return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    if fmt == "bayer16":
        expected = width * height * 2
        if len(raw) != expected:
            return None
        img = np.frombuffer(raw, dtype=np.uint16).reshape(height, width)
        return cv2.cvtColor(img, cv2.COLOR_BAYER_GRBG2BGR)
    return None


class SeestarImagerClient:
    """Single-shot client for the scope's :4800 imaging port.

    Designed for poll-style use: open socket, request one stacked frame, close.
    Persistent streaming (id=21) lives in a separate method.
    """

    def __init__(self, host: str, port: int = 4800, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._lock = threading.Lock()
        self._sock: Optional[socket.socket] = None

    # --- socket lifecycle ----------------------------------------------------

    def _open(self) -> socket.socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        try:
            sock.connect((self.host, self.port))
        except OSError as exc:
            try:
                sock.close()
            except OSError:
                pass
            raise SeestarImagerError(f"socket connect to {self.host}:{self.port} failed: {exc}") from exc
        return sock

    def close(self) -> None:
        with self._lock:
            sock, self._sock = self._sock, None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    # --- public API ----------------------------------------------------------

    def request_stacked_frame(self) -> Optional[StackedFrame]:
        """Ask the scope for the current stacked frame.

        Returns None if no stacking session is active or no frame is ready yet.
        Raises SeestarImagerError on socket / protocol / decode failures.
        """
        with self._lock:
            if self._sock is None:
                self._sock = self._open()
            sock = self._sock
        try:
            payload = (json.dumps(REQUEST_STACK) + "\r\n").encode("utf-8")
            sock.sendall(payload)
            header = self._recv_exact(sock, HEADER_SIZE)
            size, frame_id, width, height = self.parse_header(header)
            if size < EMPTY_PAYLOAD_THRESHOLD:
                # ack-only / empty response — drain any tiny body, return None
                if size > 0:
                    self._recv_exact(sock, size)
                return None
            if frame_id != REQUEST_STACK["id"]:
                # Drain and bail; caller can retry
                self._recv_exact(sock, size)
                raise SeestarImagerError(
                    f"frame id mismatch: expected {REQUEST_STACK['id']}, got {frame_id}"
                )
            data = self._recv_exact(sock, size)
            raw, raw_format = self._unzip_and_classify(data, width, height)
            return StackedFrame(width=width, height=height, raw_data=raw, frame_format=raw_format)
        except SeestarImagerError:
            # On protocol error the socket may be in an unknown state — drop it.
            self.close()
            raise
        except OSError as exc:
            self.close()
            raise SeestarImagerError(f"socket error during stacked-frame fetch: {exc}") from exc

    # --- protocol helpers (static for testability) ---------------------------

    @staticmethod
    def parse_header(header: bytes) -> Tuple[int, int, int, int]:
        """Decode the 80-byte scope header → (size, id, width, height)."""
        if header is None or len(header) < HEADER_FMT_SIZE:
            raise SeestarImagerError(f"short header: got {len(header) if header else 0} bytes")
        _s1, _s2, _s3, size, _s5, _s6, _code, frame_id, width, height = struct.unpack(
            HEADER_FMT, header[:HEADER_FMT_SIZE]
        )
        return size, frame_id, width, height

    @staticmethod
    def _recv_exact(sock: socket.socket, n: int) -> bytes:
        buf = bytearray()
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                raise SeestarImagerError(
                    f"socket closed after {len(buf)} of {n} expected bytes"
                )
            buf.extend(chunk)
        return bytes(buf)

    @staticmethod
    def _unzip_and_classify(data: bytes, width: int, height: int) -> Tuple[bytes, str]:
        """Pull raw_data out of the scope's zip wrapper and classify the pixel format."""
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                raw = zf.read("raw_data")
        except (zipfile.BadZipFile, KeyError, OSError) as exc:
            raise SeestarImagerError(f"stacked frame payload is not a valid zip: {exc}") from exc
        if width and height:
            if len(raw) == width * height * 6:
                return raw, "rgb16"
            if len(raw) == width * height * 2:
                return raw, "bayer16"
        raise SeestarImagerError(
            f"unrecognized raw_data size {len(raw)} for {width}x{height} frame"
        )
