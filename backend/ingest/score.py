"""Deal scoring using the DOS (Deal Opportunity Score) formula.

DOS = (Margin Score × 0.35) + (Velocity Score × 0.25) +
      (Segment Score × 0.20) + (Model Score × 0.12) + (Source Score × 0.08)
"""
import functools
import os
from datetime import datetime, timezone
from typing import Optional

try:
    import yaml
except ImportError:  # pragma: no cover - exercised in minimal local environments
    from backend import yaml_compat as yaml

from .transport import calc_transport_cost
from .retail_comps import retail_comp_is_usable

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
    "f150", "silverado", "ram1500", "rav4", "rogue", "crv", "tacoma",
    "camry", "accord", "model3", "modely", "tucson", "equinox", "escape",
}

_SEGMENT_TIER_2_MODELS = {
    "tahoe", "suburban", "expedition", "tundra", "ranger", "explorer",
    "highlander", "pilot", "durango", "traverse", "odyssey", "sienna",
    "carnival", "pacifica",
}

_LUXURY_MAKES = {"bmw", "mercedes", "mercedes benz", "lexus", "cadillac", "lincoln", "audi"}

RETAIL_PROXY_MULTIPLIER = 1.35
ESTIMATED_DAYS_TO_SALE_BY_TIER = {
    1: 25,
    2: 35,
    3: 50,
    4: 70,
}
SCORE_VERSION = "manheim_ready_v3"
INVESTMENT_GRADE_PROXY_SCORES = {
    "Platinum": 100.0,
    "Gold": 82.0,
    "Silver": 64.0,
    "Bronze": 25.0,
}


def _is_hd_commercial_truck(
    normalized_model: str,
    normalized_model_compact: str,
    normalized_make: str,
) -> bool:
    if "silverado" in normalized_model and ("2500" in normalized_model or "3500" in normalized_model):
        return True
    if "sierra" in normalized_model and ("2500" in normalized_model or "3500" in normalized_model):
        return True
    if "ram" in normalized_model and ("2500" in normalized_model or "3500" in normalized_model):
        return True
    if normalized_make in {"chevrolet", "chevy", "gmc", "ram"} and (
        "2500" in normalized_model or "3500" in normalized_model
    ):
        return True
    if any(token in normalized_model for token in ("f-250", "f 250", "f-350", "f 350")):
        return True
    if normalized_make == "ford" and any(token in normalized_model_compact for token in ("f250", "f350")):
        return True
    return False


def _segment_tier(model: str, make: str) -> int:
    normalized_model = _normalize_vehicle_text(model)
    normalized_model_compact = normalized_model.replace(" ", "").replace("-", "")
    normalized_make = _normalize_vehicle_text(make)

    if _is_hd_commercial_truck(normalized_model, normalized_model_compact, normalized_make):
        return 3

    if any(token in normalized_model_compact for token in _SEGMENT_TIER_1_MODELS):
        return 1
    if any(token in normalized_model_compact for token in _SEGMENT_TIER_2_MODELS):
        return 2

    if normalized_make in _LUXURY_MAKES:
        return 3

    segment = _MODEL_SEGMENT_MAP.get(model)
    if segment in {"sedan_popular", "sedan_other", "luxury"}:
        return 3

    if "sedan" in normalized_model:
        return 3

    return 4


def _estimated_days_to_sale(segment_tier: int) -> int:
    return int(ESTIMATED_DAYS_TO_SALE_BY_TIER.get(segment_tier, 70))


def _investment_grade(retail_ctm_pct: float, estimated_days_to_sale: int, segment_tier: int) -> str:
    if segment_tier >= 4:
        return "Bronze"
    if retail_ctm_pct <= 62 and estimated_days_to_sale <= 25 and segment_tier == 1:
        return "Platinum"
    if retail_ctm_pct <= 66 and estimated_days_to_sale <= 35 and segment_tier <= 2:
        return "Gold"
    if retail_ctm_pct <= 72 and estimated_days_to_sale <= 50:
        return "Silver"
    return "Bronze"


def _segment_tier_score(segment_tier: int) -> float:
    return {
        1: 100.0,
        2: 80.0,
        3: 55.0,
        4: 30.0,
    }.get(segment_tier, 30.0)


def _roi_per_day_score(roi_per_day: float) -> float:
    if roi_per_day <= 0:
        return 0.0
    if roi_per_day >= 250:
        return 100.0
    return max(0.0, min(100.0, (roi_per_day / 250.0) * 100.0))


def _transport_cost_score(transport_cost: float) -> float:
    if transport_cost <= 300:
        return 100.0
    if transport_cost <= 600:
        return 80.0
    if transport_cost <= 900:
        return 60.0
    if transport_cost <= 1200:
        return 40.0
    return 20.0


def _time_pressure_score(auction_end: Optional[str]) -> float:
    if not auction_end:
        return 40.0

    parsed_end: Optional[datetime] = None
    try:
        parsed_end = datetime.fromisoformat(str(auction_end).replace("Z", "+00:00"))
    except ValueError:
        try:
            from dateutil import parser as dateparser  # type: ignore
            parsed_end = dateparser.parse(str(auction_end))
        except Exception:
            return 40.0

    if parsed_end is None:
        return 40.0

    if parsed_end.tzinfo is not None:
        now = datetime.now(parsed_end.tzinfo)
    else:
        now = datetime.now()
    hours_remaining = max((parsed_end - now).total_seconds() / 3600.0, 0.0)

    if hours_remaining <= 6:
        return 100.0
    if hours_remaining <= 24:
        return 85.0
    if hours_remaining <= 48:
        return 65.0
    if hours_remaining <= 72:
        return 50.0
    return 35.0


def _weighted_score(
    investment_grade: str,
    roi_per_day: float,
    segment_tier: int,
    mmr_confidence_proxy: float,
    transport_cost: float,
    source_score: float,
    auction_end: Optional[str],
) -> float:
    return (
        INVESTMENT_GRADE_PROXY_SCORES.get(investment_grade, 25.0) * 0.30
        + _roi_per_day_score(roi_per_day) * 0.20
        + _segment_tier_score(segment_tier) * 0.15
        + max(0.0, min(100.0, mmr_confidence_proxy)) * 0.10
        + _transport_cost_score(transport_cost) * 0.10
        + source_score * 0.10
        + _time_pressure_score(auction_end) * 0.05
    )


def _range_width_penalty(range_width_pct: Optional[float]) -> float:
    if range_width_pct is None:
        return 0.0
    width = max(float(range_width_pct), 0.0)
    if width >= 24:
        return 22.0
    if width >= 20:
        return 16.0
    if width >= 16:
        return 10.0
    if width >= 12:
        return 5.0
    return 0.0


def _resolve_confidence_proxy(
    mmr_confidence_proxy: Optional[float],
    manheim_confidence: Optional[float],
    manheim_source_status: Optional[str],
    manheim_range_width_pct: Optional[float],
) -> float:
    if manheim_confidence is not None:
        confidence_proxy = float(manheim_confidence)
        if confidence_proxy <= 1.0:
            confidence_proxy *= 100.0
    elif mmr_confidence_proxy is not None:
        confidence_proxy = float(mmr_confidence_proxy)
    else:
        confidence_proxy = 50.0

    if manheim_source_status == "live":
        confidence_proxy -= _range_width_penalty(manheim_range_width_pct)

    return max(0.0, min(100.0, confidence_proxy))


def compute_bid_ceiling(
    current_bid: float,
    mmr_ca: float,
    total_cost: float,
    segment_tier: int,
    investment_grade: str,
    buyer_premium_pct: float,
    doc_fee: float,
    transport: float,
    recon_reserve: float,
    manheim_range_width_pct: Optional[float] = None,
    manheim_source_status: Optional[str] = None,
) -> dict:
    if investment_grade == "Bronze":
        return {
            "bid_ceiling_pct": None,
            "max_bid": 0.0,
            "bid_headroom": -max(float(current_bid or 0), 0.0),
            "ceiling_reason": "bronze_reject",
            "ceiling_pass": False,
        }

    ceiling_pct = None
    reason = None
    if investment_grade == "Platinum" and segment_tier == 1:
        ceiling_pct = 88.0
        reason = "platinum_tier1_all_in_le_88pct_mmr"
    elif investment_grade in {"Platinum", "Gold"} and segment_tier in {1, 2}:
        ceiling_pct = 85.0
        reason = "gold_band_tier1_2_all_in_le_85pct_mmr"
    elif investment_grade == "Silver":
        ceiling_pct = 82.0
        reason = "silver_all_in_le_82pct_mmr"
    else:
        return {
            "bid_ceiling_pct": None,
            "max_bid": 0.0,
            "bid_headroom": -max(float(current_bid or 0), 0.0),
            "ceiling_reason": f"unsupported_grade_tier ({investment_grade}/Tier{segment_tier})",
            "ceiling_pass": False,
        }

    if manheim_source_status == "live" and manheim_range_width_pct is not None:
        width = max(float(manheim_range_width_pct), 0.0)
        if width > 20:
            ceiling_pct -= 4.0
            reason = f"{reason}; live_range_penalty_4pct"
        elif width > 16:
            ceiling_pct -= 3.0
            reason = f"{reason}; live_range_penalty_3pct"
        elif width > 12:
            ceiling_pct -= 2.0
            reason = f"{reason}; live_range_penalty_2pct"
        elif width > 8:
            ceiling_pct -= 1.0
            reason = f"{reason}; live_range_penalty_1pct"
        else:
            reason = f"{reason}; live_range_preserved"

    if mmr_ca <= 0:
        return {
            "bid_ceiling_pct": ceiling_pct,
            "max_bid": 0.0,
            "bid_headroom": -max(float(current_bid or 0), 0.0),
            "ceiling_reason": "missing_mmr_for_ceiling",
            "ceiling_pass": False,
        }

    ceiling_total_cost = mmr_ca * (ceiling_pct / 100.0)
    fixed_costs = float(doc_fee or 0.0) + float(transport or 0.0) + float(recon_reserve or 0.0)
    bid_multiplier = 1.0 + max(float(buyer_premium_pct or 0.0), 0.0)
    max_bid = (ceiling_total_cost - fixed_costs) / bid_multiplier if bid_multiplier > 0 else 0.0
    max_bid = max(0.0, max_bid)
    bid_headroom = max_bid - max(float(current_bid or 0.0), 0.0)
    ceiling_pass = total_cost <= ceiling_total_cost and bid_headroom >= 0

    if not ceiling_pass and bid_headroom < 0:
        reason = f"{reason}; negative_headroom"
    elif not ceiling_pass:
        reason = f"{reason}; total_cost_exceeds_ceiling"

    return {
        "bid_ceiling_pct": round(ceiling_pct, 2),
        "max_bid": round(max_bid, 2),
        "bid_headroom": round(bid_headroom, 2),
        "ceiling_reason": reason,
        "ceiling_pass": ceiling_pass,
    }


def _recon_reserve(mileage: float = None, is_police_or_fleet: bool = False) -> float:
    miles = max(float(mileage or 0), 0.0)
    mileage_component = 3.0 * (miles / 1000.0)
    reserve = min(500.0 + mileage_component, 1200.0)
    if is_police_or_fleet:
        reserve += 300.0
    return reserve


def _parse_auction_end(auction_end: Optional[str]) -> Optional[datetime]:
    if not auction_end:
        return None
    raw_value = str(auction_end).strip()
    if not raw_value:
        return None
    try:
        parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _auction_stage_hours_remaining(auction_end: Optional[str]) -> Optional[float]:
    parsed = _parse_auction_end(auction_end)
    if parsed is None:
        return None
    hours_remaining = (parsed - datetime.now(timezone.utc)).total_seconds() / 3600.0
    return round(max(hours_remaining, 0.0), 2)


def resolve_pricing_maturity(
    *,
    manheim_source_status: Optional[str],
    manheim_mmr_mid: Optional[float],
    pricing_source: Optional[str],
    retail_comp_price_estimate: Optional[float],
    retail_comp_count: Optional[int],
    retail_comp_confidence: Optional[float],
    mmr_lookup_basis: Optional[str],
) -> str:
    if manheim_source_status == "live" and (manheim_mmr_mid or 0) > 0:
        return "live_market"

    market_comp_sources = {"retail_market_cache", "dealer_sales_history"}
    if pricing_source in market_comp_sources:
        return "market_comp"
    if (retail_comp_price_estimate or 0) > 0 and int(retail_comp_count or 0) > 0:
        return "market_comp"
    if (retail_comp_confidence or 0) > 0:
        return "market_comp"

    if pricing_source == "mmr_proxy":
        return "proxy"
    if manheim_source_status in {"fallback", "unavailable"}:
        return "proxy"
    if mmr_lookup_basis and mmr_lookup_basis != "unknown":
        return "proxy"

    return "unknown"


def _current_bid_trust_score(
    auction_stage_hours_remaining: Optional[float],
    pricing_maturity: str,
) -> Optional[float]:
    if auction_stage_hours_remaining is None:
        return None

    hours_remaining = max(float(auction_stage_hours_remaining), 0.0)
    if hours_remaining > 72:
        base_score = 0.15
    elif hours_remaining > 24:
        base_score = 0.25
    elif hours_remaining > 6:
        base_score = 0.4
    elif hours_remaining > 1:
        base_score = 0.6
    else:
        base_score = 0.8

    maturity_adjustment = {
        "live_market": 0.05,
        "market_comp": 0.0,
        "proxy": -0.05,
        "unknown": -0.1,
    }.get(pricing_maturity, -0.1)

    return round(max(0.05, min(0.9, base_score + maturity_adjustment)), 2)


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
    auction_end: Optional[str] = None,
    mmr_lookup_basis: Optional[str] = None,
    mmr_confidence_proxy: Optional[float] = None,
    retail_comp_price_estimate: Optional[float] = None,
    retail_comp_low: Optional[float] = None,
    retail_comp_high: Optional[float] = None,
    retail_comp_count: Optional[int] = None,
    retail_comp_confidence: Optional[float] = None,
    pricing_source: Optional[str] = None,
    pricing_updated_at: Optional[str] = None,
    manheim_mmr_mid: Optional[float] = None,
    manheim_mmr_low: Optional[float] = None,
    manheim_mmr_high: Optional[float] = None,
    manheim_range_width_pct: Optional[float] = None,
    manheim_confidence: Optional[float] = None,
    manheim_source_status: Optional[str] = None,
    manheim_updated_at: Optional[str] = None,
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
    buyer_premium_pct = site_fees.get("buyers_premium_pct", 10.0) / 100.0
    premium = bid * buyer_premium_pct
    doc_fee = site_fees.get("doc_fee", 50)
    transport = calc_transport_cost(state, rates_cfg=rates_cfg, miles_cfg=miles_cfg)
    recon_reserve = _recon_reserve(mileage=mileage, is_police_or_fleet=is_police_or_fleet)
    total_cost = bid + premium + doc_fee + transport + recon_reserve
    selected_mmr = float(manheim_mmr_mid) if manheim_mmr_mid is not None and float(manheim_mmr_mid) > 0 else float(mmr_ca or 0)
    wholesale_margin = selected_mmr - total_cost
    retail_comp_result = {
        "retail_comp_price_estimate": retail_comp_price_estimate,
        "retail_comp_low": retail_comp_low,
        "retail_comp_high": retail_comp_high,
        "retail_comp_count": retail_comp_count,
        "retail_comp_confidence": retail_comp_confidence,
        "pricing_source": pricing_source,
        "pricing_updated_at": pricing_updated_at,
    }
    use_retail_comps = retail_comp_is_usable(retail_comp_result)
    retail_asking_price_estimate = (
        float(retail_comp_price_estimate)
        if use_retail_comps and retail_comp_price_estimate is not None
        else selected_mmr * RETAIL_PROXY_MULTIPLIER
    )
    selected_pricing_source = (pricing_source or "retail_comps") if use_retail_comps else "mmr_proxy"
    gross_margin = retail_asking_price_estimate - total_cost

    m_score = _margin_score(bid, selected_mmr, total_cost)
    v_score = _velocity_score(bid, year)
    seg_score = _segment_score(model, make)
    mod_score = _model_score(model)
    src_score = _source_score(source_site)
    wholesale_ctm_pct = (total_cost / selected_mmr * 100.0) if selected_mmr > 0 else 100.0
    retail_ctm_pct = (total_cost / retail_asking_price_estimate * 100.0) if retail_asking_price_estimate > 0 else 100.0
    segment_tier = _segment_tier(model, make)
    estimated_days_to_sale = _estimated_days_to_sale(segment_tier)
    roi_per_day = gross_margin / estimated_days_to_sale if estimated_days_to_sale > 0 else 0.0
    confidence_proxy = _resolve_confidence_proxy(
        mmr_confidence_proxy=mmr_confidence_proxy,
        manheim_confidence=manheim_confidence,
        manheim_source_status=manheim_source_status,
        manheim_range_width_pct=manheim_range_width_pct,
    )
    investment_grade = _investment_grade(retail_ctm_pct, estimated_days_to_sale, segment_tier)
    pricing_maturity = resolve_pricing_maturity(
        manheim_source_status=manheim_source_status,
        manheim_mmr_mid=manheim_mmr_mid,
        pricing_source=selected_pricing_source,
        retail_comp_price_estimate=retail_comp_price_estimate,
        retail_comp_count=retail_comp_count,
        retail_comp_confidence=retail_comp_confidence,
        mmr_lookup_basis=mmr_lookup_basis,
    )
    auction_stage_hours_remaining = _auction_stage_hours_remaining(auction_end)
    current_bid_trust_score = _current_bid_trust_score(
        auction_stage_hours_remaining=auction_stage_hours_remaining,
        pricing_maturity=pricing_maturity,
    )

    legacy_dos_score = (
        m_score * 0.35
        + v_score * 0.25
        + seg_score * 0.20
        + mod_score * 0.12
        + src_score * 0.08
    )
    weighted_score = _weighted_score(
        investment_grade=investment_grade,
        roi_per_day=roi_per_day,
        segment_tier=segment_tier,
        mmr_confidence_proxy=confidence_proxy,
        transport_cost=transport,
        source_score=src_score,
        auction_end=auction_end,
    )
    ceiling_metrics = compute_bid_ceiling(
        current_bid=bid,
        mmr_ca=selected_mmr,
        total_cost=total_cost,
        segment_tier=segment_tier,
        investment_grade=investment_grade,
        buyer_premium_pct=buyer_premium_pct,
        doc_fee=doc_fee,
        transport=transport,
        recon_reserve=recon_reserve,
        manheim_range_width_pct=manheim_range_width_pct,
        manheim_source_status=manheim_source_status,
    )

    return {
        "premium": round(premium, 2),
        "buyer_premium_amount": round(premium, 2),
        "buyer_premium_pct": round(buyer_premium_pct, 4),
        "doc_fee": doc_fee,
        "transport": round(transport, 2),
        "recon_reserve": round(recon_reserve, 2),
        "total_cost": round(total_cost, 2),
        "margin": round(gross_margin, 2),
        "gross_margin": round(gross_margin, 2),
        "wholesale_margin": round(wholesale_margin, 2),
        "margin_score": round(m_score, 2),
        "velocity_score": round(v_score, 2),
        "segment_score": round(seg_score, 2),
        "model_score": round(mod_score, 2),
        "source_score": round(src_score, 2),
        "retail_proxy_multiplier": None if use_retail_comps else RETAIL_PROXY_MULTIPLIER,
        "retail_asking_price_estimate": round(retail_asking_price_estimate, 2),
        "retail_comp_price_estimate": round(float(retail_comp_price_estimate), 2) if retail_comp_price_estimate is not None else None,
        "retail_comp_low": round(float(retail_comp_low), 2) if retail_comp_low is not None else None,
        "retail_comp_high": round(float(retail_comp_high), 2) if retail_comp_high is not None else None,
        "retail_comp_count": int(retail_comp_count or 0),
        "retail_comp_confidence": round(float(retail_comp_confidence), 3) if retail_comp_confidence is not None else None,
        "pricing_source": selected_pricing_source,
        "pricing_maturity": pricing_maturity,
        "pricing_updated_at": pricing_updated_at,
        "expected_close_bid": None,
        "expected_close_source": None,
        "current_bid_trust_score": current_bid_trust_score,
        "auction_stage_hours_remaining": auction_stage_hours_remaining,
        "manheim_mmr_mid": round(float(manheim_mmr_mid), 2) if manheim_mmr_mid is not None else None,
        "manheim_mmr_low": round(float(manheim_mmr_low), 2) if manheim_mmr_low is not None else None,
        "manheim_mmr_high": round(float(manheim_mmr_high), 2) if manheim_mmr_high is not None else None,
        "manheim_range_width_pct": round(float(manheim_range_width_pct), 2) if manheim_range_width_pct is not None else None,
        "manheim_confidence": round(float(manheim_confidence), 3) if manheim_confidence is not None else None,
        "manheim_source_status": manheim_source_status or "unavailable",
        "manheim_updated_at": manheim_updated_at,
        "ctm_pct": round(retail_ctm_pct, 2),
        "wholesale_ctm_pct": round(wholesale_ctm_pct, 2),
        "retail_ctm_pct": round(retail_ctm_pct, 2),
        "segment_tier": segment_tier,
        "estimated_days_to_sale": estimated_days_to_sale,
        "roi_per_day": round(roi_per_day, 2),
        "mmr_lookup_basis": mmr_lookup_basis or "unknown",
        "mmr_confidence_proxy": round(confidence_proxy, 2),
        "investment_grade": investment_grade,
        "legacy_dos_score": round(legacy_dos_score, 2),
        "dos_score": round(weighted_score, 2),
        "score": round(weighted_score, 2),
        "score_version": SCORE_VERSION,
        **ceiling_metrics,
    }
