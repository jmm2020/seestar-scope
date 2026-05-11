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
    cfg_file.write_text("[site]\nlatitude = 51.5\nlongitude = -0.1\n")
    monkeypatch.setenv("SITE_LAT", "34.05")
    monkeypatch.setenv("SITE_LON", "-118.25")
    monkeypatch.setenv("SITE_NAME", "LA Observatory")
    cfg = load_config(cfg_file)
    assert cfg.site_latitude == pytest.approx(34.05)
    assert cfg.site_longitude == pytest.approx(-118.25)
    assert cfg.site_name == "LA Observatory"


def test_site_elevation_env_override(tmp_path, monkeypatch):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text("[site]\nelevation_m = 100.0\n")
    monkeypatch.setenv("SITE_ELEVATION_M", "250.5")
    cfg = load_config(cfg_file)
    assert cfg.site_elevation_m == pytest.approx(250.5)


def test_load_config_missing_file_returns_defaults(tmp_path):
    cfg = load_config(tmp_path / "nonexistent.toml")
    assert cfg.site_latitude == pytest.approx(37.12)
    assert cfg.site_name == "My Observatory"
    assert cfg.site_elevation_m == pytest.approx(0.0)


# --- ALP env-var resolution tests (issue #35) ---


def test_alp_host_primary_env(tmp_path, monkeypatch):
    monkeypatch.setenv("ALP_HOST", "seestar-alp")
    monkeypatch.delenv("SEESTAR_ALP_HOST", raising=False)
    cfg = load_config(tmp_path / "nonexistent.toml")
    assert cfg.seestar_alp_host == "seestar-alp"


def test_alp_host_legacy_env_fallback(tmp_path, monkeypatch):
    monkeypatch.delenv("ALP_HOST", raising=False)
    monkeypatch.setenv("SEESTAR_ALP_HOST", "legacy-host")
    cfg = load_config(tmp_path / "nonexistent.toml")
    assert cfg.seestar_alp_host == "legacy-host"


def test_alp_host_primary_takes_precedence_over_legacy(tmp_path, monkeypatch):
    monkeypatch.setenv("ALP_HOST", "primary-host")
    monkeypatch.setenv("SEESTAR_ALP_HOST", "legacy-host")
    cfg = load_config(tmp_path / "nonexistent.toml")
    assert cfg.seestar_alp_host == "primary-host"


def test_alp_host_default_when_no_env(tmp_path, monkeypatch):
    monkeypatch.delenv("ALP_HOST", raising=False)
    monkeypatch.delenv("SEESTAR_ALP_HOST", raising=False)
    cfg = load_config(tmp_path / "nonexistent.toml")
    assert cfg.seestar_alp_host == "localhost"


def test_alp_port_primary_env(tmp_path, monkeypatch):
    monkeypatch.setenv("ALP_PORT", "5556")
    monkeypatch.delenv("SEESTAR_ALP_PORT", raising=False)
    cfg = load_config(tmp_path / "nonexistent.toml")
    assert cfg.seestar_alp_port == 5556


def test_alp_port_legacy_env_fallback(tmp_path, monkeypatch):
    monkeypatch.delenv("ALP_PORT", raising=False)
    monkeypatch.setenv("SEESTAR_ALP_PORT", "9999")
    cfg = load_config(tmp_path / "nonexistent.toml")
    assert cfg.seestar_alp_port == 9999


def test_alp_port_default_when_no_env(tmp_path, monkeypatch):
    monkeypatch.delenv("ALP_PORT", raising=False)
    monkeypatch.delenv("SEESTAR_ALP_PORT", raising=False)
    cfg = load_config(tmp_path / "nonexistent.toml")
    assert cfg.seestar_alp_port == 5555


def test_alp_img_port_primary_env(tmp_path, monkeypatch):
    monkeypatch.setenv("ALP_IMG_PORT", "8000")
    monkeypatch.delenv("SEESTAR_IMG_PORT", raising=False)
    cfg = load_config(tmp_path / "nonexistent.toml")
    assert cfg.seestar_img_port == 8000


def test_alp_img_port_legacy_env_fallback(tmp_path, monkeypatch):
    monkeypatch.delenv("ALP_IMG_PORT", raising=False)
    monkeypatch.setenv("SEESTAR_IMG_PORT", "7557")
    cfg = load_config(tmp_path / "nonexistent.toml")
    assert cfg.seestar_img_port == 7557


def test_alp_img_port_default_when_no_env(tmp_path, monkeypatch):
    monkeypatch.delenv("ALP_IMG_PORT", raising=False)
    monkeypatch.delenv("SEESTAR_IMG_PORT", raising=False)
    cfg = load_config(tmp_path / "nonexistent.toml")
    assert cfg.seestar_img_port == 7556
