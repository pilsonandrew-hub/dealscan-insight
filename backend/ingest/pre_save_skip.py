"""Pre-save skip delivery-log payload helpers."""

from __future__ import annotations

from typing import Any

from backend.ingest.raw_item_identity import raw_item_identity


def build_pre_save_skip_delivery_log_kwargs(
    *,
    item: Any,
    run_id: str,
    item_index: int,
    status: str,
    error_message: str | None,
) -> dict[str, Any]:
    listing_id, listing_url = raw_item_identity(item, run_id, item_index)
    return {
        "run_id": run_id,
        "listing_id": listing_id,
        "listing_url": listing_url,
        "opportunity_id": None,
        "channel": "db_save",
        "status": status,
        "error_message": error_message,
        "require_durable": True,
    }
