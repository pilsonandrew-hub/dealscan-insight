#!/usr/bin/env python3
"""Report source candidates blocked by proxy-only pricing before opportunity save."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

import psycopg2
import psycopg2.extras

from live_verification_support import DEFAULT_ENV_FILES, get_database_url


POSTGREST_PAGE_SIZE = 1000
SUPABASE_URL_KEYS = ("SUPABASE_URL", "VITE_SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY_KEYS = ("SUPABASE_SERVICE_ROLE_KEY",)
SOURCE_POLICY_REJECT_PATTERNS = (
    re.compile(r"\bBrightDrop\b", re.IGNORECASE),
    re.compile(r"\bZevo\b", re.IGNORECASE),
    re.compile(r"\bCargo\s+Delivery\s+Van\b", re.IGNORECASE),
)


PROXY_SKIP_SQL = """
with proxy_skips as (
  select distinct on (coalesce(nullif(listing_id,''), nullif(listing_url,'')))
         run_id, listing_id, listing_url, status, error_message, created_at
  from public.ingest_delivery_log
  where created_at >= timezone('utc', now()) - (%(lookback_days)s::int * interval '1 day')
    and (
      (status = 'skipped_ceiling' and error_message like 'pricing_maturity_proxy%%')
      or (status = 'skipped_margin' and error_message like 'margin_below_floor%%pricing=proxy%%')
    )
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
         latest_delivery.status as latest_delivery_status,
         latest_delivery.error_message as latest_delivery_error_message,
         latest_delivery.created_at as latest_delivery_created_at,
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
  left join lateral (
    select idl.status, idl.error_message, idl.created_at
    from public.ingest_delivery_log idl
    where (idl.listing_id = ps.listing_id or idl.listing_url = ps.listing_url)
    order by idl.created_at desc
    limit 1
  ) latest_delivery on true
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
        return float(str(value).replace("$", "").replace(",", ""))
    except ValueError:
        return None


def _extract_money(label: str, text: str) -> float | None:
    match = re.search(rf"{re.escape(label)}=([^ ]+)", text)
    return _money(match.group(1)) if match else None


def _extract_text(label: str, text: str) -> str | None:
    match = re.search(rf"{re.escape(label)}=([A-Za-z_]+)", text)
    return match.group(1) if match else None


def parse_proxy_skip_reason(reason: str | None) -> dict[str, Any]:
    text = reason or ""
    return {
        "bid": _extract_money("bid", text),
        "cost": _extract_money("cost", text),
        "floor": _extract_money("floor", text),
        "headroom": _extract_money("headroom", text),
        "margin": _extract_money("margin", text),
        "max_bid": _extract_money("max_bid", text),
        "mmr": _extract_money("mmr", text),
        "pricing": _extract_text("pricing", text),
        "tier": _extract_text("tier", text),
    }


def _matches_source_policy_reject(row: dict[str, Any]) -> bool:
    text = " ".join(
        str(row.get(field) or "")
        for field in ("title", "make", "model")
    )
    return any(pattern.search(text) for pattern in SOURCE_POLICY_REJECT_PATTERNS)


def _is_superseded_proxy_skip(row: dict[str, Any]) -> bool:
    skip_created_at = _parse_datetime(row.get("skip_created_at"))
    latest_created_at = _parse_datetime(row.get("latest_delivery_created_at"))
    if not skip_created_at or not latest_created_at or latest_created_at <= skip_created_at:
        return False
    latest_message = str(row.get("latest_delivery_error_message") or "")
    return "pricing=proxy" not in latest_message


def classify_source_candidate(row: dict[str, Any]) -> str:
    if _matches_source_policy_reject(row):
        return "source_policy_reject"
    if not row.get("vin") or not row.get("mileage"):
        return "dirty_source_row"
    if _is_superseded_proxy_skip(row):
        return "superseded_after_skip"
    if row.get("has_market_price") or row.get("has_usable_dealer_sales"):
        return "covered_after_skip"
    parsed = parse_proxy_skip_reason(row.get("error_message"))
    margin = parsed.get("margin")
    floor = parsed.get("floor")
    if margin is not None and floor is not None and margin < floor:
        return "below_margin_floor"
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
        f"margin={parsed.get('margin')} floor={parsed.get('floor')} cost={parsed.get('cost')} "
        f"proxy_tier={parsed.get('tier')} proxy_pricing={parsed.get('pricing')} auction_active={row.get('auction_active')} "
        f"market_price={row.get('has_market_price')} dealer_sales={row.get('has_usable_dealer_sales')} "
        f"skip_at={row.get('skip_created_at')} title={row.get('title')} url={row.get('listing_url')}"
        f" latest_delivery_status={row.get('latest_delivery_status')}"
        f" latest_delivery_at={row.get('latest_delivery_created_at')}"
    )


def summarize(rows: list[dict[str, Any]]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for row in rows:
        status = classify_source_candidate(row)
        summary[status] = summary.get(status, 0) + 1
    return summary


def _parse_env_file(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return {}
    values: dict[str, str] = {}
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key:
            values[key] = value
    return values


def _get_env_value(keys: tuple[str, ...], env_file: Optional[str]) -> Optional[str]:
    for key in keys:
        value = os.environ.get(key, "").strip()
        if value:
            return value
    search_paths = [Path(env_file)] if env_file else [Path(candidate) for candidate in DEFAULT_ENV_FILES]
    for path in search_paths:
        file_values = _parse_env_file(path)
        for key in keys:
            value = (file_values.get(key) or "").strip()
            if value:
                return value
    return None


def _normalize_supabase_rest_url(supabase_url: str) -> str:
    base = supabase_url.rstrip("/")
    if base.endswith("/rest/v1"):
        return base
    return f"{base}/rest/v1"


def resolve_rest_config(env_file: Optional[str]) -> tuple[Optional[str], Optional[str], Optional[str]]:
    supabase_url = _get_env_value(SUPABASE_URL_KEYS, env_file)
    service_role_key = _get_env_value(SUPABASE_SERVICE_ROLE_KEY_KEYS, env_file)
    if not supabase_url or not service_role_key:
        return None, None, None
    return _normalize_supabase_rest_url(supabase_url), service_role_key, "env.SUPABASE_URL+SUPABASE_SERVICE_ROLE_KEY"


def _build_postgrest_url(base_url: str, table: str, query: list[tuple[str, str]]) -> str:
    encoded = urllib_parse.urlencode(query, doseq=True)
    return f"{base_url}/{table}?{encoded}" if encoded else f"{base_url}/{table}"


def _postgrest_get_json(
    base_url: str,
    service_role_key: str,
    table: str,
    query: list[tuple[str, str]],
    offset: int,
    limit: int,
) -> list[dict[str, Any]]:
    request = urllib_request.Request(
        _build_postgrest_url(base_url, table, query),
        headers={
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
            "Accept": "application/json",
            "Range-Unit": "items",
            "Range": f"{offset}-{offset + limit - 1}",
        },
    )
    try:
        with urllib_request.urlopen(request, timeout=30) as response:
            payload = response.read().decode("utf-8")
    except urllib_error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        if exc.code == 416:
            return []
        raise RuntimeError(f"Supabase REST API error for {table}: HTTP {exc.code} {body[:300]}") from exc
    except urllib_error.URLError as exc:
        raise RuntimeError(f"Supabase REST API unreachable for {table}: {exc}") from exc
    try:
        data = json.loads(payload or "[]")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Supabase REST API returned invalid JSON for {table}") from exc
    if not isinstance(data, list):
        raise RuntimeError(f"Supabase REST API returned a non-list payload for {table}")
    return [row for row in data if isinstance(row, dict)]


def _fetch_postgrest_rows(
    base_url: str,
    service_role_key: str,
    table: str,
    query: list[tuple[str, str]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = _postgrest_get_json(
            base_url=base_url,
            service_role_key=service_role_key,
            table=table,
            query=query,
            offset=offset,
            limit=POSTGREST_PAGE_SIZE,
        )
        rows.extend(page)
        if len(page) < POSTGREST_PAGE_SIZE:
            return rows
        offset += POSTGREST_PAGE_SIZE


def _parse_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _norm_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _row_key(row: dict[str, Any]) -> str:
    return _norm_text(row.get("listing_id")) or _norm_text(row.get("listing_url"))


def _positive_number(value: Any) -> bool:
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


def _is_pricing_blocked_skip(row: dict[str, Any]) -> bool:
    status = row.get("status")
    message = str(row.get("error_message") or "")
    if status == "skipped_ceiling" and message.startswith("pricing_maturity_proxy"):
        return True
    return status == "skipped_margin" and message.startswith("margin_below_floor") and "pricing=proxy" in message


def _valid_market_price(row: dict[str, Any], now: datetime) -> bool:
    expires_at = _parse_datetime(row.get("expires_at"))
    return (
        _positive_number(row.get("avg_price"))
        and _positive_number(row.get("low_price"))
        and _positive_number(row.get("high_price"))
        and int(row.get("sample_size") or 0) >= 2
        and expires_at is not None
        and expires_at >= now
    )


def _has_market_price(row: dict[str, Any], market_rows: list[dict[str, Any]], now: datetime) -> bool:
    state = _norm_text(row.get("state"))
    for market in market_rows:
        if not _valid_market_price(market, now):
            continue
        if (
            int(market.get("year") or 0) == int(row.get("year") or 0)
            and _norm_text(market.get("make")) == _norm_text(row.get("make"))
            and _norm_text(market.get("model")) == _norm_text(row.get("model"))
            and _norm_text(market.get("state")) == state
        ):
            return True
    return False


def _has_usable_dealer_sales(row: dict[str, Any], dealer_sales_rows: list[dict[str, Any]]) -> bool:
    year = int(row.get("year") or 0)
    make = _norm_text(row.get("make"))
    model = _norm_text(row.get("model"))
    state = _norm_text(row.get("state"))
    count = 0
    for sale in dealer_sales_rows:
        sale_year = int(sale.get("year") or 0)
        if not (year - 1 <= sale_year <= year + 1):
            continue
        if _norm_text(sale.get("make")) != make or _norm_text(sale.get("model")) != model:
            continue
        if state and _norm_text(sale.get("state")) != state:
            continue
        if not _positive_number(sale.get("sale_price")):
            continue
        count += 1
        if count >= 2:
            return True
    return False


def _is_clean_candidate(row: dict[str, Any], *, max_mileage: int, max_age_years: int, now: datetime) -> bool:
    if int(row.get("year") or 0) < now.year - max_age_years:
        return False
    mileage = row.get("mileage")
    try:
        parsed_mileage = int(mileage)
    except (TypeError, ValueError):
        return False
    return 0 < parsed_mileage <= max_mileage and bool(str(row.get("vin") or "").strip())


def fetch_rows_via_rest(
    supabase_url: str,
    service_role_key: str,
    *,
    lookback_days: int,
    max_mileage: int,
    max_age_years: int,
    include_dirty: bool,
    limit: int,
    now: Optional[datetime] = None,
) -> list[dict[str, Any]]:
    current_time = now or datetime.now(timezone.utc)
    base_url = _normalize_supabase_rest_url(supabase_url)
    since = (current_time - timedelta(days=lookback_days)).isoformat()
    listing_since = (current_time - timedelta(days=lookback_days + 30)).isoformat()
    sales_since = (current_time - timedelta(days=365)).isoformat()

    proxy_skip_rows = _fetch_postgrest_rows(
        base_url,
        service_role_key,
        "ingest_delivery_log",
        [
            ("select", "run_id,listing_id,listing_url,status,error_message,created_at"),
            ("created_at", f"gte.{since}"),
            ("status", "in.(skipped_ceiling,skipped_margin)"),
            ("order", "created_at.desc"),
            ("limit", str(max(limit * 5, 100))),
        ],
    )
    proxy_skip_rows = [row for row in proxy_skip_rows if _is_pricing_blocked_skip(row)]
    latest_skips: dict[str, dict[str, Any]] = {}
    for skip in proxy_skip_rows:
        key = _row_key(skip)
        if key and key not in latest_skips:
            latest_skips[key] = skip
    if not latest_skips:
        return []

    delivery_rows = _fetch_postgrest_rows(
        base_url,
        service_role_key,
        "ingest_delivery_log",
        [
            ("select", "run_id,listing_id,listing_url,status,error_message,created_at"),
            ("created_at", f"gte.{since}"),
            ("status", "in.(skipped_ceiling,skipped_margin,saved_sonar)"),
            ("order", "created_at.desc"),
            ("limit", str(max(limit * 20, 1000))),
        ],
    )
    latest_deliveries: dict[str, dict[str, Any]] = {}
    for delivery in delivery_rows:
        key = _row_key(delivery)
        if key and key in latest_skips and key not in latest_deliveries:
            latest_deliveries[key] = delivery

    sonar_rows = _fetch_postgrest_rows(
        base_url,
        service_role_key,
        "sonar_listings",
        [
            (
                "select",
                "source_site,year,make,model,state,mileage,vin,current_bid,auction_end_date,created_at,title,listing_id,listing_url",
            ),
            ("created_at", f"gte.{listing_since}"),
            ("order", "created_at.desc"),
            ("limit", str(max(limit * 20, 1000))),
        ],
    )
    latest_listings: dict[str, dict[str, Any]] = {}
    for listing in sonar_rows:
        key = _row_key(listing)
        if key and key in latest_skips and key not in latest_listings:
            latest_listings[key] = listing

    market_rows = _fetch_postgrest_rows(
        base_url,
        service_role_key,
        "market_prices",
        [
            ("select", "year,make,model,state,avg_price,low_price,high_price,sample_size,expires_at"),
            ("expires_at", f"gte.{current_time.isoformat()}"),
            ("sample_size", "gte.2"),
        ],
    )
    dealer_sales_rows = _fetch_postgrest_rows(
        base_url,
        service_role_key,
        "dealer_sales",
        [
            ("select", "year,make,model,state,sale_price,sale_date"),
            ("sale_date", f"gte.{sales_since}"),
            ("sale_price", "gt.0"),
        ],
    )

    joined: list[dict[str, Any]] = []
    for key, skip in latest_skips.items():
        listing = latest_listings.get(key)
        if not listing:
            continue
        auction_end = _parse_datetime(listing.get("auction_end_date"))
        row = {
            **listing,
            "run_id": skip.get("run_id"),
            "error_message": skip.get("error_message"),
            "skip_created_at": skip.get("created_at"),
            "sonar_created_at": listing.get("created_at"),
            "latest_delivery_status": (latest_deliveries.get(key) or {}).get("status"),
            "latest_delivery_error_message": (latest_deliveries.get(key) or {}).get("error_message"),
            "latest_delivery_created_at": (latest_deliveries.get(key) or {}).get("created_at"),
            "has_market_price": _has_market_price(listing, market_rows, current_time),
            "has_usable_dealer_sales": _has_usable_dealer_sales(listing, dealer_sales_rows),
            "auction_active": None if auction_end is None else auction_end >= current_time,
        }
        if include_dirty or _is_clean_candidate(row, max_mileage=max_mileage, max_age_years=max_age_years, now=current_time):
            joined.append(row)

    joined.sort(
        key=lambda row: (
            0 if row.get("auction_active") is True else 1 if row.get("auction_active") is None else 2,
            -(_parse_datetime(row.get("skip_created_at")) or datetime(1970, 1, 1, tzinfo=timezone.utc)).timestamp(),
        )
    )
    return joined[:limit]


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
    parser.add_argument(
        "--via-rest",
        action="store_true",
        help="Read through Supabase REST service-role API instead of direct Postgres.",
    )
    args = parser.parse_args()

    if args.lookback_days <= 0 or args.max_mileage <= 0 or args.max_age_years < 0 or args.limit <= 0:
        print("lookback, mileage, age, and limit arguments must be positive", file=sys.stderr)
        return 2

    rest_base_url, service_role_key, rest_source = resolve_rest_config(args.env_file)
    dsn = None if args.via_rest else get_database_url(args.dsn, env_file=args.env_file)
    if dsn:
        rows = fetch_rows(
            dsn,
            lookback_days=args.lookback_days,
            max_mileage=args.max_mileage,
            max_age_years=args.max_age_years,
            include_dirty=args.include_dirty,
            limit=args.limit,
        )
    else:
        if not rest_base_url or not service_role_key:
            print(
                "No live database read path found. Set a direct DB DSN, or set "
                "SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY for --via-rest.",
                file=sys.stderr,
            )
            return 2
        if args.via_rest:
            print(f"db_path=rest:{rest_source or 'unknown'}")
        else:
            print(f"db_path=rest:{rest_source or 'unknown'} (direct DSN unavailable)")
        rows = fetch_rows_via_rest(
            rest_base_url,
            service_role_key,
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
