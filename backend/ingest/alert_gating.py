"""Shared alert gating for conservative, inspectable opportunity alerts."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping, Optional

from backend.business_rules.constants import (
    HOT_DEAL_ALERT_THRESHOLD,
    HOT_DEAL_MIN_CONFIDENCE,
    HOT_DEAL_MIN_TRUST_SCORE,
    PLATINUM_MIN_ROI_PER_DAY,
    PRICING_MATURITY_ALERT_ALLOWED,
)
from backend.business_rules.pricing import pricing_allows_hot_alert

ALERT_ALLOWED_PRICING_MATURITIES = PRICING_MATURITY_ALERT_ALLOWED
ALERT_ALLOWED_GRADES = frozenset({"Premium", "Standard", "Gold", "Platinum", "Silver"})
UNKNOWN_OR_WEAK_CONDITION_GRADES = frozenset({"", "unknown", "poor"})
VIN_PLACEHOLDER_VALUES = frozenset({
    "00000000000000000",
    "11111111111111111",
    "12345678901234567",
    "ABCDEFGHIJKLMNOPQ",
    "UNKNOWNUNKNOWNUNK",
})
VIN_FORBIDDEN_CHARACTERS = frozenset({"I", "O", "Q"})
SOURCE_CONDITION_EVIDENCE_FIELDS = (
    "description",
    "details",
    "condition_notes",
    "detail_text",
    "assetLongDesc",
    "damage_type",
    "damage",
)


@dataclass(frozen=True)
class AlertThresholds:
    min_score: float = HOT_DEAL_ALERT_THRESHOLD
    platinum_min_roi_day: float = PLATINUM_MIN_ROI_PER_DAY
    min_bid_headroom: float = 0.0
    min_trust_score: float = HOT_DEAL_MIN_TRUST_SCORE
    min_confidence: float = HOT_DEAL_MIN_CONFIDENCE


def _to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        normalized = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(normalized):
        return None
    return normalized


def _pick_numeric(*values: Any) -> Optional[float]:
    for value in values:
        normalized = _to_float(value)
        if normalized is not None:
            return normalized
    return None


def _pick_confidence(record: Mapping[str, Any], breakdown: Mapping[str, Any]) -> tuple[Optional[float], bool]:
    candidates = (
        (record, "mmr_confidence_proxy"),
        (breakdown, "mmr_confidence_proxy"),
        (record, "manheim_confidence"),
        (breakdown, "manheim_confidence"),
        (record, "retail_comp_confidence"),
        (breakdown, "retail_comp_confidence"),
    )
    saw_confidence_field = False
    for source, key in candidates:
        if key not in source:
            continue
        saw_confidence_field = True
        normalized = _to_float(source.get(key))
        if normalized is None:
            return None, True
        if normalized <= 1.0:
            normalized *= 100.0
        return normalized, False
    return None, saw_confidence_field


def _pick_text(*values: Any) -> Optional[str]:
    for value in values:
        if value is None:
            continue
        normalized = str(value).strip()
        if normalized:
            return normalized
    return None


def _valid_vin_shape(value: Any) -> bool:
    vin = str(value or "").strip().upper()
    if len(vin) != 17:
        return False
    if not vin.isalnum():
        return False
    if any(char in vin for char in VIN_FORBIDDEN_CHARACTERS):
        return False
    if vin in VIN_PLACEHOLDER_VALUES:
        return False
    if len(set(vin)) <= 2:
        return False
    return True


def _score_breakdown(record: Mapping[str, Any]) -> Mapping[str, Any]:
    nested = record.get("score_breakdown")
    if isinstance(nested, Mapping):
        return nested
    return {}


def _raw_data(record: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = record.get("raw_data")
    return raw if isinstance(raw, Mapping) else {}


def _pick_record_or_raw_text(record: Mapping[str, Any], key: str) -> str:
    raw = _raw_data(record)
    for source in (record, raw):
        value = source.get(key)
        if value in (None, ""):
            continue
        text = " ".join(str(value).split()).strip()
        if text:
            return text
    return ""


def has_source_condition_evidence(record: Mapping[str, Any]) -> bool:
    title_text = _pick_record_or_raw_text(record, "title").lower()
    for key in SOURCE_CONDITION_EVIDENCE_FIELDS:
        text = _pick_record_or_raw_text(record, key)
        if text and text.lower() != title_text:
            return True
    return False


def collect_alert_signals(record: Mapping[str, Any]) -> dict[str, Any]:
    breakdown = _score_breakdown(record)
    pricing_maturity = _pick_text(record.get("pricing_maturity"), breakdown.get("pricing_maturity")) or "unknown"
    investment_grade = _pick_text(record.get("investment_grade"), breakdown.get("investment_grade")) or "Unknown"
    pricing_source = _pick_text(record.get("pricing_source"), breakdown.get("pricing_source")) or "unknown"
    expected_close_source = _pick_text(
        record.get("expected_close_source"),
        breakdown.get("expected_close_source"),
    ) or "unknown"
    confidence, confidence_invalid = _pick_confidence(record, breakdown)

    return {
        "score": _pick_numeric(record.get("dos_score"), record.get("score"), breakdown.get("dos_score"), breakdown.get("score")) or 0.0,
        "investment_grade": investment_grade,
        "roi_per_day": _pick_numeric(record.get("roi_per_day"), breakdown.get("roi_per_day")) or 0.0,
        "bid_headroom": _pick_numeric(record.get("bid_headroom"), breakdown.get("bid_headroom")) or 0.0,
        "pricing_maturity": pricing_maturity,
        "pricing_source": pricing_source,
        "retail_comp_count": _pick_numeric(record.get("retail_comp_count"), breakdown.get("retail_comp_count")),
        "retail_comp_confidence": _pick_numeric(
            record.get("retail_comp_confidence"),
            breakdown.get("retail_comp_confidence"),
        ),
        "current_bid_trust_score": _pick_numeric(
            record.get("current_bid_trust_score"),
            breakdown.get("current_bid_trust_score"),
        ),
        "confidence": confidence,
        "confidence_invalid": confidence_invalid,
        "acquisition_price_basis": _pick_numeric(
            record.get("acquisition_price_basis"),
            breakdown.get("acquisition_price_basis"),
        ),
        "acquisition_basis_source": _pick_text(
            record.get("acquisition_basis_source"),
            breakdown.get("acquisition_basis_source"),
        ) or "unknown",
        "projected_total_cost": _pick_numeric(
            record.get("projected_total_cost"),
            breakdown.get("projected_total_cost"),
            record.get("total_cost"),
            breakdown.get("total_cost"),
        ),
        "mmr_lookup_basis": _pick_text(
            record.get("mmr_lookup_basis"),
            breakdown.get("mmr_lookup_basis"),
        ) or "unknown",
        "max_bid": _pick_numeric(record.get("max_bid"), breakdown.get("max_bid")),
        "expected_close_bid": _pick_numeric(
            record.get("expected_close_bid"),
            breakdown.get("expected_close_bid"),
        ),
        "expected_close_source": expected_close_source,
        "vin": _pick_text(record.get("vin"), breakdown.get("vin")),
        "mileage": _pick_numeric(record.get("mileage"), breakdown.get("mileage")),
        "mileage_invalid": any(
            key in source and _to_float(source.get(key)) is None
            for source, key in ((record, "mileage"), (breakdown, "mileage"))
        ),
        "condition_grade": _pick_text(
            record.get("condition_grade"),
            breakdown.get("condition_grade"),
            record.get("condition"),
            breakdown.get("condition"),
        ),
        "source_condition_evidence_present": has_source_condition_evidence(record),
    }


def evaluate_alert_gate(
    record: Mapping[str, Any],
    thresholds: AlertThresholds | None = None,
) -> dict[str, Any]:
    config = thresholds or AlertThresholds()
    signals = collect_alert_signals(record)

    reasons: list[str] = []

    if signals["score"] < config.min_score:
        reasons.append(f"score<{config.min_score:.0f}")
    if signals["investment_grade"] not in ALERT_ALLOWED_GRADES:
        reasons.append(f"grade={signals['investment_grade']}")
    if signals["pricing_maturity"] not in ALERT_ALLOWED_PRICING_MATURITIES:
        reasons.append(f"pricing_maturity={signals['pricing_maturity']}")
    if not _valid_vin_shape(signals["vin"]):
        reasons.append("vin_unverified")
    if signals.get("mileage_invalid") or signals["mileage"] is None or signals["mileage"] <= 0:
        reasons.append("mileage_missing")
    condition_grade = str(signals["condition_grade"] or "").strip().lower()
    if condition_grade in UNKNOWN_OR_WEAK_CONDITION_GRADES:
        reasons.append("condition_unverified")
    elif not signals.get("source_condition_evidence_present"):
        reasons.append("condition_evidence_missing")

    confidence = signals["confidence"]
    if signals.get("confidence_invalid"):
        reasons.append("confidence_invalid")
    elif confidence is None:
        reasons.append("confidence_missing")
    elif confidence < config.min_confidence:
        reasons.append(f"confidence<{config.min_confidence:.0f}")

    current_bid_trust_score = signals["current_bid_trust_score"]
    if current_bid_trust_score is not None and current_bid_trust_score < config.min_trust_score:
        reasons.append(f"trust<{config.min_trust_score:.2f}")

    bid_headroom = signals["bid_headroom"]
    if bid_headroom is not None and bid_headroom < config.min_bid_headroom:
        reasons.append(f"headroom<{config.min_bid_headroom:.0f}")

    pricing_ok, pricing_reason = pricing_allows_hot_alert(record)
    if not pricing_ok and pricing_reason:
        reasons.append(pricing_reason)

    alert_type = None
    if not reasons:
        if (
            signals["investment_grade"] in ("Platinum", "Premium")
            and signals["roi_per_day"] >= config.platinum_min_roi_day
        ):
            alert_type = "platinum"
        else:
            alert_type = "hot"

    summary = (
        f"type={alert_type or 'blocked'}"
        f" | grade={signals['investment_grade']}"
        f" | score={signals['score']:.1f}"
        f" | maturity={signals['pricing_maturity']}"
        f" | confidence={confidence if confidence is not None else 'na'}"
        f" | roi_day={signals['roi_per_day']:.0f}"
    )

    return {
        "eligible": not reasons,
        "alert_type": alert_type,
        "blocking_reasons": reasons,
        "summary": summary,
        "signals": signals,
    }
