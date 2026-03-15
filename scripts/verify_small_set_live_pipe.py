#!/usr/bin/env python3
"""Verify live opportunities on a small trusted source set without faking completeness."""

from __future__ import annotations

import argparse
import os
import sys
from typing import Iterable, Optional

import psycopg2
import psycopg2.extras


DEFAULT_TRUSTED_SOURCES = ("govdeals", "publicsurplus")
OUTCOME_PROBE_NOTES = "[probe] live verification write check"


def get_database_url(explicit_dsn: Optional[str]) -> Optional[str]:
    if explicit_dsn:
        return explicit_dsn
    return (
        os.getenv("DATABASE_URL")
        or os.getenv("SUPABASE_DB_URL")
        or os.getenv("SUPABASE_DATABASE_URL")
    )


def normalize_sources(raw_sources: Iterable[str]) -> list[str]:
    normalized = sorted({source.strip().lower() for source in raw_sources if source and source.strip()})
    return normalized or list(DEFAULT_TRUSTED_SOURCES)


def pct(part: int, total: int) -> str:
    if total <= 0:
        return "n/a"
    return f"{(part / total) * 100.0:.1f}%"


def connect(dsn: str):
    return psycopg2.connect(dsn)


def fetch_summary(connection, sources: list[str], lookback_hours: int) -> dict:
    with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(
            """
            select
              count(*)::int as landed_rows,
              count(*) filter (where pricing_maturity = 'live_market')::int as live_market_rows,
              count(*) filter (where pricing_maturity = 'market_comp')::int as market_comp_rows,
              count(*) filter (where pricing_maturity = 'proxy')::int as proxy_rows,
              count(*) filter (where pricing_maturity = 'unknown' or pricing_maturity is null)::int as unknown_rows,
              count(*) filter (
                where acquisition_price_basis is not null
                  and acquisition_price_basis > 0
              )::int as acquisition_basis_present_rows,
              count(*) filter (
                where projected_total_cost is not null
                  and projected_total_cost > 0
              )::int as projected_total_cost_present_rows,
              count(*) filter (
                where expected_close_bid is not null
                  and expected_close_bid > 0
              )::int as expected_close_present_rows,
              count(*) filter (where current_bid_trust_score is not null)::int as trust_score_present_rows,
              count(*) filter (
                where current_bid_trust_score is not null
                  and current_bid_trust_score >= 0.25
              )::int as trust_score_gte_025_rows,
              count(*) filter (
                where investment_grade is not null
                  and bid_headroom is not null
                  and max_bid is not null
                  and acquisition_price_basis is not null
                  and projected_total_cost is not null
              )::int as projected_economics_present_rows,
              count(*) filter (
                where investment_grade is null
                  or bid_headroom is null
                  or max_bid is null
                  or acquisition_price_basis is null
                  or projected_total_cost is null
              )::int as missing_key_field_rows,
              count(*) filter (
                where outcome_sale_price is not null
                  or outcome_sale_date is not null
                  or outcome_days_to_sale is not null
                  or outcome_notes is not null
                  or outcome_recorded_at is not null
              )::int as rows_with_outcomes,
              min(processed_at) as oldest_processed_at,
              max(processed_at) as newest_processed_at
            from public.opportunities
            where processed_at >= now() - (%s * interval '1 hour')
              and lower(source) = any(%s)
            """,
            (lookback_hours, sources),
        )
        row = cursor.fetchone()
        return dict(row or {})


def fetch_source_breakdown(connection, sources: list[str], lookback_hours: int) -> list[dict]:
    with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(
            """
            select
              lower(source) as source,
              count(*)::int as landed_rows,
              count(*) filter (where pricing_maturity = 'live_market')::int as live_market_rows,
              count(*) filter (where pricing_maturity = 'market_comp')::int as market_comp_rows,
              count(*) filter (where pricing_maturity = 'proxy')::int as proxy_rows,
              count(*) filter (where pricing_maturity = 'unknown' or pricing_maturity is null)::int as unknown_rows,
              count(*) filter (
                where acquisition_price_basis is not null
                  and projected_total_cost is not null
                  and investment_grade is not null
              )::int as pricing_core_present_rows
            from public.opportunities
            where processed_at >= now() - (%s * interval '1 hour')
              and lower(source) = any(%s)
            group by lower(source)
            order by landed_rows desc, source asc
            """,
            (lookback_hours, sources),
        )
        return [dict(row) for row in cursor.fetchall()]


def fetch_recent_samples(
    connection,
    sources: list[str],
    lookback_hours: int,
    sample_limit: int,
) -> list[dict]:
    with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(
            """
            select
              id,
              lower(source) as source,
              processed_at,
              pricing_maturity,
              pricing_source,
              current_bid,
              current_bid_trust_score,
              expected_close_bid,
              expected_close_source,
              acquisition_price_basis,
              projected_total_cost,
              investment_grade,
              bid_headroom,
              roi_per_day,
              outcome_recorded_at,
              title
            from public.opportunities
            where processed_at >= now() - (%s * interval '1 hour')
              and lower(source) = any(%s)
            order by processed_at desc
            limit %s
            """,
            (lookback_hours, sources, sample_limit),
        )
        return [dict(row) for row in cursor.fetchall()]


def run_outcome_probe(
    connection,
    sources: list[str],
    lookback_hours: int,
    explicit_opportunity_id: Optional[str],
) -> tuple[bool, str]:
    original_autocommit = connection.autocommit
    connection.autocommit = False
    try:
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            if explicit_opportunity_id:
                cursor.execute(
                    """
                    select id, title
                    from public.opportunities
                    where id = %s
                    limit 1
                    """,
                    (explicit_opportunity_id,),
                )
            else:
                cursor.execute(
                    """
                    select id, title
                    from public.opportunities
                    where processed_at >= now() - (%s * interval '1 hour')
                      and lower(source) = any(%s)
                    order by processed_at desc
                    limit 1
                    """,
                    (lookback_hours, sources),
                )
            target = cursor.fetchone()
            if not target:
                connection.rollback()
                return False, "no candidate row available for outcomes write probe"

            cursor.execute(
                """
                update public.opportunities
                set
                  outcome_notes = %s,
                  outcome_recorded_at = timezone('utc', now())
                where id = %s
                returning id, outcome_recorded_at
                """,
                (OUTCOME_PROBE_NOTES, target["id"]),
            )
            updated = cursor.fetchone()
            if not updated:
                connection.rollback()
                return False, f"update returned no row for {target['id']}"

            connection.rollback()
            return True, f"rolled back update on {target['id']} ({target.get('title', 'unknown')[:80]})"
    except Exception as exc:
        connection.rollback()
        return False, str(exc)
    finally:
        connection.autocommit = original_autocommit


def print_summary(summary: dict) -> None:
    total = int(summary.get("landed_rows") or 0)
    print("Live pipe summary")
    print(f"- Landed rows: {total}")
    print(
        "- Pricing maturity mix: "
        f"live_market={summary.get('live_market_rows', 0)} ({pct(int(summary.get('live_market_rows') or 0), total)}), "
        f"market_comp={summary.get('market_comp_rows', 0)} ({pct(int(summary.get('market_comp_rows') or 0), total)}), "
        f"proxy={summary.get('proxy_rows', 0)} ({pct(int(summary.get('proxy_rows') or 0), total)}), "
        f"unknown={summary.get('unknown_rows', 0)} ({pct(int(summary.get('unknown_rows') or 0), total)})"
    )
    print(
        "- Required pricing fields present: "
        f"acquisition_basis={summary.get('acquisition_basis_present_rows', 0)} ({pct(int(summary.get('acquisition_basis_present_rows') or 0), total)}), "
        f"projected_total_cost={summary.get('projected_total_cost_present_rows', 0)} ({pct(int(summary.get('projected_total_cost_present_rows') or 0), total)}), "
        f"expected_close={summary.get('expected_close_present_rows', 0)} ({pct(int(summary.get('expected_close_present_rows') or 0), total)}), "
        f"trust_score={summary.get('trust_score_present_rows', 0)} ({pct(int(summary.get('trust_score_present_rows') or 0), total)})"
    )
    print(
        "- Economics coverage: "
        f"projected_economics_present={summary.get('projected_economics_present_rows', 0)} ({pct(int(summary.get('projected_economics_present_rows') or 0), total)}), "
        f"missing_key_fields={summary.get('missing_key_field_rows', 0)} ({pct(int(summary.get('missing_key_field_rows') or 0), total)})"
    )
    print(
        "- Trust threshold coverage: "
        f"current_bid_trust_score>=0.25 on {summary.get('trust_score_gte_025_rows', 0)} rows "
        f"({pct(int(summary.get('trust_score_gte_025_rows') or 0), total)})"
    )
    print(
        "- Outcomes currently populated: "
        f"{summary.get('rows_with_outcomes', 0)} rows ({pct(int(summary.get('rows_with_outcomes') or 0), total)})"
    )
    print(
        "- Time window observed: "
        f"{summary.get('oldest_processed_at') or 'n/a'} -> {summary.get('newest_processed_at') or 'n/a'}"
    )


def print_source_breakdown(rows: list[dict]) -> None:
    if not rows:
        return
    print("\nBy source")
    for row in rows:
        total = int(row.get("landed_rows") or 0)
        print(
            f"- {row.get('source')}: landed={total}, "
            f"live_market={row.get('live_market_rows', 0)}, "
            f"market_comp={row.get('market_comp_rows', 0)}, "
            f"proxy={row.get('proxy_rows', 0)}, "
            f"unknown={row.get('unknown_rows', 0)}, "
            f"pricing_core_present={row.get('pricing_core_present_rows', 0)} ({pct(int(row.get('pricing_core_present_rows') or 0), total)})"
        )


def print_recent_samples(rows: list[dict]) -> None:
    if not rows:
        return
    print("\nRecent samples")
    for row in rows:
        title = (row.get("title") or "unknown").replace("\n", " ")[:72]
        print(
            "- "
            f"{row.get('processed_at')} | {row.get('source')} | {row.get('pricing_maturity') or 'unknown'} | "
            f"trust={row.get('current_bid_trust_score') if row.get('current_bid_trust_score') is not None else 'n/a'} | "
            f"basis={row.get('acquisition_price_basis') if row.get('acquisition_price_basis') is not None else 'n/a'} | "
            f"projected_total={row.get('projected_total_cost') if row.get('projected_total_cost') is not None else 'n/a'} | "
            f"grade={row.get('investment_grade') or 'n/a'} | headroom={row.get('bid_headroom') if row.get('bid_headroom') is not None else 'n/a'} | "
            f"outcome_recorded_at={row.get('outcome_recorded_at') or 'n/a'} | {title}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify the live pipe on a small trusted source set using the canonical opportunities table."
    )
    parser.add_argument("--dsn", help="Postgres connection string. Defaults to DATABASE_URL/SUPABASE_DB_URL.")
    parser.add_argument(
        "--sources",
        nargs="+",
        default=list(DEFAULT_TRUSTED_SOURCES),
        help="Trusted source set to verify. Default: govdeals publicsurplus",
    )
    parser.add_argument(
        "--lookback-hours",
        type=int,
        default=24,
        help="How far back to inspect processed_at rows. Default: 24",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=12,
        help="How many recent rows to print. Default: 12",
    )
    parser.add_argument(
        "--probe-outcome-write",
        action="store_true",
        help="Attempt a rolled-back write to outcome fields on a recent row.",
    )
    parser.add_argument(
        "--outcome-opportunity-id",
        help="Specific opportunity id to use for the rolled-back outcome write probe.",
    )
    args = parser.parse_args()

    dsn = get_database_url(args.dsn)
    if not dsn:
        print("DATABASE_URL (or --dsn) is required for live pipe verification.", file=sys.stderr)
        return 2

    sources = normalize_sources(args.sources)

    try:
        connection = connect(dsn)
    except Exception as exc:
        print(f"Unable to connect to live database: {exc}", file=sys.stderr)
        return 2

    try:
        summary = fetch_summary(connection, sources=sources, lookback_hours=args.lookback_hours)
        total = int(summary.get("landed_rows") or 0)

        print(
            "Trusted source set: "
            + ", ".join(sources)
            + f" | lookback_hours={args.lookback_hours}"
        )
        print_summary(summary)
        print_source_breakdown(fetch_source_breakdown(connection, sources=sources, lookback_hours=args.lookback_hours))
        print_recent_samples(
            fetch_recent_samples(
                connection,
                sources=sources,
                lookback_hours=args.lookback_hours,
                sample_limit=args.sample_limit,
            )
        )

        exit_code = 0
        if total <= 0:
            print("\nVerification failed: no landed rows found for the trusted source set in the requested window.")
            exit_code = 1

        if args.probe_outcome_write:
            ok, detail = run_outcome_probe(
                connection,
                sources=sources,
                lookback_hours=args.lookback_hours,
                explicit_opportunity_id=args.outcome_opportunity_id,
            )
            status = "passed" if ok else "failed"
            print(f"\nOutcome write probe {status}: {detail}")
            if not ok:
                exit_code = 1

        return exit_code
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
