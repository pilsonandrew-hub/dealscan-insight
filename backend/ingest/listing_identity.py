"""Listing identity helpers for ingest delivery/audit surfaces."""

from __future__ import annotations

import hashlib


def compute_listing_id(source: str, listing_url: str) -> str:
    """Compute the stable listing id used by ingest, alert, and delivery logs."""
    normalized_source = (source or "unknown").strip().lower()
    normalized_url = (listing_url or "").strip()
    return hashlib.sha256(f"{normalized_source}|{normalized_url}".encode()).hexdigest()[:40]
