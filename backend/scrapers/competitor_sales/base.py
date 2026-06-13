"""Shared utilities for competitor sold-listing scrapers.

Provides:
- ``robots_allows`` — robots.txt compliance check (cached per host).
- ``RateLimiter`` — simple polite request pacing.
- ``build_competitor_sale_row`` — normalize a scraped lot into a competitor_sales row.
- ``write_competitor_sales`` — idempotent upsert into the competitor_sales table.

The normalization helpers are pure (no network/DB) so they can be unit-tested.
"""

from __future__ import annotations

import logging
import re
import time
import urllib.robotparser
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from backend.ingest.competitor_pricing import normalize_vehicle_class

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = (
    "DealerScopeBot/1.0 (+https://dealerscope.app; market-comp research)"
)

VIN_PATTERN = re.compile(r"\b([A-HJ-NPR-Z0-9]{17})\b", re.IGNORECASE)

US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL",
    "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT",
    "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI",
    "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
}

_ROBOTS_CACHE: Dict[str, urllib.robotparser.RobotFileParser] = {}
_ROBOTS_LOCK = Lock()


def robots_allows(url: str, user_agent: str = DEFAULT_USER_AGENT) -> bool:
    """Return True if ``url`` may be fetched per the host's robots.txt.

    Fails open (returns True) when robots.txt cannot be retrieved — the standard
    convention — but fails closed for explicit disallow rules.
    """
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return True
        host_key = f"{parsed.scheme}://{parsed.netloc}"
        with _ROBOTS_LOCK:
            parser = _ROBOTS_CACHE.get(host_key)
            if parser is None:
                parser = urllib.robotparser.RobotFileParser()
                parser.set_url(f"{host_key}/robots.txt")
                try:
                    parser.read()
                except Exception:
                    # robots.txt unreachable — convention is to allow.
                    _ROBOTS_CACHE[host_key] = urllib.robotparser.RobotFileParser()
                    return True
                _ROBOTS_CACHE[host_key] = parser
        return parser.can_fetch(user_agent, url)
    except Exception:
        return True


class RateLimiter:
    """Block until at least ``min_interval`` seconds have passed since last call."""

    def __init__(self, min_interval: float = 1.0):
        self.min_interval = max(0.0, float(min_interval))
        self._last = 0.0
        self._lock = Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last
            sleep_for = self.min_interval - elapsed
            if sleep_for > 0:
                time.sleep(sleep_for)
            self._last = time.monotonic()


def _to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        value = value.strip().replace(",", "").replace("$", "")
        if value == "":
            return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed


def _to_int(value: Any) -> Optional[int]:
    parsed = _to_float(value)
    if parsed is None:
        return None
    return int(parsed)


def extract_vin(*texts: Any) -> Optional[str]:
    """Find the first 17-char VIN across the provided text fields."""
    blob = " ".join(str(t or "") for t in texts)
    match = VIN_PATTERN.search(blob)
    return match.group(1).upper() if match else None


def normalize_state(location: Any, explicit_state: Any = None) -> Optional[str]:
    """Resolve a 2-letter US state from an explicit field or a 'City, ST' string."""
    if explicit_state:
        candidate = str(explicit_state).strip().upper()
        if candidate in US_STATES:
            return candidate
    if location:
        tokens = re.split(r"[,\s]+", str(location).strip().upper())
        for token in reversed(tokens):
            if token in US_STATES:
                return token
    return None


def _normalize_dt(value: Any) -> Optional[str]:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        parsed = parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        return parsed.isoformat()
    except (TypeError, ValueError):
        return str(value)


def dedup_key(source: str, source_listing_id: Optional[str], listing_url: str) -> str:
    """Stable per-listing key used for upsert conflict resolution."""
    suffix = (source_listing_id or "").strip() or (listing_url or "").strip()
    return f"{(source or '').strip().lower()}|{suffix}"


def build_competitor_sale_row(
    *,
    source: str,
    listing_url: str,
    sale_price: Any,
    source_listing_id: Optional[str] = None,
    vin: Optional[str] = None,
    year: Any = None,
    make: Optional[str] = None,
    model: Optional[str] = None,
    trim: Optional[str] = None,
    mileage: Any = None,
    auction_end_date: Any = None,
    condition_notes: Optional[str] = None,
    location: Optional[str] = None,
    state: Optional[str] = None,
    raw: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Normalize a scraped lot into a competitor_sales row.

    Returns ``None`` when the lot is not a usable comp (no positive sale price,
    or no make/model/vin to identify the vehicle).
    """
    price = _to_float(sale_price)
    if not price or price <= 0:
        return None

    make_clean = (make or "").strip()
    model_clean = (model or "").strip()
    if not make_clean and not model_clean and not vin:
        return None

    row: Dict[str, Any] = {
        "source": (source or "").strip().lower(),
        "source_listing_id": (str(source_listing_id).strip() if source_listing_id else None),
        "listing_url": (listing_url or "").strip(),
        "vin": (vin or "").strip().upper() or None,
        "year": _to_int(year),
        "make": make_clean or None,
        "model": model_clean or None,
        "trim": (trim or "").strip() or None,
        "mileage": _to_int(mileage),
        "vehicle_class": normalize_vehicle_class(make_clean, model_clean),
        "sale_price": round(price, 2),
        "currency": "USD",
        "auction_end_date": _normalize_dt(auction_end_date),
        "condition_notes": (condition_notes or "").strip() or None,
        "location": (location or "").strip() or None,
        "state": normalize_state(location, state),
        "raw_payload": raw or {},
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }
    return row


def _is_competitor_sales_url_conflict(exc: Exception) -> bool:
    error_text = str(exc).lower()
    has_unique_violation = (
        "duplicate key" in error_text
        or "unique constraint" in error_text
        or "23505" in error_text
    )
    mentions_url_target = (
        "idx_competitor_sales_source_url_upsert" in error_text
        or "idx_competitor_sales_source_url" in error_text
        or "competitor_sales_source_url" in error_text
    )
    return has_unique_violation and mentions_url_target


def _existing_source_listing_id_for_url(row: Dict[str, Any], supabase_client: Any) -> tuple[bool, Optional[str]]:
    try:
        resp = (
            supabase_client.table("competitor_sales")
            .select("source_listing_id")
            .eq("source", row.get("source"))
            .eq("listing_url", row.get("listing_url"))
            .limit(1)
            .execute()
        )
    except Exception as exc:  # pragma: no cover - network/db path
        logger.error("[competitor_sales] could not verify url-conflict row identity: %s", exc)
        return False, None
    if not resp.data:
        return True, None
    existing_id = resp.data[0].get("source_listing_id")
    return True, str(existing_id).strip() if existing_id else None


def _delete_url_only_duplicate(row: Dict[str, Any], supabase_client: Any) -> bool:
    try:
        supabase_client.table("competitor_sales").delete().eq(
            "source",
            row.get("source"),
        ).eq(
            "listing_url",
            row.get("listing_url"),
        ).is_(
            "source_listing_id",
            "null",
        ).execute()
    except Exception as exc:  # pragma: no cover - network/db path
        logger.error("[competitor_sales] could not delete url-only duplicate: %s", exc)
        return False
    return True


def write_competitor_sales(rows: List[Dict[str, Any]], supabase_client: Any) -> int:
    """Idempotently upsert competitor_sales rows. Returns number written."""
    valid = [r for r in rows if r and r.get("sale_price")]
    if not valid:
        return 0
    if supabase_client is None:
        logger.warning("[competitor_sales] no supabase client; %d rows not written", len(valid))
        return 0

    with_ids = [r for r in valid if r.get("source_listing_id")]
    without_ids: List[Dict[str, Any]] = []
    for row in valid:
        if row.get("source_listing_id"):
            continue
        payload = dict(row)
        payload.pop("source_listing_id", None)
        without_ids.append(payload)
    written = 0

    if with_ids:
        try:
            resp = (
                supabase_client.table("competitor_sales")
                .upsert(with_ids, on_conflict="source,source_listing_id", ignore_duplicates=False)
                .execute()
            )
            written += len(resp.data) if resp.data else 0
        except Exception as exc:  # pragma: no cover - network/db path
            if _is_competitor_sales_url_conflict(exc):
                logger.warning(
                    "[competitor_sales] listing-id batch hit url conflict; retrying %d rows individually",
                    len(with_ids),
                )
                for row in with_ids:
                    try:
                        resp = (
                            supabase_client.table("competitor_sales")
                            .upsert([row], on_conflict="source,source_listing_id", ignore_duplicates=False)
                            .execute()
                        )
                        written += len(resp.data) if resp.data else 0
                    except Exception as row_exc:  # pragma: no cover - network/db path
                        if not _is_competitor_sales_url_conflict(row_exc):
                            logger.error("[competitor_sales] row upsert by listing id failed: %s", row_exc)
                            continue
                        lookup_ok, existing_id = _existing_source_listing_id_for_url(row, supabase_client)
                        if not lookup_ok:
                            continue
                        row_id = str(row.get("source_listing_id") or "").strip()
                        if existing_id not in (None, "", row_id):
                            logger.error(
                                "[competitor_sales] refusing url fallback for %s because listing_url is tied to another source_listing_id",
                                row.get("listing_url"),
                            )
                            continue
                        if not existing_id and row_id:
                            if not _delete_url_only_duplicate(row, supabase_client):
                                continue
                            try:
                                resp = (
                                    supabase_client.table("competitor_sales")
                                    .upsert([row], on_conflict="source,source_listing_id", ignore_duplicates=False)
                                    .execute()
                                )
                                written += len(resp.data) if resp.data else 0
                                continue
                            except Exception as retry_exc:  # pragma: no cover - network/db path
                                logger.error(
                                    "[competitor_sales] row upsert by listing id after url-only cleanup failed: %s",
                                    retry_exc,
                                )
                                continue
                        try:
                            resp = (
                                supabase_client.table("competitor_sales")
                                .upsert([row], on_conflict="source,listing_url", ignore_duplicates=False)
                                .execute()
                            )
                            written += len(resp.data) if resp.data else 0
                        except Exception as fallback_exc:  # pragma: no cover - network/db path
                            logger.error("[competitor_sales] row upsert by url fallback failed: %s", fallback_exc)
            else:
                logger.error("[competitor_sales] upsert by listing id failed: %s", exc)

    if without_ids:
        try:
            resp = (
                supabase_client.table("competitor_sales")
                .upsert(without_ids, on_conflict="source,listing_url", ignore_duplicates=False)
                .execute()
            )
            written += len(resp.data) if resp.data else 0
        except Exception as exc:  # pragma: no cover - network/db path
            logger.warning(
                "[competitor_sales] url batch upsert failed; retrying %d rows individually: %s",
                len(without_ids),
                exc,
            )
            for row in without_ids:
                try:
                    resp = (
                        supabase_client.table("competitor_sales")
                        .upsert([row], on_conflict="source,listing_url", ignore_duplicates=False)
                        .execute()
                    )
                    written += len(resp.data) if resp.data else 0
                except Exception as row_exc:  # pragma: no cover - network/db path
                    logger.error("[competitor_sales] row upsert by url failed: %s", row_exc)

    logger.info("[competitor_sales] wrote %d rows", written)
    return written
