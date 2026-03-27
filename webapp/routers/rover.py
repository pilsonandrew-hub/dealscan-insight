"""
Rover recommendation engine endpoints.
Implements preference-based deal ranking with event weighting + decay.

Fixes applied (2026-03-11):
- Auth required on both endpoints (Supabase JWT validation)
- 500 errors genericized (no internals leaked)
- apply_decay bug note documented

Redis affinity vectors added (2026-03-14):
- increment_affinity() called after each event (non-fatal if Redis down)
- get_recommendations() re-ranks by affinity boost (up to +15 pts)
"""
from fastapi import APIRouter, Depends, HTTPException, Header, status
from supabase import Client, create_client
from supabase.lib.client_options import ClientOptions
from typing import Any, Optional
from datetime import datetime, timezone
import time
import os
import logging
import uuid
from backend.rover.heuristic_scorer import build_preference_vector, score_item, rank_opportunities

router = APIRouter(prefix="/api/rover", tags=["rover"])
logger = logging.getLogger(__name__)

_event_rate: dict[str, list[float]] = {}

_VALID_EVENT_TYPES = ['view', 'click', 'save', 'bid', 'purchase', 'pass']

# Prefer backend-only env vars; fall back to VITE_* for compatibility during transition
from backend.ingest.config_loader import get_config as _get_config
SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL") or _get_config("SUPABASE_URL") or ""
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY") or _get_config("SUPABASE_ANON_KEY") or ""

# Background-only client for auth verification.
_background_supabase_client: Optional[Client] = None
try:
    if SUPABASE_URL and SUPABASE_ANON_KEY:
        _background_supabase_client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
except Exception as _e:
    logger.warning(f"Rover Supabase client init failed (non-fatal): {_e}")

# Service-role client reserved for write operations only.
_write_supabase_client: Optional[Client] = None
try:
    service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if SUPABASE_URL and service_role_key:
        _write_supabase_client = create_client(SUPABASE_URL, service_role_key)
except Exception as _e:
    logger.warning(f"Rover write Supabase client init failed (non-fatal): {_e}")

_redis_client = None
try:
    from backend.rover.redis_affinity import get_redis_client
    _redis_client = get_redis_client()
    if _redis_client:
        logger.info("[ROVER] Redis affinity client initialised")
    else:
        logger.info("[ROVER] Redis not configured — affinity disabled")
except Exception as _re:
    logger.warning(f"[ROVER] Redis affinity init failed (non-fatal): {_re}")


def get_user_supabase_client(authorization: str = Header(..., alias="Authorization")) -> Client:
    """Create a user-scoped Supabase client that forwards the caller JWT for RLS."""
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Supabase configuration missing (URL or anon key).",
        )

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format. Expected 'Bearer <token>'.",
        )

    token = authorization.replace("Bearer ", "", 1).strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token.",
        )

    try:
        return create_client(
            SUPABASE_URL,
            SUPABASE_ANON_KEY,
            options=ClientOptions(headers={"Authorization": f"Bearer {token}"}),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {exc}",
        )


def _coerce_number(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _serialize_recommendation(row: dict) -> dict:
    dos_score = _coerce_number(row.get("dos_score", row.get("score")), 0.0)
    current_bid = _coerce_number(row.get("current_bid", row.get("buy_now_price")), 0.0)
    estimated_sale_price = _coerce_number(row.get("estimated_sale_price", row.get("mmr")), 0.0)
    price = current_bid or estimated_sale_price
    roi = _coerce_number(row.get("roi_percentage", row.get("roi")), 0.0)
    profit = _coerce_number(row.get("potential_profit", row.get("gross_margin", row.get("profit_margin"))), 0.0)

    mmr_val = _coerce_number(row.get("mmr", row.get("estimated_sale_price")), 0.0)

    # Build human-readable "why this deal?" signal list for the UI tooltip
    why_signals: list[str] = []
    if dos_score >= 80:
        why_signals.append(f"Top-tier DOS score ({dos_score:.0f})")
    elif dos_score >= 65:
        why_signals.append(f"Solid DOS score ({dos_score:.0f})")
    if roi >= 25:
        why_signals.append(f"Excellent {roi:.0f}% ROI")
    elif roi >= 15:
        why_signals.append(f"{roi:.0f}% ROI")
    if profit >= 2000:
        why_signals.append(f"${profit:,.0f} profit potential")
    inv_grade = row.get("investment_grade")
    if inv_grade in ("Platinum", "Gold"):
        why_signals.append(f"{inv_grade} investment grade")
    if mmr_val and price and price < mmr_val:
        under_pct = (mmr_val - price) / mmr_val * 100
        if under_pct >= 10:
            why_signals.append(f"{under_pct:.0f}% below MMR")
    state = row.get("state")
    if state:
        why_signals.append(f"{state} (low-rust state)" if state in ("CA", "TX", "AZ", "FL", "NV", "CO") else state)

    return {
        "id": row.get("id"),
        "make": row.get("make"),
        "model": row.get("model"),
        "year": row.get("year"),
        "price": price,
        "current_bid": current_bid,
        "estimated_sale_price": estimated_sale_price,
        "mileage": row.get("mileage"),
        "source": row.get("source") or row.get("source_site"),
        "source_site": row.get("source_site") or row.get("source"),
        "state": state,
        "vin": row.get("vin"),
        "mmr": mmr_val,
        "dos_score": round(dos_score, 2),
        "score": round(dos_score, 2),
        "match_pct": round(dos_score, 2),
        "_score": round(max(0.0, min(1.0, dos_score / 100.0)), 4),
        "arbitrage_score": round(dos_score, 2),
        "roi_percentage": round(roi, 2),
        "potential_profit": round(profit, 2),
        "total_cost": _coerce_number(row.get("total_cost"), current_bid),
        "transportation_cost": _coerce_number(row.get("transportation_cost", row.get("estimated_transport")), 0.0),
        "fees_cost": _coerce_number(row.get("fees_cost", row.get("auction_fees")), 0.0),
        "buyer_premium": _coerce_number(row.get("buyer_premium"), 0.0),
        "confidence_score": round(dos_score, 2),
        "auction_end": row.get("auction_end") or row.get("auction_end_date"),
        "created_at": row.get("created_at"),
        "investment_grade": row.get("investment_grade"),
        "why_signals": why_signals,
    }


def _verify_auth(authorization: Optional[str]) -> str:
    """
    Validate Supabase JWT. Returns user_id on success.
    Raises 401 if missing or invalid.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")

    token = authorization.split(" ", 1)[1]
    if not _background_supabase_client:
        raise HTTPException(status_code=503, detail="Service unavailable")

    try:
        # Verify token against Supabase auth
        user = _background_supabase_client.auth.get_user(token)
        if not user or not user.user:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        return user.user.id
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def _write_rover_event(user_id: str, event_type: str, item_data: dict[str, Any], weight: float) -> int:
    if not _write_supabase_client:
        raise HTTPException(status_code=503, detail="Service unavailable")

    result = _write_supabase_client.table("rover_events").insert({
        "user_id": user_id,
        "event_type": event_type,
        "item_data": item_data,
        "weight": weight,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }).execute()
    return len(result.data or [])


def _record_sale_intent(opportunity_id: str, user_id: str) -> None:
    """Record a BUY intent in dealer_sales with outcome=pending.

    Idempotent: skips if a row already exists with outcome 'sold' or 'passed'.
    Only inserts/updates when no row exists or the existing row is still 'pending'.
    """
    if not _write_supabase_client:
        return  # non-fatal — rover_event is the primary record

    try:
        # Check for existing row
        existing = (
            _write_supabase_client.table("dealer_sales")
            .select("id,outcome")
            .eq("opportunity_id", opportunity_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if existing.data:
            current_outcome = (existing.data[0].get("outcome") or "").lower()
            if current_outcome in ("sold", "passed"):
                logger.debug(
                    "[ROVER] dealer_sales skip: opportunity=%s already %s",
                    opportunity_id[:8], current_outcome,
                )
                return

        # Fetch opportunity details for the sales record
        opp = (
            _write_supabase_client.table("opportunities")
            .select("make,model,year,mileage,state,current_bid,mmr_estimated")
            .eq("id", opportunity_id)
            .limit(1)
            .execute()
        )
        opp_data = (opp.data or [{}])[0]

        sale_price = opp_data.get("current_bid") or 0
        payload = {
            "user_id": user_id,
            "opportunity_id": opportunity_id,
            "make": opp_data.get("make") or "Unknown",
            "model": opp_data.get("model") or "Unknown",
            "year": opp_data.get("year") or 0,
            "mileage": opp_data.get("mileage"),
            "state": opp_data.get("state"),
            "sale_price": sale_price,
            "outcome": "pending",
            "source": "telegram_buy",
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }

        _write_supabase_client.table("dealer_sales").upsert(
            payload, on_conflict="opportunity_id,user_id"
        ).execute()

        logger.info(
            "[ROVER] dealer_sales intent recorded: opportunity=%s user=%s...",
            opportunity_id[:8], user_id[:8],
        )
    except Exception as exc:
        logger.warning("[ROVER] dealer_sales intent write failed (non-fatal): %s", exc)


def _apply_rover_action(opportunity_id: str, action: str, user_id: str) -> None:
    if not _write_supabase_client:
        raise HTTPException(status_code=503, detail="Service unavailable")

    if action in {"buy", "watch"}:
        event_type = "click" if action == "buy" else "save"
        weight = 1 if action == "buy" else 3
        _write_rover_event(
            user_id=user_id,
            event_type=event_type,
            item_data={
                "opportunity_id": opportunity_id,
                "source": "telegram_button",
                "action": action,
            },
            weight=weight,
        )
        # Record sale intent in dealer_sales for BUY actions
        if action == "buy":
            _record_sale_intent(opportunity_id, user_id)
        return

    if action == "pass":
        _write_supabase_client.table("opportunities").update({
            "pipeline_step": "passed",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", opportunity_id).execute()
        return

    raise HTTPException(status_code=400, detail="Unsupported action")


@router.get("/recommendations")
async def get_recommendations(
    user_id: str,
    limit: int = 20,
    authorization: Optional[str] = Header(None),
    supabase_client: Client = Depends(get_user_supabase_client),
):
    """Get personalized deal recommendations for a user."""
    # Verify auth and ensure user can only see their own recommendations
    auth_user_id = _verify_auth(authorization)
    if auth_user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        now_ms = time.time() * 1000
        effective_limit = max(1, min(limit, 20))
        # Fetch a wider pool so affinity re-ranking has room to surface better matches
        fetch_limit = min(effective_limit * 3, 60)
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        current_year = datetime.now(timezone.utc).year
        premium_year_cutoff = current_year - 4
        standard_year_cutoff = current_year - 10
        HIGH_RUST_STATES_ROVER = {
            "OH", "MI", "PA", "NY", "WI", "MN", "IL", "IN", "MO", "IA", "ND", "SD",
            "NE", "KS", "WV", "ME", "NH", "VT", "MA", "RI", "CT", "NJ", "MD", "DE",
        }
        opps_resp = supabase_client.table("opportunities")\
            .select("id,make,model,year,mileage,state,current_bid,mmr_estimated,dos_score,vehicle_tier,auction_end_date,source_site,investment_grade,gross_margin,roi_pct,max_bid,score_breakdown")\
            .gte("dos_score", 65)\
            .neq("vehicle_tier", "rejected")\
            .gte("year", standard_year_cutoff)\
            .order("dos_score", desc=True)\
            .or_(f"auction_end_date.gt.{now_iso},auction_end_date.is.null")\
            .limit(fetch_limit)\
            .execute()

        # Post-fetch: filter rust states (DB can't do set membership easily)
        all_rows = opps_resp.data or []
        raw_rows = [
            r for r in all_rows
            if not (
                str(r.get("state") or "").upper() in HIGH_RUST_STATES_ROVER
                and not (r.get("year") and int(r.get("year", 0)) >= current_year - 2)
            )
        ]
        personalized = False

        # --- Heuristic preference vector (from event history) ---
        heuristic_prefs: dict[str, float] = {}
        try:
            events_resp = supabase_client.table("rover_events")\
                .select("event_type,item_data,timestamp")\
                .eq("user_id", user_id)\
                .order("timestamp", desc=True)\
                .limit(200)\
                .execute()
            rover_events_raw = events_resp.data or []
            # Normalise: heuristic_scorer expects timestamp_ms key
            rover_events = [
                {
                    "event_type": e.get("event_type", "view"),
                    "item_data": e.get("item_data") or {},
                    "timestamp_ms": (
                        # timestamp col is ISO string; parse to ms if needed
                        float(e["timestamp_ms"]) if "timestamp_ms" in e
                        else (
                            __import__("datetime").datetime.fromisoformat(
                                e["timestamp"].rstrip("Z")
                            ).timestamp() * 1000
                            if e.get("timestamp") else now_ms
                        )
                    ),
                }
                for e in rover_events_raw
            ]
            heuristic_prefs = build_preference_vector(rover_events, now_ms)
            if heuristic_prefs:
                personalized = True
        except Exception as _he:
            logger.warning(f"[ROVER] Heuristic prefs fetch failed (non-fatal): {_he}")

        # --- Affinity re-ranking ---
        affinity: dict[str, float] = {}
        if _redis_client:
            try:
                from backend.rover.redis_affinity import get_affinity_vector
                affinity = get_affinity_vector(_redis_client, user_id)
            except Exception as _ae:
                logger.warning(f"[ROVER] Affinity fetch failed (non-fatal): {_ae}")

        if affinity or heuristic_prefs:
            personalized = True
            max_aff = max(affinity.values()) if affinity else 1.0
            if max_aff <= 0:
                max_aff = 1.0

            def _affinity_boost(row: dict) -> float:
                if not affinity:
                    return 0.0
                from backend.rover.redis_affinity import _extract_dimensions

                dims = _extract_dimensions(row)
                if not dims:
                    return 0.0
                raw = sum(affinity.get(d, 0.0) for d in dims) / len(dims)
                return raw / max_aff if max_aff > 0 else 0.0  # normalised 0–1

            def _effective_score(row: dict) -> float:
                dos = _coerce_number(row.get("dos_score", row.get("score")), 0.0)
                heuristic_boost = score_item(heuristic_prefs, row) if heuristic_prefs else 0.0
                return dos + _affinity_boost(row) * 15.0 + heuristic_boost

            raw_rows = sorted(raw_rows, key=_effective_score, reverse=True)
        elif raw_rows:
            # Cold start: no Redis or heuristic data — rank_opportunities uses DOS score
            raw_rows = rank_opportunities({}, raw_rows, top_n=len(raw_rows))

        items = [_serialize_recommendation(row) for row in raw_rows[:effective_limit]]

        return {
            "precomputedAt": int(now_ms),
            "items": items,
            "recommendations": items,
            "data": items,
            "totalCount": len(items),
            "confidence": min(1.0, len(items) / 20),
            "coldStart": not personalized,
            "personalized": personalized,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ROVER] Recommendations error for {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/events")
async def track_event(
    payload: dict,
    authorization: Optional[str] = Header(None),
    supabase_client: Client = Depends(get_user_supabase_client),
):
    """Track a user interaction event for preference learning."""
    # Validate event_type before JWT auth (fail fast)
    event_type = payload.get("event", "view")
    if event_type not in _VALID_EVENT_TYPES:
        raise HTTPException(status_code=400, detail="Invalid event_type")

    auth_user_id = _verify_auth(authorization)

    # Rate limit: max 10 events per user per minute
    now_ts = time.time()
    bucket = _event_rate.setdefault(auth_user_id, [])
    bucket[:] = [t for t in bucket if now_ts - t < 60]
    if len(bucket) >= 10:
        raise HTTPException(status_code=429, detail="Too many events, slow down")
    bucket.append(now_ts)

    # Ensure userId matches authenticated user (prevent poisoning other users' vectors)
    payload_user_id = payload.get("userId") or payload.get("user_id")
    if payload_user_id and payload_user_id != auth_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        from backend.rover.heuristic_scorer import EVENT_WEIGHTS

        raw_weight = EVENT_WEIGHTS[event_type]

        item_data = payload.get("item", {})

        # Deduplicate: view events within 5 min, other events within 30 s
        if _redis_client:
            try:
                from backend.rover.redis_affinity import is_duplicate_event
                item_id = str(item_data.get("id") or item_data.get("deal_id") or "")
                dedup_ttl = 300 if event_type == "view" else 30
                if item_id and is_duplicate_event(_redis_client, auth_user_id, event_type, item_id, dedup_ttl):
                    logger.debug("[ROVER] Deduplicated event type=%s user=%s... item=%s", event_type, auth_user_id[:8], item_id)
                    return {"ok": True, "deduped": True}
            except Exception as _de:
                logger.debug(f"[ROVER] Dedup check failed (non-fatal): {_de}")

        # Store raw weight — decay is applied at read time in build_preference_vector()
        rows_written = _write_rover_event(
            user_id=auth_user_id,
            event_type=event_type,
            item_data=item_data,
            weight=raw_weight,
        )
        if rows_written:
            logger.info(
                "[ROVER] Event written OK: type=%s user=%s... rows=%d",
                event_type, auth_user_id[:8], rows_written,
            )
        else:
            logger.warning(
                "[ROVER] Event insert returned 0 rows (possible write failure): type=%s user=%s...",
                event_type, auth_user_id[:8],
            )

        # Update Redis affinity vector (non-fatal)
        if _redis_client:
            try:
                from backend.rover.redis_affinity import increment_affinity
                increment_affinity(_redis_client, auth_user_id, payload, event_type, raw_weight)
            except Exception as _re:
                logger.warning(f"[ROVER] Redis affinity update failed (non-fatal): {_re}")

        return {"ok": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ROVER] Event tracking error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


INTERNAL_API_SECRET = os.getenv("INTERNAL_API_SECRET", "")


@router.post("/actions")
async def record_action(
    payload: dict[str, Any],
    x_internal_secret: str = Header(None, alias="X-Internal-Secret"),
):
    if not INTERNAL_API_SECRET or x_internal_secret != INTERNAL_API_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    """Record a rover action from internal callers such as Telegram callbacks."""
    opportunity_id = str(payload.get("opportunity_id") or "").strip()
    action = str(payload.get("action") or "").strip().lower()
    user_id = str(payload.get("user_id") or "").strip()

    if not opportunity_id or not action or not user_id:
        raise HTTPException(status_code=400, detail="Missing opportunity_id, action, or user_id")

    try:
        uuid.UUID(opportunity_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid opportunity id")

    if action not in {"buy", "watch", "pass"}:
        raise HTTPException(status_code=400, detail="Unsupported action")

    try:
        _apply_rover_action(opportunity_id=opportunity_id, action=action, user_id=user_id)
        return {"ok": True, "action": action, "opportunity_id": opportunity_id, "user_id": user_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[ROVER] Action recording error: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")
