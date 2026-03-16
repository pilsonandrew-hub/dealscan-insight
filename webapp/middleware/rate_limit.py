"""
Production-grade rate limiting with Redis backend
Supports per-IP, per-user, and per-route limits
"""
import ipaddress
import logging
import time
import json
from typing import Optional, Dict, Any, Iterable
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
import redis.asyncio as redis
from config.settings import settings

logger = logging.getLogger(__name__)

_FORWARDED_IP_HEADERS = ("cf-connecting-ip", "true-client-ip", "x-real-ip")


def _parse_ip(value: Optional[str]) -> Optional[str]:
    if value in {None, ""}:
        return None
    candidate = str(value).strip()
    if not candidate:
        return None
    try:
        return ipaddress.ip_address(candidate).compressed
    except ValueError:
        return None


def _parse_x_forwarded_for(value: Optional[str]) -> list[str]:
    if value in {None, ""}:
        return []
    parsed: list[str] = []
    for part in str(value).split(","):
        ip = _parse_ip(part)
        if ip:
            parsed.append(ip)
    return parsed


def _trusted_proxy_networks(raw_value: Optional[str]) -> tuple[ipaddress._BaseNetwork, ...]:
    networks: list[ipaddress._BaseNetwork] = []
    for part in (raw_value or "").split(","):
        candidate = part.strip()
        if not candidate:
            continue
        try:
            networks.append(ipaddress.ip_network(candidate, strict=False))
        except ValueError:
            logger.warning("[RATE_LIMIT] Ignoring invalid trusted proxy CIDR %r", candidate)
    return tuple(networks)


def _ip_in_networks(ip: Optional[str], networks: Iterable[ipaddress._BaseNetwork]) -> bool:
    normalized_ip = _parse_ip(ip)
    if not normalized_ip:
        return False
    address = ipaddress.ip_address(normalized_ip)
    return any(address in network for network in networks)


def extract_client_ip(
    request: Request,
    *,
    trust_proxy_headers: Optional[bool] = None,
    trusted_proxy_cidrs: Optional[str] = None,
) -> str:
    """Extract a client IP without trusting spoofable proxy headers from untrusted peers."""
    peer_ip = _parse_ip(request.client.host if request.client else None) or "unknown"
    should_trust_proxy_headers = (
        settings.rate_limit_trust_proxy_headers
        if trust_proxy_headers is None
        else trust_proxy_headers
    )
    if not should_trust_proxy_headers:
        return peer_ip

    trusted_networks = _trusted_proxy_networks(
        settings.rate_limit_trusted_proxy_cidrs
        if trusted_proxy_cidrs is None
        else trusted_proxy_cidrs
    )
    if not _ip_in_networks(peer_ip, trusted_networks):
        return peer_ip

    forwarded_chain = _parse_x_forwarded_for(request.headers.get("x-forwarded-for"))
    if forwarded_chain:
        for candidate_ip in reversed(forwarded_chain):
            if not _ip_in_networks(candidate_ip, trusted_networks):
                return candidate_ip
        return forwarded_chain[0]

    for header in _FORWARDED_IP_HEADERS:
        if forwarded_ip := _parse_ip(request.headers.get(header)):
            return forwarded_ip

    return peer_ip

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Redis-backed distributed rate limiting"""

    INGEST_ROUTE = "/api/ingest/apify"

    def __init__(self, app):
        super().__init__(app)
        self.redis_client = None
        self.window_size = max(int(settings.rate_limit_window_seconds), 1)
        self.default_limit = max(int(settings.rate_limit_requests), 1)
        self.ingest_window_size = max(int(settings.rate_limit_ingest_window_seconds), 1)
        self.ingest_limit = max(int(settings.rate_limit_ingest_requests), 1)

        # Route-specific limits
        self.route_limits = {
            "/auth/login": 5,           # Stricter for auth
            "/upload": 10,              # File uploads
            "/opportunities": 50,       # Main data endpoint
            "/vehicles": 50,
            "/ml/predict": 20,          # ML inference
            self.INGEST_ROUTE: self.ingest_limit,
        }
        self.protected_routes = {self.INGEST_ROUTE}

    async def dispatch(self, request: Request, call_next):
        route = request.url.path
        client_ip = extract_client_ip(request)

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
            except Exception as exc:
                failure_response = self._rate_limit_backend_failure_response(
                    route=route,
                    client_ip=client_ip,
                    stage="redis_init",
                    error=exc,
                )
                if failure_response is not None:
                    return failure_response
                return await call_next(request)

        # Extract identifiers
        user_id = getattr(getattr(request.state, "user", None), "id", None)

        # Check rate limits
        try:
            is_limited = await self._is_rate_limited(client_ip, user_id, route)
        except Exception as exc:
            failure_response = self._rate_limit_backend_failure_response(
                route=route,
                client_ip=client_ip,
                stage="redis_check",
                error=exc,
            )
            if failure_response is not None:
                return failure_response
            return await call_next(request)

        if is_limited:
            window_size = self._window_for_route(route)
            return JSONResponse(
                {
                    "error": "Rate limit exceeded",
                    "message": "Too many requests. Please try again later.",
                    "retry_after": window_size
                },
                status_code=429,
                headers={"Retry-After": str(window_size)}
            )

        return await call_next(request)

    async def _is_rate_limited(self, ip: str, user_id: Optional[int], route: str) -> bool:
        """Check if request should be rate limited"""
        current_time = int(time.time())
        window_size = self._window_for_route(route)
        window_start = current_time - (current_time % window_size)

        # Determine limit for this route
        limit = self.route_limits.get(route, self.default_limit)

        # Create keys for different rate limit types
        keys = [
            f"rl:ip:{ip}:{window_start}",           # Per-IP
            f"rl:route:{route}:{window_start}",     # Per-route global
        ]

        if user_id:
            keys.append(f"rl:user:{user_id}:{window_start}")  # Per-user

        # Use Redis pipeline for atomic operations
        async with self.redis_client.pipeline() as pipe:
            # Increment all counters
            for key in keys:
                pipe.incr(key)
                pipe.expire(key, window_size + 10)  # Buffer for cleanup

            results = await pipe.execute()

        # Check if any limit exceeded
        for i in range(0, len(results), 2):
            count = results[i]
            if count > limit:
                # Log rate limit hit
                await self._log_rate_limit_hit(ip, user_id, route, count, limit)
                return True

        return False

    async def _log_rate_limit_hit(self, ip: str, user_id: Optional[int], route: str, count: int, limit: int):
        """Log rate limit violations for monitoring"""
        log_data = {
            "event": "rate_limit_exceeded",
            "ip": ip,
            "user_id": user_id,
            "route": route,
            "count": count,
            "limit": limit,
            "timestamp": time.time()
        }
        if route in self.protected_routes:
            logger.warning(
                "[INGEST_RATE_LIMIT] blocked | route=%s | client_ip=%s | count=%s | limit=%s",
                route,
                ip,
                count,
                limit,
            )
        try:
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
            return {"available": route not in self.protected_routes, "limit": self.route_limits.get(route, self.default_limit)}

        current_time = int(time.time())
        window_size = self._window_for_route(route)
        window_start = current_time - (current_time % window_size)
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
                "reset_time": window_start + window_size,
                "available": max_count < limit
            }
        except Exception:
            return {"available": route not in self.protected_routes, "limit": limit}

    def _window_for_route(self, route: str) -> int:
        if route == self.INGEST_ROUTE:
            return self.ingest_window_size
        return self.window_size

    def _rate_limit_backend_failure_response(
        self,
        *,
        route: str,
        client_ip: str,
        stage: str,
        error: Exception,
    ) -> Optional[JSONResponse]:
        if route in self.protected_routes:
            logger.error(
                "[INGEST_RATE_LIMIT] fail_closed | stage=%s | route=%s | client_ip=%s | error=%s",
                stage,
                route,
                client_ip,
                error,
            )
            return JSONResponse(
                {
                    "error": "Ingest rate limit unavailable",
                    "message": "Ingest protection is unavailable. Retry after Redis recovers.",
                },
                status_code=503,
            )

        logger.warning(
            "[RATE_LIMIT] fail_open | stage=%s | route=%s | client_ip=%s | error=%s",
            stage,
            route,
            client_ip,
            error,
        )
        return None
