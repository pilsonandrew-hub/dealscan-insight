# PRIMARY ENTRYPOINT - use this. webapp/main.py is deprecated.
"""
DealerScope — Unified Backend Entrypoint
Combines the FastAPI webapp routers with the scrape/score pipeline.
"""
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from webapp.middleware.request_id import RequestIDMiddleware
from webapp.middleware.rate_limit import RateLimitMiddleware
from webapp.middleware.security import SecurityMiddleware
from webapp.middleware.error_handler import ErrorHandlerMiddleware
from webapp.routers import auth, vehicles, opportunities, upload, ml, admin, ingest
from webapp.database import init_db
from webapp.monitoring import setup_monitoring

logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp":"%(asctime)s","level":"%(levelname)s","module":"%(name)s","message":"%(message)s"}',
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pipeline state (in-memory; production should use Redis/DB)
# ---------------------------------------------------------------------------
_pipeline_state: dict = {
    "status": "idle",
    "last_run": None,
    "last_error": None,
    "task_id": None,
}


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting DealerScope unified backend")
    await init_db()
    setup_monitoring(app)
    yield
    logger.info("Shutting down DealerScope unified backend")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="DealerScope API",
    version="5.0.0",
    description="Unified vehicle arbitrage platform — scrapers + ML + API",
    docs_url="/docs" if os.getenv("DEBUG", "false").lower() == "true" else None,
    redoc_url="/redoc" if os.getenv("DEBUG", "false").lower() == "true" else None,
    lifespan=lifespan,
)

# Middleware stack
app.add_middleware(SecurityMiddleware)
app.add_middleware(ErrorHandlerMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Register webapp routers
# ---------------------------------------------------------------------------
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(vehicles.router, prefix="/api/vehicles", tags=["vehicles"])
app.include_router(opportunities.router, prefix="/api/opportunities", tags=["opportunities"])
app.include_router(upload.router, prefix="/api/upload", tags=["upload"])
app.include_router(ml.router, prefix="/api/ml", tags=["ml"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(ingest.router)  # Apify webhook endpoint


# ---------------------------------------------------------------------------
# Pipeline endpoints
# ---------------------------------------------------------------------------
async def _run_pipeline_async():
    """Background task: run the full scrape → score pipeline."""
    from backend.ingest.scrape_all import main as scrape_main

    _pipeline_state["status"] = "running"
    _pipeline_state["last_error"] = None
    try:
        await scrape_main()
        _pipeline_state["status"] = "idle"
        _pipeline_state["last_run"] = datetime.now(timezone.utc).isoformat()
        logger.info("Pipeline completed successfully")
    except Exception as exc:
        _pipeline_state["status"] = "error"
        _pipeline_state["last_error"] = str(exc)
        logger.exception("Pipeline failed")


@app.post("/api/pipeline/run", tags=["pipeline"])
async def trigger_pipeline():
    """Kick off the scrape + score pipeline as a background task."""
    if _pipeline_state["status"] == "running":
        return {"status": "already_running", "message": "Pipeline is already in progress"}

    # Fire and forget — Celery handles this in production; asyncio.create_task in dev
    asyncio.create_task(_run_pipeline_async())
    return {"status": "started", "message": "Pipeline triggered"}


@app.get("/api/pipeline/status", tags=["pipeline"])
async def pipeline_status():
    """Return current pipeline run state."""
    return {
        "status": _pipeline_state["status"],
        "last_run": _pipeline_state["last_run"],
        "last_error": _pipeline_state["last_error"],
    }


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/healthz", include_in_schema=False)
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
