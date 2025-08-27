"""
Enhanced environment validation and configuration management
Provides comprehensive validation for production deployments
"""
import os
import re
import secrets
from typing import List, Dict, Any, Optional
from pathlib import Path


class EnvironmentValidator:
    """Validates environment configuration for security and completeness"""
    
    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.environment = os.getenv("ENVIRONMENT", "development").lower()
    
    def validate_all(self) -> Dict[str, Any]:
        """Run comprehensive environment validation"""
        self.validate_security_settings()
        self.validate_database_config()
        self.validate_redis_config()
        self.validate_file_paths()
        self.validate_api_keys()
        
        return {
            "valid": len(self.errors) == 0,
            "errors": self.errors,
            "warnings": self.warnings,
            "environment": self.environment
        }
    
    def validate_security_settings(self):
        """Validate security-related environment variables"""
        secret_key = os.getenv("SECRET_KEY", "")
        
        # Secret key validation
        if not secret_key or secret_key == "CHANGE_ME_IN_PRODUCTION":
            if self.environment in ("production", "staging"):
                self.errors.append("SECRET_KEY must be set to a secure value in production")
            else:
                self.warnings.append("SECRET_KEY should be set to a secure value")
        elif len(secret_key) < 32:
            self.errors.append("SECRET_KEY must be at least 32 characters long")
        
        # Algorithm validation
        algorithm = os.getenv("ALGORITHM", "HS256")
        if algorithm not in ("HS256", "RS256", "ES256"):
            self.warnings.append(f"Algorithm '{algorithm}' may not be secure")
        
        # Token expiration validation
        try:
            access_expire = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
            if access_expire > 60 and self.environment == "production":
                self.warnings.append("Access token expiration > 60 minutes may be insecure")
        except ValueError:
            self.errors.append("ACCESS_TOKEN_EXPIRE_MINUTES must be a valid integer")
    
    def validate_database_config(self):
        """Validate database configuration"""
        db_url = os.getenv("DATABASE_URL", "")
        
        if not db_url:
            self.errors.append("DATABASE_URL is required")
            return
        
        # Check for localhost in production
        if self.environment == "production" and "localhost" in db_url:
            self.warnings.append("Using localhost database in production may not be intended")
        
        # Check for default credentials
        if "dealerscope:dealerscope" in db_url and self.environment == "production":
            self.errors.append("Default database credentials detected in production")
        
        # Pool size validation
        try:
            pool_size = int(os.getenv("DATABASE_POOL_SIZE", "10"))
            if pool_size < 5:
                self.warnings.append("Database pool size < 5 may cause performance issues")
            elif pool_size > 50:
                self.warnings.append("Database pool size > 50 may cause resource issues")
        except ValueError:
            self.errors.append("DATABASE_POOL_SIZE must be a valid integer")
    
    def validate_redis_config(self):
        """Validate Redis configuration"""
        redis_url = os.getenv("REDIS_URL", "")
        
        if not redis_url:
            self.warnings.append("REDIS_URL not set - caching will be disabled")
            return
        
        # Check for localhost in production
        if self.environment == "production" and "localhost" in redis_url:
            self.warnings.append("Using localhost Redis in production may not be intended")
    
    def validate_file_paths(self):
        """Validate file system paths"""
        ml_model_path = os.getenv("ML_MODEL_PATH", "./models")
        
        # Check if ML model path exists or can be created
        try:
            Path(ml_model_path).mkdir(parents=True, exist_ok=True)
        except (OSError, PermissionError) as e:
            self.errors.append(f"Cannot create ML model path '{ml_model_path}': {e}")
        
        # Check upload size limits
        try:
            max_upload = int(os.getenv("MAX_UPLOAD_SIZE", str(50 * 1024 * 1024)))
            if max_upload > 100 * 1024 * 1024:  # 100MB
                self.warnings.append("MAX_UPLOAD_SIZE > 100MB may cause memory issues")
        except ValueError:
            self.errors.append("MAX_UPLOAD_SIZE must be a valid integer")
    
    def validate_api_keys(self):
        """Validate external API keys"""
        api_keys = {
            "MANHEIM_API_KEY": "Manheim API integration",
            "GEOCODING_API_KEY": "Geocoding services"
        }
        
        for key, service in api_keys.items():
            value = os.getenv(key)
            if value and len(value) < 16:
                self.warnings.append(f"{key} for {service} appears to be too short")
    
    def generate_secure_secret(self, length: int = 64) -> str:
        """Generate a cryptographically secure secret key"""
        return secrets.token_urlsafe(length)
    
    def suggest_improvements(self) -> List[str]:
        """Suggest configuration improvements"""
        suggestions = []
        
        if self.environment == "production":
            suggestions.extend([
                "Use environment variables for all secrets",
                "Enable database SSL connections",
                "Set up monitoring for configuration changes",
                "Implement secret rotation policies",
                "Use a dedicated secret management service"
            ])
        
        if not os.getenv("SENTRY_DSN"):
            suggestions.append("Configure Sentry DSN for error tracking")
        
        if not os.getenv("SMTP_SERVER"):
            suggestions.append("Configure SMTP settings for notifications")
        
        return suggestions


def validate_environment() -> Dict[str, Any]:
    """Convenience function to validate current environment"""
    validator = EnvironmentValidator()
    return validator.validate_all()


def print_validation_report():
    """Print a formatted validation report"""
    result = validate_environment()
    
    print(f"\n🔍 Environment Validation Report")
    print(f"Environment: {result['environment'].upper()}")
    print("=" * 50)
    
    if result['errors']:
        print(f"\n❌ ERRORS ({len(result['errors'])}):")
        for error in result['errors']:
            print(f"  • {error}")
    
    if result['warnings']:
        print(f"\n⚠️  WARNINGS ({len(result['warnings'])}):")
        for warning in result['warnings']:
            print(f"  • {warning}")
    
    if result['valid'] and not result['warnings']:
        print(f"\n✅ All validations passed!")
    elif result['valid']:
        print(f"\n✅ Configuration is valid (with warnings)")
    else:
        print(f"\n❌ Configuration has errors that must be resolved")
    
    # Suggestions
    validator = EnvironmentValidator()
    suggestions = validator.suggest_improvements()
    if suggestions:
        print(f"\n💡 SUGGESTIONS:")
        for suggestion in suggestions:
            print(f"  • {suggestion}")
    
    print()
    return result['valid']


if __name__ == "__main__":
    import sys
    is_valid = print_validation_report()
    sys.exit(0 if is_valid else 1)