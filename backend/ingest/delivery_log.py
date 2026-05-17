"""Pure helpers for ingest delivery-log rows."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_delivery_log_row(
    *,
    run_id: str,
    listing_id: str,
    channel: str,
    status: str,
    listing_url: Optional[str] = None,
    opportunity_id: Optional[str] = None,
    external_id: Optional[str] = None,
    error_message: Optional[str] = None,
    now_fn: Callable[[], str] = utc_now_iso,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "listing_id": listing_id,
        "listing_url": listing_url,
        "opportunity_id": opportunity_id,
        "channel": channel,
        "status": status,
        "external_id": external_id,
        "error_message": error_message,
        "updated_at": now_fn(),
    }


def build_delivery_log_insert_row(row: dict[str, Any]) -> dict[str, Any]:
    insert_row = dict(row)
    insert_row["attempt_count"] = 1
    insert_row["created_at"] = row["updated_at"]
    return insert_row


def build_delivery_log_update_row(
    row: dict[str, Any],
    existing: Optional[dict[str, Any]],
) -> dict[str, Any]:
    update_row = dict(row)
    update_row["attempt_count"] = int((existing or {}).get("attempt_count") or 0) + 1
    return update_row
