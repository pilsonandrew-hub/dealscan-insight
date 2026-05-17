"""VIN normalization and duplicate-check helpers for ingest persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional


def normalize_vin(vin: Optional[str]) -> Optional[str]:
    """Normalize a VIN: strip whitespace and uppercase."""
    if not vin:
        return None
    normalized = vin.strip().upper()
    return normalized if normalized else None


def check_vin_duplicate(
    vin: str,
    new_dos_score: float,
    *,
    supabase_client: Any,
    now_iso: Optional[str] = None,
) -> tuple[Optional[str], bool]:
    """
    Check if a live opportunity with this VIN already exists in Supabase.

    Returns (existing_id, should_update) where should_update is true only when
    the new score is strictly higher than the existing score.
    """
    if supabase_client is None:
        return None, False

    auction_cutoff = now_iso or datetime.now(timezone.utc).isoformat()
    result = (
        supabase_client.table("opportunities")
        .select("id, listing_url, dos_score")
        .eq("vin", vin)
        .gte("auction_end_date", auction_cutoff)
        .limit(1)
        .execute()
    )
    if result.data:
        existing = result.data[0]
        existing_id = existing.get("id")
        existing_score = float(existing.get("dos_score") or 0)
        return existing_id, new_dos_score > existing_score
    return None, False
