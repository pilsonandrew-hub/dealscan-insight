#!/usr/bin/env python3
"""Report clean proxy-priced candidates that still lack market-comp coverage."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from typing import Optional

import psycopg2
import psycopg2.extras

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.business_rules.constants import (
    STANDARD_MAX_MILEAGE,
    STANDARD_VEHICLE_MAX_AGE_YEARS,
)
from live_verification_support import get_database_url
from report_pricing_blocked_source_candidates import (
    _fetch_postgrest_rows,
    _is_pricing_blocked_skip,
    _normalize_supabase_rest_url,
    _parse_datetime,
    _positive_number,
    _row_key,
    parse_proxy_skip_reason,
    resolve_rest_config,
)


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
    'opportunity_proxy' as candidate_origin,
    is_active,
    is_active as opportunity_active,
    null::boolean as auction_active,
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
    and year >= extract(year from now())::int - %(max_age_years)s
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
),
competitor_sales_matches as (
  select
    cp.id,
    count(cs.id)::int as competitor_sales_matches,
    count(cs.id) filter (
      where cs.sale_price > 0
        and cs.auction_end_date >= timezone('utc', now()) - interval '365 days'
    )::int as usable_competitor_sales_matches
  from clean_proxy cp
  left join public.competitor_sales cs
    on cs.year = cp.year
    and lower(trim(cs.make)) = cp.make
    and lower(trim(cs.model)) = cp.model
    and coalesce(nullif(lower(trim(cs.state)), ''), '') = coalesce(cp.state, '')
  group by cp.id
)
select
  cp.*,
  mm.market_prices_matches,
  mm.usable_market_prices_matches,
  dsm.dealer_sales_matches,
  dsm.usable_dealer_sales_matches,
  oh.market_comp_opportunity_history,
  oh.usable_opportunity_history,
  csm.competitor_sales_matches,
  csm.usable_competitor_sales_matches
from clean_proxy cp
join market_matches mm on mm.id = cp.id
join dealer_sales_matches dsm on dsm.id = cp.id
join opportunity_history oh on oh.id = cp.id
join competitor_sales_matches csm on csm.id = cp.id
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


def recommended_action_for_status(status: str) -> str:
    return {
        "covered_by_market_prices": "none",
        "covered_by_dealer_sales": "refresh_market_prices_from_dealer_sales",
        "covered_by_competitor_sales": "refresh_market_prices_from_competitor_sales",
        "seedable_from_internal_history": "refresh_market_prices_from_dealer_sales",
        "insufficient_internal_history": "wait_for_more_internal_history",
        "insufficient_competitor_sales": "request_completed_sales_evidence",
        "blocked_no_internal_comp_evidence": "request_completed_sales_evidence",
        "dirty_source_row": "ignore_dirty_source_row",
        "expired_pricing_gap": "ignore_expired_listing",
    }.get(status, "request_completed_sales_evidence")


def _recovery_key(row: dict) -> tuple[int | None, str, str, str | None]:
    try:
        year = int(row.get("year")) if row.get("year") is not None else None
    except (TypeError, ValueError):
        year = None
    return (
        year,
        _norm_text(row.get("make")),
        _norm_text(row.get("model")),
        _norm_text(row.get("state")) or None,
    )


def _status_from_counts(evidence_counts: dict[str, int]) -> str:
    if evidence_counts["usable_market_prices"] > 0:
        return "covered_by_market_prices"
    if evidence_counts["usable_dealer_sales"] >= 2:
        return "covered_by_dealer_sales"
    if evidence_counts["usable_competitor_sales"] >= MIN_SEEDABLE_HISTORY_ROWS:
        return "covered_by_competitor_sales"
    if evidence_counts["usable_internal_history"] >= MIN_SEEDABLE_HISTORY_ROWS:
        return "seedable_from_internal_history"
    if evidence_counts["usable_internal_history"] > 0:
        return "insufficient_internal_history"
    if evidence_counts["competitor_sales"] > 0:
        return "insufficient_competitor_sales"
    return "blocked_no_internal_comp_evidence"


def group_recovery_rows(rows: list[dict]) -> list[dict]:
    groups: dict[tuple[int | None, str, str, str | None], dict] = {}
    for row in rows:
        key = _recovery_key(row)
        group = groups.setdefault(
            key,
            {
                "key": {
                    "year": key[0],
                    "make": key[1],
                    "model": key[2],
                    "state": key[3],
                },
                "candidate_count": 0,
                "source_counts": {},
                "evidence_counts": {
                    "usable_market_prices": 0,
                    "market_prices": 0,
                    "usable_dealer_sales": 0,
                    "dealer_sales": 0,
                    "usable_internal_history": 0,
                    "internal_history": 0,
                    "usable_competitor_sales": 0,
                    "competitor_sales": 0,
                },
            },
        )
        group["candidate_count"] += 1
        source = _norm_text(row.get("source") or row.get("source_site")) or "unknown"
        group["source_counts"][source] = group["source_counts"].get(source, 0) + 1
        evidence_counts = group["evidence_counts"]
        evidence_counts["usable_market_prices"] = max(
            evidence_counts["usable_market_prices"],
            int(row.get("usable_market_prices_matches") or 0),
        )
        evidence_counts["market_prices"] = max(
            evidence_counts["market_prices"],
            int(row.get("market_prices_matches") or 0),
        )
        evidence_counts["usable_dealer_sales"] = max(
            evidence_counts["usable_dealer_sales"],
            int(row.get("usable_dealer_sales_matches") or 0),
        )
        evidence_counts["dealer_sales"] = max(
            evidence_counts["dealer_sales"],
            int(row.get("dealer_sales_matches") or 0),
        )
        evidence_counts["usable_internal_history"] = max(
            evidence_counts["usable_internal_history"],
            int(row.get("usable_opportunity_history") or 0),
        )
        evidence_counts["internal_history"] = max(
            evidence_counts["internal_history"],
            int(row.get("market_comp_opportunity_history") or 0),
        )
        evidence_counts["usable_competitor_sales"] = max(
            evidence_counts["usable_competitor_sales"],
            int(row.get("usable_competitor_sales_matches") or 0),
        )
        evidence_counts["competitor_sales"] = max(
            evidence_counts["competitor_sales"],
            int(row.get("competitor_sales_matches") or 0),
        )

    recovery_groups = []
    for group in groups.values():
        status = _status_from_counts(group["evidence_counts"])
        group["status"] = status
        group["recommended_action"] = recommended_action_for_status(status)
        recovery_groups.append(group)
    return sorted(
        recovery_groups,
        key=lambda group: (
            -int(group["candidate_count"]),
            group["key"]["year"] or 0,
            group["key"]["make"],
            group["key"]["model"],
            group["key"]["state"] or "",
        ),
    )


def format_recovery_group(group: dict) -> str:
    key = group.get("key") or {}
    evidence = group.get("evidence_counts") or {}
    sources = group.get("source_counts") or {}
    source_text = ",".join(f"{source}:{count}" for source, count in sorted(sources.items()))
    return (
        "- "
        f"{key.get('year')} {key.get('make')} {key.get('model')} "
        f"state={key.get('state') or 'unknown'} "
        f"candidates={group.get('candidate_count', 0)} "
        f"sources={source_text or 'none'} "
        f"status={group.get('status')} "
        f"action={group.get('recommended_action')} "
        f"market={evidence.get('usable_market_prices', 0)}/{evidence.get('market_prices', 0)} "
        f"dealer_sales={evidence.get('usable_dealer_sales', 0)}/{evidence.get('dealer_sales', 0)} "
        f"competitor_sales={evidence.get('usable_competitor_sales', 0)}/{evidence.get('competitor_sales', 0)} "
        f"history={evidence.get('usable_internal_history', 0)}/{evidence.get('internal_history', 0)}"
    )


def format_gap_row(row: dict) -> str:
    evidence_status = classify_gap(row)
    origin = row.get("candidate_origin") or "opportunity_proxy"
    opportunity_active = row.get("opportunity_active")
    if opportunity_active is None and origin == "opportunity_proxy":
        opportunity_active = row.get("is_active")
    auction_active = row.get("auction_active")
    return (
        "- "
        f"origin={origin} "
        f"{row['year']} {row['make']} {row['model']} "
        f"state={row.get('state') or 'unknown'} source={row.get('source') or row.get('source_site')} "
        f"opportunity_active={opportunity_active} auction_active={auction_active} dos={row.get('dos_score')} "
        f"grade={row.get('investment_grade')} headroom={row.get('bid_headroom')} "
        f"bid={row.get('current_bid')} expected_close={row.get('expected_close_bid')} "
        f"retail_proxy={row.get('retail_asking_price_estimate')} "
        f"market={row.get('usable_market_prices_matches')}/{row.get('market_prices_matches')} "
        f"dealer_sales={row.get('usable_dealer_sales_matches')}/{row.get('dealer_sales_matches')} "
        f"history={row.get('usable_opportunity_history')}/{row.get('market_comp_opportunity_history')} "
        f"evidence={evidence_status} "
        f"title={row.get('title')}"
    )


def _norm_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _clean_proxy_row(row: dict[str, Any], *, max_mileage: int, max_age_years: int, now_year: int) -> dict[str, Any] | None:
    if row.get("pricing_maturity") != "proxy":
        return None
    try:
        year = int(row.get("year") or 0)
    except (TypeError, ValueError):
        return None
    if year < now_year - max_age_years:
        return None
    if not str(row.get("vin") or "").strip():
        return None
    try:
        mileage = int(row.get("mileage") or 0)
    except (TypeError, ValueError):
        return None
    if mileage <= 0 or mileage > max_mileage:
        return None
    cleaned = dict(row)
    cleaned["make"] = _norm_text(cleaned.get("make"))
    cleaned["model"] = _norm_text(cleaned.get("model"))
    cleaned["state"] = _norm_text(cleaned.get("state")) or None
    cleaned["candidate_origin"] = "opportunity_proxy"
    cleaned["opportunity_active"] = cleaned.get("is_active")
    cleaned["auction_active"] = None
    return cleaned


def _market_price_matches(row: dict[str, Any], market_rows: list[dict[str, Any]], now: datetime) -> tuple[int, int]:
    matches = 0
    usable = 0
    for market in market_rows:
        if (
            int(market.get("year") or 0) != int(row.get("year") or 0)
            or _norm_text(market.get("make")) != _norm_text(row.get("make"))
            or _norm_text(market.get("model")) != _norm_text(row.get("model"))
        ):
            continue
        matches += 1
        expires_at = _parse_datetime(market.get("expires_at"))
        if (
            _positive_number(market.get("avg_price"))
            and _positive_number(market.get("low_price"))
            and _positive_number(market.get("high_price"))
            and int(market.get("sample_size") or 0) >= 2
            and expires_at is not None
            and expires_at >= now
            and market.get("source")
        ):
            usable += 1
    return matches, usable


def _dealer_sales_matches(row: dict[str, Any], dealer_sales_rows: list[dict[str, Any]], now: datetime) -> tuple[int, int]:
    matches = 0
    usable = 0
    for sale in dealer_sales_rows:
        sale_year = int(sale.get("year") or 0)
        if not int(row.get("year") or 0) - 1 <= sale_year <= int(row.get("year") or 0) + 1:
            continue
        if _norm_text(sale.get("make")) != row.get("make") or _norm_text(sale.get("model")) != row.get("model"):
            continue
        matches += 1
        sale_date = _parse_datetime(sale.get("sale_date"))
        if _positive_number(sale.get("sale_price")) and sale_date is not None and sale_date >= now - timedelta(days=365):
            usable += 1
    return matches, usable


def _competitor_sales_matches(
    row: dict[str, Any],
    competitor_sales_rows: list[dict[str, Any]],
    now: datetime,
) -> tuple[int, int]:
    matches = 0
    usable = 0
    for sale in competitor_sales_rows:
        if int(sale.get("year") or 0) != int(row.get("year") or 0):
            continue
        if _norm_text(sale.get("make")) != row.get("make") or _norm_text(sale.get("model")) != row.get("model"):
            continue
        if (_norm_text(sale.get("state")) or None) != (row.get("state") or None):
            continue
        matches += 1
        sale_date = _parse_datetime(sale.get("auction_end_date") or sale.get("sale_date"))
        if _positive_number(sale.get("sale_price")) and sale_date is not None and sale_date >= now - timedelta(days=365):
            usable += 1
    return matches, usable


def _opportunity_history_matches(row: dict[str, Any], history_rows: list[dict[str, Any]]) -> tuple[int, int]:
    matches = 0
    usable = 0
    for history in history_rows:
        if history.get("id") == row.get("id"):
            continue
        if (
            int(history.get("year") or 0) != int(row.get("year") or 0)
            or _norm_text(history.get("make")) != row.get("make")
            or _norm_text(history.get("model")) != row.get("model")
            or (_norm_text(history.get("state")) or None) != (row.get("state") or None)
        ):
            continue
        matches += 1
        if (
            history.get("pricing_maturity") == "market_comp"
            and history.get("pricing_source") == "dealer_sales_history"
            and _positive_number(history.get("retail_comp_price_estimate"))
            and int(history.get("retail_comp_count") or 0) >= 2
            and float(history.get("retail_comp_confidence") or 0) >= 0.60
        ):
            usable += 1
    return matches, usable


def _is_clean_active_delivery_skip(row: dict[str, Any], *, max_mileage: int, max_age_years: int, now: datetime) -> bool:
    try:
        year = int(row.get("year") or 0)
    except (TypeError, ValueError):
        return False
    if year < now.year - max_age_years:
        return False
    if not str(row.get("vin") or "").strip():
        return False
    try:
        mileage = int(row.get("mileage") or 0)
    except (TypeError, ValueError):
        return False
    if mileage <= 0 or mileage > max_mileage:
        return False
    auction_end = _parse_datetime(row.get("auction_end_date"))
    return auction_end is not None and auction_end >= now


def _fetch_delivery_pricing_skip_rows(
    base_url: str,
    service_role_key: str,
    *,
    lookback_days: int,
    max_mileage: int,
    max_age_years: int,
    limit: int,
    now: datetime,
) -> list[dict[str, Any]]:
    since = (now - timedelta(days=lookback_days)).isoformat()
    listing_since = (now - timedelta(days=lookback_days + 30)).isoformat()

    skip_rows = _fetch_postgrest_rows(
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
    latest_skips: dict[str, dict[str, Any]] = {}
    for skip in skip_rows:
        if not _is_pricing_blocked_skip(skip):
            continue
        key = _row_key(skip)
        if key and key not in latest_skips:
            latest_skips[key] = skip
    if not latest_skips:
        return []

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

    rows: list[dict[str, Any]] = []
    for key, skip in latest_skips.items():
        listing = latest_listings.get(key)
        if not listing:
            continue
        if not _is_clean_active_delivery_skip(
            listing,
            max_mileage=max_mileage,
            max_age_years=max_age_years,
            now=now,
        ):
            continue
        parsed_reason = parse_proxy_skip_reason(skip.get("error_message"))
        rows.append(
            {
                "id": f"delivery:{skip.get('run_id') or 'unknown'}:{key}",
                "candidate_origin": "delivery_pricing_skip",
                "source": listing.get("source_site"),
                "source_site": listing.get("source_site"),
                "title": listing.get("title"),
                "year": listing.get("year"),
                "make": _norm_text(listing.get("make")),
                "model": _norm_text(listing.get("model")),
                "state": _norm_text(listing.get("state")) or None,
                "mileage": listing.get("mileage"),
                "vin": listing.get("vin"),
                "pricing_maturity": "proxy",
                "pricing_source": "delivery_skip",
                "opportunity_active": None,
                "auction_active": True,
                "dos_score": None,
                "processed_at": skip.get("created_at"),
                "bid_headroom": None,
                "investment_grade": None,
                "current_bid": listing.get("current_bid") or parsed_reason.get("bid"),
                "expected_close_bid": listing.get("current_bid") or parsed_reason.get("bid"),
                "acquisition_price_basis": "current_bid",
                "projected_total_cost": parsed_reason.get("cost"),
                "max_bid": parsed_reason.get("max_bid"),
                "retail_asking_price_estimate": parsed_reason.get("mmr"),
                "listing_url": listing.get("listing_url"),
            }
        )
    return rows[:limit]


def fetch_gap_rows_via_rest(
    supabase_url: str,
    service_role_key: str,
    *,
    lookback_days: int,
    max_mileage: int,
    max_age_years: int,
    limit: int,
    now: Optional[datetime] = None,
) -> list[dict[str, Any]]:
    current_time = now or datetime.now(timezone.utc)
    base_url = _normalize_supabase_rest_url(supabase_url)
    since = (current_time - timedelta(days=lookback_days)).isoformat()
    sales_since = (current_time - timedelta(days=365)).isoformat()

    opportunity_select = (
        "id,source,source_site,title,year,make,model,state,mileage,vin,pricing_maturity,"
        "pricing_source,is_active,dos_score,processed_at,bid_headroom,investment_grade,"
        "current_bid,expected_close_bid,acquisition_price_basis,projected_total_cost,max_bid,"
        "retail_asking_price_estimate,listing_url,retail_comp_price_estimate,retail_comp_count,"
        "retail_comp_confidence"
    )
    recent_rows = _fetch_postgrest_rows(
        base_url,
        service_role_key,
        "opportunities",
        [
            ("select", opportunity_select),
            ("processed_at", f"gte.{since}"),
            ("order", "processed_at.desc"),
            ("limit", str(max(limit * 10, 1000))),
        ],
    )
    clean_proxy_rows = [
        cleaned
        for row in recent_rows
        if (
            cleaned := _clean_proxy_row(
                row,
                max_mileage=max_mileage,
                max_age_years=max_age_years,
                now_year=current_time.year,
            )
        )
        is not None
    ][:limit]
    delivery_skip_rows = _fetch_delivery_pricing_skip_rows(
        base_url,
        service_role_key,
        lookback_days=lookback_days,
        max_mileage=max_mileage,
        max_age_years=max_age_years,
        limit=limit,
        now=current_time,
    )
    clean_proxy_rows = [*clean_proxy_rows, *delivery_skip_rows][:limit]
    if not clean_proxy_rows:
        return []

    market_rows = _fetch_postgrest_rows(
        base_url,
        service_role_key,
        "market_prices",
        [
            ("select", "id,year,make,model,state,avg_price,low_price,high_price,sample_size,expires_at,source"),
            ("expires_at", f"gte.{current_time.isoformat()}"),
        ],
    )
    dealer_sales_rows = _fetch_postgrest_rows(
        base_url,
        service_role_key,
        "dealer_sales",
        [
            ("select", "id,year,make,model,state,sale_price,sale_date"),
            ("sale_date", f"gte.{sales_since}"),
        ],
    )
    competitor_sales_rows = _fetch_postgrest_rows(
        base_url,
        service_role_key,
        "competitor_sales",
        [
            ("select", "id,year,make,model,state,sale_price,auction_end_date,source"),
            ("auction_end_date", f"gte.{sales_since}"),
        ],
    )
    history_rows = _fetch_postgrest_rows(
        base_url,
        service_role_key,
        "opportunities",
        [
            ("select", opportunity_select),
            ("pricing_maturity", "eq.market_comp"),
            ("pricing_source", "eq.dealer_sales_history"),
            ("limit", str(max(limit * 20, 1000))),
        ],
    )

    enriched: list[dict[str, Any]] = []
    for row in clean_proxy_rows:
        market_total, market_usable = _market_price_matches(row, market_rows, current_time)
        sales_total, sales_usable = _dealer_sales_matches(row, dealer_sales_rows, current_time)
        competitor_total, competitor_usable = _competitor_sales_matches(row, competitor_sales_rows, current_time)
        history_total, history_usable = _opportunity_history_matches(row, history_rows)
        enriched.append(
            {
                **row,
                "market_prices_matches": market_total,
                "usable_market_prices_matches": market_usable,
                "dealer_sales_matches": sales_total,
                "usable_dealer_sales_matches": sales_usable,
                "competitor_sales_matches": competitor_total,
                "usable_competitor_sales_matches": competitor_usable,
                "market_comp_opportunity_history": history_total,
                "usable_opportunity_history": history_usable,
            }
        )
    return enriched


def fetch_gap_rows(
    dsn: str,
    *,
    lookback_days: int,
    max_mileage: int,
    max_age_years: int,
    limit: int,
) -> list[dict]:
    with psycopg2.connect(dsn) as connection:
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(
                REPORT_SQL,
                {
                    "lookback_days": lookback_days,
                    "max_mileage": max_mileage,
                    "max_age_years": max_age_years,
                    "limit": limit,
                },
            )
            return [dict(row) for row in cursor.fetchall()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", help="Postgres DSN. Defaults to env/.env live helpers.")
    parser.add_argument("--env-file", help="Env file to read when DSN is not provided.")
    parser.add_argument("--lookback-days", type=int, default=7)
    parser.add_argument("--max-mileage", type=int, default=STANDARD_MAX_MILEAGE)
    parser.add_argument("--max-age-years", type=int, default=STANDARD_VEHICLE_MAX_AGE_YEARS)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument(
        "--via-rest",
        action="store_true",
        help="Read through Supabase REST service-role API instead of direct Postgres.",
    )
    parser.add_argument(
        "--grouped",
        action="store_true",
        help="Print aggregate recovery groups instead of row-level candidates.",
    )
    args = parser.parse_args()

    if args.lookback_days <= 0:
        print("--lookback-days must be positive", file=sys.stderr)
        return 2
    if args.max_mileage <= 0:
        print("--max-mileage must be positive", file=sys.stderr)
        return 2
    if args.max_age_years < 0:
        print("--max-age-years must be non-negative", file=sys.stderr)
        return 2
    if args.limit <= 0:
        print("--limit must be positive", file=sys.stderr)
        return 2

    rest_base_url, service_role_key, rest_source = resolve_rest_config(args.env_file)
    dsn = None if args.via_rest else get_database_url(args.dsn, env_file=args.env_file)
    if dsn:
        rows = fetch_gap_rows(
            dsn,
            lookback_days=args.lookback_days,
            max_mileage=args.max_mileage,
            max_age_years=args.max_age_years,
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
        rows = fetch_gap_rows_via_rest(
            rest_base_url,
            service_role_key,
            lookback_days=args.lookback_days,
            max_mileage=args.max_mileage,
            max_age_years=args.max_age_years,
            limit=args.limit,
        )
    print(
        f"clean_proxy_candidates={len(rows)} "
        f"lookback_days={args.lookback_days} "
        f"max_mileage={args.max_mileage} max_age_years={args.max_age_years}"
    )
    if args.grouped:
        groups = group_recovery_rows(rows)
        print(f"pricing_recovery_groups={len(groups)}")
        for group in groups:
            print(format_recovery_group(group))
    else:
        for row in rows:
            print(format_gap_row(row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
