"""
Saved Searches router — Crosshair alerts via Telegram.

Endpoints:
  POST   /api/saved-searches              — create a saved search (auth required)
  GET    /api/saved-searches              — list user's saved searches (auth required)
  DELETE /api/saved-searches/{id}         — delete a saved search (auth required)
  POST   /api/saved-searches/check        — scheduler endpoint (shared secret)
                                            checks new deals against all saved searches,
                                            fires Telegram alert when match found
                                            with DOS >= threshold.

Design principles:
- Mirrors sniper.py auth + Telegram patterns exactly.
- All DB operations non-fatal — log errors, never crash the endpoint.
- Telegram alerts fire-and-forget (asyncio.create_task).
- /check endpoint guarded by SAVED_SEARCH_SECRET shared secret.
"""

import asyncio
import logging
import os
import secrets
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Header, HTTPException

router = APIRouter(prefix="/api/saved-searches", tags=["saved_searches"])
logger = logging.getLogger(__name__)

# ─── Env / credentials ───────────────────────────────────────────────────────

_supabase_url = os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL", "")
_supabase_key = (
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    or os.getenv("SUPABASE_ANON_KEY")
    or os.getenv("VITE_SUPABASE_ANON_KEY", "")
)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
SAVED_SEARCH_SECRET = os.getenv("SAVED_SEARCH_SECRET", "")

supa = None
try:
    if _supabase_url and _supabase_key:
        from supabase import create_client
        supa = create_client(_supabase_url, _supabase_key)
        logger.info("[SAVED_SEARCHES] Supabase client initialized")
    else:
        logger.warning("[SAVED_SEARCHES] Supabase client NOT initialized — missing env vars")
except Exception as _e:
    logger.warning(f"[SAVED_SEARCHES] Supabase client init failed (non-fatal): {_e}")


# ─── Auth helpers (mirrors sniper.py pattern exactly) ─────────────────────────

def _verify_auth(authorization: Optional[str]) -> str:
    """Validate Supabase JWT. Returns user_id on success. Raises 401 on failure."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    token = authorization.split(" ", 1)[1]
    if not supa:
        raise HTTPException(status_code=503, detail="Service unavailable")
    try:
        user = supa.auth.get_user(token)
        if not user or not user.user:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        return user.user.id
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def _verify_check_secret(authorization: Optional[str]) -> None:
    """Verify the internal cron shared secret."""
    if not SAVED_SEARCH_SECRET:
        raise HTTPException(status_code=503, detail="Saved search check not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    token = authorization.split(" ", 1)[1]
    if not secrets.compare_digest(token, SAVED_SEARCH_SECRET):
        raise HTTPException(status_code=401, detail="Invalid saved search secret")


# ─── Telegram helpers ─────────────────────────────────────────────────────────

async def _send_telegram(chat_id: str, text: str) -> None:
    """Fire-and-forget Telegram message. Non-fatal on any error."""
    if not TELEGRAM_BOT_TOKEN or not chat_id:
        return
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": False,
                },
            )
            resp.raise_for_status()
            logger.info("[SAVED_SEARCHES] Telegram sent to chat_id=%s", chat_id)
    except Exception as exc:
        logger.error("[SAVED_SEARCHES] Telegram send failed (non-fatal): %s", exc)


def _build_alert(saved_search: dict, opp: dict) -> str:
    """Build Telegram alert message for a saved search match."""
    name = saved_search.get("name", "Saved Search")
    title = f"{opp.get('year', '')} {opp.get('make', '')} {opp.get('model', '')}".strip()
    dos = opp.get("dos_score") or 0
    current = opp.get("current_bid") or 0
    state = opp.get("state", "?")
    source = opp.get("source", "?")
    opp_id = opp.get("id", "")
    lot_url = opp.get("listing_url", "")
    deal_url = f"https://dealscan-insight.vercel.app/deal/{opp_id}"

    msg = (
        f"🎯 *Saved Search Match: {name}*\n"
        f"{title}\n"
        f"📍 {state} • {source}\n"
        f"💰 Current bid: ${current:,.0f}\n"
        f"📊 DOS Score: *{dos}*\n\n"
        f"👉 [View Deal]({deal_url})"
    )
    if lot_url:
        msg += f" | [Direct →]({lot_url})"
    return msg


# ─── POST /api/saved-searches ─────────────────────────────────────────────────

@router.post("")
async def create_saved_search(
    payload: dict,
    authorization: Optional[str] = Header(None),
):
    """
    Create a saved search.

    Body: { name, filters, dos_threshold?, telegram_chat_id? }
    Auth: Supabase JWT (Bearer token)
    """
    user_id = _verify_auth(authorization)

    name = (payload.get("name") or "").strip()
    filters = payload.get("filters") or {}
    dos_threshold = int(payload.get("dos_threshold") or 65)
    telegram_chat_id = (payload.get("telegram_chat_id") or "").strip() or None

    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    if not isinstance(filters, dict):
        raise HTTPException(status_code=400, detail="filters must be an object")
    if dos_threshold < 0 or dos_threshold > 100:
        raise HTTPException(status_code=400, detail="dos_threshold must be between 0 and 100")

    if not supa:
        raise HTTPException(status_code=503, detail="Service unavailable")

    try:
        row = {
            "user_id": user_id,
            "name": name,
            "filters": filters,
            "dos_threshold": dos_threshold,
            "telegram_chat_id": telegram_chat_id,
        }
        result = supa.table("saved_searches").insert(row).execute()
        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to create saved search")
        return {"ok": True, "saved_search": result.data[0]}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[SAVED_SEARCHES] Insert failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


# ─── GET /api/saved-searches ──────────────────────────────────────────────────

@router.get("")
async def list_saved_searches(
    authorization: Optional[str] = Header(None),
):
    """List the authenticated user's saved searches."""
    user_id = _verify_auth(authorization)

    if not supa:
        raise HTTPException(status_code=503, detail="Service unavailable")

    try:
        resp = (
            supa.table("saved_searches")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(100)
            .execute()
        )
        return {"saved_searches": resp.data or [], "count": len(resp.data or [])}
    except Exception as exc:
        logger.error("[SAVED_SEARCHES] List failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


# ─── DELETE /api/saved-searches/{id} ─────────────────────────────────────────

@router.delete("/{search_id}")
async def delete_saved_search(
    search_id: str,
    authorization: Optional[str] = Header(None),
):
    """Delete a saved search. Only the owner can delete."""
    user_id = _verify_auth(authorization)

    if not supa:
        raise HTTPException(status_code=503, detail="Service unavailable")

    try:
        existing = (
            supa.table("saved_searches")
            .select("id, user_id")
            .eq("id", search_id)
            .limit(1)
            .execute()
        )
        if not existing.data:
            raise HTTPException(status_code=404, detail="Saved search not found")
        if existing.data[0]["user_id"] != user_id:
            raise HTTPException(status_code=403, detail="Forbidden")

        supa.table("saved_searches").delete().eq("id", search_id).execute()
        return {"ok": True, "id": search_id}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[SAVED_SEARCHES] Delete failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


# ─── POST /api/saved-searches/check (internal cron endpoint) ─────────────────

@router.post("/check")
async def saved_searches_check(
    authorization: Optional[str] = Header(None),
):
    """
    Internal scheduler endpoint — called by GitHub Actions every 30 minutes.
    Checks new opportunities against all saved searches. Fires Telegram alert
    when a match is found with DOS >= dos_threshold.

    Auth: Bearer {SAVED_SEARCH_SECRET}
    """
    _verify_check_secret(authorization)

    if not supa:
        logger.error("[SAVED_SEARCHES_CHECK] Supabase unavailable")
        return {"ok": False, "error": "Supabase unavailable"}

    now = datetime.now(timezone.utc)
    stats = {
        "searches_checked": 0,
        "alerts_sent": 0,
        "errors": 0,
    }

    # Fetch all saved searches that have a telegram_chat_id configured
    try:
        searches_resp = (
            supa.table("saved_searches")
            .select("*")
            .not_.is_("telegram_chat_id", "null")
            .execute()
        )
        searches = searches_resp.data or []
    except Exception as exc:
        logger.error("[SAVED_SEARCHES_CHECK] Failed to fetch saved searches: %s", exc)
        return {"ok": False, "error": str(exc)}

    logger.info(
        "[SAVED_SEARCHES_CHECK] Processing %d saved searches at %s",
        len(searches), now.isoformat()
    )

    alert_tasks = []

    for ss in searches:
        stats["searches_checked"] += 1
        ss_id = ss["id"]
        filters = ss.get("filters") or {}
        dos_threshold = int(ss.get("dos_threshold") or 65)
        chat_id = ss.get("telegram_chat_id") or ""
        last_alerted = ss.get("last_alerted_at")

        # Build query for new opportunities matching this saved search's filters
        try:
            query = (
                supa.table("opportunities")
                .select("id, year, make, model, state, source, current_bid, dos_score, listing_url, created_at")
                .gte("dos_score", dos_threshold)
                .order("dos_score", desc=True)
                .limit(3)
            )

            # Apply saved filter fields if present
            if filters.get("make"):
                query = query.ilike("make", f"%{filters['make']}%")
            if filters.get("model"):
                query = query.ilike("model", f"%{filters['model']}%")
            if filters.get("state"):
                query = query.eq("state", filters["state"])
            if filters.get("yearMin"):
                query = query.gte("year", int(filters["yearMin"]))
            if filters.get("yearMax"):
                query = query.lte("year", int(filters["yearMax"]))
            if filters.get("minPrice"):
                query = query.gte("current_bid", int(filters["minPrice"]))
            if filters.get("maxPrice"):
                query = query.lte("current_bid", int(filters["maxPrice"]))

            # Only look at deals newer than last alert (or last 30 min if never alerted)
            if last_alerted:
                query = query.gt("created_at", last_alerted)
            else:
                cutoff = datetime.now(timezone.utc).replace(
                    minute=(datetime.now(timezone.utc).minute // 30) * 30,
                    second=0, microsecond=0
                )
                query = query.gt("created_at", cutoff.isoformat())

            result = query.execute()
            matches = result.data or []
        except Exception as exc:
            logger.error("[SAVED_SEARCHES_CHECK] Query failed for search %s: %s", ss_id, exc)
            stats["errors"] += 1
            continue

        if not matches:
            continue

        # Fire an alert for the best match (highest DOS)
        best = matches[0]
        if chat_id:
            msg = _build_alert(ss, best)
            alert_tasks.append(asyncio.create_task(_send_telegram(chat_id, msg)))
            stats["alerts_sent"] += 1
            logger.info(
                "[SAVED_SEARCHES_CHECK] Alert queued for search=%s opp=%s dos=%s",
                ss_id, best.get("id"), best.get("dos_score")
            )

        # Update last_alerted_at
        try:
            supa.table("saved_searches").update(
                {"last_alerted_at": now.isoformat()}
            ).eq("id", ss_id).execute()
        except Exception as exc:
            logger.warning("[SAVED_SEARCHES_CHECK] Failed to update last_alerted_at for %s: %s", ss_id, exc)

    if alert_tasks:
        try:
            await asyncio.gather(*alert_tasks, return_exceptions=True)
        except Exception as exc:
            logger.warning("[SAVED_SEARCHES_CHECK] Alert gather error (non-fatal): %s", exc)

    logger.info(
        "[SAVED_SEARCHES_CHECK] Done | searches=%d alerts=%d errors=%d",
        stats["searches_checked"], stats["alerts_sent"], stats["errors"]
    )
    return {"ok": True, **stats}
