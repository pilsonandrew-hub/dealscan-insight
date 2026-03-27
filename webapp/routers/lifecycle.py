"""
Deal lifecycle management — expire and archive stale deals (DEA-13).
"""
import os
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import JSONResponse

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
    """Mark deals older than max_age_days as expired in Supabase."""
    if _supabase_client is None:
        logger.warning("[LIFECYCLE] Supabase client not available — skipping expiration")
        return {"expired": 0, "error": "supabase_unavailable"}

    cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat()
    try:
        result = (
            _supabase_client.table("opportunities")
            .update({"status": "expired"})
            .lt("ingested_at", cutoff)
            .neq("status", "expired")
            .neq("status", "archived")
            .neq("status", "passed")
            .execute()
        )
        count = len(result.data) if result.data else 0
        logger.info(f"[LIFECYCLE] Expired {count} deals older than {max_age_days} days")
        return {"expired": count, "cutoff": cutoff}
    except Exception as e:
        logger.error(f"[LIFECYCLE] expire_stale_deals failed: {e}")
        return {"expired": 0, "error": str(e)}


@router.post("/expire")
async def expire_deals_endpoint(background_tasks: BackgroundTasks):
    """Expire deals older than 7 days. Runs in background."""
    background_tasks.add_task(expire_stale_deals)
    return JSONResponse(
        status_code=202,
        content={"status": "accepted", "message": "Deal expiration started in background"},
    )
