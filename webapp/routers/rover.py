"""
Rover recommendation engine endpoints.
Implements preference-based deal ranking with event weighting + decay.
"""
from fastapi import APIRouter, HTTPException
import time
import os
from supabase import create_client

router = APIRouter(prefix="/api/rover", tags=["rover"])

_supabase_url = os.getenv("VITE_SUPABASE_URL", "")
_supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY", "")
supa = create_client(_supabase_url, _supabase_key) if _supabase_url and _supabase_key else None


@router.get("/recommendations")
async def get_recommendations(user_id: str, limit: int = 25):
    """Get personalized deal recommendations for a user."""
    if not supa:
        raise HTTPException(status_code=503, detail="Database not configured")

    try:
        from backend.rover.heuristic_scorer import build_preference_vector, rank_opportunities

        # Load user event history (last 30 days)
        events_resp = supa.table("rover_events")\
            .select("*")\
            .eq("user_id", user_id)\
            .order("timestamp", desc=True)\
            .limit(200)\
            .execute()

        events = events_resp.data or []

        # Convert timestamps to ms for decay calc
        now_ms = time.time() * 1000
        for e in events:
            if e.get("timestamp"):
                from datetime import datetime
                dt = datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00"))
                e["timestamp_ms"] = dt.timestamp() * 1000

        # Build preference vector
        prefs = build_preference_vector(events, now_ms)

        # Load recent opportunities from Supabase
        opps_resp = supa.table("opportunities")\
            .select("*")\
            .in_("status", ["hot", "good"])\
            .order("score", desc=True)\
            .limit(200)\
            .execute()

        opportunities = opps_resp.data or []

        # Rank by preference
        ranked = rank_opportunities(prefs, opportunities, top_n=limit)

        return {
            "precomputedAt": int(now_ms),
            "items": ranked,
            "totalCount": len(ranked),
            "confidence": min(1.0, len(events) / 50),  # Confidence grows with event history
            "coldStart": len(events) == 0
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/events")
async def track_event(payload: dict):
    """Track a user interaction event for preference learning."""
    if not supa:
        raise HTTPException(status_code=503, detail="Database not configured")

    try:
        from backend.rover.heuristic_scorer import EVENT_WEIGHTS, apply_decay

        event_type = payload.get("event", "view")
        raw_weight = EVENT_WEIGHTS.get(event_type, 0.2)
        now_ms = time.time() * 1000
        decayed_weight = apply_decay(raw_weight, now_ms, now_ms)

        supa.table("rover_events").insert({
            "user_id": payload.get("userId"),
            "event_type": event_type,
            "item_data": payload.get("item", {}),
            "weight": decayed_weight,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }).execute()

        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
