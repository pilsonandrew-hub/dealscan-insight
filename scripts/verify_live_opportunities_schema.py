#!/usr/bin/env python3
"""Verify the live public.opportunities schema against the March 2026 launch-safe path."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from typing import Dict, Iterable, Optional

import psycopg2


@dataclass(frozen=True)
class RequiredColumn:
    name: str
    expected_type: str
    source_migration: str
    required: bool = True


REQUIRED_COLUMNS: tuple[RequiredColumn, ...] = (
    RequiredColumn("id", "uuid", "20260311_init_schema.sql"),
    RequiredColumn("listing_id", "text", "20260311_init_schema.sql"),
    RequiredColumn("source", "text", "20260311_init_schema.sql"),
    RequiredColumn("title", "text", "20260311_init_schema.sql"),
    RequiredColumn("year", "integer", "20260311_init_schema.sql"),
    RequiredColumn("make", "text", "20260311_init_schema.sql"),
    RequiredColumn("model", "text", "20260311_init_schema.sql"),
    RequiredColumn("mileage", "integer", "20260311_init_schema.sql"),
    RequiredColumn("state", "text", "20260311_init_schema.sql"),
    RequiredColumn("vin", "text", "20260311_init_schema.sql"),
    RequiredColumn("current_bid", "double precision", "20260311_init_schema.sql"),
    RequiredColumn("mmr", "double precision", "20260311_init_schema.sql"),
    RequiredColumn("estimated_transport", "double precision", "20260311_init_schema.sql"),
    RequiredColumn("auction_fees", "double precision", "20260311_init_schema.sql"),
    RequiredColumn("gross_margin", "double precision", "20260311_init_schema.sql"),
    RequiredColumn("roi", "double precision", "20260311_init_schema.sql"),
    RequiredColumn("dos_score", "double precision", "20260311_init_schema.sql"),
    RequiredColumn("auction_end_date", "timestamp with time zone", "20260311_init_schema.sql"),
    RequiredColumn("listing_url", "text", "20260311_init_schema.sql"),
    RequiredColumn("image_url", "text", "20260311_init_schema.sql"),
    RequiredColumn("raw_data", "jsonb", "20260311_init_schema.sql"),
    RequiredColumn("created_at", "timestamp with time zone", "20260311_init_schema.sql"),
    RequiredColumn("updated_at", "timestamp with time zone", "20260311_init_schema.sql"),
    RequiredColumn("run_id", "character varying", "20260312_event_identity.sql"),
    RequiredColumn("source_run_id", "character varying", "20260312_event_identity.sql"),
    RequiredColumn("pipeline_step", "character varying", "20260312_event_identity.sql"),
    RequiredColumn("step_status", "character varying", "20260312_event_identity.sql"),
    RequiredColumn("processed_at", "timestamp with time zone", "20260312_event_identity.sql"),
    RequiredColumn("canonical_id", "character varying", "20260312_deduplication.sql"),
    RequiredColumn("is_duplicate", "boolean", "20260312_deduplication.sql"),
    RequiredColumn("canonical_record_id", "uuid", "20260312_deduplication.sql"),
    RequiredColumn("all_sources", "array", "20260312_deduplication.sql"),
    RequiredColumn("duplicate_count", "integer", "20260312_deduplication.sql"),
    RequiredColumn("recon_reserve", "double precision", "20260314_total_cost.sql"),
    RequiredColumn("total_cost", "double precision", "20260314_total_cost.sql"),
    RequiredColumn("pricing_source", "text", "20260314_retail_comps.sql"),
    RequiredColumn("retail_comp_price_estimate", "double precision", "20260314_retail_comps.sql"),
    RequiredColumn("retail_comp_low", "double precision", "20260314_retail_comps.sql"),
    RequiredColumn("retail_comp_high", "double precision", "20260314_retail_comps.sql"),
    RequiredColumn("retail_comp_count", "integer", "20260314_retail_comps.sql"),
    RequiredColumn("retail_comp_confidence", "double precision", "20260314_retail_comps.sql"),
    RequiredColumn("pricing_updated_at", "timestamp with time zone", "20260314_retail_comps.sql"),
    RequiredColumn("manheim_mmr_mid", "double precision", "20260314_manheim_ready.sql"),
    RequiredColumn("manheim_mmr_low", "double precision", "20260314_manheim_ready.sql"),
    RequiredColumn("manheim_mmr_high", "double precision", "20260314_manheim_ready.sql"),
    RequiredColumn("manheim_range_width_pct", "double precision", "20260314_manheim_ready.sql"),
    RequiredColumn("manheim_confidence", "double precision", "20260314_manheim_ready.sql"),
    RequiredColumn("manheim_source_status", "text", "20260314_manheim_ready.sql"),
    RequiredColumn("manheim_updated_at", "timestamp with time zone", "20260314_manheim_ready.sql"),
    RequiredColumn("ctm_pct", "double precision", "20260314_investment_grade.sql"),
    RequiredColumn("segment_tier", "integer", "20260314_investment_grade.sql"),
    RequiredColumn("investment_grade", "text", "20260314_investment_grade.sql"),
    RequiredColumn("retail_asking_price_estimate", "double precision", "20260314_proxy_scoring_upgrade.sql"),
    RequiredColumn("retail_proxy_multiplier", "double precision", "20260314_proxy_scoring_upgrade.sql"),
    RequiredColumn("wholesale_ctm_pct", "double precision", "20260314_proxy_scoring_upgrade.sql"),
    RequiredColumn("retail_ctm_pct", "double precision", "20260314_proxy_scoring_upgrade.sql"),
    RequiredColumn("estimated_days_to_sale", "integer", "20260314_proxy_scoring_upgrade.sql"),
    RequiredColumn("roi_per_day", "double precision", "20260314_proxy_scoring_upgrade.sql"),
    RequiredColumn("mmr_lookup_basis", "text", "20260314_proxy_scoring_upgrade.sql"),
    RequiredColumn("mmr_confidence_proxy", "double precision", "20260314_proxy_scoring_upgrade.sql"),
    RequiredColumn("bid_ceiling_pct", "double precision", "20260314_proxy_scoring_upgrade.sql"),
    RequiredColumn("max_bid", "double precision", "20260314_proxy_scoring_upgrade.sql"),
    RequiredColumn("bid_headroom", "double precision", "20260314_proxy_scoring_upgrade.sql"),
    RequiredColumn("ceiling_reason", "text", "20260314_proxy_scoring_upgrade.sql"),
    RequiredColumn("score_version", "text", "20260314_proxy_scoring_upgrade.sql"),
    RequiredColumn("buyer_premium", "double precision", "20260314_launch_alignment.sql"),
    RequiredColumn("city", "text", "20260314_launch_alignment.sql"),
    RequiredColumn("condition_grade", "text", "20260314_launch_alignment.sql"),
    RequiredColumn("legacy_dos_score", "double precision", "20260314_launch_alignment.sql"),
    RequiredColumn("pricing_maturity", "text", "20260314_launch_alignment.sql"),
    RequiredColumn("outcome_sale_price", "double precision", "20260314_launch_alignment.sql"),
    RequiredColumn("outcome_sale_date", "date", "20260314_launch_alignment.sql"),
    RequiredColumn("outcome_days_to_sale", "integer", "20260314_launch_alignment.sql"),
    RequiredColumn("outcome_notes", "text", "20260314_launch_alignment.sql"),
    RequiredColumn("outcome_recorded_at", "timestamp with time zone", "20260314_launch_alignment.sql"),
    RequiredColumn("expected_close_bid", "double precision", "20260315_expected_close_groundwork.sql"),
    RequiredColumn("current_bid_trust_score", "double precision", "20260315_expected_close_groundwork.sql"),
    RequiredColumn("expected_close_source", "text", "20260315_expected_close_groundwork.sql"),
    RequiredColumn("auction_stage_hours_remaining", "double precision", "20260315_expected_close_groundwork.sql"),
)


TYPE_ALIASES = {
    "uuid": {"uuid"},
    "text": {"text", "character varying"},
    "character varying": {"character varying", "text"},
    "integer": {"integer", "smallint", "bigint"},
    "double precision": {"double precision", "real", "numeric"},
    "timestamp with time zone": {"timestamp with time zone"},
    "date": {"date"},
    "jsonb": {"jsonb"},
    "boolean": {"boolean"},
    "array": {"array"},
}


def iter_required_columns() -> Iterable[RequiredColumn]:
    return REQUIRED_COLUMNS


def get_database_url(explicit_dsn: Optional[str]) -> Optional[str]:
    if explicit_dsn:
        return explicit_dsn
    return (
        os.getenv("DATABASE_URL")
        or os.getenv("SUPABASE_DB_URL")
        or os.getenv("SUPABASE_DATABASE_URL")
    )


def normalize_type(data_type: str, udt_name: str) -> str:
    if data_type == "ARRAY":
        return "array"
    if data_type == "USER-DEFINED":
        return udt_name
    return data_type


def fetch_live_columns(dsn: str) -> Dict[str, dict]:
    connection = psycopg2.connect(dsn)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select
                  column_name,
                  data_type,
                  udt_name,
                  is_nullable
                from information_schema.columns
                where table_schema = 'public'
                  and table_name = 'opportunities'
                order by ordinal_position
                """
            )
            return {
                name: {
                    "data_type": normalize_type(data_type, udt_name),
                    "is_nullable": is_nullable,
                }
                for name, data_type, udt_name, is_nullable in cursor.fetchall()
            }
    finally:
        connection.close()


def print_required_columns() -> None:
    print("Required public.opportunities columns for the March 2026 launch-safe path:")
    for column in iter_required_columns():
        print(f"- {column.name}: {column.expected_type} ({column.source_migration})")


def verify_schema(dsn: str) -> int:
    try:
        live_columns = fetch_live_columns(dsn)
    except Exception as exc:
        print(f"Unable to inspect live schema: {exc}", file=sys.stderr)
        return 2

    missing: list[RequiredColumn] = []
    mismatched: list[tuple[RequiredColumn, str]] = []

    for column in iter_required_columns():
        live_column = live_columns.get(column.name)
        if live_column is None:
            missing.append(column)
            continue

        live_type = live_column["data_type"]
        allowed_types = TYPE_ALIASES.get(column.expected_type, {column.expected_type})
        if live_type not in allowed_types:
            mismatched.append((column, live_type))

    print(f"Checked {len(REQUIRED_COLUMNS)} required columns on public.opportunities.")
    for column in iter_required_columns():
        live_column = live_columns.get(column.name)
        if live_column is None:
            print(f"[missing] {column.name} ({column.expected_type}) from {column.source_migration}")
            continue
        print(
            f"[ok] {column.name}: {live_column['data_type']} "
            f"(nullable={live_column['is_nullable']})"
        )

    if missing or mismatched:
        print("\nSchema verification failed.")
        if missing:
            print("Missing columns:")
            for column in missing:
                print(f"- {column.name} ({column.expected_type}) from {column.source_migration}")
        if mismatched:
            print("Type mismatches:")
            for column, live_type in mismatched:
                print(
                    f"- {column.name}: expected {column.expected_type}, got {live_type} "
                    f"({column.source_migration})"
                )
        return 1

    print("\nSchema verification passed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify the live public.opportunities schema against March 2026 launch-safe expectations."
    )
    parser.add_argument("--dsn", help="Postgres connection string. Defaults to DATABASE_URL/SUPABASE_DB_URL.")
    parser.add_argument(
        "--print-required",
        action="store_true",
        help="Print the required canonical columns without connecting to a database.",
    )
    args = parser.parse_args()

    if args.print_required:
        print_required_columns()
        return 0

    dsn = get_database_url(args.dsn)
    if not dsn:
        print("DATABASE_URL (or --dsn) is required for live verification.", file=sys.stderr)
        print_required_columns()
        return 2

    return verify_schema(dsn)


if __name__ == "__main__":
    raise SystemExit(main())
