"""Lifecycle memory helpers for opportunity rows."""

from __future__ import annotations

import hashlib
import math
from typing import Any, Mapping, Optional


def _text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _numeric(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _int_count(value: Any) -> int:
    number = _numeric(value)
    return int(number) if number is not None and number > 0 else 0


def compute_source_fingerprint(row: Mapping[str, Any]) -> str:
    """Return a stable source-side identity for lifecycle continuity."""
    source = _text(row.get("source_site") or row.get("source")).lower()
    identity = (
        _text(row.get("canonical_id"))
        or _text(row.get("vin")).upper()
        or _text(row.get("listing_url"))
        or "|".join(
            [
                _text(row.get("year")),
                _text(row.get("make")).lower(),
                _text(row.get("model")).lower(),
                _text(row.get("state")).upper(),
            ]
        )
    )
    return hashlib.md5(f"{source}|{identity}".encode("utf-8"), usedforsecurity=False).hexdigest()


def build_initial_lifecycle_fields(row: Mapping[str, Any], *, now_iso: str) -> dict[str, Any]:
    return {
        "first_seen_at": row.get("first_seen_at") or now_iso,
        "last_seen_at": now_iso,
        "relist_count": _int_count(row.get("relist_count")),
        "bid_change_count": _int_count(row.get("bid_change_count")),
        "source_fingerprint": row.get("source_fingerprint") or compute_source_fingerprint(row),
    }


def _changed(incoming: Any, existing: Any) -> bool:
    incoming_text = _text(incoming)
    existing_text = _text(existing)
    if not incoming_text or not existing_text:
        return False
    return incoming_text != existing_text


def build_lifecycle_update(
    incoming: Mapping[str, Any],
    existing: Mapping[str, Any],
    *,
    now_iso: str,
) -> dict[str, Any]:
    update: dict[str, Any] = {
        "last_seen_at": now_iso,
        "source_fingerprint": compute_source_fingerprint(incoming),
    }
    if _changed(incoming.get("listing_url"), existing.get("listing_url")) or _changed(
        incoming.get("auction_end_date"),
        existing.get("auction_end_date"),
    ):
        update["relist_count"] = _int_count(existing.get("relist_count")) + 1

    incoming_bid = _numeric(incoming.get("current_bid"))
    existing_bid = _numeric(existing.get("current_bid"))
    if incoming_bid is not None and existing_bid is not None and incoming_bid != existing_bid:
        update["bid_change_count"] = _int_count(existing.get("bid_change_count")) + 1

    if not existing.get("first_seen_at"):
        update["first_seen_at"] = now_iso
    return update
