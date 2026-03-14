# PRIMARY ENTRYPOINT - use this. webapp/main.py is deprecated.
"""
DealerScope — Unified Backend Entrypoint
Combines the FastAPI webapp routers with the scrape/score pipeline.
"""
import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Depends, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

# Middleware — import with fallbacks
try:
    from webapp.middleware.request_id import RequestIDMiddleware
except Exception as e:
    RequestIDMiddleware = None
    logging.warning(f"request_id middleware unavailable: {e}")

try:
    from webapp.middleware.rate_limit import RateLimitMiddleware
except Exception as e:
    RateLimitMiddleware = None
    logging.warning(f"rate_limit middleware unavailable: {e}")

try:
    from webapp.middleware.security import SecurityMiddleware
except Exception as e:
    SecurityMiddleware = None
    logging.warning(f"security middleware unavailable: {e}")

try:
    from webapp.middleware.error_handler import ErrorHandlerMiddleware
except Exception as e:
    ErrorHandlerMiddleware = None
    logging.warning(f"error_handler middleware unavailable: {e}")

# Routers — import each independently so one failure doesn't kill everything
import importlib
_routers = {}
for _rname in ["auth", "vehicles", "opportunities", "upload", "ml", "admin", "ingest", "rover", "outcomes"]:
    try:
        _routers[_rname] = importlib.import_module(f"webapp.routers.{_rname}")
        logging.info(f"Router loaded: {_rname}")
    except Exception as e:
        logging.warning(f"Router {_rname} unavailable: {e}")

try:
    from webapp.database import init_db
except Exception as e:
    init_db = None
    logging.warning(f"database unavailable: {e}")

try:
    from webapp.monitoring import setup_monitoring
except Exception as e:
    setup_monitoring = None
    logging.warning(f"monitoring unavailable: {e}")

logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp":"%(asctime)s","level":"%(levelname)s","module":"%(name)s","message":"%(message)s"}',
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)
PIPELINE_SECRET = os.getenv("PIPELINE_SECRET")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-in-prod")

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
    required_vars = [
        "SUPABASE_SERVICE_ROLE_KEY",
        "TELEGRAM_BOT_TOKEN",
        "APIFY_WEBHOOK_SECRET",
        "APIFY_TOKEN",
    ]
    for var in required_vars:
        if not os.getenv(var):
            logger.critical(f"STARTUP FATAL: {var} is not set. Refusing to start.")
            if os.getenv("ENVIRONMENT") == "production":
                sys.exit(1)
    if SECRET_KEY == "dev-secret-change-in-prod" and os.getenv("ENVIRONMENT", "production").lower() == "production":
        logger.critical(
            "SECRET_KEY is not set; using development fallback in production. "
            "Set SECRET_KEY immediately."
        )
    if not PIPELINE_SECRET:
        logger.critical("MISSING REQUIRED ENV VAR: PIPELINE_SECRET — pipeline routes are disabled")
    try:
        await init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.warning(f"Database init failed (non-fatal): {e}")
    try:
        setup_monitoring(app)
    except Exception as e:
        logger.warning(f"Monitoring setup failed (non-fatal): {e}")
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

# Middleware stack — only add if available
if SecurityMiddleware:
    app.add_middleware(SecurityMiddleware)
if ErrorHandlerMiddleware:
    app.add_middleware(ErrorHandlerMiddleware)
if RequestIDMiddleware:
    app.add_middleware(RequestIDMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1024)
if RateLimitMiddleware:
    app.add_middleware(RateLimitMiddleware)
_DEFAULT_ALLOWED_ORIGINS = [
    "https://dealscan-insight.vercel.app",
    "https://dealscan-insight-production.up.railway.app",
    "http://localhost:5173",
    "http://localhost:3000",
]
_configured_allowed_origins = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", "").split(",")
    if o.strip()
]
_ALLOWED_ORIGINS = list(dict.fromkeys(_DEFAULT_ALLOWED_ORIGINS + _configured_allowed_origins))
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-Apify-Webhook-Secret"],
)

# ---------------------------------------------------------------------------
# Register webapp routers — only those that loaded successfully
# ---------------------------------------------------------------------------
_prefix_map = {
    "auth": "/api/auth",
    "vehicles": "/api/vehicles",
    "opportunities": "/api/opportunities",
    "upload": "/api/upload",
    "ml": "/api/ml",
    "admin": "/api/admin",
    "ingest": "",
    "rover": "",
    "outcomes": "",
}
for _name, _mod in _routers.items():
    try:
        app.include_router(_mod.router, prefix=_prefix_map.get(_name, f"/api/{_name}"))
        logger.info(f"Registered router: {_name}")
    except Exception as e:
        logger.warning(f"Could not register router {_name}: {e}")


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


async def require_pipeline_auth(
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
):
    if not PIPELINE_SECRET:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found",
        )
    if authorization != f"Bearer {PIPELINE_SECRET}":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )


@app.post("/api/pipeline/run", tags=["pipeline"])
async def trigger_pipeline():
    """Legacy pipeline trigger disabled in favor of Apify webhooks."""
    return {
        "status": "disabled",
        "message": "Use Apify webhooks for scraping — /api/ingest/apify",
    }


@app.get("/api/pipeline/status", tags=["pipeline"])
async def pipeline_status(_: None = Depends(require_pipeline_auth)):
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
@app.get("/health", include_in_schema=False)
async def health():
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
