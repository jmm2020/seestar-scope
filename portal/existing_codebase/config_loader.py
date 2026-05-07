"""TOML configuration loader for SeestarScope."""
import os
import toml
from pathlib import Path
from typing import Any


# Default config path relative to project root
DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.toml"


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
    def seestar_ip(self) -> str:
        return os.environ.get("SEESTAR_IP", self.seestar.get("ip_address", "192.168.0.132"))

    @property
    def seestar_port(self) -> int:
        return int(os.environ.get("SEESTAR_PORT", self.seestar.get("alpaca_port", 32323)))

    @property
    def stellarium_host(self) -> str:
        return os.environ.get("STELLARIUM_HOST", self.stellarium.get("host", "localhost"))

    @property
    def stellarium_port(self) -> int:
        return int(os.environ.get("STELLARIUM_PORT", self.stellarium.get("port", 8091)))

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
