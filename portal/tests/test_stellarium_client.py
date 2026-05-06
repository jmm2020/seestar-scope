"""Tests for StellariumClient - no live Stellarium required."""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from clients.stellarium_client import StellariumClient, StellariumObject


# --- StellariumObject tests ---

def test_stellarium_object_creation():
    obj = StellariumObject(
        name="M42",
        object_type="nebula",
        ra_j2000_hours=5.588,
        dec_j2000_degrees=-5.391,
        altitude=45.0,
        azimuth=180.0,
        magnitude=4.0,
        above_horizon=True,
        constellation="Ori",
        rise="18h00m",
        set_time="06h00m",
    )
    assert obj.name == "M42"
    assert obj.above_horizon is True
    assert obj.ra_j2000_hours == 5.588
    assert obj.dec_j2000_degrees == -5.391
    assert obj.constellation == "Ori"


def test_stellarium_object_below_horizon():
    obj = StellariumObject(
        name="Canopus",
        object_type="star",
        ra_j2000_hours=6.399,
        dec_j2000_degrees=-52.696,
        altitude=-10.0,
        azimuth=180.0,
        magnitude=-0.74,
        above_horizon=False,
        constellation="Car",
        rise="",
        set_time="",
    )
    assert obj.above_horizon is False


# --- StellariumClient construction ---

def test_client_default_construction():
    client = StellariumClient()
    assert client.base_url == "http://localhost:8091"
    assert client.timeout == 5


def test_client_custom_construction():
    client = StellariumClient(host="192.168.1.100", port=9091, timeout=10)
    assert client.base_url == "http://192.168.1.100:9091"
    assert client.timeout == 10


# --- Mocked HTTP tests ---

def test_is_available_true():
    client = StellariumClient()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    with patch.object(client.session, "get", return_value=mock_resp):
        assert client.is_available() is True


def test_is_available_false():
    client = StellariumClient()
    import requests
    with patch.object(client.session, "get", side_effect=requests.exceptions.ConnectionError()):
        assert client.is_available() is False


def test_get_selected_object():
    client = StellariumClient()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = '{"name": "M42"}'
    mock_resp.json.return_value = {
        "name": "M42",
        "object-type": "nebula",
        "raJ2000": 83.82,
        "decJ2000": -5.391,
        "altitude": 45.0,
        "azimuth": 180.0,
        "vmag": 4.0,
        "above-horizon": True,
        "iauConstellation": "Ori",
        "rise": "18h00m",
        "set": "06h00m",
    }
    with patch.object(client.session, "get", return_value=mock_resp):
        obj = client.get_selected_object()
        assert obj is not None
        assert obj.name == "M42"
        assert abs(obj.ra_j2000_hours - 83.82 / 15.0) < 0.001
        assert obj.dec_j2000_degrees == -5.391
        assert obj.above_horizon is True


def test_get_selected_object_negative_ra():
    """Stellarium returns negative RA for some objects - must add 360."""
    client = StellariumClient()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = '{"name": "Moon"}'
    mock_resp.json.return_value = {
        "name": "Moon",
        "object-type": "moon",
        "raJ2000": -132.6275,
        "decJ2000": -23.7602,
        "altitude": 14.65,
        "azimuth": 223.1,
        "vmag": -10.10,
        "above-horizon": True,
        "iauConstellation": "Lib",
        "rise": "1h24m",
        "set": "11h10m",
    }
    with patch.object(client.session, "get", return_value=mock_resp):
        obj = client.get_selected_object()
        assert obj is not None
        expected_ra = (360 - 132.6275) / 15.0
        assert abs(obj.ra_j2000_hours - expected_ra) < 0.001


def test_get_selected_object_no_selection():
    client = StellariumClient()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "no current selection"
    with patch.object(client.session, "get", return_value=mock_resp):
        obj = client.get_selected_object()
        assert obj is None


def test_get_selected_object_error():
    client = StellariumClient()
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    with patch.object(client.session, "get", return_value=mock_resp):
        obj = client.get_selected_object()
        assert obj is None


def test_lookup_object():
    client = StellariumClient()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = '{"name": "Jupiter"}'
    mock_resp.json.return_value = {
        "name": "Jupiter",
        "object-type": "planet",
        "raJ2000": 50.0,
        "decJ2000": 18.5,
        "altitude": 60.0,
        "azimuth": 200.0,
        "vmag": -2.5,
        "above-horizon": True,
        "iauConstellation": "Ari",
        "rise": "15h00m",
        "set": "03h00m",
    }
    with patch.object(client.session, "get", return_value=mock_resp):
        obj = client.lookup_object("Jupiter")
        assert obj is not None
        assert obj.name == "Jupiter"
        assert abs(obj.ra_j2000_hours - 50.0 / 15.0) < 0.001


def test_lookup_object_not_found():
    client = StellariumClient()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "not found"
    with patch.object(client.session, "get", return_value=mock_resp):
        obj = client.lookup_object("FakeObject999")
        assert obj is None
