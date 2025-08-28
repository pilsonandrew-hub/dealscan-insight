"""
Simplified FastAPI app that runs without dependencies
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="DealerScope API",
    version="1.0.0",
    description="Intelligent Vehicle Arbitrage Platform - Minimal Mode"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Health check
@app.get("/healthz")
async def health_check():
    """Health check for load balancers"""
    return {"status": "healthy", "version": "1.0.0", "mode": "minimal"}

@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "DealerScope API - Running in minimal mode", "status": "ok"}

# Basic error handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {type(exc).__name__}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "mode": "minimal"}
    )

# Import minimal routers
try:
    from webapp.minimal_routers import (
        auth_router, vehicles_router, opportunities_router,
        upload_router, ml_router, admin_router
    )
    
    app.include_router(auth_router, prefix="/auth", tags=["Authentication"])
    app.include_router(vehicles_router, prefix="/vehicles", tags=["Vehicles"])
    app.include_router(opportunities_router, prefix="/opportunities", tags=["Opportunities"])
    app.include_router(upload_router, prefix="/upload", tags=["Upload"])
    app.include_router(ml_router, prefix="/ml", tags=["ML"])
    app.include_router(admin_router, prefix="/admin", tags=["Admin"])
    
    logger.info("Loaded minimal routers successfully")
    
except Exception as e:
    logger.warning(f"Could not load minimal routers: {e}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    logger.info(f"Starting DealerScope API in minimal mode on port {port}")
    uvicorn.run(
        "webapp.simple_main:app",
        host="0.0.0.0",
        port=port,
        reload=False
    )