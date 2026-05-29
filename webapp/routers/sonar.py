"""
Sonar — Vehicle search via Supabase opportunities index.

Endpoints:
  POST /api/sonar/search      — query Supabase, return results instantly
  GET  /api/sonar/status/{id}  — retrieve cached results by job ID
"""

import json
import logging
import uuid
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone

try:
    import redis.asyncio as redis
except ModuleNotFoundError:  # pragma: no cover - exercised in minimal test envs
    redis = None
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from supabase import create_client

from config.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sonar", tags=["sonar"])

JOB_TTL_SECONDS = 300

SUPABASE_URL = settings.supabase_url
SUPABASE_ANON_KEY = (
    os.getenv("SUPABASE_ANON_KEY")
    or os.getenv("VITE_SUPABASE_ANON_KEY")
    or os.getenv("VITE_SUPABASE_PUBLISHABLE_KEY")
)
SUPABASE_SERVICE_ROLE_KEY = settings.supabase_service_role_key


# ── Models ────────────────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str
    min_price: float = Field(default=0, ge=0)
    max_price: float = Field(default=75000, ge=0)
    extended: bool = False


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


# ── Auth helpers ──────────────────────────────────────────────────────────────

def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = authorization.replace("Bearer ", "", 1).strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing authentication token")
    return token


def _supabase_auth_api_key() -> str:
    """Return the anon/publishable key used for Supabase Auth introspection.

    Token introspection does not require service-role privileges. Falling back
    to the service-role key would turn an anon-key misconfiguration into silent
    privilege escalation, so Sonar fails closed when no anon/publishable key is
    configured.
    """
    return (SUPABASE_ANON_KEY or "").strip()


def _fetch_supabase_user(token: str) -> dict:
    """Validate a Supabase access token through Supabase Auth REST.

    This avoids relying on supabase-py auth header behavior in Railway while
    preserving the same security boundary: Supabase Auth validates signature,
    expiry, issuer, and revocation state and returns the authenticated user.
    """
    api_key = _supabase_auth_api_key()
    if not SUPABASE_URL or not api_key:
        raise HTTPException(status_code=503, detail="Authentication service unavailable")

    req = urllib.request.Request(
        f"{SUPABASE_URL.rstrip('/')}/auth/v1/user",
        headers={"apikey": api_key, "Authorization": f"Bearer {token}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        if exc.code in {400, 401, 403}:
            raise HTTPException(status_code=401, detail="Authentication failed") from exc
        logger.warning("[SONAR_AUTH] Supabase auth HTTP %s", exc.code)
        raise HTTPException(status_code=503, detail="Authentication service unavailable") from exc
    except Exception as exc:
        logger.warning("[SONAR_AUTH] Supabase auth validation failed: %s", exc)
        raise HTTPException(status_code=503, detail="Authentication service unavailable") from exc


def _extract_user_id(user_response) -> str | None:
    if isinstance(user_response, dict):
        return user_response.get("id") or user_response.get("sub")
    user = getattr(user_response, "user", None)
    if user is None:
        return None
    if isinstance(user, dict):
        return user.get("id") or user.get("sub")
    return getattr(user, "id", None) or getattr(user, "sub", None)


def require_sonar_user_id(authorization: str | None = Header(None, alias="Authorization")) -> str:
    """Validate the caller Supabase JWT and return the authenticated user id."""
    token = _extract_bearer_token(authorization)
    user_response = _fetch_supabase_user(token)
    user_id = _extract_user_id(user_response)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication failed")
    return str(user_id)

# ── Redis helper ──────────────────────────────────────────────────────────────

_redis_pool = None


async def _get_redis():
    global _redis_pool
    if _redis_pool is not None:
        return _redis_pool
    if redis is None:
        return None
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


PARTS_KEYWORDS = [
    "bulb", "tire", "tires", "wheel", "wheels", "seat", "seats", "door",
    "mirror", "hood", "bumper", "fender", "engine part", "transmission part",
    "headlight", "taillight", "brake pad", "oil filter", "air filter",
    "spark plug", "wiper", "battery charger", "jack stand", "lug nut",
]


def _is_parts_listing(title: str, make: str) -> bool:
    """Return True if the listing looks like a parts/accessories item."""
    if make:
        return False
    title_lower = title.lower()
    return any(kw in title_lower for kw in PARTS_KEYWORDS)


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

    mileage = row.get("mileage")
    if mileage is None:
        mileage = row.get("odometer")

    return SonarResult(
        id=str(row.get("id", "")),
        title=title,
        year=int(year) if year else None,
        make=make,
        model=model,
        trim=row.get("trim") or "",
        currentBid=float(row.get("current_bid") or 0),
        timeRemaining=_time_remaining(row.get("auction_end_date")),
        endsAt=str(ends_at) if ends_at else "",
        location=location,
        condition="",
        sourceName=row.get("source") or row.get("source_site") or "",
        sourceUrl=row.get("listing_url") or "",
        mileage=mileage,
        auctionSource=row.get("source") or "",
        issuingAgency=row.get("agency_name") or "",
        titleStatus=row.get("title_status") or row.get("condition_grade") or "Unknown",
        isAsIs=True,
        photoUrl=row.get("image_url") or row.get("photo_url") or row.get("thumbnail_url") or "",
    ).model_dump()


# ── Supabase client ──────────────────────────────────────────────────────────

def _get_supabase():
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise HTTPException(status_code=503, detail="Supabase credentials not configured")
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/search")
async def sonar_search(req: SearchRequest, authorization: str | None = Header(None, alias="Authorization")):
    """Query the Supabase opportunities index and return results instantly."""
    user_id = require_sonar_user_id(authorization)
    sb = _get_supabase()
    job_id = uuid.uuid4().hex

    if req.extended:
        # Extended mode — query sonar_listings, no DOS/state/mileage filters
        query = sb.table("sonar_listings").select("*")
    else:
        # Standard mode — filtered opportunities
        query = sb.table("opportunities").select("*").eq("is_active", True).gte("dos_score", 50)

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
    query = query.order("created_at", desc=True).limit(200) if req.extended else query.order("dos_score", desc=True).limit(200)

    resp = query.execute()
    rows = resp.data or []

    results = [_row_to_result(row) for row in rows]
    results = [r for r in results if not _is_parts_listing(r.get("title", ""), r.get("make", ""))]

    # Cache in Redis for status endpoint
    job_data = {
        "job_id": job_id,
        "user_id": user_id,
        "status": "complete",
        "results": results,
        "sources": {"Database": "done"},
        "timed_out": False,
    }
    await _store_job(job_id, job_data)

    logger.info(f"[SONAR] Search complete job={job_id} user={user_id} query={req.query!r} results={len(results)}")

    return {
        "job_id": job_id,
        "status": "complete",
        "results": results,
        "sources": {"Database": "done"},
        "timed_out": False,
    }


@router.get("/status/{job_id}")
async def sonar_status(job_id: str, authorization: str | None = Header(None, alias="Authorization")):
    """Retrieve cached search results by job ID."""
    user_id = require_sonar_user_id(authorization)
    job = await _load_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or expired")
    if str(job.get("user_id") or "") != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to access this job")

    return {
        "status": job.get("status", "complete"),
        "results": job.get("results", []),
        "sources": job.get("sources", {}),
        "timed_out": job.get("timed_out", False),
    }
