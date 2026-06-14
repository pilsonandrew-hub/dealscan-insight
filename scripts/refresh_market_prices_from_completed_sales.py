#!/usr/bin/env python3
"""Preview market_prices refresh rows from trusted completed-sale evidence.

Dry-run only in the first implementation slice. This script intentionally
ignores active auction bids, proxy MMR, titles, listing URLs, and raw payloads as
pricing evidence.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timedelta, timezone
from statistics import mean
from typing import Any


DEFAULT_MIN_SAMPLE_SIZE = 5
DEFAULT_TTL_DAYS = 14
DEFAULT_MAX_EVIDENCE_AGE_DAYS = 365


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _safe_price(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed) or parsed <= 0:
        return None
    return parsed


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _row_vehicle_key(row: dict[str, Any]) -> tuple[int | None, str, str, str | None]:
    try:
        year = int(row.get("year")) if row.get("year") is not None else None
    except (TypeError, ValueError):
        year = None
    return (
        year,
        _normalize_text(row.get("make")),
        _normalize_text(row.get("model")),
        _normalize_text(row.get("state")) or None,
    )


def build_market_price_preview(
    rows: list[dict[str, Any]],
    *,
    source: str,
    source_run_id: str,
    now: datetime,
    ttl_days: int = DEFAULT_TTL_DAYS,
    min_sample_size: int = DEFAULT_MIN_SAMPLE_SIZE,
    max_evidence_age_days: int = DEFAULT_MAX_EVIDENCE_AGE_DAYS,
) -> dict[str, Any] | None:
    if min_sample_size < 2 or ttl_days <= 0 or not source_run_id:
        return None

    now_utc = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    usable: list[tuple[dict[str, Any], float, datetime]] = []
    expected_key: tuple[int | None, str, str, str | None] | None = None
    for row in rows:
        key = _row_vehicle_key(row)
        if not key[0] or not key[1] or not key[2]:
            continue
        if expected_key is None:
            expected_key = key
        if key != expected_key:
            continue
        price = _safe_price(row.get("sale_price"))
        sale_date = _parse_datetime(row.get("auction_end_date") or row.get("sale_date"))
        if price is None or sale_date is None:
            continue
        if sale_date < now_utc - timedelta(days=max_evidence_age_days):
            continue
        usable.append((row, price, sale_date.astimezone(timezone.utc)))

    if expected_key is None or len(usable) < min_sample_size:
        return None

    prices = [price for _, price, _ in usable]
    latest_sale = max(sale_date for _, _, sale_date in usable)
    source_clean = _normalize_text(source)
    return {
        "year": expected_key[0],
        "make": expected_key[1],
        "model": expected_key[2],
        "state": expected_key[3],
        "avg_price": round(mean(prices), 2),
        "low_price": round(min(prices), 2),
        "high_price": round(max(prices), 2),
        "sample_size": len(prices),
        "source": source_clean,
        "source_run_id": source_run_id,
        "confidence_notes": (
            f"Market price preview from {len(prices)} trusted completed-sale rows; "
            "does not use active bids or model-derived pricing."
        ),
        "metadata": {
            "seed_basis": source_clean,
            "evidence_count": len(prices),
            "max_evidence_age_days": max_evidence_age_days,
        },
        "last_updated": latest_sale.isoformat(),
        "expires_at": (now_utc + timedelta(days=ttl_days)).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-json", help="JSON file containing completed-sale rows for one vehicle group.")
    parser.add_argument("--source", default="competitor_sales")
    parser.add_argument("--source-run-id", required=True)
    parser.add_argument("--ttl-days", type=int, default=DEFAULT_TTL_DAYS)
    parser.add_argument("--min-sample-size", type=int, default=DEFAULT_MIN_SAMPLE_SIZE)
    args = parser.parse_args()

    rows: list[dict[str, Any]] = []
    if args.input_json:
        with open(args.input_json, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        rows = loaded if isinstance(loaded, list) else []
    preview = build_market_price_preview(
        rows,
        source=args.source,
        source_run_id=args.source_run_id,
        now=datetime.now(timezone.utc),
        ttl_days=args.ttl_days,
        min_sample_size=args.min_sample_size,
    )
    print(json.dumps({"preview": preview}, indent=2, sort_keys=True, default=str))
    return 0 if preview else 1


if __name__ == "__main__":
    raise SystemExit(main())
