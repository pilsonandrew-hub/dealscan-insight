#!/usr/bin/env python3
"""Verify live pricing-substrate schema and evidence readiness."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Iterable, Optional

import psycopg2
import psycopg2.extras

from live_verification_support import get_database_url


@dataclass(frozen=True)
class RequiredColumn:
    table: str
    name: str
    expected_type: str


REQUIRED_MARKET_PRICE_COLUMNS: tuple[RequiredColumn, ...] = (
    RequiredColumn("market_prices", "id", "uuid"),
    RequiredColumn("market_prices", "year", "integer"),
    RequiredColumn("market_prices", "make", "text"),
    RequiredColumn("market_prices", "model", "text"),
    RequiredColumn("market_prices", "state", "text"),
    RequiredColumn("market_prices", "avg_price", "numeric"),
    RequiredColumn("market_prices", "low_price", "numeric"),
    RequiredColumn("market_prices", "high_price", "numeric"),
    RequiredColumn("market_prices", "sample_size", "integer"),
    RequiredColumn("market_prices", "source", "text"),
    RequiredColumn("market_prices", "source_run_id", "text"),
    RequiredColumn("market_prices", "source_url", "text"),
    RequiredColumn("market_prices", "confidence_notes", "text"),
    RequiredColumn("market_prices", "last_updated", "timestamp with time zone"),
    RequiredColumn("market_prices", "expires_at", "timestamp with time zone"),
    RequiredColumn("market_prices", "created_at", "timestamp with time zone"),
    RequiredColumn("market_prices", "updated_at", "timestamp with time zone"),
)

REQUIRED_MARKET_PRICE_INDEXES = {
    "idx_market_prices_ymm_state_updated",
    "idx_market_prices_ymm_updated",
    "idx_market_prices_expires_at",
}

TYPE_ALIASES = {
    "uuid": {"uuid"},
    "text": {"text", "character varying"},
    "integer": {"integer", "smallint", "bigint"},
    "numeric": {"numeric", "double precision", "real"},
    "timestamp with time zone": {"timestamp with time zone"},
}


def _normalize_type(data_type: str, udt_name: str) -> str:
    if data_type == "USER-DEFINED":
        return udt_name
    return data_type


def _fetch_columns(connection, table: str) -> dict[str, str]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            select column_name, data_type, udt_name
            from information_schema.columns
            where table_schema = 'public'
              and table_name = %s
            """,
            (table,),
        )
        return {
            name: _normalize_type(data_type, udt_name)
            for name, data_type, udt_name in cursor.fetchall()
        }


def _fetch_indexes(connection, table: str) -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            select indexname
            from pg_indexes
            where schemaname = 'public'
              and tablename = %s
            """,
            (table,),
        )
        return {row[0] for row in cursor.fetchall()}


def _fetch_readiness(connection) -> dict:
    with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(
            """
            select
              (
                select count(*)::int
                from public.market_prices
              ) as market_prices_rows,
              (
                select count(*)::int
                from public.market_prices
                where avg_price > 0
                  and low_price > 0
                  and high_price > 0
                  and coalesce(sample_size, 0) >= 2
                  and expires_at >= timezone('utc', now())
                  and source is not null
              ) as market_prices_usable_rows,
              (
                select count(*)::int
                from public.dealer_sales
              ) as dealer_sales_rows,
              (
                select count(*)::int
                from public.dealer_sales
                where sale_price > 0
                  and sale_date >= timezone('utc', now()) - interval '365 days'
              ) as dealer_sales_usable_rows,
              (
                select max(sale_date)
                from public.dealer_sales
              ) as latest_dealer_sale_date
            """
        )
        return dict(cursor.fetchone() or {})


def _iter_schema_failures(columns: dict[str, str], indexes: set[str]) -> Iterable[str]:
    for column in REQUIRED_MARKET_PRICE_COLUMNS:
        live_type = columns.get(column.name)
        if live_type is None:
            yield f"missing column public.{column.table}.{column.name}"
            continue
        allowed_types = TYPE_ALIASES.get(column.expected_type, {column.expected_type})
        if live_type not in allowed_types:
            yield (
                f"type mismatch public.{column.table}.{column.name}: "
                f"expected {column.expected_type}, got {live_type}"
            )

    for index_name in sorted(REQUIRED_MARKET_PRICE_INDEXES - indexes):
        yield f"missing index public.{index_name}"


def verify_pricing_substrate(dsn: str, *, require_ready: bool) -> int:
    try:
        connection = psycopg2.connect(dsn)
    except Exception as exc:
        print(f"Unable to connect to database: {exc}", file=sys.stderr)
        return 2

    try:
        columns = _fetch_columns(connection, "market_prices")
        indexes = _fetch_indexes(connection, "market_prices")
        failures = list(_iter_schema_failures(columns, indexes))
        if failures:
            print("Pricing substrate schema verification failed.")
            for failure in failures:
                print(f"- {failure}")
            return 1

        try:
            readiness = _fetch_readiness(connection)
        except Exception as exc:
            print(f"Pricing substrate readiness query failed: {exc}", file=sys.stderr)
            return 1

        market_usable = int(readiness.get("market_prices_usable_rows") or 0)
        dealer_usable = int(readiness.get("dealer_sales_usable_rows") or 0)
        ready = bool(market_usable > 0 or dealer_usable >= 2)

        print("Pricing substrate schema verification passed.")
        print(f"- market_prices_rows: {readiness.get('market_prices_rows')}")
        print(f"- market_prices_usable_rows: {market_usable}")
        print(f"- dealer_sales_rows: {readiness.get('dealer_sales_rows')}")
        print(f"- dealer_sales_usable_rows: {dealer_usable}")
        print(f"- latest_dealer_sale_date: {readiness.get('latest_dealer_sale_date')}")
        print(f"- ready_for_market_comp_pricing: {str(ready).lower()}")

        if require_ready and not ready:
            print("Pricing substrate evidence is not ready.", file=sys.stderr)
            return 1
        return 0
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", help="Postgres DSN. Defaults to env/.env live helpers.")
    parser.add_argument("--env-file", help="Env file to read when DSN is not provided.")
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="Fail if schema is present but usable pricing evidence is not ready.",
    )
    args = parser.parse_args()

    dsn = get_database_url(args.dsn, env_file=args.env_file)
    if not dsn:
        print(
            "No database DSN found. Set SUPABASE_DB_URL, SUPABASE_DATABASE_URL, "
            "SUPABASE_DIRECT_DB_URL, DATABASE_URL, or pass --dsn.",
            file=sys.stderr,
        )
        return 2

    return verify_pricing_substrate(dsn, require_ready=args.require_ready)


if __name__ == "__main__":
    raise SystemExit(main())
