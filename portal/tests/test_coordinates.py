"""Tests for coordinate conversion and formatting utilities."""

import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.coordinates import (
    ra_degrees_to_hours,
    ra_hours_to_degrees,
    format_ra,
    format_dec,
    parse_ra,
    parse_dec,
    hours_to_hms,
    degrees_to_dms,
)


def test_ra_degrees_to_hours_positive():
    assert abs(ra_degrees_to_hours(180.0) - 12.0) < 0.001


def test_ra_degrees_to_hours_zero():
    assert abs(ra_degrees_to_hours(0.0) - 0.0) < 0.001


def test_ra_degrees_to_hours_negative():
    """Stellarium Moon test case: raJ2000=-132.6275 -> should add 360 first."""
    result = ra_degrees_to_hours(-132.6275)
    expected = (360 - 132.6275) / 15.0  # 15.158...
    assert abs(result - expected) < 0.01


def test_ra_degrees_to_hours_full_circle():
    assert abs(ra_degrees_to_hours(360.0) - 24.0) < 0.001


def test_ra_hours_to_degrees():
    assert abs(ra_hours_to_degrees(12.0) - 180.0) < 0.001


def test_hours_to_hms():
    h, m, s = hours_to_hms(7.620278)
    assert h == 7
    assert m == 37
    assert abs(s - 13.0) < 0.2


def test_degrees_to_dms_positive():
    d, m, s, sign = degrees_to_dms(45.0)
    assert sign == "+"
    assert d == 45
    assert m == 0
    assert abs(s - 0.0) < 0.1


def test_degrees_to_dms_negative():
    d, m, s, sign = degrees_to_dms(-23.76)
    assert sign == "-"
    assert d == 23
    assert m == 45
    assert abs(s - 36.0) < 0.1


def test_format_ra():
    assert format_ra(12.0) == "12h 00m 00.0s"


def test_format_ra_complex():
    result = format_ra(7.620278)
    assert result.startswith("7h 37m")


def test_format_dec_positive():
    result = format_dec(45.0)
    assert result.startswith("+45")


def test_format_dec_negative():
    result = format_dec(-23.76)
    assert result.startswith("-23")
    assert "45'" in result


def test_parse_ra_hms():
    result = parse_ra("7h 37m 13.0s")
    assert abs(result - 7.6203) < 0.01


def test_parse_ra_colon():
    result = parse_ra("12:00:00")
    assert abs(result - 12.0) < 0.001


def test_parse_ra_decimal():
    result = parse_ra("5.588")
    assert abs(result - 5.588) < 0.001


def test_parse_dec_colon():
    result = parse_dec("-23:45:36.0")
    assert abs(result - (-23.76)) < 0.01


def test_parse_dec_decimal():
    result = parse_dec("-5.391")
    assert abs(result - (-5.391)) < 0.001
