"""
Application settings — Railway-safe, robust defaults
"""
import os
import json
from typing import List, Optional, Any
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_list(v: Any) -> Any:
    """Parse list fields — handles JSON array, comma-separated, or empty string."""
    if isinstance(v, list):
        return v
    if not isinstance(v, str) or not v.strip():
        return []
    try:
        parsed = json.loads(v.strip())
        return parsed if isinstance(parsed, list) else [str(parsed)]
    except (json.JSONDecodeError, ValueError):
        return [x.strip() for x in v.split(",") if x.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "DealerScope"
    app_version: str = "5.0.0"
    debug: bool = False
    environment: str = "production"

    # Security
    secret_key: str = "dealerscope-prod-2026-xK9mP2qR8nL4wZ7v"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Database
    database_url: str = ""
    database_pool_size: int = 5
    database_max_overflow: int = 10
    database_pool_timeout: int = 30

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Rate limiting
    rate_limit_requests: int = 100
    rate_limit_window_seconds: int = 60

    # File upload
    max_upload_size: int = 50 * 1024 * 1024
    allowed_file_types: List[str] = ["text/csv", "application/vnd.ms-excel"]

    # ML/AI
    ml_enabled: bool = False
    ml_model_path: str = "./models"
    ml_prediction_timeout: int = 30

    # External APIs
    manheim_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    geocoding_api_key: Optional[str] = None
    sentry_dsn: Optional[str] = None

    # Scraping
    scraping_enabled: bool = True
    scraping_rate_limit: int = 3
    scraping_max_pages: int = 50
    scraping_timeout: int = 30

    # Email
    smtp_server: Optional[str] = None
    smtp_port: int = 587
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None

    # Prometheus
    prometheus_enabled: bool = False

    @field_validator("allowed_file_types", mode="before")
    @classmethod
    def parse_allowed_file_types(cls, v: Any) -> Any:
        return _parse_list(v)

    @field_validator("database_url", mode="before")
    @classmethod
    def parse_database_url(cls, v: Any) -> Any:
        if not v:
            return ""
        return str(v)

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def is_development(self) -> bool:
        return self.environment.lower() == "development"


settings = Settings()
