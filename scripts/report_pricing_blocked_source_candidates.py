#!/usr/bin/env python3
"""Report source candidates blocked by proxy-only pricing before opportunity save."""

from __future__ import annotations

import argparse
import re
import sys
from typing import Any

import psycopg2
import psycopg2.extras

from live_verification_support import get_database_url


PROXY_SKIP_SQL = """
with proxy_skips as (
  select distinct on (coalesce(nullif(listing_id,''), nullif(listing_url,'')))
         run_id, listing_id, listing_url, error_message, created_at
  from public.ingest_delivery_log
  where created_at >= timezone('utc', now()) - (%(lookback_days)s::int * interval '1 day')
    and status = 'skipped_ceiling'
    and error_message like 'pricing_maturity_proxy%%'
  order by coalesce(nullif(listing_id,''), nullif(listing_url,'')), created_at desc
),
joined as (
  select distinct on (coalesce(nullif(sl.listing_id,''), nullif(sl.listing_url,'')))
         sl.source_site,
         sl.year,
         sl.make,
         sl.model,
         sl.state,
         sl.mileage,
         sl.vin,
         sl.current_bid,
         sl.auction_end_date,
         sl.created_at as sonar_created_at,
         ps.error_message,
         ps.created_at as skip_created_at,
         sl.title,
         sl.listing_url,
         exists (
           select 1
           from public.market_prices mp
           where mp.year = sl.year
             and mp.make = lower(trim(sl.make))
             and mp.model = lower(trim(sl.model))
             and coalesce(mp.state, '') = coalesce(nullif(lower(trim(sl.state)), ''), '')
             and mp.avg_price > 0
             and mp.low_price > 0
             and mp.high_price > 0
             and coalesce(mp.sample_size, 0) >= 2
             and mp.expires_at >= timezone('utc', now())
         ) as has_market_price,
         exists (
           select 1
           from public.dealer_sales ds
           where ds.year between sl.year - 1 and sl.year + 1
             and lower(trim(ds.make)) = lower(trim(sl.make))
             and lower(trim(ds.model)) = lower(trim(sl.model))
             and (sl.state is null or upper(ds.state) = upper(sl.state))
             and ds.sale_price > 0
             and ds.sale_date >= timezone('utc', now()) - interval '365 days'
           group by lower(trim(ds.make)), lower(trim(ds.model))
           having count(*) >= 2
         ) as has_usable_dealer_sales
  from proxy_skips ps
  join public.sonar_listings sl
    on (sl.listing_id = ps.listing_id or sl.listing_url = ps.listing_url)
  order by coalesce(nullif(sl.listing_id,''), nullif(sl.listing_url,'')), sl.created_at desc
)
select
  *,
  case
    when auction_end_date is null then null
    else auction_end_date >= timezone('utc', now())
  end as auction_active
from joined
where (%(include_dirty)s or (
    year >= extract(year from now())::int - %(max_age_years)s
    and coalesce(mileage, 999999999) > 0
    and coalesce(mileage, 999999999) <= %(max_mileage)s
    and coalesce(vin,'') <> ''
  ))
order by
  case
    when auction_end_date >= timezone('utc', now()) then 0
    when auction_end_date is null then 1
    else 2
  end,
  skip_created_at desc
limit %(limit)s
"""


def _money(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value.replace("$", "").replace(",", ""))
    except ValueError:
        return None


def parse_proxy_skip_reason(reason: str | None) -> dict[str, Any]:
    text = reason or ""
    return {
        "bid": _money((re.search(r"bid=([^ ]+)", text) or [None, None])[1]),
        "mmr": _money((re.search(r"mmr=([^ ]+)", text) or [None, None])[1]),
        "headroom": _money((re.search(r"headroom=([^ ]+)", text) or [None, None])[1]),
        "tier": (re.search(r"tier=([A-Za-z_]+)", text) or [None, None])[1],
    }


def classify_source_candidate(row: dict[str, Any]) -> str:
    if row.get("has_market_price") or row.get("has_usable_dealer_sales"):
        return "covered_after_skip"
    if not row.get("vin") or not row.get("mileage"):
        return "dirty_source_row"
    if row.get("auction_active") is False:
        return "expired_pricing_gap"
    if row.get("auction_active") is None:
        return "unknown_auction_status_pricing_gap"
    return "active_clean_pricing_gap"


def format_candidate(row: dict[str, Any]) -> str:
    status = classify_source_candidate(row)
    parsed = parse_proxy_skip_reason(row.get("error_message"))
    return (
        "- "
        f"status={status} "
        f"source={row.get('source_site')} "
        f"{row.get('year')} {row.get('make')} {row.get('model')} "
        f"state={row.get('state') or 'unknown'} mileage={row.get('mileage')} vin={row.get('vin') or 'missing'} "
        f"bid={row.get('current_bid')} proxy_bid={parsed.get('bid')} proxy_mmr={parsed.get('mmr')} "
        f"proxy_tier={parsed.get('tier')} auction_active={row.get('auction_active')} "
        f"market_price={row.get('has_market_price')} dealer_sales={row.get('has_usable_dealer_sales')} "
        f"skip_at={row.get('skip_created_at')} title={row.get('title')} url={row.get('listing_url')}"
    )


def summarize(rows: list[dict[str, Any]]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for row in rows:
        status = classify_source_candidate(row)
        summary[status] = summary.get(status, 0) + 1
    return summary


def fetch_rows(
    dsn: str,
    *,
    lookback_days: int,
    max_mileage: int,
    max_age_years: int,
    include_dirty: bool,
    limit: int,
) -> list[dict[str, Any]]:
    with psycopg2.connect(dsn) as connection:
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(
                PROXY_SKIP_SQL,
                {
                    "lookback_days": lookback_days,
                    "max_mileage": max_mileage,
                    "max_age_years": max_age_years,
                    "include_dirty": include_dirty,
                    "limit": limit,
                },
            )
            return [dict(row) for row in cursor.fetchall()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", help="Postgres DSN. Defaults to env/.env live helpers.")
    parser.add_argument("--env-file", help="Env file to read when DSN is not provided.")
    parser.add_argument("--lookback-days", type=int, default=7)
    parser.add_argument("--max-mileage", type=int, default=50000)
    parser.add_argument("--max-age-years", type=int, default=4)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--include-dirty", action="store_true")
    args = parser.parse_args()

    if args.lookback_days <= 0 or args.max_mileage <= 0 or args.max_age_years < 0 or args.limit <= 0:
        print("lookback, mileage, age, and limit arguments must be positive", file=sys.stderr)
        return 2

    dsn = get_database_url(args.dsn, env_file=args.env_file)
    if not dsn:
        print(
            "No database DSN found. Set SUPABASE_DB_URL, SUPABASE_DATABASE_URL, "
            "SUPABASE_DIRECT_DB_URL, DATABASE_URL, or pass --dsn.",
            file=sys.stderr,
        )
        return 2

    rows = fetch_rows(
        dsn,
        lookback_days=args.lookback_days,
        max_mileage=args.max_mileage,
        max_age_years=args.max_age_years,
        include_dirty=args.include_dirty,
        limit=args.limit,
    )
    summary = summarize(rows)
    print(
        f"pricing_proxy_source_candidates={len(rows)} "
        f"lookback_days={args.lookback_days} max_mileage={args.max_mileage} "
        f"summary={summary}"
    )
    for row in rows:
        print(format_candidate(row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
