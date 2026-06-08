"""Canonical eligibility and economics gates derived from business_rules.constants."""

from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Mapping, Optional

from backend.business_rules.constants import (
    HIGH_RUST_STATES,
    PREMIUM_BID_CEILING_PCT,
    PREMIUM_MAX_MILEAGE,
    PREMIUM_MIN_MARGIN,
    PREMIUM_VEHICLE_MAX_AGE_YEARS,
    RUST_STATE_NEW_VEHICLE_YEARS,
    STANDARD_BID_CEILING_PCT,
    STANDARD_MAX_MILEAGE,
    STANDARD_MAX_MILES_PER_YEAR,
    STANDARD_MIN_MARGIN,
    STANDARD_VEHICLE_MAX_AGE_YEARS,
)


def current_calendar_year() -> int:
    return datetime.now(timezone.utc).year


def _coerce_float(value: object) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        value = value.strip().replace(",", "").replace("$", "")
        if value == "":
            return None
    try:
        normalized = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(normalized):
        return None
    return normalized


def _coerce_year(value: object) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        year = int(float(value))
    except (TypeError, ValueError):
        return None
    current = current_calendar_year()
    if 1980 <= year <= current + 1:
        return year
    return None


def is_high_rust_state_rejected(state: object, year: object) -> bool:
    normalized_state = str(state or "").upper().strip()
    if normalized_state not in HIGH_RUST_STATES:
        return False
    model_year = _coerce_year(year)
    return model_year is None or model_year < current_calendar_year() - RUST_STATE_NEW_VEHICLE_YEARS


def determine_vehicle_tier(year: object, mileage: object) -> str:
    """Return premium | standard | rejected per canonical two-lane policy."""
    current_year = current_calendar_year()
    premium_year_cutoff = current_year - PREMIUM_VEHICLE_MAX_AGE_YEARS
    standard_year_cutoff = current_year - STANDARD_VEHICLE_MAX_AGE_YEARS
    model_year = _coerce_year(year)
    if model_year is None:
        return "rejected"

    if model_year < standard_year_cutoff:
        return "rejected"

    if model_year >= premium_year_cutoff:
        vehicle_tier = "premium"
    else:
        vehicle_tier = "standard"

    mileage_value = _coerce_float(mileage)
    if mileage_value is None or mileage_value <= 0:
        return "rejected"
    if vehicle_tier == "premium" and mileage_value > PREMIUM_MAX_MILEAGE:
        return "rejected"
    if vehicle_tier == "standard":
        if mileage_value > STANDARD_MAX_MILEAGE:
            return "rejected"
        age_years = max(1, current_year - model_year)
        if mileage_value / age_years > STANDARD_MAX_MILES_PER_YEAR:
            return "rejected"

    return vehicle_tier


def bid_ceiling_pct_for_tier(tier: str) -> Optional[float]:
    if tier == "standard":
        return STANDARD_BID_CEILING_PCT
    if tier == "premium":
        return PREMIUM_BID_CEILING_PCT
    return None


def min_margin_for_tier(tier: str) -> Optional[float]:
    if tier == "standard":
        return STANDARD_MIN_MARGIN
    if tier == "premium":
        return PREMIUM_MIN_MARGIN
    return None


def passes_ingest_margin_floor(wholesale_margin: float, tier: str) -> bool:
    """Lane-aware pre-save margin gate (replaces flat $1,500 skip)."""
    floor = min_margin_for_tier(tier)
    if floor is None:
        return False
    return float(wholesale_margin) >= floor


def passes_ceiling_and_margin(
    *,
    ceiling_pass: bool,
    gross_margin: float,
    tier: str,
) -> bool:
    if tier == "rejected":
        return False
    floor = min_margin_for_tier(tier)
    if floor is None:
        return False
    return bool(ceiling_pass) and float(gross_margin) >= floor


def passes_rover_economics(record: Mapping[str, Any]) -> tuple[bool, list[str]]:
    """Server-side Rover filter using scored opportunity fields."""
    reasons: list[str] = []
    tier = str(record.get("vehicle_tier") or "rejected").lower()
    if tier == "rejected":
        reasons.append("tier=rejected")

    dos = _coerce_float(record.get("dos_score")) or 0.0
    from backend.business_rules.constants import ROVER_RECOMMENDATION_THRESHOLD

    if dos < ROVER_RECOMMENDATION_THRESHOLD:
        reasons.append(f"dos<{ROVER_RECOMMENDATION_THRESHOLD:.0f}")

    state = record.get("state")
    year = record.get("year")
    if is_high_rust_state_rejected(state, year):
        reasons.append("rust_state")

    margin = _coerce_float(record.get("gross_margin"))
    floor = min_margin_for_tier(tier)
    if floor is not None and (margin is None or margin < floor):
        reasons.append(f"margin<{floor:.0f}")

    ceiling_pass = record.get("ceiling_pass")
    if ceiling_pass is False:
        reasons.append("ceiling_fail")

    risk_flags = record.get("risk_flags") or []
    if isinstance(risk_flags, list) and "rust_state_source" in risk_flags:
        reasons.append("rust_flag")

    return (not reasons, reasons)
