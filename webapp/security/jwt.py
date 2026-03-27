"""
JWT token management with refresh token support
"""
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Any
from jose import JWTError, jwt
from config.settings import settings

# Token configuration
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7

def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create access token"""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access"
    })
    
    return jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)

def create_refresh_token(data: Dict[str, Any]) -> str:
    """Create refresh token"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "refresh"
    })
    
    return jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)

def verify_token(token: str, token_type: str = "access") -> Optional[Dict[str, Any]]:
    """Verify and decode token"""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        
        # Check token type
        if payload.get("type") != token_type:
            return None
            
        # Check expiration
        exp = payload.get("exp")
        if exp and datetime.fromtimestamp(exp, tz=timezone.utc) < datetime.now(timezone.utc):
            return None
            
        return payload
        
    except JWTError:
        return None

def get_token_expiry(token: str) -> Optional[datetime]:
    """Get token expiry time"""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        exp = payload.get("exp")
        if exp:
            return datetime.fromtimestamp(exp, tz=timezone.utc)
    except JWTError:
        pass
    return None

class TokenBlacklist:
    """Redis-backed token blacklist with TTL auto-expiry.
    Falls back to in-memory set if Redis is unavailable (graceful degradation)."""

    DEFAULT_TTL = 86400  # 24 hours fallback

    def __init__(self):
        import redis
        import logging
        self._redis = None
        self._fallback: set = set()
        try:
            client = redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=2)
            client.ping()  # Test connection immediately
            self._redis = client
        except Exception as e:
            logging.getLogger(__name__).warning(
                f"[TokenBlacklist] Redis unavailable ({e}), using in-memory fallback"
            )

    def _key(self, token: str) -> str:
        import hashlib
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        return f"bl:{token_hash}"

    def add_token(self, token: str):
        """Add token to blacklist with TTL matching token expiry"""
        if self._redis:
            try:
                expiry = get_token_expiry(token)
                if expiry:
                    ttl = int((expiry - datetime.now(timezone.utc)).total_seconds())
                    ttl = max(ttl, 1)
                else:
                    ttl = self.DEFAULT_TTL
                self._redis.setex(self._key(token), ttl, "1")
                return
            except Exception:
                pass
        self._fallback.add(self._key(token))

    def is_blacklisted(self, token: str) -> bool:
        """Check if token is blacklisted"""
        if self._redis:
            try:
                return self._redis.exists(self._key(token)) > 0
            except Exception:
                pass
        return self._key(token) in self._fallback

# Global blacklist instance
token_blacklist = TokenBlacklist()