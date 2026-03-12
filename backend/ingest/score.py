"""Deal scoring using the DOS (Deal Opportunity Score) formula.

DOS = (Margin Score × 0.35) + (Velocity Score × 0.25) +
      (Segment Score × 0.20) + (Model Score × 0.12) + (Source Score × 0.08)
"""
import functools
import os
from datetime import datetime

import yaml

from .transport import calc_transport_cost

_CONFIGS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")

SEGMENT_SCORES = {
    "truck": 95,
    "suv_large": 90,
    "suv_mid": 85,
    "luxury": 80,
    "ev_trending": 78,
    "sedan_popular": 65,
    "ev_other": 55,
    "sedan_other": 45,
    "coupe": 35,
    "minivan": 30,
}

TIER_1_MODELS = [
    "F-150", "Silverado 1500", "Ram 1500", "Tacoma", "RAV4",
    "CR-V", "Rogue", "Camry", "Accord", "Tesla Model Y", "Tesla Model 3",
]

TIER_2_MODELS = [
    "Highlander", "Pilot", "Explorer", "Equinox", "Corolla",
    "Civic", "Altima", "Escape", "Tundra", "Colorado", "Frontier",
]

# Model → segment classification
_MODEL_SEGMENT_MAP = {
    "F-150": "truck", "Silverado 1500": "truck", "Ram 1500": "truck",
    "Tacoma": "truck", "Tundra": "truck", "Colorado": "truck", "Frontier": "truck",
    "RAV4": "suv_mid", "CR-V": "suv_mid", "Rogue": "suv_mid", "Escape": "suv_mid",
    "Equinox": "suv_mid",
    "Highlander": "suv_large", "Pilot": "suv_large", "Explorer": "suv_large",
    "Camry": "sedan_popular", "Accord": "sedan_popular", "Corolla": "sedan_popular",
    "Civic": "sedan_popular", "Altima": "sedan_popular",
    "Tesla Model Y": "ev_trending", "Tesla Model 3": "ev_trending",
}


@functools.lru_cache(maxsize=1)
def _load_fees() -> dict:
    with open(os.path.join(_CONFIGS_DIR, "fees.yml")) as f:
        return yaml.safe_load(f).get("sites", {})


def _margin_score(bid: float, mmr_ca: float, total_cost: float) -> float:
    """Score 0-100 based on margin percentage."""
    if mmr_ca <= 0:
        return 50.0
    margin_pct = (mmr_ca - total_cost) / mmr_ca * 100
    # Map margin_pct to 0-100: 0% → 50, 20%+ → 100, negative → 0
    if margin_pct >= 20:
        return 100.0
    if margin_pct <= 0:
        return max(0.0, 50.0 + margin_pct * 2.5)
    return 50.0 + (margin_pct / 20.0) * 50.0


def _velocity_score(bid: float, year: int) -> float:
    """Score based on price point and age (proxy for days-to-sell velocity)."""
    score = 50.0
    if bid < 10000:
        score += 20
    elif bid < 20000:
        score += 10
    if year:
        age = datetime.now().year - year
        if 1 <= age <= 3:
            score += 25
        elif age <= 5:
            score += 15
        elif age <= 7:
            score += 5
    return min(100.0, score)


def _segment_score(model: str, make: str) -> float:
    """Look up segment score from SEGMENT_SCORES."""
    segment = _MODEL_SEGMENT_MAP.get(model)
    if not segment:
        make_lower = (make or "").lower()
        model_lower = (model or "").lower()
        if any(t in model_lower for t in ["f-150", "f150", "silverado", "ram", "tacoma",
                                           "tundra", "colorado", "frontier", "ranger",
                                           "canyon", "gladiator"]):
            segment = "truck"
        elif any(t in model_lower for t in ["suv", "4runner", "pathfinder", "rav4",
                                             "cr-v", "forester", "outback", "tiguan"]):
            segment = "suv_mid"
        elif any(t in model_lower for t in ["model s", "model x", "leaf", "bolt"]):
            segment = "ev_other"
        elif make_lower in {"bmw", "mercedes", "lexus", "cadillac", "lincoln", "audi"}:
            segment = "luxury"
        else:
            segment = "sedan_other"
    return float(SEGMENT_SCORES.get(segment, 45))


def _model_score(model: str) -> float:
    """Score based on model tier."""
    if model in TIER_1_MODELS:
        return 100.0
    if model in TIER_2_MODELS:
        return 75.0
    return 50.0


def _source_score(source_site: str) -> float:
    """Score based on auction source reliability."""
    return {
        "GovDeals": 100.0,
        "PublicSurplus": 90.0,
        "IAA": 70.0,
        "Copart": 65.0,
    }.get(source_site, 60.0)


def score_deal(
    bid: float,
    mmr_ca: float,
    state: str,
    source_site: str,
    model: str = "",
    make: str = "",
    year: int = None,
    fees_cfg: dict = None,
    rates_cfg: dict = None,
    miles_cfg: dict = None,
) -> dict:
    """
    Compute full DOS score and deal metrics.

    Returns a dict with premium, doc_fee, transport, total_cost, margin,
    margin_score, velocity_score, segment_score, model_score, source_score,
    and dos_score (0-100).
    """
    if fees_cfg is None:
        fees_cfg = _load_fees()

    site_fees = fees_cfg.get(source_site, {"buyers_premium_pct": 10.0, "doc_fee": 50})
    premium = bid * site_fees.get("buyers_premium_pct", 10.0) / 100.0
    doc_fee = site_fees.get("doc_fee", 50)
    transport = calc_transport_cost(state, rates_cfg=rates_cfg, miles_cfg=miles_cfg)
    total_cost = bid + premium + doc_fee + transport
    margin = mmr_ca - total_cost

    m_score = _margin_score(bid, mmr_ca, total_cost)
    v_score = _velocity_score(bid, year)
    seg_score = _segment_score(model, make)
    mod_score = _model_score(model)
    src_score = _source_score(source_site)

    dos_score = (
        m_score * 0.35
        + v_score * 0.25
        + seg_score * 0.20
        + mod_score * 0.12
        + src_score * 0.08
    )

    return {
        "premium": round(premium, 2),
        "doc_fee": doc_fee,
        "transport": round(transport, 2),
        "total_cost": round(total_cost, 2),
        "margin": round(margin, 2),
        "margin_score": round(m_score, 2),
        "velocity_score": round(v_score, 2),
        "segment_score": round(seg_score, 2),
        "model_score": round(mod_score, 2),
        "source_score": round(src_score, 2),
        "dos_score": round(dos_score, 2),
        "score": round(dos_score, 2),  # alias for compatibility
    }
