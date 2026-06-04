"""Internal read-only DealerScope truth surfaces for governed operators."""
from __future__ import annotations

import logging
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, Header, HTTPException, Path

from backend.business_rules.constants import ALERTS_ENABLED_PRODUCTION_DEFAULT
from backend.ingest.alert_gating import evaluate_alert_gate
from backend.ingest.condition import score_condition
from webapp.database import supabase_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/internal", tags=["internal"])


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
    if not x_internal_secret or x_internal_secret.strip() != expected:
        logger.warning("[INTERNAL_AUTH] rejected unauthorized internal request")
        raise HTTPException(status_code=401, detail="Invalid internal authorization")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _alerts_runtime_status() -> dict[str, Any]:
    raw = os.getenv("ALERTS_ENABLED")
    effective = (raw if raw is not None else ALERTS_ENABLED_PRODUCTION_DEFAULT).strip().lower()
    return {
        "enabled": effective == "true",
        "source": "env" if raw is not None else "production_default",
        "raw_value": raw if raw in {"true", "false"} else ("set_non_boolean" if raw is not None else None),
        "production_default": ALERTS_ENABLED_PRODUCTION_DEFAULT,
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
        if not _condition_blocker_basis(row):
            continue
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
    for evidence in _condition_evidence_fields(row).values():
        if evidence.get("present") and not evidence.get("matches_title"):
            return True
    return False


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
        "id,is_active,dos_score,score,title,year,mileage,pricing_maturity,condition_grade,vin,source_site,created_at,auction_end_date,investment_grade,roi_per_day,bid_headroom,current_bid_trust_score,mmr_confidence_proxy,manheim_confidence,retail_comp_confidence,pricing_source,expected_close_source,retail_comp_count,acquisition_price_basis,acquisition_basis_source,projected_total_cost,total_cost,mmr_lookup_basis,max_bid,expected_close_bid,raw_data",
        order=("created_at", True),
        limit=1000,
    )
    active_rows = [row for row in opp_rows if row.get("is_active") is True]
    active_dos80 = [
        row for row in active_rows
        if float(row.get("dos_score") or row.get("score") or 0) >= 80
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


@router.get("/opportunity-condition-proof/{opportunity_id}", include_in_schema=False)
def opportunity_condition_proof(
    opportunity_id: str = Path(..., min_length=1),
    x_internal_secret: Optional[str] = Header(None, alias="X-Internal-Secret"),
) -> dict[str, Any]:
    """Return sanitized condition-evidence truth for one governed opportunity row."""
    verify_internal_secret(x_internal_secret)
    return build_opportunity_condition_proof(opportunity_id)
