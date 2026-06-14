"""Internal read-only DealerScope truth surfaces for governed operators."""
from __future__ import annotations

import logging
import hmac
import os
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, Header, HTTPException, Path

from backend.business_rules.constants import (
    ALERTS_ENABLED_PRODUCTION_DEFAULT,
    DOS_SAVE_THRESHOLD,
    HOT_DEAL_ALERT_THRESHOLD,
)
from backend.ingest.alert_gating import evaluate_alert_gate, has_source_condition_evidence
from backend.ingest.condition import score_condition
from webapp.database import supabase_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/internal", tags=["internal"])
MID_DEAL_SCORE_THRESHOLD = 65.0


def _internal_secret() -> str:
    return (
        os.getenv("INTERNAL_API_SECRET", "").strip()
        or os.getenv("LIFECYCLE_CRON_SECRET", "").strip()
    )


def verify_internal_secret(x_internal_secret: Optional[str]) -> None:
    expected = _internal_secret()
    if not expected:
        logger.error("[INTERNAL_AUTH] INTERNAL_API_SECRET or LIFECYCLE_CRON_SECRET not configured")
        raise HTTPException(status_code=503, detail="Internal authorization not configured")
    if not x_internal_secret or not hmac.compare_digest(x_internal_secret.strip(), expected):
        logger.warning("[INTERNAL_AUTH] rejected unauthorized internal request")
        raise HTTPException(status_code=401, detail="Invalid internal authorization")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _alerts_runtime_status() -> dict[str, Any]:
    raw = os.getenv("ALERTS_ENABLED")
    effective = (raw if raw is not None else ALERTS_ENABLED_PRODUCTION_DEFAULT).strip().lower()
    telegram_bot_configured = bool((os.getenv("TELEGRAM_BOT_TOKEN") or "").strip())
    telegram_chat_configured = bool((os.getenv("TELEGRAM_CHAT_ID") or "").strip())
    return {
        "enabled": effective == "true",
        "source": "env" if raw is not None else "production_default",
        "raw_value": raw if raw in {"true", "false"} else ("set_non_boolean" if raw is not None else None),
        "production_default": ALERTS_ENABLED_PRODUCTION_DEFAULT,
        "telegram_bot_configured": telegram_bot_configured,
        "telegram_chat_configured": telegram_chat_configured,
        "telegram_ready": effective == "true" and telegram_bot_configured and telegram_chat_configured,
    }


def _safe_count(table: str, filters: Optional[list[tuple[str, str, Any]]] = None) -> int:
    query = supabase_client.table(table).select("id", count="exact")
    for method, column, value in filters or []:
        if method == "not_":
            query = query.not_(column, *value)
        else:
            query = getattr(query, method)(column, value)
    result = query.limit(1).execute()
    return int(getattr(result, "count", None) or 0)


def _optional_count(table: str) -> tuple[str, int]:
    try:
        return "present", _safe_count(table)
    except Exception:
        logger.warning("[PIPELINE_TRUTH] optional table unavailable: %s", table)
        return "missing", 0


def _optional_filtered_count(table: str, filters: list[tuple[str, str, Any]]) -> int:
    try:
        return _safe_count(table, filters)
    except Exception:
        logger.warning("[PIPELINE_TRUTH] optional filtered count unavailable: %s", table)
        return 0


def _safe_rows(table: str, select: str, *, order: Optional[tuple[str, bool]] = None, limit: int = 200, filters: Optional[list[tuple[str, str, Any]]] = None) -> list[dict[str, Any]]:
    query = supabase_client.table(table).select(select)
    for method, column, value in filters or []:
        query = getattr(query, method)(column, value)
    if order:
        column, desc = order
        query = query.order(column, desc=desc)
    result = query.limit(limit).execute()
    rows = getattr(result, "data", None) or []
    return rows if isinstance(rows, list) else []


def _optional_rows(table: str, select: str, *, order: Optional[tuple[str, bool]] = None, limit: int = 10) -> list[dict[str, Any]]:
    try:
        return _safe_rows(table, select, order=order, limit=limit)
    except Exception:
        logger.warning("[PIPELINE_TRUTH] optional rows unavailable: %s", table)
        return []


def _as_positive_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _as_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _has_column(rows: list[dict[str, Any]], column: str) -> bool:
    return any(column in row for row in rows)


def _photo_count(row: dict[str, Any]) -> Optional[int]:
    if "photo_count" not in row:
        return None
    try:
        parsed = int(float(row.get("photo_count")))
    except (TypeError, ValueError):
        return None
    return max(parsed, 0)


def _bidder_count(row: dict[str, Any]) -> Optional[int]:
    if "bidder_count" not in row:
        return None
    try:
        parsed = int(float(row.get("bidder_count")))
    except (TypeError, ValueError):
        return None
    return max(parsed, 0)


def _parse_optional_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _market_price_diagnostics(rows: list[dict[str, Any]], *, now: datetime) -> dict[str, Any]:
    failed_predicates: Counter[str] = Counter()
    latest_expires_at: Optional[str] = None
    latest_expires_dt: Optional[datetime] = None
    usable_rows = 0

    for row in rows:
        expires_at = row.get("expires_at")
        expires_dt = _parse_optional_datetime(expires_at)
        if expires_at and (latest_expires_dt is None or (expires_dt and expires_dt > latest_expires_dt)):
            latest_expires_at = str(expires_at)
            latest_expires_dt = expires_dt

        row_failures: list[str] = []
        if not _as_positive_float(row.get("avg_price")) or not _as_positive_float(row.get("low_price")) or not _as_positive_float(row.get("high_price")):
            row_failures.append("nonpositive_price")
        if _as_int(row.get("sample_size")) < 2:
            row_failures.append("sample_size_lt_2")
        if not expires_dt or expires_dt < now:
            row_failures.append("expired")
        if not row.get("source"):
            row_failures.append("source_missing")
        if row_failures:
            failed_predicates.update(row_failures)
        else:
            usable_rows += 1

    return {
        "market_prices_usable_rows": usable_rows,
        "market_prices_unusable_reason_counts": dict(failed_predicates),
        "market_prices_latest_expires_at": latest_expires_at,
    }


def _pricing_substrate_truth() -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    recent_sale_cutoff = (now - timedelta(days=365)).isoformat()

    market_prices_status, market_prices_rows = _optional_count("market_prices")
    market_prices_usable_rows = 0
    market_price_diagnostics = {
        "market_prices_unusable_reason_counts": {},
        "market_prices_latest_expires_at": None,
    }
    if market_prices_status == "present":
        market_price_rows = _optional_rows(
            "market_prices",
            "id,avg_price,low_price,high_price,sample_size,expires_at,source",
            order=("expires_at", True),
            limit=200,
        )
        market_price_diagnostics = _market_price_diagnostics(market_price_rows, now=now)
        market_prices_usable_rows = int(market_price_diagnostics["market_prices_usable_rows"])

    dealer_sales_status, dealer_sales_rows = _optional_count("dealer_sales")
    dealer_sales_usable_rows = 0
    if dealer_sales_status == "present":
        dealer_sales_usable_rows = _optional_filtered_count(
            "dealer_sales",
            [
                ("gt", "sale_price", 0),
                ("gte", "sale_date", recent_sale_cutoff),
            ],
        )

    latest_dealer_sale_rows = _optional_rows(
        "dealer_sales",
        "id,sale_date",
        order=("sale_date", True),
        limit=1,
    ) if dealer_sales_status == "present" else []
    latest_dealer_sale_date = latest_dealer_sale_rows[0].get("sale_date") if latest_dealer_sale_rows else None

    return {
        "market_prices_table": market_prices_status,
        "market_prices_rows": market_prices_rows,
        "market_prices_usable_rows": market_prices_usable_rows,
        **market_price_diagnostics,
        "dealer_sales_table": dealer_sales_status,
        "dealer_sales_rows": dealer_sales_rows,
        "dealer_sales_usable_rows": dealer_sales_usable_rows,
        "latest_dealer_sale_date": latest_dealer_sale_date,
        "ready_for_market_comp_pricing": bool(
            market_prices_usable_rows > 0
            or dealer_sales_usable_rows >= 2
        ),
    }


def _status_counts(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        value = row.get(key)
        if value is not None:
            counter[str(value)] += 1
    return dict(counter.most_common(20))


def _safe_section_rows(
    table: str,
    select: str,
    *,
    order: Optional[tuple[str, bool]] = None,
    limit: int = 200,
    filters: Optional[list[tuple[str, str, Any]]] = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        rows = _safe_rows(table, select, order=order, limit=limit, filters=filters)
        return {"status": "ok", "row_count": len(rows)}, rows
    except Exception as exc:
        logger.warning("[SELLER_RECOVERY_AUDIT] section unavailable table=%s: %s", table, exc)
        return {"status": "unavailable", "reason": str(exc)[:160], "row_count": None}, []


def _seller_recovery_reason_counts(rows: list[dict[str, Any]], key: str = "error_message") -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        value = str(row.get(key) or row.get("reason") or "").strip()
        if value:
            counter[value[:120]] += 1
    return dict(counter.most_common(20))


def _first_number(row: dict[str, Any], *keys: str) -> Optional[float]:
    for key in keys:
        parsed = _as_positive_float(row.get(key))
        if parsed is not None:
            return parsed
    return None


def _candidate_recovery_reasons(row: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if not row.get("vin"):
        reasons.append("missing_vin")
    if row.get("mileage") in (None, "", 0):
        reasons.append("missing_mileage")
    if not (row.get("auction_end_date") or row.get("auction_end") or row.get("auction_end_time")):
        reasons.append("missing_auction_end")
    if str(row.get("condition_grade") or "").strip().lower() in {"", "unknown", "poor"}:
        reasons.append("condition_unverified")
    if str(row.get("pricing_maturity") or "").strip().lower() == "proxy":
        reasons.append("proxy_pricing")
    risk_flags = {str(flag).strip().lower() for flag in (row.get("risk_flags") or [])}
    if "missing_photos" in risk_flags:
        reasons.append("missing_photos_flag")
    photo_count = _photo_count(row)
    if photo_count == 0:
        reasons.append("zero_photo_count")
    elif photo_count is not None and photo_count < 3:
        reasons.append("low_photo_count")
    return reasons


RECOVERY_REASON_WEIGHTS = {
    "missing_vin": 4.0,
    "missing_mileage": 4.0,
    "missing_auction_end": 4.0,
    "condition_unverified": 5.0,
    "proxy_pricing": 5.0,
    "missing_photos_flag": 4.0,
    "zero_photo_count": 4.0,
    "low_photo_count": 2.0,
}


def _bounded_component(value: float, maximum: float) -> float:
    return round(max(0.0, min(float(value), maximum)), 2)


def _component_from_amount(value: Optional[float], *, cap: float, points: float) -> float:
    if value is None or value <= 0:
        return 0.0
    return _bounded_component((min(value, cap) / cap) * points, points)


def _source_key(value: Any) -> str:
    return str(value or "unknown").strip().lower()[:80] or "unknown"


def _recovery_tier(score: float) -> str:
    if score >= 75:
        return "high"
    if score >= 45:
        return "medium"
    return "low"


def _source_health_by_source(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        source = _source_key(row.get("source_name"))
        latest.setdefault(source, row)
    return latest


def _source_health_component(source_site: str, source_health_index: dict[str, dict[str, Any]]) -> float:
    row = source_health_index.get(_source_key(source_site))
    if not row:
        return 0.0
    score = 2.0
    if (_as_int(row.get("failed_runs")) or 0) > 0:
        score += 3.0
    if (_as_int(row.get("skipped_count")) or 0) > 0:
        score += 2.0
    if (_as_int(row.get("parse_event_count")) or 0) > 0:
        score += 2.0
    if (_as_int(row.get("saved_count")) or 0) > 0:
        score += 1.0
    return _bounded_component(score, 10.0)


def _source_keys_with_bidder_counts(rows: list[dict[str, Any]]) -> set[str]:
    return {
        _source_key(row.get("source_site") or row.get("source"))
        for row in rows
        if _bidder_count(row) is not None
    }


def _candidate_evidence(row: dict[str, Any], *, source_bidder_sources: set[str]) -> dict[str, Any]:
    opportunity_bidder = _bidder_count(row)
    source_mirror_bidder = bool(
        opportunity_bidder is None
        and _source_key(row.get("source_site") or row.get("source")) in source_bidder_sources
    )
    return {
        "dos_score_present": _numeric_score(row) is not None,
        "gross_margin_present": _first_number(row, "gross_margin", "potential_profit", "margin") is not None,
        "bid_headroom_present": _first_number(row, "bid_headroom") is not None,
        "photo_count_present": _photo_count(row) is not None,
        "opportunity_bidder_count_present": opportunity_bidder is not None,
        "source_mirror_bidder_count_present": source_mirror_bidder,
        "bidder_depth_surface": (
            "opportunities"
            if opportunity_bidder is not None
            else "source_mirror"
            if source_mirror_bidder
            else None
        ),
        "pricing_maturity": str(row.get("pricing_maturity") or "unknown")[:80],
    }


def _score_candidate(
    row: dict[str, Any],
    reasons: list[str],
    *,
    source_bidder_sources: set[str],
    source_health_index: dict[str, dict[str, Any]],
) -> tuple[float, dict[str, float], dict[str, Any]]:
    gross_margin = _first_number(row, "gross_margin", "potential_profit", "margin")
    bid_headroom = _first_number(row, "bid_headroom")
    value_gap = _bounded_component(
        _component_from_amount(gross_margin, cap=25000.0, points=25.0)
        + _component_from_amount(bid_headroom, cap=25000.0, points=15.0),
        40.0,
    )
    listing_quality = _bounded_component(
        sum(RECOVERY_REASON_WEIGHTS.get(reason, 0.0) for reason in reasons),
        30.0,
    )
    evidence = _candidate_evidence(row, source_bidder_sources=source_bidder_sources)
    evidence_strength = _bounded_component(
        (3.0 if evidence["dos_score_present"] else 0.0)
        + (2.0 if evidence["gross_margin_present"] else 0.0)
        + (2.0 if evidence["bid_headroom_present"] else 0.0)
        + (4.0 if evidence["photo_count_present"] else 0.0)
        + (4.0 if evidence["opportunity_bidder_count_present"] else 0.0)
        + (3.0 if evidence["source_mirror_bidder_count_present"] else 0.0)
        + (3.0 if str(row.get("pricing_maturity") or "").lower() == "market_comp" else 0.0)
        + (2.0 if str(row.get("pricing_maturity") or "").lower() != "proxy" else 0.0),
        20.0,
    )
    source_health = _source_health_component(
        str(row.get("source_site") or row.get("source") or "unknown"),
        source_health_index,
    )
    components = {
        "value_gap": value_gap,
        "listing_quality": listing_quality,
        "evidence_strength": evidence_strength,
        "source_health": source_health,
    }
    score = round(sum(components.values()), 2)
    return score, components, evidence


def _seller_recovery_candidates(
    rows: list[dict[str, Any]],
    *,
    source_listing_rows: Optional[list[dict[str, Any]]] = None,
    source_health_rows: Optional[list[dict[str, Any]]] = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    source_listing_rows = source_listing_rows or []
    source_health_index = _source_health_by_source(source_health_rows or [])
    source_bidder_sources = _source_keys_with_bidder_counts(source_listing_rows)
    candidates: list[dict[str, Any]] = []
    for row in rows:
        if row.get("is_active") is False:
            continue
        gross_margin = _first_number(row, "gross_margin", "potential_profit", "margin")
        bid_headroom = _first_number(row, "bid_headroom")
        if gross_margin is None and bid_headroom is None:
            continue
        reasons = _candidate_recovery_reasons(row)
        if not reasons:
            continue
        score = _numeric_score(row)
        recovery_score, score_components, evidence = _score_candidate(
            row,
            reasons,
            source_bidder_sources=source_bidder_sources,
            source_health_index=source_health_index,
        )
        candidates.append({
            "id": str(row.get("id") or "")[:80],
            "source_site": str(row.get("source_site") or row.get("source") or "unknown")[:80],
            "year": _as_int(row.get("year")) if row.get("year") is not None else None,
            "make": str(row.get("make") or "")[:80],
            "model": str(row.get("model") or "")[:80],
            "dos_score": round(score, 2) if score is not None else None,
            "gross_margin": round(gross_margin, 2) if gross_margin is not None else None,
            "bid_headroom": round(bid_headroom, 2) if bid_headroom is not None else None,
            "pricing_maturity": str(row.get("pricing_maturity") or "unknown")[:80],
            "recovery_reasons": reasons,
            "recovery_score": recovery_score,
            "recovery_tier": _recovery_tier(recovery_score),
            "score_components": score_components,
            "evidence": evidence,
            "truth_boundary": "Internal prioritization from governed fields only; not a recovery guarantee or seller-intent claim.",
        })
    candidates.sort(
        key=lambda item: (
            float(item["recovery_score"] or 0),
            float(item["gross_margin"] or 0),
            float(item["bid_headroom"] or 0),
            float(item["dos_score"] or 0),
        ),
        reverse=True,
    )
    return candidates[:limit]


def _listing_quality_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    active_rows = [row for row in rows if row.get("is_active") is not False]
    known_photo_counts = [
        photo_count
        for row in active_rows
        if (photo_count := _photo_count(row)) is not None
    ]
    known_bidder_counts = [
        bidder_count
        for row in active_rows
        if (bidder_count := _bidder_count(row)) is not None
    ]
    return {
        "sample_count": len(active_rows),
        "missing_vin_count": sum(1 for row in active_rows if not row.get("vin")),
        "missing_mileage_count": sum(1 for row in active_rows if row.get("mileage") in (None, "", 0)),
        "missing_auction_end_count": sum(1 for row in active_rows if not (row.get("auction_end_date") or row.get("auction_end") or row.get("auction_end_time"))),
        "condition_unverified_count": sum(1 for row in active_rows if str(row.get("condition_grade") or "").strip().lower() in {"", "unknown", "poor"}),
        "proxy_pricing_count": sum(1 for row in active_rows if str(row.get("pricing_maturity") or "").strip().lower() == "proxy"),
        "missing_photos_flag_count": sum(1 for row in active_rows if "missing_photos" in {str(flag).strip().lower() for flag in (row.get("risk_flags") or [])}),
        "photo_count_known_count": len(known_photo_counts),
        "zero_photo_count": sum(1 for count in known_photo_counts if count == 0),
        "low_photo_count_count": sum(1 for count in known_photo_counts if count < 3),
        "average_photo_count": round(sum(known_photo_counts) / len(known_photo_counts), 2) if known_photo_counts else None,
        "bidder_count_known_count": len(known_bidder_counts),
        "zero_bidder_count": sum(1 for count in known_bidder_counts if count == 0),
        "thin_bidder_count": sum(1 for count in known_bidder_counts if count < 3),
        "average_bidder_count": round(sum(known_bidder_counts) / len(known_bidder_counts), 2) if known_bidder_counts else None,
        "source_counts": _status_counts(active_rows, "source_site"),
    }


def _source_listing_quality_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    known_bidder_counts = [
        bidder_count
        for row in rows
        if (bidder_count := _bidder_count(row)) is not None
    ]
    return {
        "sample_count": len(rows),
        "bidder_count_known_count": len(known_bidder_counts),
        "zero_bidder_count": sum(1 for count in known_bidder_counts if count == 0),
        "thin_bidder_count": sum(1 for count in known_bidder_counts if count < 3),
        "average_bidder_count": round(sum(known_bidder_counts) / len(known_bidder_counts), 2) if known_bidder_counts else None,
        "source_counts": _status_counts(rows, "source_site") or _status_counts(rows, "source"),
    }


def _recovery_rollups(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    reason_counts: Counter[str] = Counter()
    tier_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    source_scores: dict[str, list[float]] = defaultdict(list)
    source_reasons: dict[str, Counter[str]] = defaultdict(Counter)
    for candidate in candidates:
        source = str(candidate.get("source_site") or "unknown")[:80]
        tier_counts[str(candidate.get("recovery_tier") or "low")] += 1
        source_counts[source] += 1
        source_scores[source].append(float(candidate.get("recovery_score") or 0))
        for reason in candidate.get("recovery_reasons") or []:
            reason_counts[str(reason)] += 1
            source_reasons[source][str(reason)] += 1
    top_sources = []
    for source, scores in source_scores.items():
        top_sources.append({
            "source_site": source,
            "candidate_count": source_counts[source],
            "average_recovery_score": round(sum(scores) / len(scores), 2) if scores else 0.0,
            "top_reasons": [reason for reason, _count in source_reasons[source].most_common(5)],
        })
    top_sources.sort(
        key=lambda item: (item["average_recovery_score"], item["candidate_count"]),
        reverse=True,
    )
    return {
        "reason_counts": dict(reason_counts.most_common(20)),
        "tier_counts": {
            "high": tier_counts.get("high", 0),
            "medium": tier_counts.get("medium", 0),
            "low": tier_counts.get("low", 0),
        },
        "source_counts": dict(source_counts.most_common(20)),
        "top_sources_by_score": top_sources[:10],
    }


def _source_health_summary(
    source_health_rows: list[dict[str, Any]],
    delivery_rows: list[dict[str, Any]],
    parse_event_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    observed_sources = {
        _source_key(row.get("source_name"))
        for row in source_health_rows
        if row.get("source_name")
    }
    return {
        "observed_source_count": len(observed_sources),
        "sources_with_failed_runs": len({
            _source_key(row.get("source_name"))
            for row in source_health_rows
            if row.get("source_name") and (_as_int(row.get("failed_runs")) or 0) > 0
        }),
        "total_processed_runs": sum(_as_int(row.get("processed_runs")) or 0 for row in source_health_rows),
        "total_failed_runs": sum(_as_int(row.get("failed_runs")) or 0 for row in source_health_rows),
        "total_saved_count": sum(_as_int(row.get("saved_count")) or 0 for row in source_health_rows),
        "total_skipped_count": sum(_as_int(row.get("skipped_count")) or 0 for row in source_health_rows),
        "total_parse_event_count": sum(_as_int(row.get("parse_event_count")) or 0 for row in source_health_rows),
        "top_delivery_statuses": _status_counts(delivery_rows, "status"),
        "top_parse_event_statuses": _status_counts(parse_event_rows, "status"),
    }


SELLER_RECOVERY_TRUTH_BOUNDARIES = {
    "candidate_ranking": "Internal deterministic prioritization, not a recovery guarantee.",
    "bidder_depth": "Uses governed opportunity bidder_count when present; otherwise uses governed source mirror bidder_count when present.",
    "photo_quality": "Uses governed photo_count and missing_photos risk flags; does not infer photo quality from private raw payloads.",
    "source_health": "Aggregates run and parse-event observability; does not prove seller intent.",
}


def build_seller_recovery_audit() -> dict[str, Any]:
    sections: dict[str, dict[str, Any]] = {}
    sections["source_health"], source_health_rows = _safe_section_rows(
        "source_health_daily",
        "source_name,observed_date,total_runs,processed_runs,failed_runs,item_count,saved_count,skipped_count,parse_event_count,latest_started_at",
        order=("observed_date", True),
        limit=200,
    )
    sections["deliveries"], delivery_rows = _safe_section_rows(
        "ingest_delivery_log",
        "status,error_message,created_at",
        order=("created_at", True),
        limit=500,
    )
    sections["parse_events"], parse_event_rows = _safe_section_rows(
        "parse_events",
        "source_name,event_type,status,reason,created_at",
        order=("created_at", True),
        limit=500,
    )
    sections["opportunities"], opportunity_rows = _safe_section_rows(
        "opportunities",
        "*",
        order=("updated_at", True),
        limit=500,
    )
    sections["source_listings"], source_listing_rows = _safe_section_rows(
        "sonar_listings",
        "*",
        order=("created_at", True),
        limit=500,
    )

    candidates = _seller_recovery_candidates(
        opportunity_rows,
        source_listing_rows=source_listing_rows,
        source_health_rows=source_health_rows,
    )
    opportunity_bidder_available = any(_bidder_count(row) is not None for row in opportunity_rows)
    source_bidder_available = any(_bidder_count(row) is not None for row in source_listing_rows)
    source_health = [
        {
            "source_name": str(row.get("source_name") or "unknown")[:80],
            "observed_date": row.get("observed_date"),
            "total_runs": _as_int(row.get("total_runs")),
            "processed_runs": _as_int(row.get("processed_runs")),
            "failed_runs": _as_int(row.get("failed_runs")),
            "item_count": _as_int(row.get("item_count")),
            "saved_count": _as_int(row.get("saved_count")),
            "skipped_count": _as_int(row.get("skipped_count")),
            "parse_event_count": _as_int(row.get("parse_event_count")),
            "latest_started_at": row.get("latest_started_at"),
        }
        for row in source_health_rows[:50]
    ]
    unsupported_dimensions = {
        "bidder_depth": {
            "status": "available" if opportunity_bidder_available or source_bidder_available else "unavailable",
            "evidence_surface": (
                "opportunities"
                if opportunity_bidder_available
                else "source_mirror"
                if source_bidder_available
                else None
            ),
            "reason": (
                "Governed opportunity bidder_count evidence is present on sampled rows."
                if opportunity_bidder_available
                else "Governed source mirror bidder_count evidence is present on sampled rows."
                if source_bidder_available
                else "No governed bidder-count evidence is currently present across sampled opportunity or source mirror rows."
            ),
        },
        "photo_count": {
            "status": "available" if _has_column(opportunity_rows, "photo_count") else "unavailable",
            "reason": (
                "Governed opportunity photo_count field is queryable on sampled rows."
                if _has_column(opportunity_rows, "photo_count")
                else "Current normalized opportunity rows only prove missing_photos as a risk flag, not a reliable photo count."
            ),
        },
    }
    status = "degraded" if sections["opportunities"]["status"] != "ok" else "ok"
    unavailable_dimensions = [
        name
        for name, details in unsupported_dimensions.items()
        if details.get("status") == "unavailable"
    ]
    return {
        "generated_at": _now_iso(),
        "status": status,
        "scope": "internal_seller_recovery_audit",
        "summary": {
            "source_count": len({row.get("source_name") for row in source_health_rows if row.get("source_name")}),
            "candidate_count": len(candidates),
            "unavailable_dimensions": unavailable_dimensions,
        },
        "sections": sections,
        "source_health": source_health,
        "listing_quality": _listing_quality_summary(opportunity_rows),
        "source_listing_quality": _source_listing_quality_summary(source_listing_rows),
        "source_health_summary": _source_health_summary(source_health_rows, delivery_rows, parse_event_rows),
        "recovery_rollups": _recovery_rollups(candidates),
        "delivery_status_counts": _status_counts(delivery_rows, "status"),
        "delivery_reason_counts": _seller_recovery_reason_counts(delivery_rows),
        "parse_event_status_counts": _status_counts(parse_event_rows, "status"),
        "parse_event_type_counts": _status_counts(parse_event_rows, "event_type"),
        "parse_event_reason_counts": _seller_recovery_reason_counts(parse_event_rows, "reason"),
        "value_leak_candidates": candidates,
        "unsupported_dimensions": unsupported_dimensions,
        "truth_boundary": "Internal aggregate audit. Does not print VINs, listing URLs, descriptions, raw payloads, user data, or tokens.",
        "truth_boundaries": SELLER_RECOVERY_TRUTH_BOUNDARIES,
    }


def _numeric_score(row: dict[str, Any]) -> Optional[float]:
    score = row.get("dos_score") if row.get("dos_score") is not None else row.get("score")
    try:
        return float(score)
    except (TypeError, ValueError):
        return None


def _dos_score_bucket(score: Optional[float]) -> str:
    if score is None:
        return "missing"
    if score >= HOT_DEAL_ALERT_THRESHOLD:
        return "80_plus"
    if score >= MID_DEAL_SCORE_THRESHOLD:
        return "65_to_79"
    if score >= DOS_SAVE_THRESHOLD:
        return "50_to_64"
    return "under_50"


def _dos_score_buckets(rows: list[dict[str, Any]]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        counter[_dos_score_bucket(_numeric_score(row))] += 1
    return dict(counter.most_common())


def _dos_score_stats(rows: list[dict[str, Any]]) -> dict[str, Optional[float]]:
    scores = [
        score
        for row in rows
        if (score := _numeric_score(row)) is not None
    ]
    if not scores:
        return {
            "active_dos_score_min_sample": None,
            "active_dos_score_max_sample": None,
            "active_dos_score_avg_sample": None,
        }
    return {
        "active_dos_score_min_sample": round(min(scores), 2),
        "active_dos_score_max_sample": round(max(scores), 2),
        "active_dos_score_avg_sample": round(sum(scores) / len(scores), 2),
    }


def _alert_gate_breakdown(rows: list[dict[str, Any]], *, limit: int = 25) -> list[dict[str, Any]]:
    breakdown: list[dict[str, Any]] = []
    for row in rows[:limit]:
        gate = evaluate_alert_gate(row)
        signals = gate.get("signals") or {}
        condition_blocker_basis = _condition_blocker_basis(row)
        breakdown.append({
            "id": row.get("id"),
            "source_site": row.get("source_site"),
            "created_at": row.get("created_at"),
            "dos_score": row.get("dos_score") or row.get("score"),
            "eligible": bool(gate.get("eligible")),
            "alert_type": gate.get("alert_type"),
            "blocking_reasons": gate.get("blocking_reasons") or [],
            "summary": gate.get("summary"),
            "signals": {
                "pricing_maturity": signals.get("pricing_maturity"),
                "investment_grade": signals.get("investment_grade"),
                "confidence": signals.get("confidence"),
                "mileage": signals.get("mileage"),
                "condition_grade": signals.get("condition_grade"),
                "condition_blocker_basis": condition_blocker_basis,
                "current_bid_trust_score": signals.get("current_bid_trust_score"),
            },
        })
    return breakdown


def _gate_blocker_counts(breakdown: list[dict[str, Any]]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for item in breakdown:
        for reason in item.get("blocking_reasons") or []:
            counter[str(reason)] += 1
    return dict(counter.most_common(20))


_EXPLICIT_NEGATIVE_CONDITION_SIGNALS = frozenset({
    "flood",
    "fire",
    "hail",
    "storm",
    "water damage",
    "salvage",
    "frame damage",
    "structural damage",
    "rollover",
    "totaled",
    "no start",
    "not running",
    "does not run",
    "non-runner",
    "non runner",
    "will not start",
    "won't start",
    "grade_1",
    "grade_2",
    "needs work",
    "parts only",
    "wrecked",
    "branded title",
    "rebuilt",
    "odometer rollback",
    "lemon",
    "engine performance concerns",
    "dash warning indicators",
    "warning indicators",
    "major components missing",
    "interior defects",
    "ac issues",
    "a/c issues",
    "need jumpstart",
    "check engine",
    "repairs required",
    "open manufacturer recall",
    "remedy not yet available",
})


def _raw_data(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("raw_data")
    return raw if isinstance(raw, dict) else {}


def _pick_row_or_raw(row: dict[str, Any], *keys: str) -> Any:
    raw = _raw_data(row)
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
        value = raw.get(key)
        if value not in (None, ""):
            return value
    return None


def _condition_description(row: dict[str, Any]) -> str:
    """Combine source condition text without letting title-like fields shadow detail text."""
    title_text = " ".join(str(_pick_row_or_raw(row, "title") or "").split()).strip().lower()
    parts: list[str] = []
    seen: set[str] = set()
    for key in ("description", "details", "condition_notes", "detail_text", "assetLongDesc"):
        value = _pick_row_or_raw(row, key)
        if value in (None, ""):
            continue
        text = " ".join(str(value).split()).strip()
        if not text:
            continue
        normalized = text.lower()
        if normalized == title_text:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        parts.append(text)
    return " ".join(parts)


def _condition_blocker_basis(row: dict[str, Any]) -> Optional[str]:
    condition_grade = str(row.get("condition_grade") or "").strip().lower()
    if condition_grade not in {"", "poor", "unknown"}:
        return None

    title = str(_pick_row_or_raw(row, "title") or "")
    description = _condition_description(row)
    damage_type = str(_pick_row_or_raw(row, "damage_type", "damage", "title_status") or "")
    mileage = _pick_row_or_raw(row, "mileage")
    year = _pick_row_or_raw(row, "year")

    condition = score_condition(
        title=title,
        description=description,
        mileage=mileage or 0,
        year=year or 0,
        damage_type=damage_type,
    )
    signals = {str(signal).lower() for signal in condition.get("condition_signals") or []}
    if signals & _EXPLICIT_NEGATIVE_CONDITION_SIGNALS:
        return "explicit_negative_condition_signal"
    if year or mileage:
        return "age_mileage_heuristic"
    if title or description or damage_type:
        return "source_text_without_negative_signal"
    return "missing_condition_evidence"


def _condition_blocker_basis_sample(row: dict[str, Any]) -> Optional[dict[str, Any]]:
    basis = _condition_blocker_basis(row)
    if not basis:
        return None

    title = str(_pick_row_or_raw(row, "title") or "")
    description = _condition_description(row)
    damage_type = str(_pick_row_or_raw(row, "damage_type", "damage", "title_status") or "")
    mileage = _pick_row_or_raw(row, "mileage")
    year = _pick_row_or_raw(row, "year")
    condition = score_condition(
        title=title,
        description=description,
        mileage=mileage or 0,
        year=year or 0,
        damage_type=damage_type,
    )
    source_text_excerpt = " ".join(
        f"{title} {description} {damage_type}".split()
    )[:240]
    return {
        "id": row.get("id"),
        "source_site": row.get("source_site") or row.get("source"),
        "title": title or None,
        "year": year,
        "mileage": mileage,
        "condition_grade": row.get("condition_grade"),
        "condition_blocker_basis": basis,
        "condition_signals": condition.get("condition_signals") or [],
        "source_text_excerpt": source_text_excerpt,
    }


def _condition_blocker_basis_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        basis = _condition_blocker_basis(row)
        if basis:
            counter[basis] += 1
    return dict(counter.most_common(20))


def _condition_blocker_basis_by_source(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    by_source: dict[str, Counter[str]] = {}
    for row in rows:
        basis = _condition_blocker_basis(row)
        if not basis:
            continue
        source = str(row.get("source_site") or row.get("source") or "unknown").strip().lower() or "unknown"
        by_source.setdefault(source, Counter())[basis] += 1
    return {
        source: dict(counter.most_common(20))
        for source, counter in sorted(by_source.items())
    }


def _condition_blocker_basis_samples(rows: list[dict[str, Any]], *, limit: int = 20) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for row in rows:
        sample = _condition_blocker_basis_sample(row)
        if sample:
            samples.append(sample)
        if len(samples) >= limit:
            break
    return samples


def _condition_storage_gap_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    gap_rows: list[dict[str, Any]] = []
    for row in rows:
        if _stored_source_condition_evidence(row):
            continue
        gap_rows.append(row)
    return gap_rows


def _condition_storage_gap_by_source(rows: list[dict[str, Any]]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in _condition_storage_gap_rows(rows):
        source = str(row.get("source_site") or row.get("source") or "unknown").strip().lower() or "unknown"
        counter[source] += 1
    return dict(counter.most_common(20))


def _condition_storage_gap_samples(rows: list[dict[str, Any]], *, limit: int = 20) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for row in _condition_storage_gap_rows(rows):
        proof = _opportunity_condition_proof_row(row)
        samples.append({
            "id": proof.get("id"),
            "source_site": proof.get("source_site"),
            "title": proof.get("title"),
            "year": proof.get("year"),
            "mileage": proof.get("mileage"),
            "condition_grade": proof.get("condition_grade"),
            "condition_blocker_basis": proof.get("condition_blocker_basis"),
            "condition_evidence_fields": proof.get("condition_evidence_fields"),
            "condition_backfill_assessment": proof.get("condition_backfill_assessment"),
            "source_identity": proof.get("source_identity"),
            "raw_data_keys_present": proof.get("raw_data_keys_present"),
        })
        if len(samples) >= limit:
            break
    return samples


def _condition_evidence_fields(row: dict[str, Any]) -> dict[str, dict[str, Any]]:
    title_text = " ".join(str(_pick_row_or_raw(row, "title") or "").split()).strip().lower()
    evidence: dict[str, dict[str, Any]] = {}
    for key in ("description", "details", "condition_notes", "detail_text", "assetLongDesc"):
        value = _pick_row_or_raw(row, key)
        text = " ".join(str(value or "").split()).strip()
        evidence[key] = {
            "present": bool(text),
            "length": len(text),
            "matches_title": bool(text and text.lower() == title_text),
        }
    return evidence


def _raw_data_keys_present(row: dict[str, Any]) -> list[str]:
    raw = _raw_data(row)
    return sorted(
        key
        for key, value in raw.items()
        if value not in (None, "", [], {})
    )


def _public_url_without_query(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    parts = urlsplit(text)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return None
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _source_identity(row: dict[str, Any]) -> dict[str, Any]:
    vin = str(_pick_row_or_raw(row, "vin") or "").strip()
    return {
        "listing_id": _pick_row_or_raw(row, "listing_id"),
        "listing_url": _public_url_without_query(_pick_row_or_raw(row, "listing_url", "url")),
        "source_run_id": _pick_row_or_raw(row, "source_run_id"),
        "run_id": _pick_row_or_raw(row, "run_id"),
        "actor_run_id": _pick_row_or_raw(row, "actor_run_id"),
        "apify_run_id": _pick_row_or_raw(row, "apify_run_id"),
        "vin_present": bool(vin),
        "vin_suffix": vin[-6:] if len(vin) >= 6 else (vin or None),
    }


def _stored_source_condition_evidence(row: dict[str, Any]) -> bool:
    return has_source_condition_evidence(row)


def _condition_backfill_assessment(row: dict[str, Any]) -> dict[str, Any]:
    has_evidence = _stored_source_condition_evidence(row)
    if has_evidence:
        return {
            "stored_source_condition_evidence": True,
            "status": "source_condition_evidence_present",
            "reason": "stored row already has non-title condition evidence",
        }
    return {
        "stored_source_condition_evidence": False,
        "status": "blocked_missing_source_condition_evidence",
        "reason": "stored row has no non-title condition evidence to justify backfill",
    }


def _opportunity_condition_proof_row(row: dict[str, Any]) -> dict[str, Any]:
    sample = _condition_blocker_basis_sample(row) or {}
    return {
        "id": row.get("id"),
        "source_site": row.get("source_site") or row.get("source"),
        "title": str(_pick_row_or_raw(row, "title") or "") or None,
        "year": _pick_row_or_raw(row, "year"),
        "mileage": _pick_row_or_raw(row, "mileage"),
        "condition_grade": row.get("condition_grade"),
        "condition_blocker_basis": sample.get("condition_blocker_basis") or _condition_blocker_basis(row),
        "condition_signals": sample.get("condition_signals") or [],
        "source_text_excerpt": sample.get("source_text_excerpt") or "",
        "condition_evidence_fields": _condition_evidence_fields(row),
        "condition_backfill_assessment": _condition_backfill_assessment(row),
        "source_identity": _source_identity(row),
        "raw_data_keys_present": _raw_data_keys_present(row),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "listing_id": row.get("listing_id"),
    }


def build_opportunity_condition_proof(opportunity_id: str) -> dict[str, Any]:
    if supabase_client is None:
        raise HTTPException(status_code=503, detail="Supabase service client unavailable")
    clean_id = str(opportunity_id or "").strip()
    if not clean_id:
        raise HTTPException(status_code=400, detail="Opportunity id is required")

    rows = _safe_rows(
        "opportunities",
        "id,title,year,mileage,condition_grade,source_site,created_at,raw_data",
        limit=1,
        filters=[("eq", "id", clean_id)],
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    return {
        "status": "ok",
        "generated_at": _now_iso(),
        "selector": {"id": clean_id},
        "opportunity": _opportunity_condition_proof_row(rows[0]),
    }


def build_pipeline_truth() -> dict[str, Any]:
    if supabase_client is None:
        raise HTTPException(status_code=503, detail="Supabase service client unavailable")

    pricing_substrate = _pricing_substrate_truth()

    opp_rows = _safe_rows(
        "opportunities",
        "id,is_active,dos_score,score,title,year,mileage,pricing_maturity,condition_grade,vin,source_site,created_at,auction_end_date,investment_grade,roi_per_day,estimated_days_to_sale,gross_margin,bid_headroom,current_bid_trust_score,mmr_confidence_proxy,manheim_confidence,retail_comp_confidence,pricing_source,expected_close_source,retail_comp_count,acquisition_price_basis,acquisition_basis_source,projected_total_cost,total_cost,mmr_lookup_basis,max_bid,expected_close_bid,auction_stage_hours_remaining,vehicle_tier,designated_lane,raw_data",
        order=("created_at", True),
        limit=1000,
    )
    active_rows = [row for row in opp_rows if row.get("is_active") is True]
    active_dos80 = [
        row for row in active_rows
        if (_numeric_score(row) or 0.0) >= HOT_DEAL_ALERT_THRESHOLD
    ]
    active_dos80_gate_breakdown = _alert_gate_breakdown(active_dos80)
    active_dos80_condition_storage_gap_rows = _condition_storage_gap_rows(active_dos80)

    webhook_rows = _safe_rows(
        "webhook_log",
        "id,received_at,source,run_id,item_count,processing_status,error_message",
        order=("received_at", True),
        limit=25,
    )
    alert_rows = _safe_rows(
        "alert_log",
        "id,sent_at,channel,delivery_state,alert_type,dos_score",
        order=("sent_at", True),
        limit=25,
    )
    delivery_rows = _safe_rows(
        "ingest_delivery_log",
        "id,created_at,channel,status,error_message",
        order=("created_at", True),
        limit=200,
    )

    total_opportunities = _safe_count("opportunities")
    active_total = _safe_count("opportunities", [("eq", "is_active", True)])
    alerts_total = _safe_count("alert_log")

    return {
        "status": "ok",
        "generated_at": _now_iso(),
        "opportunities": {
            "total": total_opportunities,
            "active": active_total,
            "sample_size": len(opp_rows),
            "active_sample": len(active_rows),
            "active_source_counts_sample": _status_counts(active_rows, "source_site"),
            "active_pricing_maturity_counts_sample": _status_counts(active_rows, "pricing_maturity"),
            "active_condition_counts_sample": _status_counts(active_rows, "condition_grade"),
            "active_dos_score_buckets_sample": _dos_score_buckets(active_rows),
            **_dos_score_stats(active_rows),
            "active_gate_breakdown_sample": _alert_gate_breakdown(active_rows),
            "active_dos80_sample": len(active_dos80),
            "active_dos80_missing_mileage_sample": sum(1 for row in active_dos80 if row.get("mileage") in (None, "", 0)),
            "active_dos80_proxy_pricing_sample": sum(1 for row in active_dos80 if row.get("pricing_maturity") == "proxy"),
            "active_dos80_missing_vin_sample": sum(1 for row in active_dos80 if not row.get("vin")),
            "active_dos80_condition_unverified_sample": sum(1 for row in active_dos80 if str(row.get("condition_grade") or "").lower() in {"", "poor", "unknown"}),
            "source_counts_sample": _status_counts(active_dos80, "source_site"),
            "active_dos80_condition_counts_sample": _status_counts(active_dos80, "condition_grade"),
            "active_dos80_condition_blocker_basis_counts_sample": _condition_blocker_basis_counts(active_dos80),
            "active_dos80_condition_blocker_basis_by_source_sample": _condition_blocker_basis_by_source(active_dos80),
            "active_dos80_condition_blocker_basis_samples": _condition_blocker_basis_samples(active_dos80),
            "active_dos80_condition_storage_gap_count_sample": len(active_dos80_condition_storage_gap_rows),
            "active_dos80_condition_storage_gap_by_source_sample": _condition_storage_gap_by_source(active_dos80),
            "active_dos80_condition_storage_gap_samples": _condition_storage_gap_samples(active_dos80),
            "active_dos80_pricing_maturity_counts_sample": _status_counts(active_dos80, "pricing_maturity"),
            "active_dos80_alert_eligible_sample": sum(1 for row in active_dos80_gate_breakdown if row.get("eligible") is True),
            "active_dos80_gate_blocker_counts_sample": _gate_blocker_counts(active_dos80_gate_breakdown),
            "active_dos80_gate_breakdown": active_dos80_gate_breakdown,
        },
        "webhooks": {
            "recent_count": len(webhook_rows),
            "status_counts": _status_counts(webhook_rows, "processing_status"),
            "latest": webhook_rows[:10],
        },
        "pricing_substrate": pricing_substrate,
        "alerts": {
            "runtime": _alerts_runtime_status(),
            "total": alerts_total,
            "recent_count": len(alert_rows),
            "latest_sent_at": alert_rows[0].get("sent_at") if alert_rows else None,
            "delivery_state_counts": _status_counts(alert_rows, "delivery_state"),
            "latest": alert_rows[:10],
        },
        "deliveries": {
            "recent_count": len(delivery_rows),
            "channel_counts": _status_counts(delivery_rows, "channel"),
            "status_counts": _status_counts(delivery_rows, "status"),
            "latest_telegram_alert_created_at": next((row.get("created_at") for row in delivery_rows if row.get("channel") == "telegram_alert"), None),
        },
    }


@router.get("/pipeline-truth", include_in_schema=False)
def pipeline_truth(x_internal_secret: Optional[str] = Header(None, alias="X-Internal-Secret")) -> dict[str, Any]:
    """Return aggregate-only pipeline truth for governed internal operators."""
    verify_internal_secret(x_internal_secret)
    return build_pipeline_truth()


@router.get("/seller-recovery-audit", include_in_schema=False)
def seller_recovery_audit(x_internal_secret: Optional[str] = Header(None, alias="X-Internal-Secret")) -> dict[str, Any]:
    """Return sanitized seller-side listing recovery diagnostics."""
    verify_internal_secret(x_internal_secret)
    return build_seller_recovery_audit()


@router.get("/opportunity-condition-proof/{opportunity_id}", include_in_schema=False)
def opportunity_condition_proof(
    opportunity_id: str = Path(..., min_length=1),
    x_internal_secret: Optional[str] = Header(None, alias="X-Internal-Secret"),
) -> dict[str, Any]:
    """Return sanitized condition-evidence truth for one governed opportunity row."""
    verify_internal_secret(x_internal_secret)
    return build_opportunity_condition_proof(opportunity_id)
