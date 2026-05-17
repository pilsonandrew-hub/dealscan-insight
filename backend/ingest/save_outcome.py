"""Persistence outcome helpers for DealerScope ingest.

This module records save outcomes without changing ingest behavior. It is intentionally
small so persistence observability can be tested before larger ingest.py extraction.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def mark_save_outcome(
    vehicle: dict,
    status: str,
    *,
    opportunity_id: Optional[str] = None,
    error_message: Optional[str] = None,
) -> dict:
    """Record the current save outcome in a queryable, non-silent form."""
    score_breakdown = vehicle.get("score_breakdown") or {}
    outcome = {
        "status": status,
        "opportunity_id": opportunity_id,
        "error_message": error_message,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "score_version": score_breakdown.get("score_version"),
        "score_engine_impl": score_breakdown.get("score_engine_impl"),
        "score_assumption_level": score_breakdown.get("assumption_level"),
        "score_fallback_flags": score_breakdown.get("fallback_flags", []),
    }
    vehicle["_save_status"] = status
    vehicle["_save_outcome"] = outcome
    return outcome
