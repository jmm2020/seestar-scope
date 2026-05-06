"""Tests for star catalog lookups."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from catalog.messier import (
    lookup_messier,
    search_catalog,
    get_all_objects,
    get_objects_by_type,
    MESSIER_CATALOG,
)


def test_messier_catalog_completeness():
    """All 110 Messier objects present."""
    assert len(MESSIER_CATALOG) == 110


def test_lookup_messier_m42():
    result = lookup_messier("M42")
    assert result is not None
    assert result["common_name"] == "Orion Nebula"
    assert abs(result["ra_hours"] - 5.588) < 0.01
    assert result["object_type"] == "Diffuse Nebula"


def test_lookup_messier_case_insensitive():
    result = lookup_messier("m42")
    assert result is not None
    assert result["common_name"] == "Orion Nebula"


def test_lookup_messier_space_tolerant():
    result = lookup_messier("M 42")
    assert result is not None
    assert result["common_name"] == "Orion Nebula"


def test_lookup_messier_not_found():
    assert lookup_messier("M999") is None


def test_lookup_messier_invalid():
    assert lookup_messier("NGC7000") is None


def test_lookup_messier_m31():
    result = lookup_messier("M31")
    assert result is not None
    assert result["common_name"] == "Andromeda Galaxy"
    assert result["object_type"] == "Galaxy"


def test_lookup_messier_m1():
    result = lookup_messier("M1")
    assert result is not None
    assert result["common_name"] == "Crab Nebula"


def test_search_catalog_by_name():
    results = search_catalog("Orion")
    assert len(results) >= 1
    names = [r["common_name"] for r in results]
    assert "Orion Nebula" in names


def test_search_catalog_by_type():
    results = search_catalog("Planetary Nebula")
    assert len(results) >= 3  # M27, M57, M76, M97


def test_get_all_objects():
    objects = get_all_objects()
    assert len(objects) == 110


def test_get_objects_by_type_galaxy():
    galaxies = get_objects_by_type("Galaxy")
    assert len(galaxies) > 20  # Many galaxies in Messier catalog


def test_get_objects_by_type_case_insensitive():
    results = get_objects_by_type("globular")
    assert len(results) > 10
