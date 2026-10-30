"""Configuration loader and schema validation."""

from pathlib import Path
from typing import Any, List as TList

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseModel):
    name: str = "google-maps-hotel-scraper"
    environment: str = "development"
    data_dir: str = "data"
    snapshots_dir: str = "snapshots"
    export_dir: str = "data/exports"


class DatabaseConfig(BaseModel):
    url: str = "sqlite+aiosqlite:///data/hotels.db"
    echo_sql: bool = False


class AntiBotConfig(BaseModel):
    rotate_user_agents: bool = True
    detect_captcha: bool = True
    captcha_cooldown_sec: int = 180
    max_retries: int = 3
    backoff_multiplier: float = 2.0


class ProxyConfig(BaseModel):
    enabled: bool = False
    rotation_strategy: str = "round_robin"
    list: TList[str] = Field(default_factory=list)


class ViewportConfig(BaseModel):
    width: int = 1440
    height: int = 900


class ScraperConfig(BaseModel):
    concurrency: int = 2
    headless: bool = True
    timeout_ms: int = 30000
    slow_mo_ms: int = 50
    min_delay_sec: float = 2.0
    max_delay_sec: float = 4.5
    viewport: ViewportConfig = Field(default_factory=ViewportConfig)
    locale: str = "en-US"
    timezone_id: str = "UTC"
    user_data_dir: str = "data/browser_context"
    anti_bot: AntiBotConfig = Field(default_factory=AntiBotConfig)
    proxies: ProxyConfig = Field(default_factory=ProxyConfig)


class BoundingBoxConfig(BaseModel):
    min_lat: float
    max_lat: float
    min_lng: float
    max_lng: float


class RegionConfig(BaseModel):
    name: str
    country: str
    query_template: str = "hotels in {area}"
    strategy: str = "grid"  # "grid" or "neighborhoods"
    bbox: BoundingBoxConfig | None = None
    grid_step_km: float = 4.0
    neighborhoods: list[str] = Field(default_factory=list)


class GooglePlacesApiConfig(BaseModel):
    api_key_env_var: str = "GOOGLE_PLACES_API_KEY"
    language_code: str = "en"


class ProvidersConfig(BaseModel):
    active: str = "google_maps_playwright"
    google_places_api: GooglePlacesApiConfig = Field(
        default_factory=GooglePlacesApiConfig
    )


class Settings(BaseSettings):
    """Unified application settings loaded from YAML and overridden by ENV."""

    app: AppConfig = Field(default_factory=AppConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    scraper: ScraperConfig = Field(default_factory=ScraperConfig)
    regions: list[RegionConfig] = Field(default_factory=list)

    # Direct ENV overrides
    environment: str | None = None
    log_level: str = "INFO"
    log_json: bool = True
    database_url: str | None = None
    scraper_headless: bool | None = None
    scraper_concurrency: int | None = None
    proxies_enabled: bool | None = None
    proxies_list: str | None = None
    google_places_api_key: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


def load_settings(config_path: str = "config/config.yaml") -> Settings:
    """Load settings from YAML file with environment variable overrides."""
    yaml_data: dict[str, Any] = {}
    cfg_file = Path(config_path)

    if cfg_file.exists():
        with open(cfg_file, "r", encoding="utf-8") as f:
            yaml_data = yaml.safe_load(f) or {}

    settings = Settings(**yaml_data)

    # Apply environment variable overrides if present
    if settings.database_url:
        settings.database.url = settings.database_url
    if settings.scraper_headless is not None:
        settings.scraper.headless = settings.scraper_headless
    if settings.scraper_concurrency is not None:
        settings.scraper.concurrency = settings.scraper_concurrency
    if settings.proxies_enabled is not None:
        settings.scraper.proxies.enabled = settings.proxies_enabled
    if settings.proxies_list:
        settings.scraper.proxies.list = [
            p.strip() for p in settings.proxies_list.split(",") if p.strip()
        ]
    if settings.environment:
        settings.app.environment = settings.environment

    # Ensure required runtime directories exist
    Path(settings.app.data_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.app.snapshots_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.app.export_dir).mkdir(parents=True, exist_ok=True)

    return settings
