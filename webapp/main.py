"""
DealerScope FastAPI Production Application
Secure, scalable arbitrage platform with ML/AI integration
"""
from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.security import HTTPBearer
from starlette.responses import JSONResponse
import logging
import uvicorn
import os
from contextlib import asynccontextmanager

from config.settings import settings
from webapp.middleware.request_id import RequestIDMiddleware
from webapp.middleware.rate_limit import RateLimitMiddleware
from webapp.middleware.security import SecurityMiddleware
from webapp.middleware.error_handler import ErrorHandlerMiddleware
from webapp.routers import auth, vehicles, opportunities, upload, ml, admin
from webapp.database import init_db
from webapp.monitoring import setup_monitoring

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp":"%(asctime)s","level":"%(levelname)s","module":"%(name)s","message":"%(message)s"}',
    handlers=[logging.StreamHandler()]
)

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup/shutdown lifecycle"""
    # Startup
    logger.info("Starting DealerScope API")
    await init_db()
    setup_monitoring(app)
    yield
    # Shutdown  
    logger.info("Shutting down DealerScope API")

# Create FastAPI app
app = FastAPI(
    title="DealerScope API",
    version=settings.app_version,
    description="Intelligent Vehicle Arbitrage Platform",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan
)

# Security middleware stack (order matters)
app.add_middleware(SecurityMiddleware)
app.add_middleware(ErrorHandlerMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(RateLimitMiddleware)

# CORS configuration
allowed_origins = os.getenv("ALLOWED_ORIGINS", "").split(",") if not settings.debug else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Health check endpoints
@app.get("/healthz")
async def health_check():
    """Health check for load balancers"""
    return {"status": "healthy", "version": settings.app_version}

@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    from webapp.monitoring import get_metrics
    return get_metrics()

# Include routers with authentication
bearer_scheme = HTTPBearer()

app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(vehicles.router, prefix="/vehicles", tags=["Vehicles"])
app.include_router(opportunities.router, prefix="/opportunities", tags=["Opportunities"])
app.include_router(upload.router, prefix="/upload", tags=["Data Upload"])
app.include_router(ml.router, prefix="/ml", tags=["Machine Learning"])
app.include_router(admin.router, prefix="/admin", tags=["Administration"])

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {type(exc).__name__}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "request_id": getattr(request.state, "request_id", "unknown")}
    )

if __name__ == "__main__":
    # Get port from environment variable (Cloud Run provides PORT=8080)
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(
        "webapp.main:app",
        host="0.0.0.0",
        port=port,
        reload=settings.debug,
        access_log=settings.debug,
        timeout_keep_alive=120,
        timeout_graceful_shutdown=30
    )