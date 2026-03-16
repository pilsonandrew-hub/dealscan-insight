"""
Application settings — Railway-safe, robust defaults
"""
import logging
import os
from typing import Optional, Any
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-in-prod")


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
    secret_key: str = SECRET_KEY
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
    rate_limit_ingest_requests: int = 10
    rate_limit_ingest_window_seconds: int = 60
    rate_limit_trust_proxy_headers: bool = False
    rate_limit_trusted_proxy_cidrs: str = "127.0.0.1/32,::1/128"

    # File upload
    max_upload_size: int = 50 * 1024 * 1024

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
if settings.secret_key == "dev-secret-change-in-prod" and settings.is_production:
    logger.critical(
        "SECRET_KEY is not set; using development fallback in production. "
        "Set SECRET_KEY immediately."
    )
