"""
Deal lifecycle management — expire and archive stale deals (DEA-13).
"""
import os
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/lifecycle", tags=["lifecycle"])

_supabase_client = None
try:
    _supabase_url = os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL")
    _supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY")
    if _supabase_url and _supabase_key:
        from supabase import create_client
        _supabase_client = create_client(_supabase_url, _supabase_key)
except Exception as e:
    logger.warning(f"[LIFECYCLE] Supabase client not available: {e}")


def expire_stale_deals(max_age_days: int = 7) -> dict:
    """Deactivate deals older than max_age_days in Supabase.

    The live opportunities table uses ``is_active`` as the lifecycle surface
    and ``created_at`` as the available age surface. Do not write a synthetic
    ``status='expired'`` value here: the production schema does not expose an
    opportunities.status column, and historical migrations that mention it used
    deal-quality values rather than lifecycle states.
    """
    if _supabase_client is None:
        logger.warning("[LIFECYCLE] Supabase client not available — skipping expiration")
        return {"expired": 0, "error": "supabase_unavailable"}

    cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat()
    try:
        result = (
            _supabase_client.table("opportunities")
            .update({"is_active": False})
            .lt("created_at", cutoff)
            .eq("is_active", True)
            .execute()
        )
        count = len(result.data) if result.data else 0
        logger.info(f"[LIFECYCLE] Deactivated {count} deals older than {max_age_days} days")
        return {"expired": count, "cutoff": cutoff}
    except Exception as e:
        logger.error(f"[LIFECYCLE] expire_stale_deals failed: {e}")
        return {"expired": 0, "error": str(e)}


def _verify_lifecycle_secret(x_internal_secret: Optional[str]) -> None:
    expected = (
        os.getenv("INTERNAL_API_SECRET", "").strip()
        or os.getenv("LIFECYCLE_CRON_SECRET", "").strip()
    )
    if not expected:
        logger.error("[LIFECYCLE_AUTH] INTERNAL_API_SECRET or LIFECYCLE_CRON_SECRET not configured")
        raise HTTPException(status_code=503, detail="Lifecycle authorization not configured")
    if not x_internal_secret or x_internal_secret.strip() != expected:
        logger.warning("[LIFECYCLE_AUTH] rejected unauthorized expire request")
        raise HTTPException(status_code=401, detail="Invalid lifecycle authorization")


@router.post("/expire")
async def expire_deals_endpoint(
    background_tasks: BackgroundTasks,
    x_internal_secret: Optional[str] = Header(None),
):
    """Expire deals older than 7 days. Runs in background."""
    _verify_lifecycle_secret(x_internal_secret)
    background_tasks.add_task(expire_stale_deals)
    return JSONResponse(
        status_code=202,
        content={"status": "accepted", "message": "Deal expiration started in background"},
    )
