"""TOML configuration loader for SeestarScope."""

import os
import toml
from pathlib import Path
from typing import Any


# Default config path relative to project root
DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.toml"


def _require_env(var: str) -> str:
    """Return the value of a required environment variable, raising if unset or empty."""
    val = os.environ.get(var)
    if not val:
        raise ValueError(f"{var} is required but not set. Add it to your .env file.")
    return val


class Config:
    """Configuration wrapper with dot-access and defaults."""

    def __init__(self, data: dict):
        self._data = data

    def get(self, key: str, default: Any = None) -> Any:
        """Get a top-level config value."""
        return self._data.get(key, default)

    @property
    def seestar(self) -> dict:
        return self._data.get("seestar", {})

    @property
    def stellarium(self) -> dict:
        return self._data.get("stellarium", {})

    @property
    def ui(self) -> dict:
        return self._data.get("ui", {})

    @property
    def imaging(self) -> dict:
        return self._data.get("imaging", {})

    @property
    def catalog(self) -> dict:
        return self._data.get("catalog", {})

    @property
    def site(self) -> dict:
        return self._data.get("site", {})

    @property
    def seestar_ip(self) -> str:
        return os.environ.get("SEESTAR_IP", self.seestar.get("ip_address", "192.168.0.132"))

    @property
    def seestar_port(self) -> int:
        return int(os.environ.get("SEESTAR_PORT", self.seestar.get("alpaca_port", 32323)))

    @property
    def seestar_alp_host(self) -> str:
        toml_default = self.seestar.get("alp_host", "localhost")
        return os.environ.get("ALP_HOST") or os.environ.get("SEESTAR_ALP_HOST") or toml_default

    @property
    def seestar_alp_port(self) -> int:
        toml_default = self.seestar.get("alp_port", 5555)
        raw = os.environ.get("ALP_PORT") or os.environ.get("SEESTAR_ALP_PORT") or toml_default
        return int(raw)

    @property
    def seestar_img_port(self) -> int:
        toml_default = self.seestar.get("img_port", 7556)
        raw = os.environ.get("ALP_IMG_PORT") or os.environ.get("SEESTAR_IMG_PORT") or toml_default
        return int(raw)

    @property
    def stellarium_host(self) -> str:
        return os.environ.get("STELLARIUM_HOST", self.stellarium.get("host", "localhost"))

    @property
    def stellarium_port(self) -> int:
        return int(os.environ.get("STELLARIUM_PORT", self.stellarium.get("port", 8090)))

    @property
    def auto_connect(self) -> bool:
        return self.seestar.get("auto_connect", True)

    @property
    def ui_port(self) -> int:
        return self.ui.get("port", 8502)

    @property
    def theme(self) -> str:
        return self.ui.get("theme", "dark")

    @property
    def refresh_interval(self) -> int:
        return self.ui.get("refresh_interval_seconds", 2)

    @property
    def default_gain(self) -> int:
        return self.imaging.get("default_gain", 80)

    @property
    def default_exposure(self) -> float:
        return self.imaging.get("default_exposure_seconds", 10)

    @property
    def save_directory(self) -> str:
        return self.imaging.get("save_directory", "./captures")

    @property
    def auto_save(self) -> bool:
        return self.imaging.get("auto_save", False)

    @property
    def use_builtin_catalog(self) -> bool:
        return self.catalog.get("use_builtin", True)

    @property
    def use_stellarium_lookup(self) -> bool:
        return self.catalog.get("use_stellarium_lookup", True)

    @property
    def site_latitude(self) -> float:
        return float(os.environ.get("SITE_LAT", self.site.get("latitude", 37.12)))

    @property
    def site_longitude(self) -> float:
        return float(os.environ.get("SITE_LON", self.site.get("longitude", -123.45)))

    @property
    def site_elevation_m(self) -> float:
        return float(os.environ.get("SITE_ELEVATION_M", self.site.get("elevation_m", 0.0)))

    @property
    def site_name(self) -> str:
        return os.environ.get("SITE_NAME", self.site.get("name", "My Observatory"))

    # Auth + Billing (Phase 5a — Supabase + Stripe).
    # Required secrets raise ValueError on access if unset; optional price IDs return None.

    @property
    def supabase_url(self) -> str:
        return _require_env("SUPABASE_URL")

    @property
    def supabase_anon_key(self) -> str:
        return _require_env("SUPABASE_ANON_KEY")

    @property
    def supabase_service_role_key(self) -> str:
        return _require_env("SUPABASE_SERVICE_ROLE_KEY")

    @property
    def supabase_jwt_secret(self) -> str:
        return _require_env("SUPABASE_JWT_SECRET")

    @property
    def stripe_secret_key(self) -> str:
        return _require_env("STRIPE_SECRET_KEY")

    @property
    def stripe_webhook_secret(self) -> str:
        return _require_env("STRIPE_WEBHOOK_SECRET")

    @property
    def stripe_watch_price_id(self) -> str | None:
        return os.environ.get("STRIPE_WATCH_PRICE_ID") or None

    @property
    def stripe_control_price_id(self) -> str | None:
        return os.environ.get("STRIPE_CONTROL_PRICE_ID") or None


def load_config(path: str | Path | None = None) -> Config:
    """Load configuration from TOML file.

    Args:
        path: Path to config.toml. If None, uses default location.

    Returns:
        Config object with all settings.
    """
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if config_path.exists():
        data = toml.load(config_path)
    else:
        data = {}
    return Config(data)
