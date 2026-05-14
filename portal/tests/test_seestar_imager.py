"""Tests for SeestarImagerClient — no live hardware required.

Wire-level protocol reference comes from vendor/seestar_alp/device/protocols/binary.py
(parse_header) and device/protocols/imager.py (handle_stack / handle_preview_frame).

Verified live header capture from firmware 7.34 at 192.168.0.132:4800 on
2026-05-13 after sending {"id": 23, "method": "get_stacked_img"}:

    03c30002005000000015747700000117000000000000... (80 bytes total)

    fmt = ">HHHIHHBBHH" → first 20 bytes:
    _s1=0x03c3, _s2=0x0002, _s3=0x0050,
    size=0x00000015 (21), _s5=0x7477, _s6=0x0000,
    code=0x01, id=0x17 (23), width=0, height=0

This corresponds to "no stack currently available" — request acknowledged,
zero-size payload follows.
"""

import io
import struct
import sys
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from clients.seestar_imager import (
    SeestarImagerClient,
    SeestarImagerError,
    StackedFrame,
)


LIVE_EMPTY_HEADER = (
    struct.pack(">HHHIHHBBHH", 0x03C3, 0x0002, 0x0050, 21, 0x7477, 0, 1, 23, 0, 0) + b"\x00" * 60
)
assert len(LIVE_EMPTY_HEADER) == 80


def _build_header(size: int, frame_id: int, width: int, height: int) -> bytes:
    """Build an 80-byte header matching the scope's wire format."""
    fmt = ">HHHIHHBBHH"
    head = struct.pack(fmt, 0x03C3, 0x0002, 0x0050, size, 0, 0, 1, frame_id, width, height)
    return head + b"\x00" * (80 - len(head))


def _zip_raw_payload(raw: bytes) -> bytes:
    """Wrap raw frame bytes in the zip format the scope uses for stacked frames."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("raw_data", raw)
    return buf.getvalue()


# --- parse_header --------------------------------------------------------


def test_parse_header_matches_live_empty_response():
    """The 80-byte header captured live decodes to size=21, id=23, w=0, h=0."""
    size, frame_id, width, height = SeestarImagerClient.parse_header(LIVE_EMPTY_HEADER)
    assert size == 21
    assert frame_id == 23
    assert width == 0
    assert height == 0


def test_parse_header_rejects_short_input():
    with pytest.raises(SeestarImagerError):
        SeestarImagerClient.parse_header(b"\x00" * 10)


# --- request_stacked_frame: behavioral ------------------------------------


def _fake_socket(*chunks: bytes) -> MagicMock:
    """Build a mock socket whose recv() yields the given chunks in order."""
    sock = MagicMock()
    queue = list(chunks)

    def fake_recv(n):
        if not queue:
            return b""
        head = queue.pop(0)
        # If chunk is larger than n, split it
        if len(head) > n:
            queue.insert(0, head[n:])
            return head[:n]
        return head

    sock.recv.side_effect = fake_recv
    sock.sendall.return_value = None
    sock.close.return_value = None
    return sock


@patch("clients.seestar_imager.socket.socket")
def test_request_stacked_frame_returns_none_when_empty(mock_socket_cls):
    """When the scope says 'no stack ready' (size < 1000), return None."""
    sock = _fake_socket(LIVE_EMPTY_HEADER, b"\x00" * 21)
    mock_socket_cls.return_value = sock

    client = SeestarImagerClient("192.168.0.132")
    result = client.request_stacked_frame()
    client.close()

    assert result is None


@patch("clients.seestar_imager.socket.socket")
def test_request_stacked_frame_returns_bayer_payload(mock_socket_cls):
    """A w*h*2 byte payload (uint16 Bayer) decodes into a StackedFrame."""
    width, height = 1080, 1920
    raw_pixels = (np.arange(width * height, dtype=np.uint16) % 65535).tobytes()
    assert len(raw_pixels) == width * height * 2

    payload = _zip_raw_payload(raw_pixels)
    header = _build_header(len(payload), frame_id=23, width=width, height=height)

    sock = _fake_socket(header, payload)
    mock_socket_cls.return_value = sock

    client = SeestarImagerClient("192.168.0.132")
    frame = client.request_stacked_frame()
    client.close()

    assert isinstance(frame, StackedFrame)
    assert frame.width == width
    assert frame.height == height
    assert frame.frame_format == "bayer16"
    assert frame.raw_data == raw_pixels


@patch("clients.seestar_imager.socket.socket")
def test_request_stacked_frame_returns_rgb16_payload(mock_socket_cls):
    """A w*h*6 byte payload (uint16 RGB) decodes into a StackedFrame."""
    width, height = 320, 200  # small for test speed
    raw_pixels = bytes((i * 3 + ch) % 256 for i in range(width * height) for ch in range(6))
    assert len(raw_pixels) == width * height * 6

    payload = _zip_raw_payload(raw_pixels)
    header = _build_header(len(payload), frame_id=23, width=width, height=height)

    sock = _fake_socket(header, payload)
    mock_socket_cls.return_value = sock

    client = SeestarImagerClient("192.168.0.132")
    frame = client.request_stacked_frame()
    client.close()

    assert isinstance(frame, StackedFrame)
    assert frame.width == width
    assert frame.height == height
    assert frame.frame_format == "rgb16"
    assert frame.raw_data == raw_pixels


@patch("clients.seestar_imager.socket.socket")
def test_request_stacked_frame_raises_on_socket_error(mock_socket_cls):
    sock = MagicMock()
    sock.connect.side_effect = OSError("nope")
    mock_socket_cls.return_value = sock

    client = SeestarImagerClient("192.168.0.132")
    with pytest.raises(SeestarImagerError):
        client.request_stacked_frame()


@patch("clients.seestar_imager.socket.socket")
def test_request_stacked_frame_raises_on_closed_socket(mock_socket_cls):
    """If the socket closes before the full header arrives, raise."""
    sock = _fake_socket(b"\x00" * 5)  # only 5 of 80 bytes, then EOF
    mock_socket_cls.return_value = sock

    client = SeestarImagerClient("192.168.0.132")
    with pytest.raises(SeestarImagerError):
        client.request_stacked_frame()


@patch("clients.seestar_imager.socket.socket")
def test_request_stacked_frame_opens_fresh_socket_each_call(mock_socket_cls):
    """The scope's :4800 protocol is one-shot — each poll must open its own socket.

    Regression test for the cache bug that broke /api/imager/stacked.jpg on every
    poll after the first: the client cached self._sock and reused it, but the
    scope closes the connection after each response, so the 2nd sendall() hit
    [Errno 32] Broken pipe and the route returned 502 Bad Gateway.
    """
    sock1 = _fake_socket(LIVE_EMPTY_HEADER, b"\x00" * 21)
    sock2 = _fake_socket(LIVE_EMPTY_HEADER, b"\x00" * 21)
    mock_socket_cls.side_effect = [sock1, sock2]

    client = SeestarImagerClient("192.168.0.132")
    assert client.request_stacked_frame() is None
    assert client.request_stacked_frame() is None

    assert mock_socket_cls.call_count == 2, "second call must open a fresh socket"
    sock1.close.assert_called()
    sock2.close.assert_called()


@patch("clients.seestar_imager.socket.socket")
def test_request_stacked_frame_handles_corrupt_zip(mock_socket_cls):
    """A non-zip payload of >=1000 bytes should raise rather than silently corrupt."""
    junk = b"\x00" * 2048
    header = _build_header(len(junk), frame_id=23, width=1080, height=1920)

    sock = _fake_socket(header, junk)
    mock_socket_cls.return_value = sock

    client = SeestarImagerClient("192.168.0.132")
    with pytest.raises(SeestarImagerError):
        client.request_stacked_frame()


# --- StackedFrame.to_jpeg -------------------------------------------------


def test_stacked_frame_to_jpeg_bayer():
    """A bayer16 frame demosaics and encodes to a valid JPEG byte string."""
    width, height = 64, 48
    raw = (np.arange(width * height, dtype=np.uint16) % 65535).tobytes()
    frame = StackedFrame(width=width, height=height, raw_data=raw, frame_format="bayer16")
    jpeg = frame.to_jpeg()
    assert isinstance(jpeg, bytes)
    assert jpeg[:3] == b"\xff\xd8\xff"  # JPEG magic


def test_stacked_frame_to_jpeg_rgb16():
    """An rgb16 frame encodes to a valid JPEG."""
    width, height = 64, 48
    raw = bytes(i % 256 for i in range(width * height * 6))
    frame = StackedFrame(width=width, height=height, raw_data=raw, frame_format="rgb16")
    jpeg = frame.to_jpeg()
    assert jpeg[:3] == b"\xff\xd8\xff"
