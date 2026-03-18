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
from fastapi import APIRouter, HTTPException, Header
from typing import Optional
import time
import os
import logging
from backend.rover.heuristic_scorer import build_preference_vector, score_item, rank_opportunities

router = APIRouter(prefix="/api/rover", tags=["rover"])
logger = logging.getLogger(__name__)

# Prefer backend-only env vars; fall back to VITE_* for compatibility during transition
_supabase_url = os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL", "")
_supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY", "")

supa = None
try:
    if _supabase_url and _supabase_key:
        from supabase import create_client
        supa = create_client(_supabase_url, _supabase_key)
except Exception as _e:
    logger.warning(f"Rover Supabase client init failed (non-fatal): {_e}")

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
        "state": row.get("state"),
        "vin": row.get("vin"),
        "mmr": _coerce_number(row.get("mmr", row.get("estimated_sale_price")), 0.0),
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
    }


def _verify_auth(authorization: Optional[str]) -> str:
    """
    Validate Supabase JWT. Returns user_id on success.
    Raises 401 if missing or invalid.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")

    token = authorization.split(" ", 1)[1]
    if not supa:
        raise HTTPException(status_code=503, detail="Service unavailable")

    try:
        # Verify token against Supabase auth
        user = supa.auth.get_user(token)
        if not user or not user.user:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        return user.user.id
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


@router.get("/recommendations")
async def get_recommendations(
    user_id: str,
    limit: int = 20,
    authorization: Optional[str] = Header(None),
):
    """Get personalized deal recommendations for a user."""
    # Verify auth and ensure user can only see their own recommendations
    auth_user_id = _verify_auth(authorization)
    if auth_user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    if not supa:
        raise HTTPException(status_code=503, detail="Service unavailable")

    try:
        now_ms = time.time() * 1000
        effective_limit = max(1, min(limit, 20))
        # Fetch a wider pool so affinity re-ranking has room to surface better matches
        fetch_limit = min(effective_limit * 3, 60)
        opps_resp = supa.table("opportunities")\
            .select("*")\
            .gte("dos_score", 65)\
            .order("dos_score", desc=True)\
            .limit(fetch_limit)\
            .execute()

        raw_rows = opps_resp.data or []
        personalized = False

        # --- Heuristic preference vector (from event history) ---
        heuristic_prefs: dict[str, float] = {}
        try:
            events_resp = supa.table("rover_events")\
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
            "coldStart": False,
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
):
    """Track a user interaction event for preference learning."""
    auth_user_id = _verify_auth(authorization)

    if not supa:
        raise HTTPException(status_code=503, detail="Service unavailable")

    # Ensure userId matches authenticated user (prevent poisoning other users' vectors)
    payload_user_id = payload.get("userId") or payload.get("user_id")
    if payload_user_id and payload_user_id != auth_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        from backend.rover.heuristic_scorer import EVENT_WEIGHTS

        event_type = payload.get("event", "view")
        if event_type not in EVENT_WEIGHTS:
            raise HTTPException(status_code=400, detail=f"Invalid event type: {event_type}")

        raw_weight = EVENT_WEIGHTS[event_type]

        item_data = payload.get("item", {})

        # Store raw weight — decay is applied at read time in build_preference_vector()
        supa.table("rover_events").insert({
            "user_id": auth_user_id,
            "event_type": event_type,
            "item_data": item_data,
            "weight": raw_weight,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }).execute()

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
