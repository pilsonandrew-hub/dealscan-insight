"""
Production-grade rate limiting with Redis backend
Supports per-IP, per-user, and per-route limits
"""
import time
import json
from typing import Optional, Dict, Any
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
import redis.asyncio as redis
from config.settings import settings

def extract_client_ip(request: Request) -> str:
    """Extract real client IP handling various proxy headers"""
    # Check proxy headers in order of preference
    for header in ["cf-connecting-ip", "true-client-ip", "x-real-ip"]:
        if ip := request.headers.get(header):
            return ip.strip()
    
    # Check X-Forwarded-For (take last IP in chain)
    if forwarded := request.headers.get("x-forwarded-for"):
        return forwarded.split(",")[-1].strip()
    
    # Fallback to direct connection
    return request.client.host if request.client else "unknown"

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Redis-backed distributed rate limiting"""
    
    def __init__(self, app):
        super().__init__(app)
        self.redis_client = None
        self.window_size = 60  # seconds
        self.default_limit = 100  # requests per window
        
        # Route-specific limits
        self.route_limits = {
            "/auth/login": 5,           # Stricter for auth
            "/upload": 10,              # File uploads
            "/opportunities": 50,       # Main data endpoint
            "/vehicles": 50,
            "/ml/predict": 20,          # ML inference
        }
    
    async def dispatch(self, request: Request, call_next):
        # Initialize Redis connection if needed
        if not self.redis_client:
            try:
                self.redis_client = redis.from_url(
                    settings.redis_url, 
                    decode_responses=True,
                    socket_timeout=1.0,
                    socket_connect_timeout=1.0
                )
                await self.redis_client.ping()
            except Exception:
                # Fallback: continue without rate limiting if Redis unavailable
                return await call_next(request)
        
        # Extract identifiers
        client_ip = extract_client_ip(request)
        user_id = getattr(getattr(request.state, "user", None), "id", None)
        route = request.url.path
        
        # Check rate limits
        if await self._is_rate_limited(client_ip, user_id, route):
            return JSONResponse(
                {
                    "error": "Rate limit exceeded",
                    "message": "Too many requests. Please try again later.",
                    "retry_after": self.window_size
                },
                status_code=429,
                headers={"Retry-After": str(self.window_size)}
            )
        
        return await call_next(request)
    
    async def _is_rate_limited(self, ip: str, user_id: Optional[int], route: str) -> bool:
        """Check if request should be rate limited"""
        current_time = int(time.time())
        window_start = current_time - (current_time % self.window_size)
        
        # Determine limit for this route
        limit = self.route_limits.get(route, self.default_limit)
        
        # Create keys for different rate limit types
        keys = [
            f"rl:ip:{ip}:{window_start}",           # Per-IP
            f"rl:route:{route}:{window_start}",     # Per-route global
        ]
        
        if user_id:
            keys.append(f"rl:user:{user_id}:{window_start}")  # Per-user
        
        try:
            # Use Redis pipeline for atomic operations
            async with self.redis_client.pipeline() as pipe:
                # Increment all counters
                for key in keys:
                    pipe.incr(key)
                    pipe.expire(key, self.window_size + 10)  # Buffer for cleanup
                
                results = await pipe.execute()
                
                # Check if any limit exceeded
                for i in range(0, len(results), 2):
                    count = results[i]
                    if count > limit:
                        # Log rate limit hit
                        await self._log_rate_limit_hit(ip, user_id, route, count, limit)
                        return True
                
                return False
                
        except Exception as e:
            # Redis error - allow request but log
            print(f"Rate limit Redis error: {e}")
            return False
    
    async def _log_rate_limit_hit(self, ip: str, user_id: Optional[int], route: str, count: int, limit: int):
        """Log rate limit violations for monitoring"""
        try:
            log_data = {
                "event": "rate_limit_exceeded",
                "ip": ip,
                "user_id": user_id,
                "route": route,
                "count": count,
                "limit": limit,
                "timestamp": time.time()
            }
            
            # Store in Redis for monitoring dashboard
            await self.redis_client.lpush(
                "rate_limit_violations",
                json.dumps(log_data)
            )
            await self.redis_client.ltrim("rate_limit_violations", 0, 999)  # Keep last 1000
            
        except Exception:
            pass  # Don't fail request due to logging issues

    async def get_rate_limit_status(self, ip: str, user_id: Optional[int], route: str) -> Dict[str, Any]:
        """Get current rate limit status for debugging"""
        if not self.redis_client:
            return {"available": True, "limit": self.default_limit}
            
        current_time = int(time.time())
        window_start = current_time - (current_time % self.window_size)
        limit = self.route_limits.get(route, self.default_limit)
        
        keys = [f"rl:ip:{ip}:{window_start}"]
        if user_id:
            keys.append(f"rl:user:{user_id}:{window_start}")
            
        try:
            counts = await self.redis_client.mget(keys)
            max_count = max((int(c) if c else 0) for c in counts)
            
            return {
                "limit": limit,
                "used": max_count,
                "remaining": max(0, limit - max_count),
                "reset_time": window_start + self.window_size,
                "available": max_count < limit
            }
        except Exception:
            return {"available": True, "limit": limit}