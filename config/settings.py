"""
Application settings with Pydantic v2
"""
import os
from typing import List, Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Application settings"""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # Application
    app_name: str = "DealerScope"
    app_version: str = "4.8.0"
    debug: bool = False
    environment: str = "production"
    
    # Security
    secret_key: str = "development-secret-key-change-in-production-32chars"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    
    # Database
    database_url: str = "postgresql://dealerscope:dealerscope@localhost:5432/dealerscope"
    database_pool_size: int = 10
    database_max_overflow: int = 20
    database_pool_timeout: int = 30
    
    # Redis
    redis_url: str = "redis://localhost:6379/0"
    
    # Rate limiting
    rate_limit_requests: int = 100
    rate_limit_window_seconds: int = 60
    
    # File upload
    max_upload_size: int = 50 * 1024 * 1024  # 50MB
    allowed_file_types: List[str] = ["text/csv", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"]
    
    # ML/AI
    ml_enabled: bool = True
    ml_model_path: str = "./models"
    ml_prediction_timeout: int = 30
    
    # External APIs
    manheim_api_key: Optional[str] = None
    geocoding_api_key: Optional[str] = None
    
    # Scraping
    scraping_enabled: bool = True
    scraping_rate_limit: int = 3  # seconds between requests
    scraping_max_pages: int = 50
    scraping_timeout: int = 30
    
    # Monitoring
    sentry_dsn: Optional[str] = None
    prometheus_enabled: bool = True
    
    # Email (for notifications)
    smtp_server: Optional[str] = None
    smtp_port: int = 587
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    
    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        allowed = ["development", "testing", "staging", "production"]
        if v.lower() not in allowed:
            raise ValueError(f"Environment must be one of: {allowed}")
        return v.lower()
    
    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not v:
            raise ValueError("Database URL is required")
        return v
    
    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("Secret key must be at least 32 characters long")
        
        # Additional security checks for production
        if v == "CHANGE_ME_IN_PRODUCTION":
            import os
            env = os.getenv("ENVIRONMENT", "development").lower()
            if env in ("production", "staging"):
                raise ValueError("Secret key must be changed in production/staging environments")
        
        # Check for common weak patterns
        weak_patterns = ["password", "secret", "key", "123", "abc", "test"]
        if any(pattern in v.lower() for pattern in weak_patterns):
            import warnings
            warnings.warn("Secret key contains common patterns - consider using a more secure key")
        
        return v
    
    @property
    def is_development(self) -> bool:
        return self.environment == "development"
    
    @property
    def is_production(self) -> bool:
        return self.environment == "production"
    
    @property
    def is_testing(self) -> bool:
        return self.environment == "testing"

# Global settings instance
settings = Settings()

# Enhanced settings validation on startup
def validate_settings_on_startup():
    """Comprehensive settings validation with detailed error reporting"""
    try:
        from .environment_validator import validate_environment
        
        # Run comprehensive validation
        validation_result = validate_environment()
        
        if not validation_result['valid']:
            error_msg = "Configuration validation failed:\n"
            for error in validation_result['errors']:
                error_msg += f"  ❌ {error}\n"
            
            if validation_result['warnings']:
                error_msg += "Warnings:\n"
                for warning in validation_result['warnings']:
                    error_msg += f"  ⚠️  {warning}\n"
            
            if settings.is_production:
                raise ValueError(error_msg)
            else:
                print(f"⚠️  {error_msg}")
        
        # Create required directories
        if settings.ml_enabled and not os.path.exists(settings.ml_model_path):
            try:
                os.makedirs(settings.ml_model_path, exist_ok=True)
            except (OSError, PermissionError) as e:
                error_msg = f"Cannot create ML model directory '{settings.ml_model_path}': {e}"
                if settings.is_production:
                    raise ValueError(error_msg)
                else:
                    print(f"⚠️  {error_msg}")
        
        # Log successful validation
        if validation_result['valid'] and not validation_result['warnings']:
            print("✅ Configuration validation passed")
        elif validation_result['valid']:
            print(f"✅ Configuration valid with {len(validation_result['warnings'])} warnings")
            
    except ImportError:
        # Fallback to basic validation if environment_validator is not available
        validation_errors = []
        
        if settings.is_production and settings.secret_key == "CHANGE_ME_IN_PRODUCTION":
            validation_errors.append("Secret key must be changed in production")
        
        if settings.ml_enabled and not os.path.exists(settings.ml_model_path):
            os.makedirs(settings.ml_model_path, exist_ok=True)
        
        if validation_errors:
            raise ValueError(f"Configuration errors: {validation_errors}")
            
    except Exception as e:
        print(f"Settings validation failed: {e}")
        if settings.is_production:
            raise

# Run validation on import
validate_settings_on_startup()