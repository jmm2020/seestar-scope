"""Backend configuration"""

from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Backend settings"""

    # App
    app_name: str = "SeestarScope Backend"
    debug: bool = True
    port: int = 8503

    # Seestar telescope
    seestar_ip: str = "192.168.0.132"
    seestar_port: int = 32323
    auto_connect: bool = True

    # Stellarium
    stellarium_host: str = "localhost"
    stellarium_port: int = 8090

    # Observing site (lat/lon/elevation for astronomy + weather)
    site_latitude: float = 37.12
    site_longitude: float = -123.45
    site_elevation_m: float = 0.0
    site_name: str = "My Observatory"

    # Storage paths (relative to backend/)
    data_dir: Path = Path("../data")
    captures_dir: Path = data_dir / "captures"
    gallery_dir: Path = data_dir / "gallery"
    processing_dir: Path = data_dir / "processing"
    calibration_dir: Path = data_dir / "calibration"

    # Siril
    siril_cli_path: str = "siril-cli"

    # Auth + Billing (Phase 5a)
    supabase_url: str | None = None                        # URL, not a secret
    supabase_anon_key: SecretStr | None = None
    supabase_service_role_key: SecretStr | None = None
    supabase_jwt_secret: SecretStr | None = None
    stripe_secret_key: SecretStr | None = None
    stripe_webhook_secret: SecretStr | None = None
    stripe_watch_price_id: str | None = None               # price ID, not a secret
    stripe_control_price_id: str | None = None

    class Config:
        env_file = ".env"


settings = Settings()

# Ensure directories exist
settings.captures_dir.mkdir(parents=True, exist_ok=True)
settings.gallery_dir.mkdir(parents=True, exist_ok=True)
settings.processing_dir.mkdir(parents=True, exist_ok=True)
settings.calibration_dir.mkdir(parents=True, exist_ok=True)
