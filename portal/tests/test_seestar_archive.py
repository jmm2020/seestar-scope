"""Tests for SeestarArchiveClient (:4701 guest JSON-RPC + scope HTTP archive)."""

import json
import socket
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from clients.seestar_archive import (  # noqa: E402
    OnboardItem,
    SeestarArchiveClient,
    SeestarArchiveError,
)


class FakeScopeServer:
    """Single-connection TCP echo server simulating the :4701 firmware listener.

    Mirrors the harness used by test_seestar_observer.py — handler(req) returns
    the response dict; the framework writes the wire envelope.
    """

    def __init__(self, handler, respond_after=0.0, silent=False, drop_after=False):
        self.handler = handler
        self.respond_after = respond_after
        self.silent = silent
        self.drop_after = drop_after
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        self.sock.listen(4)
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        self.received: list = []

    def _run(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn: socket.socket):
        try:
            conn.settimeout(5)
            buf = b""
            while b"\r\n" not in buf:
                chunk = conn.recv(4096)
                if not chunk:
                    return
                buf += chunk
            line = buf.split(b"\r\n", 1)[0]
            try:
                req = json.loads(line.decode("utf-8"))
            except json.JSONDecodeError:
                return
            self.received.append(req)
            if self.silent:
                time.sleep(2)
                return
            if self.respond_after:
                time.sleep(self.respond_after)
            resp = self.handler(req)
            wire_resp = {"jsonrpc": "2.0", "id": req.get("id"), **resp}
            conn.sendall((json.dumps(wire_resp) + "\r\n").encode())
            if self.drop_after:
                conn.close()
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


def _ok(result):
    return lambda req: {"code": 0, "result": result, "method": req["method"]}


# Mirrors the live :4701 probe response captured 2026-05-14 on firmware 7.34.
SAMPLE_ALBUMS = {
    "path": "MyWorks",
    "list": [
        {
            "group_name": "SolarSystem",
            "files": [
                {
                    "name": "Solar_video",
                    "thn": "Solar_video/2024-04-08-141802-Solar-timelapse_thn.jpg",
                    "count": 1,
                    "type": 0,
                },
                {
                    "name": "Lunar_video",
                    "thn": "Lunar_video/2024-06-15-211745-Lunar-timelapse_thn.jpg",
                    "count": 1,
                    "type": 0,
                },
            ],
        },
        {
            "group_name": "DeepSky",
            "files": [
                {
                    "name": "M 13",
                    "thn": "M 13/Stacked_888_M 13_10.0s_IRCUT_20240726-020555_thn.jpg",
                    "count": 1,
                    "type": 0,
                },
            ],
        },
    ],
}


def test_get_albums_success_returns_dict():
    server = FakeScopeServer(_ok(SAMPLE_ALBUMS))
    try:
        c = SeestarArchiveClient("127.0.0.1", rpc_port=server.port)
        result = c.get_albums()
        assert result["path"] == "MyWorks"
        assert len(result["list"]) == 2
    finally:
        server.close()


def test_get_albums_code_nonzero_raises():
    server = FakeScopeServer(
        lambda req: {"code": 103, "result": None, "method": req["method"]}
    )
    try:
        c = SeestarArchiveClient("127.0.0.1", rpc_port=server.port)
        with pytest.raises(SeestarArchiveError, match="code=103"):
            c.get_albums()
    finally:
        server.close()


def test_get_albums_timeout_raises():
    server = FakeScopeServer(_ok(SAMPLE_ALBUMS), silent=True)
    try:
        c = SeestarArchiveClient("127.0.0.1", rpc_port=server.port, timeout=0.5)
        with pytest.raises(SeestarArchiveError, match="timed out"):
            c.get_albums()
    finally:
        server.close()


def test_get_albums_socket_error_raises():
    # Bind a socket, immediately close → next connect refuses.
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    c = SeestarArchiveClient("127.0.0.1", rpc_port=port, timeout=0.5)
    with pytest.raises(SeestarArchiveError, match="socket error"):
        c.get_albums()


def test_list_items_parses_files_correctly():
    server = FakeScopeServer(_ok(SAMPLE_ALBUMS))
    try:
        c = SeestarArchiveClient("127.0.0.1", rpc_port=server.port, http_port=80)
        items = c.list_items()
        assert len(items) == 3
        # The two SolarSystem entries are videos, the DeepSky entry is an image.
        assert items[0].is_video is True
        assert items[1].is_video is True
        assert items[2].is_video is False
        assert items[0].name == "Solar_video"
        assert items[2].name == "M 13"
    finally:
        server.close()


def test_list_items_constructs_thumb_url():
    server = FakeScopeServer(_ok(SAMPLE_ALBUMS))
    try:
        c = SeestarArchiveClient("127.0.0.1", rpc_port=server.port, http_port=80)
        items = c.list_items()
        # Image entry — verify thumb URL pattern matches scope HTTP layout.
        image = items[2]
        assert image.thumb_url.startswith("http://127.0.0.1:80/MyWorks/")
        assert image.thumb_url.endswith("_thn.jpg")
        assert "M 13/" in image.thumb_url
    finally:
        server.close()


def test_list_items_constructs_full_url_image_ends_jpg():
    server = FakeScopeServer(_ok(SAMPLE_ALBUMS))
    try:
        c = SeestarArchiveClient("127.0.0.1", rpc_port=server.port, http_port=80)
        items = c.list_items()
        image = items[2]
        assert image.full_url.endswith(".jpg")
        assert "_thn" not in image.full_url
    finally:
        server.close()


def test_list_items_video_full_url_ends_mp4():
    server = FakeScopeServer(_ok(SAMPLE_ALBUMS))
    try:
        c = SeestarArchiveClient("127.0.0.1", rpc_port=server.port, http_port=80)
        items = c.list_items()
        # Both SolarSystem items are videos by name suffix.
        video = items[0]
        assert video.is_video is True
        assert video.full_url.endswith(".mp4")
        assert "_thn" not in video.full_url
    finally:
        server.close()


def test_list_items_empty_album_returns_empty_list():
    server = FakeScopeServer(_ok({"path": "MyWorks", "list": []}))
    try:
        c = SeestarArchiveClient("127.0.0.1", rpc_port=server.port)
        assert c.list_items() == []
    finally:
        server.close()


def test_list_items_skips_entries_without_thn():
    """A file entry missing 'thn' must not produce a broken URL."""
    server = FakeScopeServer(
        _ok(
            {
                "path": "MyWorks",
                "list": [
                    {
                        "group_name": "DeepSky",
                        "files": [
                            {"name": "good", "thn": "good/good_thn.jpg"},
                            {"name": "broken"},  # no thn
                        ],
                    }
                ],
            }
        )
    )
    try:
        c = SeestarArchiveClient("127.0.0.1", rpc_port=server.port)
        items = c.list_items()
        assert len(items) == 1
        assert items[0].name == "good"
    finally:
        server.close()


def test_is_reachable_true_when_albums_ok():
    server = FakeScopeServer(_ok(SAMPLE_ALBUMS))
    try:
        c = SeestarArchiveClient("127.0.0.1", rpc_port=server.port)
        assert c.is_reachable() is True
    finally:
        server.close()


def test_is_reachable_false_when_socket_error():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    c = SeestarArchiveClient("127.0.0.1", rpc_port=port, timeout=0.5)
    assert c.is_reachable() is False


def test_onboard_item_to_dict_roundtrips():
    item = OnboardItem(
        name="x", thumb_url="http://h/t_thn.jpg", full_url="http://h/t.jpg", is_video=False
    )
    d = item.to_dict()
    assert d == {
        "name": "x",
        "thumb_url": "http://h/t_thn.jpg",
        "full_url": "http://h/t.jpg",
        "is_video": False,
    }
