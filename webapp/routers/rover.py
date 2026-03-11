"""
Rover recommendation engine endpoints.
Implements preference-based deal ranking with event weighting + decay.

Fixes applied (2026-03-11):
- Auth required on both endpoints (Supabase JWT validation)
- 500 errors genericized (no internals leaked)
- apply_decay bug note documented
"""
from fastapi import APIRouter, HTTPException, Header
from typing import Optional
import time
import os
import logging

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
    limit: int = 25,
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
        from backend.rover.heuristic_scorer import build_preference_vector, rank_opportunities

        # Load user event history (last 200 events)
        events_resp = supa.table("rover_events")\
            .select("*")\
            .eq("user_id", user_id)\
            .order("timestamp", desc=True)\
            .limit(200)\
            .execute()

        events = events_resp.data or []

        # Convert timestamps to ms for decay calculation
        now_ms = time.time() * 1000
        for e in events:
            if e.get("timestamp"):
                from datetime import datetime, timezone
                try:
                    dt = datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00"))
                    e["timestamp_ms"] = dt.timestamp() * 1000
                except Exception:
                    e["timestamp_ms"] = now_ms

        # Build preference vector from event history
        prefs = build_preference_vector(events, now_ms)

        # Load recent high-quality opportunities
        opps_resp = supa.table("opportunities")\
            .select("*")\
            .in_("status", ["hot", "good"])\
            .order("dos_score", desc=True)\
            .limit(200)\
            .execute()

        opportunities = opps_resp.data or []

        # Rank by preference vector
        ranked = rank_opportunities(prefs, opportunities, top_n=limit)

        return {
            "precomputedAt": int(now_ms),
            "items": ranked,
            "totalCount": len(ranked),
            "confidence": min(1.0, len(events) / 50),
            "coldStart": len(events) == 0,
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
    payload_user_id = payload.get("userId")
    if payload_user_id and payload_user_id != auth_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        from backend.rover.heuristic_scorer import EVENT_WEIGHTS

        event_type = payload.get("event", "view")
        if event_type not in EVENT_WEIGHTS:
            raise HTTPException(status_code=400, detail=f"Invalid event type: {event_type}")

        raw_weight = EVENT_WEIGHTS[event_type]

        # Store raw weight — decay is applied at read time in build_preference_vector()
        supa.table("rover_events").insert({
            "user_id": auth_user_id,
            "event_type": event_type,
            "item_data": payload.get("item", {}),
            "weight": raw_weight,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }).execute()

        return {"ok": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ROVER] Event tracking error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
