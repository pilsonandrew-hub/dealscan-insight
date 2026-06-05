#!/usr/bin/env python3
"""Report recent db_save rejections with enough context to prove the next blocker."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from report_pricing_blocked_source_candidates import (
    _fetch_postgrest_rows,
    _normalize_supabase_rest_url,
    _parse_datetime,
    _row_key,
    resolve_rest_config,
)


DEFAULT_STATUSES = ("skipped_gate", "skipped_margin", "skipped_ceiling", "skipped_proof")
POLICY_GATE_PREFIXES = (
    "title_brand_rejected",
    "commercial_vehicle",
    "commercial_hd_tonnage",
    "high_rust_state",
    "non_us_state",
    "not_a_vehicle",
    "bid_not_positive",
    "no_listing_url",
)


def _truthy_vin(value: Any) -> bool:
    text = str(value or "").strip().upper()
    return len(text) == 17 and text.isalnum() and not any(ch in text for ch in "IOQ")


def _is_clean_candidate(row: dict[str, Any], *, max_mileage: int, max_age_years: int, now_year: int) -> bool:
    try:
        year = int(row.get("year") or 0)
    except (TypeError, ValueError):
        return False
    if year < now_year - max_age_years:
        return False
    try:
        mileage = int(row.get("mileage") or 0)
    except (TypeError, ValueError):
        return False
    return 0 < mileage <= max_mileage and bool(row.get("vin_present"))


def classify_rejection(
    row: dict[str, Any],
    *,
    now_year: Optional[int] = None,
    max_mileage: int = 50000,
    max_age_years: int = 4,
) -> str:
    status = str(row.get("status") or "").strip()
    reason = str(row.get("error_message") or "").strip()
    current_year = now_year or datetime.now(timezone.utc).year

    if reason == "source_quality_proof_record" or status == "skipped_proof":
        return "proof_control"
    if not row.get("listing_found", True):
        return "missing_listing_mirror"
    if not _is_clean_candidate(row, max_mileage=max_mileage, max_age_years=max_age_years, now_year=current_year):
        return "dirty_source_row"
    if row.get("auction_active") is False:
        return "expired_rejection"
    if status == "skipped_ceiling":
        if reason.startswith("pricing_maturity_proxy"):
            return "pricing_proxy_rejection"
        if reason.startswith("condition_unverified"):
            return "condition_unverified_rejection"
        return "ceiling_rejection"
    if status == "skipped_margin":
        return "clean_margin_rejection"
    if status == "skipped_gate":
        if reason == "age_or_mileage_exceeded":
            return "unexpected_clean_age_mileage_gate"
        if reason.startswith(POLICY_GATE_PREFIXES):
            return "policy_gate_rejection"
        return "clean_gate_rejection"
    return "other_rejection"


def _status_filter(statuses: tuple[str, ...]) -> str:
    escaped = ",".join(statuses)
    return f"in.({escaped})"


def fetch_rows_via_rest(
    supabase_url: str,
    service_role_key: str,
    *,
    lookback_hours: int,
    max_mileage: int,
    max_age_years: int,
    include_dirty: bool,
    limit: int,
    statuses: tuple[str, ...] = DEFAULT_STATUSES,
    now: Optional[datetime] = None,
) -> list[dict[str, Any]]:
    current_time = now or datetime.now(timezone.utc)
    base_url = _normalize_supabase_rest_url(supabase_url)
    since = (current_time - timedelta(hours=lookback_hours)).isoformat()
    listing_since = (current_time - timedelta(hours=lookback_hours + 24)).isoformat()

    delivery_rows = _fetch_postgrest_rows(
        base_url,
        service_role_key,
        "ingest_delivery_log",
        [
            ("select", "run_id,listing_id,listing_url,status,error_message,created_at"),
            ("created_at", f"gte.{since}"),
            ("status", _status_filter(statuses)),
            ("order", "created_at.desc"),
            ("limit", str(max(limit * 10, 100))),
        ],
    )
    latest_delivery: dict[str, dict[str, Any]] = {}
    for row in delivery_rows:
        key = _row_key(row)
        if key and key not in latest_delivery:
            latest_delivery[key] = row

    sonar_rows = _fetch_postgrest_rows(
        base_url,
        service_role_key,
        "sonar_listings",
        [
            (
                "select",
                "source_site,year,make,model,state,mileage,vin,current_bid,auction_end_date,created_at,listing_id,listing_url",
            ),
            ("created_at", f"gte.{listing_since}"),
            ("order", "created_at.desc"),
            ("limit", str(max(limit * 30, 1000))),
        ],
    )
    latest_listings: dict[str, dict[str, Any]] = {}
    for listing in sonar_rows:
        key = _row_key(listing)
        if key and key in latest_delivery and key not in latest_listings:
            latest_listings[key] = listing

    output: list[dict[str, Any]] = []
    for key, delivery in latest_delivery.items():
        listing = latest_listings.get(key)
        auction_end = _parse_datetime((listing or {}).get("auction_end_date"))
        row = {
            "run_id": delivery.get("run_id"),
            "listing_id_present": bool(delivery.get("listing_id")),
            "listing_url_present": bool(delivery.get("listing_url")),
            "status": delivery.get("status"),
            "error_message": delivery.get("error_message"),
            "skip_created_at": delivery.get("created_at"),
            "listing_found": bool(listing),
            "source_site": (listing or {}).get("source_site") or "unknown",
            "year": (listing or {}).get("year"),
            "make": (listing or {}).get("make"),
            "model": (listing or {}).get("model"),
            "state": (listing or {}).get("state"),
            "mileage": (listing or {}).get("mileage"),
            "vin_present": _truthy_vin((listing or {}).get("vin")),
            "current_bid": (listing or {}).get("current_bid"),
            "auction_active": None if auction_end is None else auction_end >= current_time,
            "sonar_created_at": (listing or {}).get("created_at"),
        }
        row["classification"] = classify_rejection(
            row,
            now_year=current_time.year,
            max_mileage=max_mileage,
            max_age_years=max_age_years,
        )
        if include_dirty or row["classification"] != "dirty_source_row":
            output.append(row)

    output.sort(key=lambda row: str(row.get("skip_created_at") or ""), reverse=True)
    return output[:limit]


def summarize(rows: list[dict[str, Any]]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for row in rows:
        key = str(row.get("classification") or "unknown")
        summary[key] = summary.get(key, 0) + 1
    return dict(sorted(summary.items()))


def format_candidate(row: dict[str, Any]) -> str:
    return (
        "- "
        f"classification={row.get('classification')} "
        f"source={row.get('source_site')} "
        f"status={row.get('status')} "
        f"reason={row.get('error_message')} "
        f"{row.get('year') or 'unknown'} {row.get('make') or 'unknown'} {row.get('model') or 'unknown'} "
        f"state={row.get('state') or 'unknown'} mileage={row.get('mileage')} "
        f"vin_present={row.get('vin_present')} bid={row.get('current_bid')} "
        f"auction_active={row.get('auction_active')} listing_found={row.get('listing_found')} "
        f"skip_at={row.get('skip_created_at')} run_id={row.get('run_id')}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", help="Env file to read for Supabase REST credentials.")
    parser.add_argument("--lookback-hours", type=int, default=4)
    parser.add_argument("--max-mileage", type=int, default=50000)
    parser.add_argument("--max-age-years", type=int, default=4)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--include-dirty", action="store_true")
    parser.add_argument("--via-rest", action="store_true", help="Required: read through Supabase REST.")
    args = parser.parse_args()

    if not args.via_rest:
        print("This proof is intentionally REST-only. Pass --via-rest.", flush=True)
        return 2
    if args.lookback_hours <= 0 or args.max_mileage <= 0 or args.max_age_years < 0 or args.limit <= 0:
        print("lookback, mileage, age, and limit arguments must be positive", flush=True)
        return 2

    rest_base_url, service_role_key, rest_source = resolve_rest_config(args.env_file)
    if not rest_base_url or not service_role_key:
        print("No live Supabase REST read path found. Set SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY.")
        return 2

    rows = fetch_rows_via_rest(
        rest_base_url,
        service_role_key,
        lookback_hours=args.lookback_hours,
        max_mileage=args.max_mileage,
        max_age_years=args.max_age_years,
        include_dirty=args.include_dirty,
        limit=args.limit,
    )
    print(f"db_path=rest:{rest_source or 'unknown'}")
    print(
        f"delivery_rejection_candidates={len(rows)} lookback_hours={args.lookback_hours} "
        f"max_mileage={args.max_mileage} summary={summarize(rows)}"
    )
    for row in rows:
        print(format_candidate(row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
