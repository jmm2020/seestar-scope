"""Tests for SeestarObserverClient (:4701 guest JSON-RPC channel)."""

import json
import socket
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from clients.seestar_observer import (
    SUPPORTED_METHODS,
    SeestarObserverClient,
    SeestarObserverError,
)


class FakeScopeServer:
    """Single-connection TCP echo server simulating the :4701 firmware listener.

    Behavior is configured by passing a `handler` callable: handler(request_dict)
    returns the response dict (the test framework writes the wire envelope).
    Set `respond_after` to add latency, `silent` to never reply, or `drop_after`
    to close the socket after sending the response (matching the firmware
    pattern for unknown methods).
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


def test_supported_methods_set():
    # Pin the whitelist so regressions are caught at import time.
    assert SUPPORTED_METHODS == frozenset(
        {
            "test_connection",
            "get_view_state",
            "get_setting",
            "iscope_get_app_state",
            "get_focuser_position",
            "pi_is_verified",
            "iscope_start_stack",
            "iscope_stop_view",
            "set_control_value",
            "set_setting",
        }
    )


def test_unsupported_method_refused_without_socket_call():
    client = SeestarObserverClient("127.0.0.1", port=1)  # unreachable on purpose
    with pytest.raises(SeestarObserverError, match="not on the.*guest whitelist"):
        client.call("get_device_state")  # known to crash firmware listener


def test_call_test_connection_returns_string():
    server = FakeScopeServer(_ok("server connected!"))
    try:
        c = SeestarObserverClient("127.0.0.1", port=server.port)
        assert c.call("test_connection") == "server connected!"
    finally:
        server.close()


def test_call_get_view_state_idle_returns_empty_dict():
    server = FakeScopeServer(_ok({}))
    try:
        c = SeestarObserverClient("127.0.0.1", port=server.port)
        assert c.get_view_state() == {}
    finally:
        server.close()


def test_call_get_view_state_active_returns_payload():
    payload = {
        "View": {
            "mode": "star",
            "state": "working",
            "stage": "Stack",
            "Stack": {"count": 12, "fps": 0.1},
        }
    }
    server = FakeScopeServer(_ok(payload))
    try:
        c = SeestarObserverClient("127.0.0.1", port=server.port)
        assert c.get_view_state() == payload
    finally:
        server.close()


def test_call_get_setting_returns_dict_with_keys():
    server = FakeScopeServer(_ok({"temp_unit": "C", "stack_lenhance": True}))
    try:
        c = SeestarObserverClient("127.0.0.1", port=server.port)
        result = c.get_setting()
        assert result["stack_lenhance"] is True
        assert result["temp_unit"] == "C"
    finally:
        server.close()


def test_call_get_focuser_position_returns_int():
    server = FakeScopeServer(_ok(1750))
    try:
        c = SeestarObserverClient("127.0.0.1", port=server.port)
        assert c.get_focuser_position() == 1750
    finally:
        server.close()


def test_get_focuser_position_returns_none_for_unexpected_type():
    server = FakeScopeServer(_ok("oops"))
    try:
        c = SeestarObserverClient("127.0.0.1", port=server.port)
        assert c.get_focuser_position() is None
    finally:
        server.close()


def test_non_zero_code_raises():
    server = FakeScopeServer(lambda req: {"code": 103, "result": None, "method": req["method"]})
    try:
        c = SeestarObserverClient("127.0.0.1", port=server.port)
        with pytest.raises(SeestarObserverError, match="code=103"):
            c.call("test_connection")
    finally:
        server.close()


def test_timeout_when_server_silent():
    server = FakeScopeServer(_ok("ignored"), silent=True)
    try:
        c = SeestarObserverClient("127.0.0.1", port=server.port, timeout=0.5)
        with pytest.raises(SeestarObserverError, match="timed out"):
            c.call("test_connection")
    finally:
        server.close()


def test_socket_error_when_port_closed():
    # Bind a socket, immediately close → next connect refuses.
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    c = SeestarObserverClient("127.0.0.1", port=port, timeout=0.5)
    with pytest.raises(SeestarObserverError, match="socket error"):
        c.call("test_connection")


def test_is_reachable_true_when_server_ok():
    server = FakeScopeServer(_ok("server connected!"))
    try:
        c = SeestarObserverClient("127.0.0.1", port=server.port)
        assert c.is_reachable() is True
    finally:
        server.close()


def test_is_reachable_false_when_unreachable():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    c = SeestarObserverClient("127.0.0.1", port=port, timeout=0.5)
    assert c.is_reachable() is False


def test_ignores_push_event_with_other_id():
    """If the scope pushes an event/response with a different id, the client
    should keep reading until it sees the matching id."""

    def handler_with_noise(req):
        # The FakeScopeServer only writes one envelope, so we inject the noise
        # by overriding send. Easier: use a custom server here.
        return {"code": 0, "result": "actual", "method": req["method"]}

    class NoisyServer(FakeScopeServer):
        def _serve(self, conn):
            try:
                conn.settimeout(5)
                buf = b""
                while b"\r\n" not in buf:
                    chunk = conn.recv(4096)
                    if not chunk:
                        return
                    buf += chunk
                line = buf.split(b"\r\n", 1)[0]
                req = json.loads(line.decode("utf-8"))
                self.received.append(req)
                noise = {"jsonrpc": "2.0", "id": 99999, "method": "push", "Event": "ping"}
                conn.sendall((json.dumps(noise) + "\r\n").encode())
                resp = {
                    "jsonrpc": "2.0",
                    "id": req["id"],
                    "code": 0,
                    "result": "actual",
                    "method": req["method"],
                }
                conn.sendall((json.dumps(resp) + "\r\n").encode())
            finally:
                try:
                    conn.close()
                except OSError:
                    pass

    server = NoisyServer(handler_with_noise)
    try:
        c = SeestarObserverClient("127.0.0.1", port=server.port)
        assert c.call("test_connection") == "actual"
    finally:
        server.close()


def test_request_ids_increment_across_calls():
    server = FakeScopeServer(_ok("ok"))
    try:
        c = SeestarObserverClient("127.0.0.1", port=server.port)
        c.call("test_connection")
        c.call("test_connection")
        c.call("test_connection")
        ids = [r["id"] for r in server.received]
        # IDs must be strictly increasing.
        assert ids == sorted(ids)
        assert len(set(ids)) == len(ids)
    finally:
        server.close()


# --- Write method tests ---


def test_start_stack_sends_iscope_start_stack_then_set_control_value():
    """start_stack() must send iscope_start_stack then set_control_value in order."""
    requests_seen = []

    def handler(req):
        requests_seen.append(req)
        return {"code": 0, "result": None, "method": req["method"]}

    server = FakeScopeServer(handler)
    try:
        c = SeestarObserverClient("127.0.0.1", port=server.port)
        c.start_stack(restart=False, gain=80)
        assert len(requests_seen) == 2
        assert requests_seen[0]["method"] == "iscope_start_stack"
        assert requests_seen[0]["params"] == {"restart": False}
        assert requests_seen[1]["method"] == "set_control_value"
        assert requests_seen[1]["params"] == ["gain", 80]
    finally:
        server.close()


def test_start_stack_restart_true_sends_correct_params():
    """start_stack(restart=True) must send {"restart": true} to the scope."""
    requests_seen = []

    def handler(req):
        requests_seen.append(req)
        return {"code": 0, "result": None, "method": req["method"]}

    server = FakeScopeServer(handler)
    try:
        c = SeestarObserverClient("127.0.0.1", port=server.port)
        c.start_stack(restart=True, gain=120)
        assert requests_seen[0]["params"] == {"restart": True}
        assert requests_seen[1]["params"] == ["gain", 120]
    finally:
        server.close()


def test_stop_stack_sends_iscope_stop_view_with_stack_stage():
    """stop_stack() must send iscope_stop_view with {"stage": "Stack"}."""
    requests_seen = []

    def handler(req):
        requests_seen.append(req)
        return {"code": 0, "result": None, "method": req["method"]}

    server = FakeScopeServer(handler)
    try:
        c = SeestarObserverClient("127.0.0.1", port=server.port)
        c.stop_stack()
        assert len(requests_seen) == 1
        assert requests_seen[0]["method"] == "iscope_stop_view"
        assert requests_seen[0]["params"] == {"stage": "Stack"}
    finally:
        server.close()


def test_set_stack_gain_sends_list_format():
    """set_stack_gain() must send set_control_value with a list, not a dict."""
    requests_seen = []

    def handler(req):
        requests_seen.append(req)
        return {"code": 0, "result": None, "method": req["method"]}

    server = FakeScopeServer(handler)
    try:
        c = SeestarObserverClient("127.0.0.1", port=server.port)
        c.set_stack_gain(200)
        assert len(requests_seen) == 1
        assert requests_seen[0]["method"] == "set_control_value"
        assert requests_seen[0]["params"] == ["gain", 200]
    finally:
        server.close()


def test_set_stack_lp_filter_on_sends_set_setting():
    """set_stack_lp_filter(True) must send set_setting with {"stack_lenhance": true}."""
    requests_seen = []

    def handler(req):
        requests_seen.append(req)
        return {"code": 0, "result": None, "method": req["method"]}

    server = FakeScopeServer(handler)
    try:
        c = SeestarObserverClient("127.0.0.1", port=server.port)
        c.set_stack_lp_filter(True)
        assert len(requests_seen) == 1
        assert requests_seen[0]["method"] == "set_setting"
        assert requests_seen[0]["params"] == {"stack_lenhance": True}
    finally:
        server.close()


def test_set_stack_lp_filter_off_sends_false():
    """set_stack_lp_filter(False) must send {"stack_lenhance": false}."""
    requests_seen = []

    def handler(req):
        requests_seen.append(req)
        return {"code": 0, "result": None, "method": req["method"]}

    server = FakeScopeServer(handler)
    try:
        c = SeestarObserverClient("127.0.0.1", port=server.port)
        c.set_stack_lp_filter(False)
        assert requests_seen[0]["params"] == {"stack_lenhance": False}
    finally:
        server.close()


def test_write_method_error_propagates():
    """If scope returns code != 0 on a write method, SeestarObserverError is raised."""
    server = FakeScopeServer(lambda req: {"code": 103, "result": None, "method": req["method"]})
    try:
        c = SeestarObserverClient("127.0.0.1", port=server.port)
        with pytest.raises(SeestarObserverError, match="code=103"):
            c.stop_stack()
    finally:
        server.close()
