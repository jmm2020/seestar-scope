"""Tests for AlpacaClient - no live hardware required."""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

from clients.alpaca_client import AlpacaClient, AlpacaResponse
from clients.seestar_observer import SeestarObserverError


# --- AlpacaResponse tests ---


def test_alpaca_response_success():
    resp = AlpacaResponse(value=True, error_number=0)
    assert resp.success is True


def test_alpaca_response_failure():
    resp = AlpacaResponse(error_number=1024, error_message="Not connected")
    assert resp.success is False


def test_alpaca_response_network_error():
    resp = AlpacaResponse(error_number=-1, error_message="Connection refused")
    assert resp.success is False


def test_alpaca_response_default_values():
    resp = AlpacaResponse()
    assert resp.value is None
    assert resp.error_number == 0
    assert resp.success is True


# --- AlpacaClient construction ---


def test_client_default_construction():
    client = AlpacaClient()
    assert client.base_url == "http://192.168.0.132:32323/api/v1"
    assert client.client_id == 1
    assert client.timeout == 30


def test_client_custom_construction():
    client = AlpacaClient(host="10.0.0.1", port=11111, client_id=5, timeout=10)
    assert client.base_url == "http://10.0.0.1:11111/api/v1"
    assert client.client_id == 5
    assert client.timeout == 10


def test_client_devices_list():
    assert AlpacaClient.DEVICES == ["telescope", "camera", "focuser", "filterwheel", "switch"]


def test_transaction_id_increments():
    client = AlpacaClient()
    id1 = client._next_transaction_id()
    id2 = client._next_transaction_id()
    assert id2 == id1 + 1


# --- Mocked HTTP tests ---


def _mock_get_response(value, error_number=0, error_message=""):
    """Create a mock requests.Response for GET."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "Value": value,
        "ErrorNumber": error_number,
        "ErrorMessage": error_message,
        "ServerTransactionID": 1,
    }
    return mock_resp


def _mock_put_response(error_number=0, error_message=""):
    """Create a mock requests.Response for PUT."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "ErrorNumber": error_number,
        "ErrorMessage": error_message,
        "ServerTransactionID": 1,
    }
    return mock_resp


def test_get_telescope_status():
    client = AlpacaClient()
    with patch.object(client.session, "get") as mock_get:
        mock_get.return_value = _mock_get_response(12.5)
        result = client._get("telescope", 0, "rightascension")
        assert result.success is True
        assert result.value == 12.5


def test_put_slew():
    client = AlpacaClient()
    with patch.object(client.session, "put") as mock_put:
        mock_put.return_value = _mock_put_response()
        result = client.slew_to(5.588, -5.391)
        assert result.success is True
        mock_put.assert_called_once()


def test_connect_all_success():
    client = AlpacaClient()
    with patch.object(client.session, "put") as mock_put:
        mock_put.return_value = _mock_put_response()
        results = client.connect_all()
        assert all(results.values())
        assert len(results) == 5
        assert mock_put.call_count == 5


def test_connect_all_partial_failure():
    client = AlpacaClient()
    call_count = 0

    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 3:  # Focuser fails
            return _mock_put_response(error_number=1024, error_message="Not connected")
        return _mock_put_response()

    with patch.object(client.session, "put", side_effect=side_effect):
        results = client.connect_all()
        assert results["telescope"] is True
        assert results["camera"] is True
        assert results["focuser"] is False
        assert results["filterwheel"] is True
        assert results["switch"] is True


def test_get_network_error():
    client = AlpacaClient()
    import requests

    with patch.object(
        client.session, "get", side_effect=requests.exceptions.ConnectionError("refused")
    ):
        result = client._get("telescope", 0, "rightascension")
        assert result.success is False
        assert "refused" in result.error_message


def test_set_gain():
    client = AlpacaClient()
    with patch.object(client.session, "put") as mock_put:
        mock_put.return_value = _mock_put_response()
        result = client.set_gain(80)
        assert result.success is True


def test_is_image_ready_true():
    client = AlpacaClient()
    with patch.object(client.session, "get") as mock_get:
        mock_get.return_value = _mock_get_response(True)
        assert client.is_image_ready() is True


def test_is_image_ready_false():
    client = AlpacaClient()
    with patch.object(client.session, "get") as mock_get:
        mock_get.return_value = _mock_get_response(False)
        assert client.is_image_ready() is False


def test_get_dew_heater():
    client = AlpacaClient()
    with patch.object(client.session, "get") as mock_get:
        mock_get.return_value = _mock_get_response(1)
        assert client.get_dew_heater() is True


def test_set_dew_heater():
    client = AlpacaClient()
    with patch.object(client.session, "put") as mock_put:
        mock_put.return_value = _mock_put_response()
        result = client.set_dew_heater(True)
        assert result.success is True


def test_is_alp_available_true_when_alpaca_endpoint_returns_200_with_error_shape():
    """Probe hits /management/apiversions (cheap, no scope touch); 200 with Alpaca body = healthy."""
    client = AlpacaClient()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = '{"Value": [1], "ErrorNumber": 0, "ErrorMessage": ""}'
    with patch.object(client.session, "get", return_value=mock_resp) as mock_get:
        assert client.is_alp_available() is True
    # Probe must target /management/apiversions — avoids method_sync hangs on /telescope/* paths
    call_args = mock_get.call_args
    assert call_args.args[0].endswith("/management/apiversions")


def test_is_alp_available_false_on_404_or_other_non_200():
    """A 404 (e.g. probing the wrong path) is not a healthy bridge — return False."""
    client = AlpacaClient()
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.text = "Not Found"
    with patch.object(client.session, "get", return_value=mock_resp):
        assert client.is_alp_available() is False


def test_is_alp_available_false_on_200_without_alpaca_shape():
    """A 200 from a different service (no ErrorNumber field) is not a real Alpaca response."""
    client = AlpacaClient()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "<html>some unrelated page</html>"
    with patch.object(client.session, "get", return_value=mock_resp):
        assert client.is_alp_available() is False


def test_is_alp_available_logs_on_failure():
    """Probe failure is logged at DEBUG level with URL context."""
    client = AlpacaClient()
    with (
        patch.object(
            client.session, "get", side_effect=requests.exceptions.ConnectionError("refused")
        ),
        patch("clients.alpaca_client.logger") as mock_logger,
    ):
        result = client.is_alp_available()
    assert result is False
    mock_logger.debug.assert_called_once()
    assert "is_alp_available" in mock_logger.debug.call_args.args[0]


def test_is_alp_available_timeout():
    client = AlpacaClient()
    with patch.object(
        client.session,
        "get",
        side_effect=requests.exceptions.Timeout("timed out"),
    ):
        assert client.is_alp_available() is False


# --- seestar_action() error-shape tests (regression for issue #29) ---


def _mock_action_response(value, error_number=0, error_message=""):
    """Mock the PUT response for /telescope/0/action."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "Value": value,
        "ErrorNumber": error_number,
        "ErrorMessage": error_message,
        "ServerTransactionID": 1,
        "ClientTransactionID": 1,
    }
    return mock_resp


def test_seestar_action_returns_none_on_timeout_string():
    """When ALP times out it returns a plain-text error string in Value; we must
    return None, not pass the string through to callers that expect a dict."""
    client = AlpacaClient()
    with patch.object(client.session, "put") as mock_put:
        mock_put.return_value = _mock_action_response(
            "Error: Exceeded allotted wait time for result"
        )
        result = client.seestar_action("get_device_state")
    assert result is None


def test_seestar_action_returns_none_on_non_json_string():
    """A Value that looks dict-like but isn't valid JSON (e.g. Python repr) must
    also coerce to None rather than reach the caller."""
    client = AlpacaClient()
    with patch.object(client.session, "put") as mock_put:
        mock_put.return_value = _mock_action_response(
            "{'method': 'get_device_state', 'result': 'some error'}"
        )
        result = client.seestar_action("get_device_state")
    assert result is None


def test_seestar_action_returns_none_on_non_dict_value():
    """List/number/bool values that aren't ALP-wrapped dicts coerce to None."""
    client = AlpacaClient()
    with patch.object(client.session, "put") as mock_put:
        mock_put.return_value = _mock_action_response([1, 2, 3])
        result = client.seestar_action("get_device_state")
    assert result is None


def test_seestar_action_unwraps_dict_result():
    """The happy path: ALP wraps the JSON-RPC reply as {"1": {"result": ...}}
    and we return the inner result dict."""
    client = AlpacaClient()
    with patch.object(client.session, "put") as mock_put:
        mock_put.return_value = _mock_action_response({"1": {"result": {"battery_capacity": 87}}})
        result = client.seestar_action("get_device_state")
    assert result == {"battery_capacity": 87}


def test_seestar_action_parses_json_string_value():
    """When Value is a JSON-encoded string the client should parse and unwrap it."""
    client = AlpacaClient()
    with patch.object(client.session, "put") as mock_put:
        mock_put.return_value = _mock_action_response('{"1": {"result": {"mode": "star"}}}')
        result = client.seestar_action("get_view_state")
    assert result == {"mode": "star"}


def test_seestar_action_returns_none_on_alpaca_error():
    """ALPACA ErrorNumber != 0 must return None regardless of Value content."""
    client = AlpacaClient()
    with patch.object(client.session, "put") as mock_put:
        mock_put.return_value = _mock_action_response(
            value=None, error_number=1024, error_message="Not connected"
        )
        result = client.seestar_action("get_device_state")
    assert result is None


def test_seestar_action_logs_warning_on_non_dict_value():
    """Non-dict Value (list, int, None) must log a warning — not silently return None."""
    client = AlpacaClient()
    with (
        patch.object(client.session, "put") as mock_put,
        patch("clients.alpaca_client.logger") as mock_logger,
    ):
        mock_put.return_value = _mock_action_response([1, 2, 3])
        result = client.seestar_action("get_device_state")
    assert result is None
    mock_logger.warning.assert_called_once()
    assert "unexpected value type" in mock_logger.warning.call_args.args[0]


def test_seestar_action_returns_plain_dict_without_alp_envelope():
    """A dict Value that lacks the '1' ALP wrapper is passed through unchanged."""
    client = AlpacaClient()
    with patch.object(client.session, "put") as mock_put:
        mock_put.return_value = _mock_action_response({"status": "ok"})
        result = client.seestar_action("some_method")
    assert result == {"status": "ok"}


def test_seestar_action_returns_none_when_value_key_absent():
    """When the ALPACA response omits the Value key entirely, return None cleanly."""
    client = AlpacaClient()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "ErrorNumber": 0,
        "ErrorMessage": "",
        "ServerTransactionID": 1,
        "ClientTransactionID": 1,
    }
    with (
        patch.object(client.session, "put", return_value=mock_resp),
        patch("clients.alpaca_client.logger") as mock_logger,
    ):
        result = client.seestar_action("get_device_state")
    assert result is None
    mock_logger.warning.assert_called_once()


def test_get_view_state_returns_none_on_string_payload():
    """End-to-end: when observer fails and bridge returns junk, return None.

    Avoid hitting the real scope on :4701 by injecting a stub observer that
    raises — that forces the bridge fallback, which is what this test guards.
    """
    client = AlpacaClient()
    stub_observer = MagicMock()
    stub_observer.get_view_state.side_effect = SeestarObserverError("forced fallback")
    client._observer = stub_observer
    with patch.object(client.session, "put") as mock_put:
        mock_put.return_value = _mock_action_response("not-json")
        assert client.get_view_state() is None


# --- img_stream_* tests ---
# The MJPEG live view used to be embedded with the docker network hostname
# (seestar-alp:7556/1/vid) — browser couldn't resolve the hostname AND the
# device number was wrong. The portal now exposes port+path separately so the
# browser composes the URL with window.location.hostname.


def test_img_stream_path_uses_device_zero():
    """The Seestar device is numbered 0 — /1/vid returns KeyError: 1 in alp."""
    client = AlpacaClient()
    assert client.img_stream_path == "0/vid"


def test_img_stream_port_defaults_to_7556():
    """Default seestar_alp imaging port is 7556."""
    client = AlpacaClient()
    assert client.img_stream_port == 7556


def test_img_stream_port_respects_constructor_override():
    """img_stream_port reflects the img_port constructor argument."""
    client = AlpacaClient(img_port=9999)
    assert client.img_stream_port == 9999


def test_img_stream_url_uses_device_zero_not_one():
    """Legacy img_stream_url must also use /0/vid (not /1/vid which 500s)."""
    client = AlpacaClient(alp_host="seestar-alp", img_port=7556)
    assert client.img_stream_url == "http://seestar-alp:7556/0/vid"
