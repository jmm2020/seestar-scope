"""ASCOM ALPACA REST API Client for Seestar S50.

All ALPACA endpoints follow the pattern:
  GET  http://{host}:{port}/api/v1/{device_type}/{device_number}/{property}
  PUT  http://{host}:{port}/api/v1/{device_type}/{device_number}/{action}

GET returns: {"Value": <value>, "ClientTransactionID": N, "ServerTransactionID": N, "ErrorNumber": 0, "ErrorMessage": ""}
PUT accepts: form-encoded body with action parameters + ClientID + ClientTransactionID
PUT returns: {"ClientTransactionID": N, "ServerTransactionID": N, "ErrorNumber": 0, "ErrorMessage": ""}

ErrorNumber > 0 indicates failure. Common errors:
  - 1024: "Not connected" (device not connected yet)
  - 1031: "Property not implemented"
  - 1036: "Invalid value"
"""

import json

import requests
from dataclasses import dataclass
from typing import Any, Optional, Dict, List
import logging

logger = logging.getLogger(__name__)


@dataclass
class AlpacaResponse:
    """Standard ALPACA API response."""

    value: Any = None
    error_number: int = 0
    error_message: str = ""
    server_transaction_id: int = 0

    @property
    def success(self) -> bool:
        return self.error_number == 0


class AlpacaClient:
    """Client for ASCOM ALPACA telescope control API."""

    DEVICES = ["telescope", "camera", "focuser", "filterwheel", "switch"]

    def __init__(
        self,
        host: str = "192.168.0.132",
        port: int = 32323,
        client_id: int = 1,
        timeout: int = 30,
        alp_host: str = None,
        alp_port: int = 5555,
        img_port: int = 7556,
    ):
        self.base_url = f"http://{host}:{port}/api/v1"
        # seestar_alp bridge — hosts extended actions (method_sync, method_async)
        self._alp_host = alp_host or host
        self._img_port = img_port
        self.alp_base_url = f"http://{self._alp_host}:{alp_port}/api/v1"
        self.client_id = client_id
        self.timeout = timeout
        self._transaction_id = 0
        self.session = requests.Session()
        self.connected_devices: Dict[str, bool] = {}

    def _next_transaction_id(self) -> int:
        self._transaction_id += 1
        return self._transaction_id

    def _get(self, device: str, number: int, prop: str, **params) -> AlpacaResponse:
        """GET a device property."""
        url = f"{self.base_url}/{device}/{number}/{prop}"
        try:
            resp = self.session.get(url, params=params or None, timeout=self.timeout)
            data = resp.json()
            return AlpacaResponse(
                value=data.get("Value"),
                error_number=data.get("ErrorNumber", 0),
                error_message=data.get("ErrorMessage", ""),
                server_transaction_id=data.get("ServerTransactionID", 0),
            )
        except requests.exceptions.RequestException as e:
            logger.error(f"ALPACA GET {url} failed: {e}")
            return AlpacaResponse(error_number=-1, error_message=str(e))

    def _put(self, device: str, number: int, action: str, **params) -> AlpacaResponse:
        """PUT a device action with parameters."""
        url = f"{self.base_url}/{device}/{number}/{action}"
        form_data = {
            "ClientID": self.client_id,
            "ClientTransactionID": self._next_transaction_id(),
            **params,
        }
        try:
            resp = self.session.put(url, data=form_data, timeout=self.timeout)
            data = resp.json()
            return AlpacaResponse(
                error_number=data.get("ErrorNumber", 0),
                error_message=data.get("ErrorMessage", ""),
                server_transaction_id=data.get("ServerTransactionID", 0),
            )
        except requests.exceptions.RequestException as e:
            logger.error(f"ALPACA PUT {url} failed: {e}")
            return AlpacaResponse(error_number=-1, error_message=str(e))

    # --- Connection Management ---

    def connect_all(self) -> Dict[str, bool]:
        """Connect to all 5 ALPACA devices."""
        results = {}
        for device in self.DEVICES:
            resp = self._put(device, 0, "connected", Connected="true")
            results[device] = resp.success
            self.connected_devices[device] = resp.success
            if resp.success:
                logger.info(f"Connected: {device}")
            else:
                logger.error(f"Failed to connect {device}: {resp.error_message}")
        return results

    def disconnect_all(self):
        """Disconnect all devices."""
        for device in self.DEVICES:
            self._put(device, 0, "connected", Connected="false")
            self.connected_devices[device] = False

    # --- Telescope ---

    def get_telescope_status(self) -> dict:
        """Get complete telescope status."""
        return {
            "ra": self._get("telescope", 0, "rightascension").value,
            "dec": self._get("telescope", 0, "declination").value,
            "tracking": self._get("telescope", 0, "tracking").value,
            "slewing": self._get("telescope", 0, "slewing").value,
            "at_home": self._get("telescope", 0, "athome").value,
            "at_park": self._get("telescope", 0, "atpark").value,
            "site_lat": self._get("telescope", 0, "sitelatitude").value,
            "site_long": self._get("telescope", 0, "sitelongitude").value,
        }

    def slew_to(self, ra_hours: float, dec_degrees: float) -> AlpacaResponse:
        """Slew telescope to RA/Dec (async). RA in hours, Dec in degrees."""
        return self._put(
            "telescope",
            0,
            "slewtocoordinatesasync",
            RightAscension=str(ra_hours),
            Declination=str(dec_degrees),
        )

    def set_tracking(self, enabled: bool) -> AlpacaResponse:
        return self._put("telescope", 0, "tracking", Tracking=str(enabled).lower())

    def park(self) -> AlpacaResponse:
        return self._put("telescope", 0, "park")

    def unpark(self) -> AlpacaResponse:
        return self._put("telescope", 0, "unpark")

    def find_home(self) -> AlpacaResponse:
        return self._put("telescope", 0, "findhome")

    def pulse_guide(self, direction: int, duration_ms: int) -> AlpacaResponse:
        """Pulse guide. Direction: 0=N, 1=S, 2=E, 3=W."""
        return self._put(
            "telescope", 0, "pulseguide", Direction=str(direction), Duration=str(duration_ms)
        )

    # --- Camera ---

    def get_camera_status(self) -> dict:
        STATES = {0: "Idle", 1: "Waiting", 2: "Exposing", 3: "Reading", 4: "Download", 5: "Error"}
        state = self._get("camera", 0, "camerastate").value
        return {
            "state": STATES.get(state, f"Unknown({state})"),
            "state_code": state,
            "gain": self._get("camera", 0, "gain").value,
        }

    def start_exposure(self, duration_seconds: float, light: bool = True) -> AlpacaResponse:
        """Start camera exposure. Duration in seconds, Light=True for light frames."""
        return self._put(
            "camera", 0, "startexposure", Duration=str(duration_seconds), Light=str(light).lower()
        )

    def abort_exposure(self) -> AlpacaResponse:
        return self._put("camera", 0, "abortexposure")

    def is_image_ready(self) -> bool:
        return self._get("camera", 0, "imageready").value is True

    def get_image_array(self) -> Optional[list]:
        """Get captured image as array. Only call when is_image_ready() is True."""
        resp = self._get("camera", 0, "imagearray")
        return resp.value if resp.success else None

    def set_gain(self, gain: int) -> AlpacaResponse:
        """Set camera gain (0-400)."""
        return self._put("camera", 0, "gain", Gain=str(gain))

    # --- Focuser ---

    def get_focuser_status(self) -> dict:
        return {
            "position": self._get("focuser", 0, "position").value,
            "temperature": self._get("focuser", 0, "temperature").value,
            "maxstep": self._get("focuser", 0, "maxstep").value,
        }

    def move_focuser(self, position: int) -> AlpacaResponse:
        return self._put("focuser", 0, "move", Position=str(position))

    # --- Filter Wheel ---

    def get_filter_names(self) -> List[str]:
        return self._get("filterwheel", 0, "names").value or []

    def get_filter_position(self) -> int:
        return self._get("filterwheel", 0, "position").value

    def set_filter(self, position: int) -> AlpacaResponse:
        """Set filter: 0=Dark, 1=IR, 2=LP."""
        return self._put("filterwheel", 0, "position", Position=str(position))

    # --- Switch (Dew Heater) ---

    def get_dew_heater(self) -> bool:
        return bool(self._get("switch", 0, "getswitchvalue", Id=0).value)

    def set_dew_heater(self, on: bool) -> AlpacaResponse:
        return self._put("switch", 0, "setswitchvalue", Id="0", Value="1" if on else "0")

    # --- Seestar Native (via action endpoint) ---

    def seestar_action(self, method: str, params: dict = None, sync: bool = True) -> Optional[dict]:
        """Send a native Seestar JSON-RPC command via seestar_alp's action endpoint.

        Uses method_sync (waits for response) or method_async (fire-and-forget).
        Returns the parsed Value from the response, or None on error.
        """
        payload = {"method": method}
        if params:
            payload["params"] = params
        action = "method_sync" if sync else "method_async"
        url = f"{self.alp_base_url}/telescope/0/action"
        form_data = {
            "Action": action,
            "Parameters": json.dumps(payload),
            "ClientID": str(self.client_id),
            "ClientTransactionID": str(self._next_transaction_id()),
        }
        try:
            resp = self.session.put(url, data=form_data, timeout=self.timeout)
            data = resp.json()
            if data.get("ErrorNumber", 0) != 0:
                logger.warning(f"seestar_action({method}) error: {data.get('ErrorMessage')}")
                return None
            value = data.get("Value")
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    # ALP timeout returns a plain-text string; callers expect None on failure.
                    logger.warning(
                        f"seestar_action({method}) returned non-JSON string: {value[:100]!r}"
                    )
                    return None
            if not isinstance(value, dict):
                logger.warning(
                    f"seestar_action({method}) returned unexpected value type "
                    f"{type(value).__name__!r}: {repr(value)[:100]}"
                )
                return None
            # seestar_alp wraps responses as {"1": {"result": ...}} — unwrap
            inner = value.get("1")
            if inner is None:
                inner = value.get(1)
            if isinstance(inner, dict) and "result" in inner:
                return inner["result"]
            return value
        except requests.exceptions.RequestException as e:
            logger.error(f"seestar_action({method}) failed: {e}")
            return None

    def is_alp_available(self, timeout: int = 2) -> bool:
        """Return True if the seestar_alp bridge is reachable (any HTTP response, including 4xx/5xx)."""
        try:
            self.session.get(self.alp_base_url, timeout=timeout)
            return True
        except requests.exceptions.RequestException as e:
            logger.debug(f"is_alp_available probe failed ({self.alp_base_url}): {e}")
            return False

    # --- Live View & Stacking ---

    @property
    def img_stream_port(self) -> int:
        """Port the seestar_alp imaging server listens on (browser-facing)."""
        return self._img_port

    @property
    def img_stream_path(self) -> str:
        """Path portion of the MJPEG live view stream (device 0). Browser
        composes the full URL by prepending its own location.hostname, so the
        stream is reachable wherever the portal is reachable (LAN IP, tunnel,
        localhost) without hard-coding a host."""
        return "0/vid"

    @property
    def img_stream_url(self) -> str:
        """MJPEG live view URL using the configured ALP host. Note: this only
        works from inside the docker network — for browser embedding use
        img_stream_port + img_stream_path with window.location.hostname."""
        return f"http://{self._alp_host}:{self._img_port}/0/vid"

    def start_view(self, mode: str = "star") -> Optional[dict]:
        """Start live view mode (prerequisite for stacking)."""
        return self.seestar_action("iscope_start_view", {"mode": mode}, sync=False)

    def start_stack(self, restart: bool = True, gain: int = 80) -> Optional[dict]:
        """Start stacking with optional gain setting."""
        result = self.seestar_action("iscope_start_stack", {"restart": restart}, sync=True)
        if result is not None:
            self.seestar_action("set_control_value", ["gain", gain], sync=True)
        return result

    def stop_stack(self) -> Optional[dict]:
        """Stop the current stacking session."""
        return self.seestar_action("iscope_stop_view", {"stage": "Stack"}, sync=True)

    def set_stack_gain(self, gain: int) -> Optional[dict]:
        """Set gain during stacking."""
        return self.seestar_action("set_control_value", ["gain", gain], sync=True)

    def set_stack_setting(self, key: str, value) -> Optional[dict]:
        """Set a stack processing option (dbe, star_correction, etc.)."""
        return self.seestar_action("set_setting", {"stack": {key: value}}, sync=True)

    def set_stack_lp_filter(self, enabled: bool) -> Optional[dict]:
        """Toggle light pollution filter during stacking."""
        return self.seestar_action("set_setting", {"stack_lenhance": enabled}, sync=True)

    def set_stack_dither(self, enable: bool, pix: int = 100, interval: int = 5) -> Optional[dict]:
        """Configure dither settings."""
        return self.seestar_action(
            "set_setting",
            {"stack_dither": {"enable": enable, "pix": pix, "interval": interval}},
            sync=True,
        )

    def get_device_state(self) -> Optional[dict]:
        """Get native Seestar device state — battery, WiFi, storage, sensors, firmware, etc."""
        return self.seestar_action("get_device_state")

    def get_view_state(self) -> Optional[dict]:
        """Get current view state — mode (star/moon), stage, target name."""
        return self.seestar_action("get_view_state")
