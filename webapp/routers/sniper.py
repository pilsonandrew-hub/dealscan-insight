"""
SniperScope bid assistant router.

Endpoints:
  POST   /api/sniper/targets          — arm a sniper target (auth required)
  GET    /api/sniper/targets          — list user's active targets (auth required)
  DELETE /api/sniper/targets/{id}     — cancel a target (auth required)
  POST   /api/sniper/check            — internal cron scheduler (shared secret)

Alert cadence: T-60min, T-15min, T-5min before auction close.
Ceiling exceeded alert fires immediately when current_bid >= max_bid.

Design principles:
- All DB operations non-fatal — log errors, never crash the endpoint.
- Telegram alerts fire-and-forget (asyncio.create_task).
- Follows auth pattern from webapp/routers/rover.py exactly.
- Reuses Telegram send pattern from webapp/routers/ingest.py.
"""

import asyncio
import hashlib
import logging
import os
import secrets
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Header, HTTPException

router = APIRouter(prefix="/api/sniper", tags=["sniper"])
logger = logging.getLogger(__name__)

# ─── Env / credentials ───────────────────────────────────────────────────────

_supabase_url = os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL", "")
_supabase_key = (
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    or os.getenv("SUPABASE_ANON_KEY")
    or os.getenv("VITE_SUPABASE_ANON_KEY", "")
)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
# Shared secret for the internal /api/sniper/check cron endpoint.
# Set SNIPER_CHECK_SECRET in Railway env vars.
SNIPER_CHECK_SECRET = os.getenv("SNIPER_CHECK_SECRET", "")

supa = None
try:
    if _supabase_url and _supabase_key:
        from supabase import create_client
        supa = create_client(_supabase_url, _supabase_key)
        logger.info("[SNIPER] Supabase client initialized")
    else:
        logger.warning("[SNIPER] Supabase client NOT initialized — missing env vars")
except Exception as _e:
    logger.warning(f"[SNIPER] Supabase client init failed (non-fatal): {_e}")


# ─── Auth helpers (mirrors rover.py pattern exactly) ─────────────────────────

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
    if not SNIPER_CHECK_SECRET:
        raise HTTPException(status_code=503, detail="Sniper check not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    token = authorization.split(" ", 1)[1]
    if not secrets.compare_digest(token, SNIPER_CHECK_SECRET):
        raise HTTPException(status_code=401, detail="Invalid sniper check secret")


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
            logger.info("[SNIPER] Telegram sent to chat_id=%s", chat_id)
    except Exception as exc:
        logger.error("[SNIPER] Telegram send failed (non-fatal): %s", exc)


def _build_alert_60min(opp: dict, target: dict) -> str:
    title = f"{opp.get('year','')} {opp.get('make','')} {opp.get('model','')}".strip()
    current = opp.get("current_bid") or 0
    ceiling = float(target.get("max_bid") or 0)
    state = opp.get("state", "?")
    source = opp.get("source", "?")
    opp_id = opp.get("id", "")
    lot_url = opp.get("listing_url", "")
    deal_url = f"https://dealscan-insight.vercel.app/deal/{opp_id}"
    return (
        f"⚡ *SniperScope Alert*\n"
        f"{title}\n"
        f"📍 {state} • {source}\n"
        f"💰 Current bid: ${current:,.0f}\n"
        f"🎯 Your ceiling: ${ceiling:,.0f}\n"
        f"⏰ Closes in *60 minutes*\n\n"
        f"👉 [Bid Now]({deal_url}) | [Direct →]({lot_url})"
    )


def _build_alert_15min(opp: dict, target: dict) -> str:
    title = f"{opp.get('year','')} {opp.get('make','')} {opp.get('model','')}".strip()
    current = opp.get("current_bid") or 0
    ceiling = float(target.get("max_bid") or 0)
    headroom = ceiling - current
    opp_id = opp.get("id", "")
    lot_url = opp.get("listing_url", "")
    deal_url = f"https://dealscan-insight.vercel.app/deal/{opp_id}"
    return (
        f"🔥 *FINAL WARNING — 15 Minutes*\n"
        f"{title}\n"
        f"💰 Current: ${current:,.0f} → Ceiling: ${ceiling:,.0f}\n"
        f"${headroom:,.0f} headroom remaining\n\n"
        f"👉 [BID NOW]({deal_url}) | [Direct →]({lot_url})"
    )


def _build_alert_5min(opp: dict, target: dict) -> str:
    title = f"{opp.get('year','')} {opp.get('make','')} {opp.get('model','')}".strip()
    current = opp.get("current_bid") or 0
    ceiling = float(target.get("max_bid") or 0)
    opp_id = opp.get("id", "")
    lot_url = opp.get("listing_url", "")
    deal_url = f"https://dealscan-insight.vercel.app/deal/{opp_id}"
    return (
        f"🚨 *5 MINUTES LEFT*\n"
        f"{title}\n"
        f"💰 ${current:,.0f} → ${ceiling:,.0f} ceiling\n"
        f"GO NOW 👉 [PLACE BID]({deal_url}) | [Direct →]({lot_url})"
    )


def _build_alert_close(opp: dict, target: dict) -> str:
    """Auction closed — prompt user to log outcome."""
    title = f"{opp.get('year','')} {opp.get('make','')} {opp.get('model','')}".strip()
    mileage = opp.get("mileage") or 0
    state = opp.get("state", "?")
    ceiling = float(target.get("max_bid") or 0)
    opp_id = opp.get("id", "")
    deal_url = f"https://dealscan-insight.vercel.app/deal/{opp_id}"
    return (
        f"🔔 *Auction Closed*\n\n"
        f"{title} • {mileage:,.0f} mi • {state}\n"
        f"Max Bid: ${ceiling:,.0f}\n\n"
        f"Did you bid? Log the outcome:\n{deal_url}"
    )


def _build_alert_ceiling_exceeded(opp: dict, target: dict) -> str:
    title = f"{opp.get('year','')} {opp.get('make','')} {opp.get('model','')}".strip()
    current = opp.get("current_bid") or 0
    ceiling = float(target.get("max_bid") or 0)
    opp_id = opp.get("id", "")
    lot_url = opp.get("listing_url", "")
    deal_url = f"https://dealscan-insight.vercel.app/deal/{opp_id}"
    msg = (
        f"❌ *SniperScope — Ceiling Exceeded*\n"
        f"{title}\n"
        f"Current bid (${current:,.0f}) exceeded your ceiling (${ceiling:,.0f})\n"
        f"Target cancelled."
    )
    if opp_id:
        msg += f"\n\n👉 [View Deal]({deal_url})"
        if lot_url:
            msg += f" | [Direct →]({lot_url})"
    elif lot_url:
        msg += f"\n\n👉 [View Listing]({lot_url})"
    return msg


# ─── POST /api/sniper/targets ─────────────────────────────────────────────────

@router.post("/targets")
async def create_sniper_target(
    payload: dict,
    authorization: Optional[str] = Header(None),
):
    """
    Arm a sniper target for an opportunity.

    Body: { opportunity_id, max_bid, telegram_chat_id? }
    Auth: Supabase JWT (Bearer token)
    """
    user_id = _verify_auth(authorization)

    opportunity_id = payload.get("opportunity_id")
    max_bid = payload.get("max_bid")
    telegram_chat_id = payload.get("telegram_chat_id") or ""

    if not opportunity_id:
        raise HTTPException(status_code=400, detail="opportunity_id is required")
    if not max_bid or float(max_bid) <= 0:
        raise HTTPException(status_code=400, detail="max_bid must be a positive number")

    if not supa:
        raise HTTPException(status_code=503, detail="Service unavailable")

    # Validate opportunity exists and auction hasn't ended
    try:
        opp_resp = (
            supa.table("opportunities")
            .select("id, auction_end_date, year, make, model, current_bid")
            .eq("id", str(opportunity_id))
            .limit(1)
            .execute()
        )
        if not opp_resp.data:
            raise HTTPException(status_code=404, detail="Opportunity not found")

        opp = opp_resp.data[0]
        auction_end = opp.get("auction_end_date")
        if auction_end:
            try:
                end_dt = datetime.fromisoformat(auction_end.replace("Z", "+00:00"))
                if end_dt <= datetime.now(timezone.utc):
                    raise HTTPException(status_code=400, detail="Auction has already ended")
            except HTTPException:
                raise
            except Exception:
                pass  # unparseable end date — allow the target

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[SNIPER] Opportunity lookup failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")

    # Check for existing active target (same user + opportunity)
    try:
        existing_check = (
            supa.table("sniper_targets")
            .select("id")
            .eq("user_id", user_id)
            .eq("opportunity_id", str(opportunity_id))
            .eq("status", "active")
            .limit(1)
            .execute()
        )
        if existing_check.data:
            raise HTTPException(
                status_code=409,
                detail="An active sniper target already exists for this opportunity",
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[SNIPER] Duplicate check failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")

    # Insert sniper target
    try:
        row = {
            "user_id": user_id,
            "opportunity_id": str(opportunity_id),
            "max_bid": float(max_bid),
            "status": "active",
            "alert_60min_sent": False,
            "alert_15min_sent": False,
            "alert_5min_sent": False,
            "telegram_chat_id": telegram_chat_id or None,
        }
        result = supa.table("sniper_targets").insert(row).execute()
        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to create sniper target")
        return {"ok": True, "target": result.data[0]}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[SNIPER] Target insert failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


# ─── GET /api/sniper/targets ──────────────────────────────────────────────────

@router.get("/targets")
async def list_sniper_targets(
    authorization: Optional[str] = Header(None),
):
    """
    List the authenticated user's active sniper targets, with opportunity details joined.
    """
    user_id = _verify_auth(authorization)

    if not supa:
        raise HTTPException(status_code=503, detail="Service unavailable")

    try:
        # Fetch active targets
        targets_resp = (
            supa.table("sniper_targets")
            .select("*")
            .eq("user_id", user_id)
            .eq("status", "active")
            .order("created_at", desc=True)
            .limit(50)
            .execute()
        )
        targets = targets_resp.data or []

        # Enrich with opportunity details
        enriched = []
        opp_ids = [t["opportunity_id"] for t in targets if t.get("opportunity_id")]
        opp_map: dict = {}
        if opp_ids:
            try:
                opps_resp = (
                    supa.table("opportunities")
                    .select(
                        "id, year, make, model, state, source, current_bid, auction_end_date, listing_url, image_url"
                    )
                    .in_("id", opp_ids)
                    .execute()
                )
                opp_map = {str(o["id"]): o for o in (opps_resp.data or [])}
            except Exception as exc:
                logger.warning("[SNIPER] Opportunity join failed (non-fatal): %s", exc)

        for target in targets:
            opp = opp_map.get(str(target.get("opportunity_id")), {})
            enriched.append({
                **target,
                "opportunity": opp,
            })

        return {"targets": enriched, "count": len(enriched)}

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[SNIPER] List targets failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


# ─── DELETE /api/sniper/targets/{target_id} ───────────────────────────────────

@router.delete("/targets/{target_id}")
async def cancel_sniper_target(
    target_id: str,
    authorization: Optional[str] = Header(None),
):
    """Cancel (soft-delete) a sniper target. Only the owner can cancel."""
    user_id = _verify_auth(authorization)

    if not supa:
        raise HTTPException(status_code=503, detail="Service unavailable")

    try:
        # Verify ownership
        existing = (
            supa.table("sniper_targets")
            .select("id, user_id, status")
            .eq("id", target_id)
            .limit(1)
            .execute()
        )
        if not existing.data:
            raise HTTPException(status_code=404, detail="Target not found")
        if existing.data[0]["user_id"] != user_id:
            raise HTTPException(status_code=403, detail="Forbidden")

        # Soft-cancel
        supa.table("sniper_targets").update({"status": "cancelled"}).eq("id", target_id).execute()
        return {"ok": True, "target_id": target_id, "status": "cancelled"}

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[SNIPER] Cancel target failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


# ─── Internal sniper check logic (called by scheduler + HTTP endpoint) ───────

async def _run_sniper_check_internal() -> dict:
    """
    Core sniper check logic — called directly by APScheduler and /api/sniper/check.
    Checks all active sniper targets and fires Telegram alerts at T-60, T-15, T-5.
    Also marks expired and ceiling-exceeded targets.

    Returns stats dict with targets_checked, alerts_sent, expired, ceiling_exceeded, errors.
    """
    if not supa:
        logger.error("[SNIPER_CHECK] Supabase unavailable")
        return {"ok": False, "error": "Supabase unavailable"}

    now = datetime.now(timezone.utc)
    stats = {
        "targets_checked": 0,
        "alerts_sent": 0,
        "expired": 0,
        "ceiling_exceeded": 0,
        "errors": 0,
    }

    try:
        # Fetch all active targets joined with opportunity data
        targets_resp = (
            supa.table("sniper_targets")
            .select(
                "id, user_id, opportunity_id, max_bid, telegram_chat_id, "
                "alert_60min_sent, alert_15min_sent, alert_5min_sent"
            )
            .eq("status", "active")
            .execute()
        )
        targets = targets_resp.data or []
    except Exception as exc:
        logger.error("[SNIPER_CHECK] Failed to fetch active targets: %s", exc)
        return {"ok": False, "error": str(exc)}

    logger.info("[SNIPER_CHECK] Processing %d active targets at %s", len(targets), now.isoformat())

    # Batch-fetch all relevant opportunities to avoid N+1 queries
    opp_ids = list({t["opportunity_id"] for t in targets if t.get("opportunity_id")})
    opp_map: dict = {}
    if opp_ids:
        try:
            opps_resp = (
                supa.table("opportunities")
                .select("id, year, make, model, state, source, current_bid, auction_end_date, listing_url")
                .in_("id", opp_ids)
                .execute()
            )
            opp_map = {str(o["id"]): o for o in (opps_resp.data or [])}
        except Exception as exc:
            logger.error("[SNIPER_CHECK] Opportunity batch fetch failed: %s", exc)

    alert_tasks = []

    for target in targets:
        stats["targets_checked"] += 1
        target_id = target["id"]
        opp_id = str(target.get("opportunity_id", ""))
        opp = opp_map.get(opp_id)

        if not opp:
            logger.warning("[SNIPER_CHECK] Opportunity %s not found for target %s", opp_id, target_id)
            continue

        max_bid = float(target.get("max_bid") or 0)
        current_bid = float(opp.get("current_bid") or 0)
        chat_id = target.get("telegram_chat_id") or ""
        auction_end_raw = opp.get("auction_end_date")

        # ── Ceiling exceeded check ────────────────────────────────────────────
        if current_bid >= max_bid > 0:
            try:
                supa.table("sniper_targets").update({"status": "ceiling_exceeded"}).eq("id", target_id).execute()
                stats["ceiling_exceeded"] += 1
                if chat_id:
                    msg = _build_alert_ceiling_exceeded(opp, target)
                    alert_tasks.append(asyncio.create_task(_send_telegram(chat_id, msg)))
                    stats["alerts_sent"] += 1
            except Exception as exc:
                logger.error("[SNIPER_CHECK] Ceiling exceeded update failed for %s: %s", target_id, exc)
                stats["errors"] += 1
            continue

        # ── Parse auction end time ────────────────────────────────────────────
        if not auction_end_raw:
            logger.debug(
                "[SNIPER_CHECK] Target %s skipped — opportunity %s has no auction_end_date",
                target_id, opp_id,
            )
            continue
        try:
            end_dt = datetime.fromisoformat(auction_end_raw.replace("Z", "+00:00"))
        except Exception:
            logger.warning("[SNIPER_CHECK] Unparseable auction_end_date for target %s: %s", target_id, auction_end_raw)
            continue

        minutes_to_close = (end_dt - now).total_seconds() / 60.0

        # ── Expired check ─────────────────────────────────────────────────────
        if minutes_to_close <= 0:
            try:
                supa.table("sniper_targets").update({"status": "expired"}).eq("id", target_id).execute()
                stats["expired"] += 1
            except Exception as exc:
                logger.error("[SNIPER_CHECK] Expiry update failed for %s: %s", target_id, exc)
                stats["errors"] += 1

            # ── Auction close alert — send once if chat_id exists ────────────
            if chat_id and not target.get("alert_close_sent"):
                try:
                    supa.table("sniper_targets").update({"alert_close_sent": True}).eq("id", target_id).execute()
                except Exception:
                    pass  # column may not exist yet — non-fatal
                msg = _build_alert_close(opp, target)
                alert_tasks.append(asyncio.create_task(_send_telegram(chat_id, msg)))
                stats["alerts_sent"] += 1
                logger.info("[SNIPER_CHECK] Close alert queued for target %s", target_id)

            continue

        # ── T-60 alert — atomic CAS: only update if flag is still False ─────────
        if 55 <= minutes_to_close <= 65 and not target.get("alert_60min_sent"):
            try:
                cas_result = (
                    supa.table("sniper_targets")
                    .update({"alert_60min_sent": True})
                    .eq("id", target_id)
                    .eq("alert_60min_sent", False)  # guard — only one concurrent writer wins
                    .execute()
                )
                if cas_result.data:  # we won the race
                    if chat_id:
                        msg = _build_alert_60min(opp, target)
                        alert_tasks.append(asyncio.create_task(_send_telegram(chat_id, msg)))
                        stats["alerts_sent"] += 1
                        logger.info("[SNIPER_CHECK] T-60 alert queued for target %s", target_id)
            except Exception as exc:
                logger.error("[SNIPER_CHECK] T-60 flag update failed for %s: %s", target_id, exc)
                stats["errors"] += 1

        # ── T-15 alert — atomic CAS ───────────────────────────────────────────
        if 10 <= minutes_to_close <= 20 and not target.get("alert_15min_sent"):
            try:
                cas_result = (
                    supa.table("sniper_targets")
                    .update({"alert_15min_sent": True})
                    .eq("id", target_id)
                    .eq("alert_15min_sent", False)
                    .execute()
                )
                if cas_result.data:
                    if chat_id:
                        msg = _build_alert_15min(opp, target)
                        alert_tasks.append(asyncio.create_task(_send_telegram(chat_id, msg)))
                        stats["alerts_sent"] += 1
                        logger.info("[SNIPER_CHECK] T-15 alert queued for target %s", target_id)
            except Exception as exc:
                logger.error("[SNIPER_CHECK] T-15 flag update failed for %s: %s", target_id, exc)
                stats["errors"] += 1

        # ── T-5 alert — atomic CAS ────────────────────────────────────────────
        if 0 <= minutes_to_close <= 7 and not target.get("alert_5min_sent"):
            try:
                cas_result = (
                    supa.table("sniper_targets")
                    .update({"alert_5min_sent": True})
                    .eq("id", target_id)
                    .eq("alert_5min_sent", False)
                    .execute()
                )
                if cas_result.data:
                    if chat_id:
                        msg = _build_alert_5min(opp, target)
                        alert_tasks.append(asyncio.create_task(_send_telegram(chat_id, msg)))
                        stats["alerts_sent"] += 1
                        logger.info("[SNIPER_CHECK] T-5 alert queued for target %s", target_id)
            except Exception as exc:
                logger.error("[SNIPER_CHECK] T-5 flag update failed for %s: %s", target_id, exc)
                stats["errors"] += 1

    # Fire all Telegram tasks concurrently (fire-and-forget)
    if alert_tasks:
        try:
            await asyncio.gather(*alert_tasks, return_exceptions=True)
        except Exception as exc:
            logger.warning("[SNIPER_CHECK] Alert gather error (non-fatal): %s", exc)

    logger.info(
        "[SNIPER_CHECK] Done | checked=%d alerts=%d expired=%d ceiling_exceeded=%d errors=%d",
        stats["targets_checked"],
        stats["alerts_sent"],
        stats["expired"],
        stats["ceiling_exceeded"],
        stats["errors"],
    )
    return {"ok": True, **stats}


# ─── POST /api/sniper/check (HTTP endpoint wrapper) ──────────────────────────

@router.post("/check")
async def sniper_check(
    authorization: Optional[str] = Header(None),
):
    """
    HTTP endpoint for sniper check — supports manual trigger and legacy GitHub Actions.
    Auth: Bearer {SNIPER_CHECK_SECRET}
    """
    _verify_check_secret(authorization)
    return await _run_sniper_check_internal()
# codex_write_test
