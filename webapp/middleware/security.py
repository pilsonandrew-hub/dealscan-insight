"""
Security middleware for SSRF protection, input validation, and security headers
"""
import ipaddress
import re
from typing import Set
from urllib.parse import urlparse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse

# Private IP ranges to block
PRIVATE_NETWORKS = [
    ipaddress.IPv4Network("10.0.0.0/8"),
    ipaddress.IPv4Network("172.16.0.0/12"),
    ipaddress.IPv4Network("192.168.0.0/16"),
    ipaddress.IPv4Network("127.0.0.0/8"),
    ipaddress.IPv6Network("::1/128"),
    ipaddress.IPv6Network("fc00::/7"),
    ipaddress.IPv6Network("fe80::/10"),
]

# Allowed domains for SSRF protection
ALLOWED_DOMAINS: Set[str] = {
    "govdeals.com",
    "www.govdeals.com",
    "publicsurplus.com", 
    "www.publicsurplus.com",
    "municibid.com",
    "www.municibid.com"
}

# Security headers
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data: https:; connect-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload"
}

class SecurityMiddleware(BaseHTTPMiddleware):
    """Security middleware for input validation and protection"""
    
    def __init__(self, app):
        super().__init__(app)
        self.max_request_size = 10 * 1024 * 1024  # 10MB
        
    async def dispatch(self, request: Request, call_next):
        # Check request size
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.max_request_size:
            return JSONResponse(
                {"error": "Request too large"}, 
                status_code=413
            )
        
        # Validate URL parameters for potential SSRF
        if await self._has_ssrf_risk(request):
            return JSONResponse(
                {"error": "Invalid URL parameter"}, 
                status_code=400
            )
            
        # Process request
        response = await call_next(request)
        
        # Add security headers
        for header, value in SECURITY_HEADERS.items():
            response.headers[header] = value
            
        return response
    
    async def _has_ssrf_risk(self, request: Request) -> bool:
        """Check if request parameters contain potentially dangerous URLs"""
        # Check query parameters
        for key, value in request.query_params.items():
            if key.lower() in ('url', 'link', 'redirect', 'callback'):
                if not self._is_safe_url(value):
                    return True
                    
        # Check JSON body for URL fields
        if request.headers.get("content-type") == "application/json":
            try:
                body = await request.body()
                if body:
                    import json
                    data = json.loads(body)
                    if isinstance(data, dict):
                        for key, value in data.items():
                            if isinstance(value, str) and key.lower() in ('url', 'link', 'redirect', 'callback'):
                                if not self._is_safe_url(value):
                                    return True
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass
                
        return False
    
    def _is_safe_url(self, url: str) -> bool:
        """Validate URL against SSRF attacks (validation-only, no fetch)"""
        resolved = resolve_and_validate_url(url)
        return resolved is not None


def resolve_and_validate_url(url: str):
    """Resolve hostname once, validate IP, return (resolved_ip, parsed) or None.

    Callers MUST use the returned resolved_ip for the actual HTTP request
    (with the original Host header) to prevent DNS rebinding.
    """
    import socket
    try:
        parsed = urlparse(url)

        if parsed.scheme not in ('http', 'https'):
            return None

        hostname = parsed.hostname
        if not hostname or hostname not in ALLOWED_DOMAINS:
            return None

        # Resolve ONCE — this is the IP we will connect to
        resolved_ip = socket.gethostbyname(hostname)
        ip_obj = ipaddress.ip_address(resolved_ip)

        for network in PRIVATE_NETWORKS:
            if ip_obj in network:
                return None

        return resolved_ip, parsed

    except (socket.gaierror, ValueError, Exception):
        return None


def safe_fetch(url: str, **kwargs):
    """Fetch a URL with SSRF-safe DNS pinning.

    Resolves the hostname once, validates the IP, then makes the HTTP
    request directly to the resolved IP with the original Host header.
    """
    import requests

    result = resolve_and_validate_url(url)
    if result is None:
        raise ValueError(f"URL blocked by SSRF policy: {url}")

    resolved_ip, parsed = result
    hostname = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    # Build the pinned URL: replace hostname with resolved IP
    pinned_url = url.replace(f"://{hostname}", f"://{resolved_ip}", 1)

    headers = kwargs.pop("headers", {})
    headers["Host"] = hostname

    # Disable redirects to prevent re-resolution via Location header
    kwargs.setdefault("allow_redirects", False)
    kwargs.setdefault("timeout", 30)

    return requests.get(pinned_url, headers=headers, verify=parsed.scheme == "https", **kwargs)


def is_safe_domain(domain: str) -> bool:
    """Check if domain is in allowed list"""
    return domain.lower() in ALLOWED_DOMAINS

def add_allowed_domain(domain: str) -> None:
    """Add domain to allowed list (for testing/admin)"""
    ALLOWED_DOMAINS.add(domain.lower())