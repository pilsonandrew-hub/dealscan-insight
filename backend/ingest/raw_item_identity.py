"""Raw Apify item identity helpers for pre-normalization ingest bookkeeping."""

from __future__ import annotations

import hashlib
from typing import Any, Optional


def raw_item_identity(item: Any, run_id: str, item_index: int) -> tuple[str, Optional[str]]:
    """Return deterministic listing identity and optional URL for raw dataset items.

    This is intentionally pre-normalization: it must work for malformed items so
    pre-save skip/delivery logs can still be queryable.
    """
    if not isinstance(item, dict):
        fallback_id = hashlib.sha256(f"{run_id}|raw|{item_index}".encode()).hexdigest()[:40]
        return fallback_id, None

    source = (item.get("source_site") or item.get("source") or "unknown").strip().lower()
    listing_url = (item.get("listing_url") or item.get("url") or "").strip() or None
    raw_listing_id = (
        item.get("listing_id")
        or item.get("assetId")
        or item.get("id")
        or item.get("url")
        or item.get("listing_url")
        or item.get("vin")
    )
    if raw_listing_id:
        listing_id = hashlib.sha256(f"{source}|{raw_listing_id}".encode()).hexdigest()[:40]
        return listing_id, listing_url

    title = (item.get("title") or "").strip()
    fallback_id = hashlib.sha256(
        f"{run_id}|{source}|{listing_url or title}|{item_index}".encode()
    ).hexdigest()[:40]
    return fallback_id, listing_url
