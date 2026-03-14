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


def _normalize_vehicle_text(value: str) -> str:
    return " ".join((value or "").strip().lower().replace("-", " ").split())

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


_SEGMENT_TIER_1_MODELS = {
    "f 150", "silverado", "ram", "rav4", "rogue", "cr v", "tacoma",
    "camry", "accord", "model 3", "model y", "tucson", "equinox", "escape",
}

_SEGMENT_TIER_2_MODELS = {
    "tahoe", "suburban", "expedition", "tundra", "ranger", "explorer",
    "highlander", "pilot", "durango", "traverse",
}

_LUXURY_MAKES = {"bmw", "mercedes", "mercedes benz", "lexus", "cadillac", "lincoln", "audi"}


def _segment_tier(model: str, make: str) -> int:
    normalized_model = _normalize_vehicle_text(model)
    normalized_make = _normalize_vehicle_text(make)

    if any(token in normalized_model for token in _SEGMENT_TIER_1_MODELS):
        return 1
    if any(token in normalized_model for token in _SEGMENT_TIER_2_MODELS):
        return 2

    if normalized_make in _LUXURY_MAKES:
        return 3

    segment = _MODEL_SEGMENT_MAP.get(model)
    if segment in {"sedan_popular", "sedan_other", "luxury"}:
        return 3

    if "sedan" in normalized_model:
        return 3

    return 4


def _investment_grade(ctm_pct: float, segment_tier: int) -> str:
    if ctm_pct <= 85 and segment_tier <= 2:
        return "Platinum"
    if ctm_pct <= 90 and segment_tier <= 3:
        return "Gold"
    if ctm_pct <= 95:
        return "Silver"
    return "Bronze"


def _recon_reserve(mileage: float = None, is_police_or_fleet: bool = False) -> float:
    miles = max(float(mileage or 0), 0.0)
    mileage_component = 3.0 * (miles / 1000.0)
    reserve = min(500.0 + mileage_component, 1200.0)
    if is_police_or_fleet:
        reserve += 300.0
    return reserve


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
    mileage: float = None,
    is_police_or_fleet: bool = False,
) -> dict:
    """
    Compute full DOS score and deal metrics.

    Returns a dict with premium, doc_fee, transport, recon_reserve, total_cost,
    margin, margin_score, velocity_score, segment_score, model_score,
    source_score, and dos_score (0-100).
    """
    if fees_cfg is None:
        fees_cfg = _load_fees()

    site_fees = fees_cfg.get(source_site, {"buyers_premium_pct": 10.0, "doc_fee": 50})
    premium = bid * site_fees.get("buyers_premium_pct", 10.0) / 100.0
    doc_fee = site_fees.get("doc_fee", 50)
    transport = calc_transport_cost(state, rates_cfg=rates_cfg, miles_cfg=miles_cfg)
    recon_reserve = _recon_reserve(mileage=mileage, is_police_or_fleet=is_police_or_fleet)
    total_cost = bid + premium + doc_fee + transport + recon_reserve
    margin = mmr_ca - total_cost

    m_score = _margin_score(bid, mmr_ca, total_cost)
    v_score = _velocity_score(bid, year)
    seg_score = _segment_score(model, make)
    mod_score = _model_score(model)
    src_score = _source_score(source_site)
    retail_target = mmr_ca * 1.35 if mmr_ca else 0.0
    ctm_pct = (total_cost / retail_target * 100.0) if retail_target > 0 else 100.0
    segment_tier = _segment_tier(model, make)
    investment_grade = _investment_grade(ctm_pct, segment_tier)

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
        "recon_reserve": round(recon_reserve, 2),
        "total_cost": round(total_cost, 2),
        "margin": round(margin, 2),
        "margin_score": round(m_score, 2),
        "velocity_score": round(v_score, 2),
        "segment_score": round(seg_score, 2),
        "model_score": round(mod_score, 2),
        "source_score": round(src_score, 2),
        "ctm_pct": round(ctm_pct, 2),
        "segment_tier": segment_tier,
        "investment_grade": investment_grade,
        "dos_score": round(dos_score, 2),
        "score": round(dos_score, 2),  # alias for compatibility
    }
