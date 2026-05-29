"""Fallback scoring helper for ingest failures.

This intentionally preserves the router's legacy emergency fallback behavior while
making severe fallback provenance queryable and independently testable.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.ingest.gates import LOW_RUST_STATES


PREFERRED_RESALE_MAKES = {
    "FORD",
    "TOYOTA",
    "RAM",
    "CHEVROLET",
    "CHEVY",
    "GMC",
    "HONDA",
    "NISSAN",
    "TESLA",
}


def build_fallback_score(vehicle: dict[str, Any]) -> dict[str, Any]:
    """Build the severe fallback score payload used when the main scorer fails."""
    score = 50.0
    if vehicle.get("state") in LOW_RUST_STATES:
        score += 8
    make = vehicle.get("make", "").upper()
    if make in PREFERRED_RESALE_MAKES:
        score += 12
    year = vehicle.get("year", 2000)
    age = datetime.now().year - year
    if 1 <= age <= 4:
        score += 10

    auction_stage_hours_remaining = None
    current_bid_trust_score = None
    pricing_maturity = "proxy"
    try:
        from backend.ingest.score import (
            _auction_stage_hours_remaining,
            _current_bid_trust_score,
            _round_price_basis,
        )

        auction_stage_hours_remaining = _auction_stage_hours_remaining(vehicle.get("auction_end_time"))
        current_bid_trust_score = _current_bid_trust_score(
            auction_stage_hours_remaining=auction_stage_hours_remaining,
            pricing_maturity=pricing_maturity,
        )
        acquisition_price_basis = _round_price_basis(vehicle.get("current_bid") or 0)
    except Exception:
        acquisition_price_basis = vehicle.get("current_bid") or 0

    mileage_value = vehicle.get("mileage")
    try:
        has_valid_mileage = mileage_value is not None and float(mileage_value) > 0
    except (TypeError, ValueError):
        has_valid_mileage = False

    score_provenance = {
        "engine_version": "fallback_v1",
        "engine_impl": "webapp.routers.ingest._fallback_score",
        "scored_at": datetime.now(timezone.utc).isoformat(),
        "lane": "fallback",
        "mmr_source": "none",
        "mmr_confidence_proxy": None,
        "pricing_source": "mmr_proxy",
        "fallback_flags": ["hard_fallback_score", "no_mmr"],
        "assumption_level": "severe",
        "input_profile": {
            "has_bid": bool(vehicle.get("current_bid")),
            "has_mmr": False,
            "has_live_manheim": False,
            "has_year": bool(vehicle.get("year")),
            "has_mileage": has_valid_mileage,
            "source_site": vehicle.get("source_site"),
        },
        "component_traces": [],
    }
    rounded_score = min(100, round(score, 1))
    return {
        "dos_score": rounded_score,
        "score": rounded_score,
        "legacy_dos_score": rounded_score,
        "score_version": "fallback_v1",
        "score_engine_impl": "webapp.routers.ingest._fallback_score",
        "score_timestamp_utc": score_provenance["scored_at"],
        "score_provenance": score_provenance,
        "fallback_flags": score_provenance["fallback_flags"],
        "assumption_level": score_provenance["assumption_level"],
        "mmr_estimated": 0,
        "margin": 0,
        "gross_margin": 0,
        "wholesale_margin": 0,
        "retail_asking_price_estimate": 0,
        "retail_comp_price_estimate": None,
        "retail_comp_low": None,
        "retail_comp_high": None,
        "retail_comp_count": 0,
        "retail_comp_confidence": None,
        "pricing_source": "mmr_proxy",
        "pricing_maturity": pricing_maturity,
        "pricing_updated_at": None,
        "expected_close_bid": acquisition_price_basis,
        "expected_close_source": "fallback_current_bid_only",
        "current_bid_trust_score": current_bid_trust_score,
        "auction_stage_hours_remaining": auction_stage_hours_remaining,
        "acquisition_price_basis": acquisition_price_basis,
        "acquisition_basis_source": "current_bid_fallback",
        "projected_total_cost": acquisition_price_basis,
        "manheim_mmr_mid": None,
        "manheim_mmr_low": None,
        "manheim_mmr_high": None,
        "manheim_range_width_pct": None,
        "manheim_confidence": None,
        "manheim_source_status": "unavailable",
        "manheim_updated_at": None,
        "retail_proxy_multiplier": 1.35,
        "wholesale_ctm_pct": None,
        "retail_ctm_pct": None,
        "ctm_pct": None,
        "estimated_days_to_sale": None,
        "roi_per_day": None,
        "investment_grade": None,
        "bid_ceiling_pct": None,
        "max_bid": 0,
        "bid_headroom": 0,
        "ceiling_reason": "fallback_score",
        "ceiling_pass": False,
    }
