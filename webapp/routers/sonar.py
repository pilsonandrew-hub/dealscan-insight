"""
Sonar — Vehicle search via Supabase opportunities index.

Endpoints:
  POST /api/sonar/search      — query Supabase, return results instantly
  GET  /api/sonar/status/{id}  — retrieve cached results by job ID
"""

import json
import logging
import uuid
from datetime import datetime, timezone

import redis.asyncio as redis
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from supabase import create_client

from config.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sonar", tags=["sonar"])

JOB_TTL_SECONDS = 300


# ── Models ────────────────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str
    min_price: float = Field(default=0, ge=0)
    max_price: float = Field(default=75000, ge=0)


class SonarResult(BaseModel):
    id: str
    title: str = ""
    year: int | None = None
    make: str = ""
    model: str = ""
    trim: str = ""
    currentBid: float = 0
    timeRemaining: str = ""
    endsAt: str = ""
    location: str = ""
    condition: str = ""
    sourceName: str = ""
    sourceUrl: str = ""
    mileage: int | str | None = None
    auctionSource: str = ""
    issuingAgency: str = ""
    titleStatus: str = "Unknown"
    isAsIs: bool = True
    photoUrl: str = ""


# ── Redis helper ──────────────────────────────────────────────────────────────

_redis_pool: redis.Redis | None = None


async def _get_redis() -> redis.Redis | None:
    global _redis_pool
    if _redis_pool is not None:
        return _redis_pool
    try:
        _redis_pool = redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=2)
        await _redis_pool.ping()
        return _redis_pool
    except Exception as e:
        logger.warning(f"[SONAR] Redis unavailable, using in-memory fallback: {e}")
        _redis_pool = None
        return None


# In-memory fallback when Redis is unavailable
_memory_store: dict[str, dict] = {}


async def _store_job(job_id: str, data: dict) -> None:
    r = await _get_redis()
    if r:
        await r.set(f"sonar:{job_id}", json.dumps(data), ex=JOB_TTL_SECONDS)
    else:
        _memory_store[job_id] = data


async def _load_job(job_id: str) -> dict | None:
    r = await _get_redis()
    if r:
        raw = await r.get(f"sonar:{job_id}")
        return json.loads(raw) if raw else None
    return _memory_store.get(job_id)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _time_remaining(end_str: str | None) -> str:
    if not end_str:
        return ""
    try:
        end = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
        delta = end - datetime.now(timezone.utc)
        if delta.total_seconds() <= 0:
            return "Ended"
        days = delta.days
        hours, rem = divmod(delta.seconds, 3600)
        minutes = rem // 60
        if days > 0:
            return f"{days}d {hours}h"
        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"
    except Exception:
        return ""


def _row_to_result(row: dict) -> dict:
    """Convert a Supabase opportunities row into the SonarResult shape."""
    year = row.get("year")
    make = row.get("make") or ""
    model = row.get("model") or ""
    title = row.get("title") or f"{year} {make} {model}".strip() if year else f"{make} {model}".strip()
    ends_at = row.get("auction_end_date") or ""
    city = row.get("city") or ""
    state = row.get("state") or ""
    location = f"{city}, {state}".strip(", ")

    return SonarResult(
        id=str(row.get("id", "")),
        title=title,
        year=int(year) if year else None,
        make=make,
        model=model,
        trim=row.get("trim") or "",
        currentBid=float(row.get("current_bid") or 0),
        timeRemaining=_time_remaining(ends_at if ends_at else None),
        endsAt=str(ends_at) if ends_at else "",
        location=location,
        condition="",
        sourceName=row.get("source") or row.get("source_site") or "",
        sourceUrl=row.get("listing_url") or "",
        mileage=row.get("mileage"),
        auctionSource=row.get("source") or "",
        issuingAgency="",
        titleStatus="Unknown",
        isAsIs=True,
        photoUrl=row.get("image_url") or "",
    ).model_dump()


# ── Supabase client ──────────────────────────────────────────────────────────

def _get_supabase():
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise HTTPException(status_code=503, detail="Supabase credentials not configured")
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/search")
async def sonar_search(req: SearchRequest):
    """Query the Supabase opportunities index and return results instantly."""
    sb = _get_supabase()
    job_id = uuid.uuid4().hex

    query = sb.table("opportunities").select("*").eq("is_active", True)

    # Price filters
    if req.min_price > 0:
        query = query.gte("current_bid", req.min_price)
    if req.max_price > 0:
        query = query.lte("current_bid", req.max_price)

    # Text search across title, make, model
    if req.query.strip():
        q = req.query.strip()
        query = query.or_(f"title.ilike.%{q}%,make.ilike.%{q}%,model.ilike.%{q}%")

    # Order and limit
    query = query.order("dos_score", desc=True).limit(200)

    resp = query.execute()
    rows = resp.data or []

    results = [_row_to_result(row) for row in rows]

    # Cache in Redis for status endpoint
    job_data = {
        "job_id": job_id,
        "status": "complete",
        "results": results,
        "sources": {"Database": "done"},
        "timed_out": False,
    }
    await _store_job(job_id, job_data)

    logger.info(f"[SONAR] Search complete job={job_id} query={req.query!r} results={len(results)}")

    return {
        "job_id": job_id,
        "status": "complete",
        "results": results,
        "sources": {"Database": "done"},
        "timed_out": False,
    }


@router.get("/status/{job_id}")
async def sonar_status(job_id: str):
    """Retrieve cached search results by job ID."""
    job = await _load_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or expired")

    return {
        "status": job.get("status", "complete"),
        "results": job.get("results", []),
        "sources": job.get("sources", {}),
        "timed_out": job.get("timed_out", False),
    }
