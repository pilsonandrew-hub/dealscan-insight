#!/usr/bin/env python3
"""Seed market_prices from already-proven market-comp opportunity evidence.

This script intentionally rejects proxy-only rows. It only reads opportunities
that already reached market-comp maturity through dealer_sales_history and then
creates bounded market-price cache rows for the retail-comp service.
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional

import psycopg2
import psycopg2.extras

from live_verification_support import get_database_url


SOURCE_TAG = "opportunities_market_comp_seed"
DEFAULT_MIN_GROUP_SIZE = 5


SEED_SELECT_SQL = """
with eligible as (
  select
    year::int as year,
    lower(trim(make)) as make,
    lower(trim(model)) as model,
    nullif(lower(trim(state)), '') as state,
    retail_comp_price_estimate::numeric as estimate,
    retail_comp_low::numeric as low_price,
    retail_comp_high::numeric as high_price,
    id
  from public.opportunities
  where pricing_maturity = 'market_comp'
    and pricing_source = 'dealer_sales_history'
    and retail_comp_price_estimate > 0
    and coalesce(retail_comp_count, 0) >= 2
    and coalesce(retail_comp_confidence, 0) >= 0.60
    and year is not null
    and make is not null
    and model is not null
)
select
  year,
  make,
  model,
  state,
  round(avg(estimate)::numeric, 2) as avg_price,
  round(avg(coalesce(low_price, estimate))::numeric, 2) as low_price,
  round(avg(coalesce(high_price, estimate))::numeric, 2) as high_price,
  count(*)::int as sample_size,
  (array_agg(id order by id))[1:10] as sample_opportunity_ids
from eligible
group by year, make, model, state
having count(*) >= %(min_group_size)s
order by sample_size desc, year desc, make asc, model asc, state asc nulls last
"""


SEED_INSERT_SQL = f"""
with seed_rows as (
  {SEED_SELECT_SQL}
)
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
  confidence_notes,
  metadata,
  last_updated,
  expires_at
)
select
  year,
  make,
  model,
  state,
  avg_price,
  low_price,
  high_price,
  sample_size,
  %(source_tag)s,
  %(source_run_id)s,
  'Seeded only from existing opportunities with pricing_maturity=market_comp and pricing_source=dealer_sales_history',
  jsonb_build_object(
    'seed_basis', 'opportunities.market_comp.dealer_sales_history',
    'sample_opportunity_ids', sample_opportunity_ids
  ),
  timezone('utc', now()),
  timezone('utc', now()) + (%(ttl_days)s::int * interval '1 day')
from seed_rows
where not exists (
  select 1
  from public.market_prices existing
  where existing.year = seed_rows.year
    and existing.make = seed_rows.make
    and existing.model = seed_rows.model
    and coalesce(existing.state, '') = coalesce(seed_rows.state, '')
    and existing.source = %(source_tag)s
    and existing.expires_at >= timezone('utc', now())
)
returning year, make, model, state, avg_price, sample_size
"""


def _connect(dsn: str):
    return psycopg2.connect(dsn)


def preview_seed_rows(dsn: str, limit: int, min_group_size: int) -> tuple[int, list[dict]]:
    with _connect(dsn) as connection:
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(
                f"select count(*)::int as count from ({SEED_SELECT_SQL}) seed_rows",
                {"min_group_size": min_group_size},
            )
            total = int(cursor.fetchone()["count"])
            cursor.execute(f"{SEED_SELECT_SQL} limit %(limit)s", {"min_group_size": min_group_size, "limit": limit})
            rows = [dict(row) for row in cursor.fetchall()]
            return total, rows


def apply_seed_rows(dsn: str, *, source_run_id: str, ttl_days: int, min_group_size: int) -> list[dict]:
    with _connect(dsn) as connection:
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(
                SEED_INSERT_SQL,
                {
                    "source_tag": SOURCE_TAG,
                    "source_run_id": source_run_id,
                    "ttl_days": ttl_days,
                    "min_group_size": min_group_size,
                },
            )
            inserted = [dict(row) for row in cursor.fetchall()]
        connection.commit()
        return inserted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", help="Postgres DSN. Defaults to env/.env live helpers.")
    parser.add_argument("--env-file", help="Env file to read when DSN is not provided.")
    parser.add_argument("--apply", action="store_true", help="Insert seed rows. Default is dry-run.")
    parser.add_argument("--limit", type=int, default=10, help="Preview row limit.")
    parser.add_argument("--ttl-days", type=int, default=30, help="Expiry window for inserted cache rows.")
    parser.add_argument(
        "--min-group-size",
        type=int,
        default=DEFAULT_MIN_GROUP_SIZE,
        help="Minimum grouped market-comp opportunity rows required before seeding a market price.",
    )
    parser.add_argument("--source-run-id", default="manual-2026-06-02", help="Audit id stored on inserted rows.")
    args = parser.parse_args()

    if args.ttl_days <= 0:
        print("--ttl-days must be positive", file=sys.stderr)
        return 2
    if args.min_group_size < 2:
        print("--min-group-size must be at least 2", file=sys.stderr)
        return 2

    dsn = get_database_url(args.dsn, env_file=args.env_file)
    if not dsn:
        print(
            "No database DSN found. Set SUPABASE_DB_URL, SUPABASE_DATABASE_URL, "
            "SUPABASE_DIRECT_DB_URL, DATABASE_URL, or pass --dsn.",
            file=sys.stderr,
        )
        return 2

    if args.apply:
        inserted = apply_seed_rows(
            dsn,
            source_run_id=args.source_run_id,
            ttl_days=args.ttl_days,
            min_group_size=args.min_group_size,
        )
        print(f"Inserted market_prices seed rows: {len(inserted)}")
        for row in inserted[: args.limit]:
            print(
                "- "
                f"{row['year']} {row['make']} {row['model']} "
                f"state={row.get('state') or 'national'} "
                f"avg={row['avg_price']} samples={row['sample_size']}"
            )
        return 0

    total, rows = preview_seed_rows(dsn, args.limit, args.min_group_size)
    print(f"Dry-run eligible market_prices seed groups: {total} (min_group_size={args.min_group_size})")
    for row in rows:
        print(
            "- "
            f"{row['year']} {row['make']} {row['model']} "
            f"state={row.get('state') or 'national'} "
            f"avg={row['avg_price']} samples={row['sample_size']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
