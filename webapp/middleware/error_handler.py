"""
Error handling middleware with secure logging
"""
import json
import logging
import traceback
from typing import Union
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from config.settings import settings

logger = logging.getLogger("errors")

class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """Secure error handling with request ID correlation"""
    
    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as exc:
            return await self._handle_error(request, exc)
    
    async def _handle_error(self, request: Request, exc: Exception) -> JSONResponse:
        """Handle and log errors securely"""
        request_id = getattr(request.state, "request_id", "unknown")
        user_id = getattr(getattr(request.state, "user", None), "id", None)
        
        # Create secure log entry (no sensitive data)
        log_entry = {
            "level": "error",
            "request_id": request_id,
            "user_id": user_id,
            "path": str(request.url.path),
            "method": request.method,
            "error_type": type(exc).__name__,
            "error_message": self._sanitize_error_message(str(exc))
        }
        
        # Add full traceback only in development
        if settings.debug:
            log_entry["traceback"] = traceback.format_exc()
        
        # Log the error
        logger.error(json.dumps(log_entry))
        
        # Determine response based on exception type
        status_code, error_message = self._get_error_response(exc)
        
        return JSONResponse(
            content={
                "error": error_message,
                "request_id": request_id,
                **self._get_debug_info(exc) if settings.debug else {}
            },
            status_code=status_code
        )
    
    def _sanitize_error_message(self, message: str) -> str:
        """Remove sensitive information from error messages"""
        # Remove common sensitive patterns
        sensitive_patterns = [
            r'password[=:]\s*\S+',
            r'token[=:]\s*\S+',
            r'key[=:]\s*\S+',
            r'secret[=:]\s*\S+',
            r'authorization:\s*bearer\s+\S+',
        ]
        
        import re
        sanitized = message
        for pattern in sensitive_patterns:
            sanitized = re.sub(pattern, '[REDACTED]', sanitized, flags=re.IGNORECASE)
        
        return sanitized[:500]  # Limit length
    
    def _get_error_response(self, exc: Exception) -> tuple[int, str]:
        """Determine appropriate HTTP status and message"""
        from fastapi import HTTPException
        from webapp.exceptions import ValidationError, NotFoundError, AuthenticationError
        
        if isinstance(exc, HTTPException):
            return exc.status_code, exc.detail
        elif isinstance(exc, ValidationError):
            return 400, "Invalid input data"
        elif isinstance(exc, NotFoundError):
            return 404, "Resource not found"
        elif isinstance(exc, AuthenticationError):
            return 401, "Authentication required"
        elif isinstance(exc, PermissionError):
            return 403, "Access denied"
        else:
            return 500, "Internal server error"
    
    def _get_debug_info(self, exc: Exception) -> dict:
        """Get debug information for development"""
        return {
            "debug": {
                "exception_type": type(exc).__name__,
                "exception_args": str(exc.args),
                "traceback": traceback.format_exc().split('\n')[-10:]  # Last 10 lines
            }
        }