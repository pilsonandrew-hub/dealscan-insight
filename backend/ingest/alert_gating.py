"""Shared alert gating for conservative, inspectable opportunity alerts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional


ALERT_ALLOWED_PRICING_MATURITIES = frozenset({"proxy", "market_comp", "live_market"})
ALERT_ALLOWED_GRADES = frozenset({"Gold", "Platinum"})


@dataclass(frozen=True)
class AlertThresholds:
    min_score: float = 80.0
    platinum_min_roi_day: float = 75.0
    min_bid_headroom: float = 0.0
    min_trust_score: float = 0.25
    min_confidence: float = 55.0


def _to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pick_numeric(*values: Any) -> Optional[float]:
    for value in values:
        normalized = _to_float(value)
        if normalized is not None:
            return normalized
    return None


def _pick_text(*values: Any) -> Optional[str]:
    for value in values:
        if value is None:
            continue
        normalized = str(value).strip()
        if normalized:
            return normalized
    return None


def _score_breakdown(record: Mapping[str, Any]) -> Mapping[str, Any]:
    nested = record.get("score_breakdown")
    if isinstance(nested, Mapping):
        return nested
    return {}


def collect_alert_signals(record: Mapping[str, Any]) -> dict[str, Any]:
    breakdown = _score_breakdown(record)
    pricing_maturity = _pick_text(record.get("pricing_maturity"), breakdown.get("pricing_maturity")) or "unknown"
    investment_grade = _pick_text(record.get("investment_grade"), breakdown.get("investment_grade")) or "Unknown"
    pricing_source = _pick_text(record.get("pricing_source"), breakdown.get("pricing_source")) or "unknown"
    expected_close_source = _pick_text(
        record.get("expected_close_source"),
        breakdown.get("expected_close_source"),
    ) or "unknown"
    confidence = _pick_numeric(
        record.get("mmr_confidence_proxy"),
        breakdown.get("mmr_confidence_proxy"),
        record.get("manheim_confidence"),
        breakdown.get("manheim_confidence"),
        record.get("retail_comp_confidence"),
        breakdown.get("retail_comp_confidence"),
    )
    if confidence is not None and confidence <= 1.0:
        confidence *= 100.0

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

    trust_score = signals["current_bid_trust_score"]
    if trust_score is None:
        reasons.append("missing_current_bid_trust_score")
    elif trust_score < config.min_trust_score:
        reasons.append(f"trust<{config.min_trust_score:.2f}")

    confidence = signals["confidence"]
    if confidence is None:
        reasons.append("missing_confidence")
    elif confidence < config.min_confidence:
        reasons.append(f"confidence<{config.min_confidence:.0f}")

    if signals["bid_headroom"] <= config.min_bid_headroom:
        reasons.append("non_positive_headroom")
    if (signals["acquisition_price_basis"] or 0.0) <= 0:
        reasons.append("missing_acquisition_price_basis")
    if (signals["projected_total_cost"] or 0.0) <= 0:
        reasons.append("missing_projected_total_cost")
    if (signals["max_bid"] or 0.0) <= 0:
        reasons.append("missing_max_bid")
    if (signals["expected_close_bid"] or 0.0) <= 0:
        reasons.append("missing_expected_close_bid")

    alert_type = None
    if not reasons:
        if (
            signals["investment_grade"] == "Platinum"
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
        f" | trust={trust_score if trust_score is not None else 'na'}"
        f" | confidence={confidence if confidence is not None else 'na'}"
        f" | headroom={signals['bid_headroom']:.0f}"
        f" | roi_day={signals['roi_per_day']:.0f}"
        f" | basis={signals['acquisition_price_basis'] or 0.0:.0f}"
        f" | projected_total_cost={signals['projected_total_cost'] or 0.0:.0f}"
    )

    return {
        "eligible": not reasons,
        "alert_type": alert_type,
        "blocking_reasons": reasons,
        "summary": summary,
        "signals": signals,
    }
