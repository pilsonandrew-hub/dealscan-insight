#!/usr/bin/env python3
"""Report clean proxy-priced candidates that still lack market-comp coverage."""

from __future__ import annotations

import argparse
import sys
from typing import Optional

import psycopg2
import psycopg2.extras

from live_verification_support import get_database_url


MIN_SEEDABLE_HISTORY_ROWS = 5


REPORT_SQL = """
with clean_proxy as (
  select
    id,
    source,
    source_site,
    title,
    year,
    lower(trim(make)) as make,
    lower(trim(model)) as model,
    nullif(lower(trim(state)), '') as state,
    mileage,
    vin,
    pricing_maturity,
    pricing_source,
    is_active,
    dos_score,
    processed_at,
    bid_headroom,
    investment_grade,
    current_bid,
    expected_close_bid,
    acquisition_price_basis,
    projected_total_cost,
    max_bid,
    retail_asking_price_estimate,
    listing_url
  from public.opportunities
  where processed_at >= timezone('utc', now()) - (%(lookback_days)s::int * interval '1 day')
    and pricing_maturity = 'proxy'
    and vin is not null
    and vin <> ''
    and mileage is not null
    and mileage > 0
    and mileage <= %(max_mileage)s
),
market_matches as (
  select
    cp.id,
    count(mp.id)::int as market_prices_matches,
    count(mp.id) filter (
      where mp.avg_price > 0
        and mp.low_price > 0
        and mp.high_price > 0
        and coalesce(mp.sample_size, 0) >= 2
        and mp.expires_at >= timezone('utc', now())
        and mp.source is not null
    )::int as usable_market_prices_matches
  from clean_proxy cp
  left join public.market_prices mp
    on mp.year = cp.year
    and mp.make = cp.make
    and mp.model = cp.model
    and coalesce(mp.state, '') = coalesce(cp.state, '')
  group by cp.id
),
dealer_sales_matches as (
  select
    cp.id,
    count(ds.id)::int as dealer_sales_matches,
    count(ds.id) filter (
      where ds.sale_price > 0
        and ds.sale_date >= timezone('utc', now()) - interval '365 days'
    )::int as usable_dealer_sales_matches
  from clean_proxy cp
  left join public.dealer_sales ds
    on ds.year between cp.year - 1 and cp.year + 1
    and lower(trim(ds.make)) = cp.make
    and lower(trim(ds.model)) = cp.model
    and (cp.state is null or upper(ds.state) = upper(cp.state))
  group by cp.id
),
opportunity_history as (
  select
    cp.id,
    count(hist.id)::int as market_comp_opportunity_history,
    count(hist.id) filter (
      where hist.pricing_maturity = 'market_comp'
        and hist.pricing_source = 'dealer_sales_history'
        and hist.retail_comp_price_estimate > 0
        and coalesce(hist.retail_comp_count, 0) >= 2
        and coalesce(hist.retail_comp_confidence, 0) >= 0.60
    )::int as usable_opportunity_history
  from clean_proxy cp
  left join public.opportunities hist
    on hist.year = cp.year
    and lower(trim(hist.make)) = cp.make
    and lower(trim(hist.model)) = cp.model
    and coalesce(nullif(lower(trim(hist.state)), ''), '') = coalesce(cp.state, '')
  group by cp.id
)
select
  cp.*,
  mm.market_prices_matches,
  mm.usable_market_prices_matches,
  dsm.dealer_sales_matches,
  dsm.usable_dealer_sales_matches,
  oh.market_comp_opportunity_history,
  oh.usable_opportunity_history
from clean_proxy cp
join market_matches mm on mm.id = cp.id
join dealer_sales_matches dsm on dsm.id = cp.id
join opportunity_history oh on oh.id = cp.id
order by cp.is_active desc, cp.processed_at desc
limit %(limit)s
"""


def classify_gap(row: dict, *, min_seedable_history_rows: int = MIN_SEEDABLE_HISTORY_ROWS) -> str:
    """Classify whether a clean proxy row has trusted internal comp evidence."""

    if int(row.get("usable_market_prices_matches") or 0) > 0:
        return "covered_by_market_prices"
    if int(row.get("usable_dealer_sales_matches") or 0) >= 2:
        return "covered_by_dealer_sales"

    usable_history = int(row.get("usable_opportunity_history") or 0)
    if usable_history >= min_seedable_history_rows:
        return "seedable_from_internal_history"
    if usable_history > 0:
        return "insufficient_internal_history"
    return "blocked_no_internal_comp_evidence"


def format_gap_row(row: dict) -> str:
    evidence_status = classify_gap(row)
    return (
        "- "
        f"{row['year']} {row['make']} {row['model']} "
        f"state={row.get('state') or 'unknown'} source={row.get('source') or row.get('source_site')} "
        f"active={row.get('is_active')} dos={row.get('dos_score')} "
        f"grade={row.get('investment_grade')} headroom={row.get('bid_headroom')} "
        f"bid={row.get('current_bid')} expected_close={row.get('expected_close_bid')} "
        f"retail_proxy={row.get('retail_asking_price_estimate')} "
        f"market={row.get('usable_market_prices_matches')}/{row.get('market_prices_matches')} "
        f"dealer_sales={row.get('usable_dealer_sales_matches')}/{row.get('dealer_sales_matches')} "
        f"history={row.get('usable_opportunity_history')}/{row.get('market_comp_opportunity_history')} "
        f"evidence={evidence_status} "
        f"title={row.get('title')}"
    )


def fetch_gap_rows(
    dsn: str,
    *,
    lookback_days: int,
    max_mileage: int,
    limit: int,
) -> list[dict]:
    with psycopg2.connect(dsn) as connection:
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(
                REPORT_SQL,
                {
                    "lookback_days": lookback_days,
                    "max_mileage": max_mileage,
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
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()

    if args.lookback_days <= 0:
        print("--lookback-days must be positive", file=sys.stderr)
        return 2
    if args.max_mileage <= 0:
        print("--max-mileage must be positive", file=sys.stderr)
        return 2
    if args.limit <= 0:
        print("--limit must be positive", file=sys.stderr)
        return 2

    dsn = get_database_url(args.dsn, env_file=args.env_file)
    if not dsn:
        print(
            "No database DSN found. Set SUPABASE_DB_URL, SUPABASE_DATABASE_URL, "
            "SUPABASE_DIRECT_DB_URL, DATABASE_URL, or pass --dsn.",
            file=sys.stderr,
        )
        return 2

    rows = fetch_gap_rows(
        dsn,
        lookback_days=args.lookback_days,
        max_mileage=args.max_mileage,
        limit=args.limit,
    )
    print(
        f"clean_proxy_candidates={len(rows)} "
        f"lookback_days={args.lookback_days} max_mileage={args.max_mileage}"
    )
    for row in rows:
        print(format_gap_row(row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
