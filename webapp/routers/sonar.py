"""
Sonar Phase 1 — Live vehicle search across GovDeals, PublicSurplus, HiBid.

Endpoints:
  POST /api/sonar/search      — kick off parallel Apify actor runs
  GET  /api/sonar/status/{id}  — poll run status + fetch results when done
"""

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
import redis.asyncio as redis
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from config.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sonar", tags=["sonar"])

# ── Apify config ──────────────────────────────────────────────────────────────

APIFY_TOKEN = (os.getenv("APIFY_API_TOKEN") or os.getenv("APIFY_TOKEN") or "").strip()
APIFY_BASE = "https://api.apify.com/v2"

ACTORS = {
    "GovDeals":       "CuKaIAcWyFS0EPrAz",
    "PublicSurplus":  "9xxQLlRsROnSgA42i",
    "HiBid":          "7s9e0eATTt1kuGGfE",
    "MuniciBid":      "svmsItf3CRBZuIntp",
    "GSAAuctions":    "fvDnYmGuFBCrwpEi9",
    "AllSurplus":     "gYGIfHeYeN3EzmLnB",
    "GovPlanet":      "pO2t5UDoSVmO1gvKJ",
    "Proxibid":       "bxhncvtHEP712WX2e",
    "EquipmentFacts": "0XjoegYZVcPldLstl",
    "USGovBid":       "6XO9La81aEmtsCT3g",
    "JJKane":         "lvb7T6VMFfNUQpqlq",
    "BidSpotter":     "5Eu3hfCcBBdzp6I1u",
}

JOB_TTL_SECONDS = 300
POLL_TIMEOUT_SECONDS = 240


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
        import json
        await r.set(f"sonar:{job_id}", json.dumps(data), ex=JOB_TTL_SECONDS)
    else:
        _memory_store[job_id] = data


async def _load_job(job_id: str) -> dict | None:
    r = await _get_redis()
    if r:
        import json
        raw = await r.get(f"sonar:{job_id}")
        return json.loads(raw) if raw else None
    return _memory_store.get(job_id)


# ── Apify helpers ─────────────────────────────────────────────────────────────

async def _start_actor(client: httpx.AsyncClient, actor_id: str, body: dict) -> str | None:
    """Start an Apify actor run, return the run ID or None on failure."""
    url = f"{APIFY_BASE}/acts/{actor_id}/runs"
    try:
        resp = await client.post(
            url,
            json=body,
            headers={"Authorization": f"Bearer {APIFY_TOKEN}"},
            timeout=15,
        )
        if resp.status_code in (200, 201):
            return resp.json().get("data", {}).get("id")
        logger.warning(f"[SONAR] Actor {actor_id} start failed: {resp.status_code} {resp.text[:200]}")
    except Exception as e:
        logger.warning(f"[SONAR] Actor {actor_id} start error: {e}")
    return None


async def _get_run_status(client: httpx.AsyncClient, run_id: str) -> str:
    """Return Apify run status string (READY, RUNNING, SUCCEEDED, FAILED, etc.)."""
    url = f"{APIFY_BASE}/actor-runs/{run_id}"
    try:
        resp = await client.get(
            url,
            headers={"Authorization": f"Bearer {APIFY_TOKEN}"},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json().get("data", {}).get("status", "UNKNOWN")
    except Exception as e:
        logger.warning(f"[SONAR] Run {run_id} status error: {e}")
    return "UNKNOWN"


async def _get_dataset_items(client: httpx.AsyncClient, run_id: str, limit: int = 50) -> list[dict]:
    """Fetch dataset items from a completed Apify run."""
    url = f"{APIFY_BASE}/actor-runs/{run_id}/dataset/items?limit={limit}"
    try:
        resp = await client.get(
            url,
            headers={"Authorization": f"Bearer {APIFY_TOKEN}"},
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json() if isinstance(resp.json(), list) else []
    except Exception as e:
        logger.warning(f"[SONAR] Dataset fetch error for run {run_id}: {e}")
    return []


# ── Normalize actor items to SonarResult ──────────────────────────────────────

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


def _normalize_item(item: dict, source_name: str) -> dict:
    """Convert a raw actor dataset item into the SonarResult shape."""
    # Common field mappings across all three actors
    title = item.get("title") or item.get("lead") or ""
    year = item.get("year") or item.get("modelYear")
    make = item.get("make") or item.get("makebrand") or ""
    model = item.get("model") or ""
    current_bid = (
        item.get("current_bid")
        or item.get("currentBid")
        or item.get("assetBidPrice")
        or 0
    )
    ends_at = (
        item.get("auction_end_time")
        or item.get("auction_end_date")
        or item.get("auctionEndUtc")
        or item.get("bidCloseDateTime")
        or ""
    )
    state = item.get("state") or item.get("location_state") or ""
    city = item.get("city") or item.get("locationCity") or ""
    location = f"{city}, {state}".strip(", ") if city or state else item.get("location", "")
    photo_url = (
        item.get("photo_url")
        or item.get("image_url")
        or item.get("photoUrl")
        or ""
    )
    source_url = item.get("listing_url") or item.get("listingUrl") or ""
    mileage = item.get("mileage") or item.get("meterCount")
    agency = item.get("agency_name") or item.get("seller") or item.get("auction_name") or ""
    title_status = item.get("title_status") or "Unknown"
    vin = item.get("vin") or ""

    try:
        year_int = int(year) if year else None
    except (ValueError, TypeError):
        year_int = None

    return SonarResult(
        id=f"snr-{source_name.lower()[:3]}-{uuid.uuid4().hex[:8]}",
        title=title,
        year=year_int,
        make=make,
        model=model,
        trim="",
        currentBid=float(current_bid),
        timeRemaining=_time_remaining(ends_at if ends_at else None),
        endsAt=str(ends_at) if ends_at else "",
        location=location,
        condition=vin if vin else "",
        sourceName=source_name,
        sourceUrl=source_url,
        mileage=mileage,
        auctionSource=source_name,
        issuingAgency=agency,
        titleStatus=str(title_status).capitalize() if title_status else "Unknown",
        isAsIs=True,
        photoUrl=photo_url,
    ).model_dump()


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/search")
async def sonar_search(req: SearchRequest):
    """Kick off parallel Apify actor runs for a vehicle search query."""
    if not APIFY_TOKEN:
        raise HTTPException(status_code=503, detail="Apify token not configured")

    job_id = uuid.uuid4().hex
    runs: dict[str, str | None] = {}

    actor_input = {
        "searchQuery": req.query,
        "minBid": req.min_price,
        "maxBid": req.max_price,
        "maxPages": 2,
    }

    async with httpx.AsyncClient() as client:
        import asyncio
        tasks = {
            name: _start_actor(client, actor_id, actor_input)
            for name, actor_id in ACTORS.items()
        }
        results = await asyncio.gather(*tasks.values())
        for name, run_id in zip(tasks.keys(), results):
            runs[name] = run_id

    job_data = {
        "job_id": job_id,
        "query": req.query,
        "runs": runs,
        "status": "running",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await _store_job(job_id, job_data)

    logger.info(f"[SONAR] Search started job={job_id} query={req.query!r} runs={runs}")
    logger.info(f"[SONAR] APIFY_TOKEN set: {bool(APIFY_TOKEN)}, token prefix: {APIFY_TOKEN[:15] if APIFY_TOKEN else 'NONE'}")

    return {"job_id": job_id, "status": "running"}


@router.get("/status/{job_id}")
async def sonar_status(job_id: str):
    """Poll status of a Sonar search job. Returns results when actors complete."""
    job = await _load_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or expired")

    runs: dict = job.get("runs", {})
    sources: dict[str, str] = {}
    all_results: list[dict] = []
    all_done = True

    async with httpx.AsyncClient() as client:
        for source_name, run_id in runs.items():
            if not run_id:
                sources[source_name] = "error"
                continue

            run_status = await _get_run_status(client, run_id)

            if run_status == "SUCCEEDED":
                sources[source_name] = "done"
                items = await _get_dataset_items(client, run_id)
                for item in items:
                    normalized = _normalize_item(item, source_name)
                    # Filter by search query
                    query_lower = job.get("query", "").lower()
                    title = f"{normalized.get('year','')} {normalized.get('make','')} {normalized.get('model','')} {normalized.get('title','')}".lower()
                    if query_lower and not any(q in title for q in query_lower.split()):
                        continue
                    # Skip zero/suspiciously low bids
                    bid = normalized.get('currentBid') or 0
                    try:
                        if float(bid) < 100:
                            continue
                    except (TypeError, ValueError):
                        pass
                    all_results.append(normalized)
            elif run_status in ("FAILED", "ABORTED", "TIMED-OUT"):
                sources[source_name] = "error"
                logger.warning(f"[SONAR] {source_name} run {run_id} status={run_status}")
            else:
                sources[source_name] = "scanning"
                all_done = False

    # Check if job has timed out
    created = job.get("created_at", "")
    timed_out = False
    if created:
        try:
            created_dt = datetime.fromisoformat(created)
            elapsed = (datetime.now(timezone.utc) - created_dt).total_seconds()
            if elapsed > POLL_TIMEOUT_SECONDS:
                timed_out = True
                all_done = True
        except Exception:
            pass

    # Deduplicate by sourceUrl
    seen_urls = set()
    deduped = []
    for r in all_results:
        url = r.get('sourceUrl','')
        if url not in seen_urls:
            seen_urls.add(url)
            deduped.append(r)
    all_results = deduped

    overall_status = "complete" if all_done else "running"

    if all_done:
        job["status"] = "complete"
        await _store_job(job_id, job)

    return {
        "status": overall_status,
        "results": all_results,
        "sources": sources,
        "timed_out": timed_out,
    }

@router.get("/debug-token")
async def sonar_debug_token():
    """Debug: check Apify token and connectivity from Railway."""
    import httpx
    token = APIFY_TOKEN
    result = {
        "token_set": bool(token),
        "token_prefix": token[:20] if token else "NONE",
        "token_length": len(token) if token else 0,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.apify.com/v2/users/me",
                headers={"Authorization": f"Bearer {token}"}
            )
            result["apify_status"] = resp.status_code
            result["apify_response"] = resp.json().get("data", {}).get("username", "?") if resp.status_code == 200 else resp.text[:200]
    except Exception as e:
        result["apify_error"] = str(e)
    return result
