"""Tests for config_loader.py — site properties, env-var overrides, missing-file fallback."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from config_loader import load_config  # noqa: E402


def test_site_defaults_from_toml(tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        '[site]\nlatitude = 51.5\nlongitude = -0.1\nelevation_m = 10.0\nname = "London"\n'
    )
    cfg = load_config(cfg_file)
    assert cfg.site_latitude == 51.5
    assert cfg.site_longitude == -0.1
    assert cfg.site_elevation_m == 10.0
    assert cfg.site_name == "London"


def test_site_env_overrides_toml(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('[site]\nlatitude = 51.5\nlongitude = -0.1\n')
    monkeypatch.setenv("SITE_LAT", "34.05")
    monkeypatch.setenv("SITE_LON", "-118.25")
    monkeypatch.setenv("SITE_NAME", "LA Observatory")
    cfg = load_config(cfg_file)
    assert cfg.site_latitude == pytest.approx(34.05)
    assert cfg.site_longitude == pytest.approx(-118.25)
    assert cfg.site_name == "LA Observatory"


def test_site_elevation_env_override(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('[site]\nelevation_m = 100.0\n')
    monkeypatch.setenv("SITE_ELEVATION_M", "250.5")
    cfg = load_config(cfg_file)
    assert cfg.site_elevation_m == pytest.approx(250.5)


def test_load_config_missing_file_returns_defaults(tmp_path):
    cfg = load_config(tmp_path / "nonexistent.toml")
    assert cfg.site_latitude == pytest.approx(37.12)
    assert cfg.site_name == "My Observatory"
    assert cfg.site_elevation_m == pytest.approx(0.0)
