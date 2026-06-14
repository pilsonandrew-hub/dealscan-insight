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
import os
import sys
from datetime import datetime, timedelta, timezone
from statistics import mean
from typing import Any
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request


DEFAULT_MIN_SAMPLE_SIZE = 5
DEFAULT_TTL_DAYS = 14
DEFAULT_MAX_EVIDENCE_AGE_DAYS = 365
APPLY_CONFIRMATION = "REFRESH_MARKET_PRICES_FROM_COMPLETED_SALES"


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


def confirm_apply(*, apply: bool, confirmation: str) -> bool:
    if not apply:
        return True
    return str(confirmation or "").strip() == APPLY_CONFIRMATION


def _normalize_rest_base_url(supabase_url: str) -> str:
    return supabase_url.rstrip("/").removesuffix("/rest/v1")


def _rest_json_request(method: str, url: str, service_role_key: str, payload: dict[str, Any] | None = None) -> Any:
    data = None
    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
        "Accept": "application/json",
    }
    if payload is not None:
        data = json.dumps(payload, sort_keys=True).encode("utf-8")
        headers["Content-Type"] = "application/json"
        headers["Prefer"] = "return=representation"

    request = urllib_request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib_request.urlopen(request, timeout=30) as response:
            raw_payload = response.read().decode("utf-8")
    except urllib_error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Supabase REST API error: HTTP {exc.code} {body[:300]}") from exc
    except urllib_error.URLError as exc:
        raise RuntimeError(f"Supabase REST API unreachable: {exc}") from exc

    try:
        return json.loads(raw_payload or "[]")
    except json.JSONDecodeError as exc:
        raise RuntimeError("Supabase REST API returned invalid JSON") from exc


def _market_price_rest_query(preview: dict[str, Any]) -> str:
    query = [
        ("select", "id,year,make,model,state,avg_price,sample_size,source,source_run_id"),
        ("year", f"eq.{preview['year']}"),
        ("make", f"eq.{preview['make']}"),
        ("model", f"eq.{preview['model']}"),
        ("source", f"eq.{preview['source']}"),
        ("source_run_id", f"eq.{preview['source_run_id']}"),
        ("limit", "1"),
    ]
    state = preview.get("state")
    if state:
        query.append(("state", f"eq.{state}"))
    else:
        query.append(("state", "is.null"))
    return urllib_parse.urlencode(query)


def insert_market_price_preview_via_rest(
    supabase_url: str,
    service_role_key: str,
    preview: dict[str, Any],
) -> dict[str, Any]:
    base_url = _normalize_rest_base_url(supabase_url)
    query = _market_price_rest_query(preview)
    existing = _rest_json_request(
        "GET",
        f"{base_url}/rest/v1/market_prices?{query}",
        service_role_key,
    )

    payload = {
        "year": preview["year"],
        "make": preview["make"],
        "model": preview["model"],
        "state": preview.get("state"),
        "avg_price": preview["avg_price"],
        "low_price": preview["low_price"],
        "high_price": preview["high_price"],
        "sample_size": preview["sample_size"],
        "source": preview["source"],
        "source_run_id": preview["source_run_id"],
        "source_url": None,
        "confidence_notes": preview["confidence_notes"],
        "metadata": preview["metadata"],
        "last_updated": preview["last_updated"],
        "expires_at": preview["expires_at"],
    }
    if existing:
        refreshed = _rest_json_request(
            "PATCH",
            f"{base_url}/rest/v1/market_prices?{query}",
            service_role_key,
            payload,
        )
        if not isinstance(refreshed, list) or not refreshed:
            raise RuntimeError("Supabase REST refresh returned no row")
        return dict(refreshed[0])

    inserted = _rest_json_request(
        "POST",
        f"{base_url}/rest/v1/market_prices",
        service_role_key,
        payload,
    )
    if not isinstance(inserted, list) or not inserted:
        raise RuntimeError("Supabase REST insert returned no row")
    return dict(inserted[0])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-json", help="JSON file containing completed-sale rows for one vehicle group.")
    parser.add_argument("--source", default="competitor_sales")
    parser.add_argument("--source-run-id", required=True)
    parser.add_argument("--ttl-days", type=int, default=DEFAULT_TTL_DAYS)
    parser.add_argument("--min-sample-size", type=int, default=DEFAULT_MIN_SAMPLE_SIZE)
    parser.add_argument("--apply", action="store_true", help="Insert or refresh the preview row. Default is dry-run.")
    parser.add_argument("--apply-via-rest", action="store_true", help="Use Supabase REST service-role API for apply.")
    parser.add_argument("--confirmation", default="", help=f"Required when --apply: {APPLY_CONFIRMATION}")
    args = parser.parse_args()

    if not confirm_apply(apply=args.apply, confirmation=args.confirmation):
        print(f"Apply requires confirmation={APPLY_CONFIRMATION}", file=sys.stderr)
        return 2

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
    if not preview:
        return 1
    if not args.apply:
        print("Dry-run only. Re-run with --apply after reviewing the preview.")
        return 0
    if not args.apply_via_rest:
        print("--apply currently requires --apply-via-rest.", file=sys.stderr)
        return 2

    supabase_url = os.environ.get("SUPABASE_URL", "").strip()
    service_role_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not supabase_url or not service_role_key:
        print("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required for --apply-via-rest.", file=sys.stderr)
        return 2
    applied = insert_market_price_preview_via_rest(supabase_url, service_role_key, preview)
    print(
        "Applied completed-sale market_prices row via Supabase REST: "
        f"id={applied.get('id')} avg={applied.get('avg_price')} samples={applied.get('sample_size')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
