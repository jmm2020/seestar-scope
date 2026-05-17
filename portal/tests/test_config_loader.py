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


def test_alp_port_primary_takes_precedence_over_legacy(tmp_path, monkeypatch):
    monkeypatch.setenv("ALP_PORT", "6000")
    monkeypatch.setenv("SEESTAR_ALP_PORT", "9999")
    cfg = load_config(tmp_path / "nonexistent.toml")
    assert cfg.seestar_alp_port == 6000


def test_alp_img_port_primary_takes_precedence_over_legacy(tmp_path, monkeypatch):
    monkeypatch.setenv("ALP_IMG_PORT", "8888")
    monkeypatch.setenv("SEESTAR_IMG_PORT", "7557")
    cfg = load_config(tmp_path / "nonexistent.toml")
    assert cfg.seestar_img_port == 8888


def test_alp_properties_from_toml(tmp_path, monkeypatch):
    for var in (
        "ALP_HOST",
        "SEESTAR_ALP_HOST",
        "ALP_PORT",
        "SEESTAR_ALP_PORT",
        "ALP_IMG_PORT",
        "SEESTAR_IMG_PORT",
    ):
        monkeypatch.delenv(var, raising=False)
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('[seestar]\nalp_host = "my-scope-host"\nalp_port = 6000\nimg_port = 7001\n')
    cfg = load_config(cfg_file)
    assert cfg.seestar_alp_host == "my-scope-host"
    assert cfg.seestar_alp_port == 6000
    assert cfg.seestar_img_port == 7001


# --- Auth + billing env-var tests (issue #59) ---


def test_supabase_url_raises_when_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    cfg = load_config(tmp_path / "nonexistent.toml")
    with pytest.raises(ValueError, match="SUPABASE_URL"):
        _ = cfg.supabase_url


def test_supabase_url_returns_env_value(tmp_path, monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://abcxyz.supabase.co")
    cfg = load_config(tmp_path / "nonexistent.toml")
    assert cfg.supabase_url == "https://abcxyz.supabase.co"


def test_supabase_anon_key_raises_when_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    cfg = load_config(tmp_path / "nonexistent.toml")
    with pytest.raises(ValueError, match="SUPABASE_ANON_KEY"):
        _ = cfg.supabase_anon_key


def test_supabase_anon_key_returns_env_value(tmp_path, monkeypatch):
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-test-value")
    cfg = load_config(tmp_path / "nonexistent.toml")
    assert cfg.supabase_anon_key == "anon-test-value"


def test_supabase_service_role_key_raises_when_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    cfg = load_config(tmp_path / "nonexistent.toml")
    with pytest.raises(ValueError, match="SUPABASE_SERVICE_ROLE_KEY"):
        _ = cfg.supabase_service_role_key


def test_supabase_service_role_key_returns_env_value(tmp_path, monkeypatch):
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-test-value")
    cfg = load_config(tmp_path / "nonexistent.toml")
    assert cfg.supabase_service_role_key == "service-role-test-value"


def test_supabase_jwt_secret_raises_when_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    cfg = load_config(tmp_path / "nonexistent.toml")
    with pytest.raises(ValueError, match="SUPABASE_JWT_SECRET"):
        _ = cfg.supabase_jwt_secret


def test_supabase_jwt_secret_returns_env_value(tmp_path, monkeypatch):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "jwt-secret-test-value")
    cfg = load_config(tmp_path / "nonexistent.toml")
    assert cfg.supabase_jwt_secret == "jwt-secret-test-value"


def test_stripe_secret_key_raises_when_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    cfg = load_config(tmp_path / "nonexistent.toml")
    with pytest.raises(ValueError, match="STRIPE_SECRET_KEY"):
        _ = cfg.stripe_secret_key


def test_stripe_secret_key_returns_env_value(tmp_path, monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_abc123")
    cfg = load_config(tmp_path / "nonexistent.toml")
    assert cfg.stripe_secret_key == "sk_test_abc123"


def test_stripe_webhook_secret_raises_when_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    cfg = load_config(tmp_path / "nonexistent.toml")
    with pytest.raises(ValueError, match="STRIPE_WEBHOOK_SECRET"):
        _ = cfg.stripe_webhook_secret


def test_stripe_webhook_secret_returns_env_value(tmp_path, monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_abc123")
    cfg = load_config(tmp_path / "nonexistent.toml")
    assert cfg.stripe_webhook_secret == "whsec_abc123"


def test_stripe_watch_price_id_returns_none_when_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("STRIPE_WATCH_PRICE_ID", raising=False)
    cfg = load_config(tmp_path / "nonexistent.toml")
    assert cfg.stripe_watch_price_id is None


def test_stripe_watch_price_id_returns_env_value(tmp_path, monkeypatch):
    monkeypatch.setenv("STRIPE_WATCH_PRICE_ID", "price_abc")
    cfg = load_config(tmp_path / "nonexistent.toml")
    assert cfg.stripe_watch_price_id == "price_abc"


def test_stripe_control_price_id_returns_none_when_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("STRIPE_CONTROL_PRICE_ID", raising=False)
    cfg = load_config(tmp_path / "nonexistent.toml")
    assert cfg.stripe_control_price_id is None


def test_stripe_control_price_id_returns_env_value(tmp_path, monkeypatch):
    monkeypatch.setenv("STRIPE_CONTROL_PRICE_ID", "price_xyz")
    cfg = load_config(tmp_path / "nonexistent.toml")
    assert cfg.stripe_control_price_id == "price_xyz"
