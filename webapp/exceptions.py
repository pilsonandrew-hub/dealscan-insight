"""
Custom exceptions for DealerScope
"""

class DealerScopeException(Exception):
    """Base exception for DealerScope"""
    pass

class ValidationError(DealerScopeException):
    """Data validation error"""
    pass

class NotFoundError(DealerScopeException):
    """Resource not found"""
    pass

class AuthenticationError(DealerScopeException):
    """Authentication failed"""
    pass

class RateLimitError(DealerScopeException):
    """Rate limit exceeded"""
    pass

class SSRFError(DealerScopeException):
    """SSRF attempt detected"""
    pass

class MLModelError(DealerScopeException):
    """ML model prediction error"""
    pass