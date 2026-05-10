"""Tests for pure-function utilities in views/conditions.py."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from views.conditions import _twilight_label, _moon_phase_label  # noqa: E402


@pytest.mark.parametrize(
    "astro,expected_label",
    [
        (
            {
                "is_astronomical_night": True,
                "is_nautical_twilight": False,
                "is_civil_twilight": False,
                "sun_altitude_deg": -20.0,
            },
            "Astronomical Night",
        ),
        (
            {
                "is_astronomical_night": False,
                "is_nautical_twilight": True,
                "is_civil_twilight": False,
                "sun_altitude_deg": -15.0,
            },
            "Nautical Twilight",
        ),
        (
            {
                "is_astronomical_night": False,
                "is_nautical_twilight": False,
                "is_civil_twilight": True,
                "sun_altitude_deg": -8.0,
            },
            "Civil Twilight",
        ),
        (
            {
                "is_astronomical_night": False,
                "is_nautical_twilight": False,
                "is_civil_twilight": False,
                "sun_altitude_deg": 5.0,
            },
            "Daytime",
        ),
        (
            {
                "is_astronomical_night": False,
                "is_nautical_twilight": False,
                "is_civil_twilight": False,
                "sun_altitude_deg": -4.0,
            },
            "Pre-dark",
        ),
    ],
)
def test_twilight_label(astro, expected_label):
    label, color = _twilight_label(astro)
    assert label == expected_label
    assert color.startswith("#")


@pytest.mark.parametrize(
    "pct,expected",
    [
        (0, "New Moon"),
        (4.9, "New Moon"),
        (5.0, "Crescent"),
        (39.9, "Crescent"),
        (40.0, "Quarter"),
        (59.9, "Quarter"),
        (60.0, "Gibbous"),
        (94.9, "Gibbous"),
        (95.0, "Full Moon"),
        (100.0, "Full Moon"),
    ],
)
def test_moon_phase_label(pct, expected):
    assert _moon_phase_label(pct) == expected
