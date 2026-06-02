#!/usr/bin/env python3
"""Validate governed external retail listing comps before market_prices insert.

The script is dry-run by default. It intentionally does not scrape or infer
external comps; callers must provide a JSON evidence file with source URLs and
captured timestamps for every comp.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Optional
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request
from urllib.parse import urlparse

import psycopg2
import psycopg2.extras

from live_verification_support import get_database_url


SOURCE_TAG = "external_retail_listing_comp"
DEFAULT_MIN_SAMPLE_SIZE = 3


class ExternalCompError(ValueError):
    pass


def _money(value) -> Decimal:
    try:
        amount = Decimal(str(value))
    except Exception as exc:
        raise ExternalCompError(f"invalid money value: {value!r}") from exc
    if amount <= 0:
        raise ExternalCompError(f"money value must be positive: {value!r}")
    return amount


def _positive_int(value, field: str) -> int:
    try:
        parsed = int(value)
    except Exception as exc:
        raise ExternalCompError(f"{field} must be an integer") from exc
    if parsed <= 0:
        raise ExternalCompError(f"{field} must be positive")
    return parsed


def _parse_capture_time(value: str) -> str:
    if not value:
        raise ExternalCompError("captured_at is required")
    normalized = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ExternalCompError(f"captured_at is not ISO-8601: {value}") from exc
    if parsed.tzinfo is None:
        raise ExternalCompError("captured_at must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat()


def _validate_url(value: str) -> str:
    parsed = urlparse(str(value or ""))
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ExternalCompError(f"source_url must be http(s): {value!r}")
    return str(value)


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _normalize_vehicle(document: dict) -> dict:
    vehicle = document.get("vehicle") or {}
    year = _positive_int(vehicle.get("year"), "vehicle.year")
    make = str(vehicle.get("make") or "").strip().lower()
    model = str(vehicle.get("model") or "").strip().lower()
    state = str(vehicle.get("state") or "").strip().lower() or None
    if not make:
        raise ExternalCompError("vehicle.make is required")
    if not model:
        raise ExternalCompError("vehicle.model is required")
    return {"year": year, "make": make, "model": model, "state": state}


def validate_external_comp_document(document: dict, *, min_sample_size: int = DEFAULT_MIN_SAMPLE_SIZE) -> dict:
    if min_sample_size < 2:
        raise ExternalCompError("min_sample_size must be at least 2")

    vehicle = _normalize_vehicle(document)
    source_run_id = str(document.get("source_run_id") or "").strip()
    if not source_run_id:
        raise ExternalCompError("source_run_id is required")

    report_url = document.get("source_url")
    if report_url:
        report_url = _validate_url(report_url)

    raw_comps = document.get("comps")
    if not isinstance(raw_comps, list):
        raise ExternalCompError("comps must be a list")
    if len(raw_comps) < min_sample_size:
        raise ExternalCompError(f"at least {min_sample_size} comps are required")

    seen_keys: set[tuple[str, str]] = set()
    normalized_comps = []
    prices: list[Decimal] = []
    for index, comp in enumerate(raw_comps, start=1):
        if not isinstance(comp, dict):
            raise ExternalCompError(f"comp {index} must be an object")
        source_url = _validate_url(comp.get("source_url"))
        captured_at = _parse_capture_time(comp.get("captured_at"))
        price = _money(comp.get("price"))
        mileage = _positive_int(comp.get("mileage"), f"comp {index} mileage")
        evidence_id = str(comp.get("listing_id") or comp.get("vin") or "").strip()
        if not evidence_id:
            raise ExternalCompError(f"comp {index} requires listing_id or vin")
        dedupe_key = (source_url.lower(), evidence_id.lower())
        if dedupe_key in seen_keys:
            raise ExternalCompError(f"duplicate comp evidence: {source_url} {evidence_id}")
        seen_keys.add(dedupe_key)
        prices.append(price)
        normalized_comps.append(
            {
                "source_url": source_url,
                "captured_at": captured_at,
                "price": float(_quantize(price)),
                "mileage": mileage,
                "listing_id": comp.get("listing_id"),
                "vin": comp.get("vin"),
                "title": comp.get("title"),
                "title_history_caveat": comp.get("title_history_caveat"),
            }
        )

    avg_price = _quantize(sum(prices, Decimal("0")) / Decimal(len(prices)))
    low_price = _quantize(min(prices))
    high_price = _quantize(max(prices))

    confidence_notes = str(document.get("confidence_notes") or "").strip()
    if not confidence_notes:
        confidence_notes = (
            "External retail listing comps; active-listing evidence, not closed-sale outcome evidence."
        )

    metadata = {
        "seed_basis": SOURCE_TAG,
        "vehicle": vehicle,
        "comps": normalized_comps,
        "evidence_count": len(normalized_comps),
    }

    return {
        **vehicle,
        "avg_price": avg_price,
        "low_price": low_price,
        "high_price": high_price,
        "sample_size": len(normalized_comps),
        "source": SOURCE_TAG,
        "source_run_id": source_run_id,
        "source_url": report_url or normalized_comps[0]["source_url"],
        "confidence_notes": confidence_notes,
        "metadata": metadata,
    }


def load_evidence_file(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


INSERT_SQL = """
insert into public.market_prices (
  year,
  make,
  model,
  state,
  avg_price,
  low_price,
  high_price,
  sample_size,
  source,
  source_run_id,
  source_url,
  confidence_notes,
  metadata,
  last_updated,
  expires_at
)
select
  %(year)s,
  %(make)s,
  %(model)s,
  %(state)s,
  %(avg_price)s,
  %(low_price)s,
  %(high_price)s,
  %(sample_size)s,
  %(source)s,
  %(source_run_id)s,
  %(source_url)s,
  %(confidence_notes)s,
  %(metadata)s::jsonb,
  timezone('utc', now()),
  timezone('utc', now()) + (%(ttl_days)s::int * interval '1 day')
where not exists (
  select 1
  from public.market_prices existing
  where existing.year = %(year)s
    and existing.make = %(make)s
    and existing.model = %(model)s
    and coalesce(existing.state, '') = coalesce(%(state)s, '')
    and existing.source = %(source)s
    and existing.source_run_id = %(source_run_id)s
)
returning id, year, make, model, state, avg_price, sample_size
"""


def insert_seed_row(dsn: str, seed_row: dict, *, ttl_days: int) -> Optional[dict]:
    payload = {
        **seed_row,
        "avg_price": str(seed_row["avg_price"]),
        "low_price": str(seed_row["low_price"]),
        "high_price": str(seed_row["high_price"]),
        "metadata": json.dumps(seed_row["metadata"], sort_keys=True),
        "ttl_days": ttl_days,
    }
    with psycopg2.connect(dsn) as connection:
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(INSERT_SQL, payload)
            inserted = cursor.fetchone()
        connection.commit()
    return dict(inserted) if inserted else None


def _normalize_rest_base_url(supabase_url: str) -> str:
    return supabase_url.rstrip("/").removesuffix("/rest/v1")


def _rest_json_request(method: str, url: str, service_role_key: str, payload: Optional[dict] = None):
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


def _market_price_rest_query(seed_row: dict) -> str:
    query = [
        ("select", "id,year,make,model,state,avg_price,sample_size"),
        ("year", f"eq.{seed_row['year']}"),
        ("make", f"eq.{seed_row['make']}"),
        ("model", f"eq.{seed_row['model']}"),
        ("source", f"eq.{seed_row['source']}"),
        ("source_run_id", f"eq.{seed_row['source_run_id']}"),
        ("limit", "1"),
    ]
    state = seed_row.get("state")
    if state:
        query.append(("state", f"eq.{state}"))
    else:
        query.append(("state", "is.null"))
    return urllib_parse.urlencode(query)


def insert_seed_row_via_rest(
    supabase_url: str,
    service_role_key: str,
    seed_row: dict,
    *,
    ttl_days: int,
) -> Optional[dict]:
    base_url = _normalize_rest_base_url(supabase_url)
    query = _market_price_rest_query(seed_row)
    existing = _rest_json_request(
        "GET",
        f"{base_url}/rest/v1/market_prices?{query}",
        service_role_key,
    )
    if existing:
        return None

    now = datetime.now(timezone.utc)
    payload = {
        **seed_row,
        "avg_price": float(seed_row["avg_price"]),
        "low_price": float(seed_row["low_price"]),
        "high_price": float(seed_row["high_price"]),
        "last_updated": now.isoformat(),
        "expires_at": (now + timedelta(days=ttl_days)).isoformat(),
    }
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
    parser.add_argument("--input", required=True, help="JSON evidence file.")
    parser.add_argument("--dsn", help="Postgres DSN. Defaults to env/.env live helpers.")
    parser.add_argument("--env-file", help="Env file to read when DSN is not provided.")
    parser.add_argument("--apply", action="store_true", help="Insert after validation. Default is dry-run.")
    parser.add_argument("--apply-via-rest", action="store_true", help="Use Supabase REST service-role insert for apply.")
    parser.add_argument("--ttl-days", type=int, default=14)
    parser.add_argument("--min-sample-size", type=int, default=DEFAULT_MIN_SAMPLE_SIZE)
    args = parser.parse_args()

    if args.ttl_days <= 0:
        print("--ttl-days must be positive", file=sys.stderr)
        return 2

    try:
        seed_row = validate_external_comp_document(
            load_evidence_file(Path(args.input)),
            min_sample_size=args.min_sample_size,
        )
    except (OSError, json.JSONDecodeError, ExternalCompError) as exc:
        print(f"External comp evidence rejected: {exc}", file=sys.stderr)
        return 1

    print(
        "Validated external comp seed candidate: "
        f"{seed_row['year']} {seed_row['make']} {seed_row['model']} "
        f"state={seed_row.get('state') or 'national'} "
        f"avg={seed_row['avg_price']} low={seed_row['low_price']} high={seed_row['high_price']} "
        f"samples={seed_row['sample_size']} source={seed_row['source']}"
    )

    if not args.apply:
        print("Dry-run only. Re-run with --apply to insert after review.")
        return 0

    if args.apply_via_rest:
        supabase_url = os.environ.get("SUPABASE_URL", "").strip()
        service_role_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        if not supabase_url or not service_role_key:
            print("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required for --apply-via-rest.", file=sys.stderr)
            return 2
        inserted = insert_seed_row_via_rest(
            supabase_url,
            service_role_key,
            seed_row,
            ttl_days=args.ttl_days,
        )
        if inserted:
            print(
                "Inserted external market_prices row via Supabase REST: "
                f"id={inserted['id']} avg={inserted['avg_price']} samples={inserted['sample_size']}"
            )
        else:
            print("No row inserted via Supabase REST; matching source/source_run_id already exists.")
        return 0

    dsn = get_database_url(args.dsn, env_file=args.env_file)
    if not dsn:
        print(
            "No database DSN found. Set SUPABASE_DB_URL, SUPABASE_DATABASE_URL, "
            "SUPABASE_DIRECT_DB_URL, DATABASE_URL, or pass --dsn.",
            file=sys.stderr,
        )
        return 2

    inserted = insert_seed_row(dsn, seed_row, ttl_days=args.ttl_days)
    if inserted:
        print(
            "Inserted external market_prices row: "
            f"id={inserted['id']} avg={inserted['avg_price']} samples={inserted['sample_size']}"
        )
    else:
        print("No row inserted; matching source/source_run_id already exists.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
