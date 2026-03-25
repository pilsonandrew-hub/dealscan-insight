from typing import Optional
from datetime import datetime


def _compute_dos_v2(vehicle: dict, gross_margin: float, condition_grade: Optional[str] = None) -> float:
    margin = _margin_score_v2(gross_margin)
    velocity = _velocity_score_v2(vehicle.get("auction_end_date") or vehicle.get("auction_end_time") or vehicle.get("auction_end"))
    segment = _segment_score_v2(vehicle.get("make",""), vehicle.get("model",""))
    model = _model_score_v2(vehicle.get("make",""), vehicle.get("model",""))
    source = _source_score_v2(vehicle.get("source_site",""))
    condition_adjustments = {"A": 3, "B": 1, "C": 0, "D": -3, "F": -5}
    grade_adjustment = condition_adjustments.get(condition_grade, 0)
    dos = (margin * 0.35 + velocity * 0.25 + (segment + grade_adjustment) * 0.20 + model * 0.12 + source * 0.08)
    return round(min(100.0, max(0.0, dos)), 1)


def _margin_score_v2(gross_margin: float) -> float:
    if gross_margin >= 8000: return 100
    if gross_margin >= 5000: return 80
    if gross_margin >= 3000: return 60
    if gross_margin >= 1500: return 40
    if gross_margin >= 0: return 20
    return 0


def _velocity_score_v2(auction_end) -> float:
    if not auction_end:
        return 50
    try:
        from dateutil import parser as dateparser
        end_dt = dateparser.parse(str(auction_end))
        hours = (end_dt - datetime.now(end_dt.tzinfo)).total_seconds() / 3600
        if hours <= 6: return 100
        if hours <= 24: return 80
        if hours <= 48: return 60
        if hours <= 72: return 40
        return 20
    except Exception:
        return 50


def _segment_score_v2(make: str, model: str) -> float:
    HOT_MAKES = {"FORD", "TOYOTA", "RAM", "CHEVROLET", "CHEVY", "GMC", "HONDA", "NISSAN", "TESLA", "JEEP"}
    HOT_MODELS = {"F-150", "F150", "TACOMA", "TUNDRA", "SILVERADO", "SIERRA", "CAMRY", "ACCORD", "MODEL 3", "WRANGLER"}
    score = 50.0
    if make.upper() in HOT_MAKES:
        score += 25
    if model.upper() in HOT_MODELS:
        score += 25
    return min(100, score)


def _model_score_v2(make: str, model: str) -> float:
    return _segment_score_v2(make, model)


def _source_score_v2(source: str) -> float:
    SOURCE_SCORES = {
        "govdeals": 80, "publicsurplus": 80, "gsaauctions": 75,
        "municibid": 75, "govplanet": 85, "hibid": 65,
        "proxibid": 65, "bidspotter": 60, "allsurplus": 60,
        "jjkane": 70, "usgovbid": 75,
    }
    return SOURCE_SCORES.get((source or "").lower(), 55)


def _auction_stage_hours_remaining(auction_end) -> Optional[float]:
    if not auction_end:
        return None
    try:
        from dateutil import parser as dateparser
        end_dt = dateparser.parse(str(auction_end))
        hours = (end_dt - datetime.now(end_dt.tzinfo)).total_seconds() / 3600
        return round(hours, 1)
    except Exception:
        return None


def _current_bid_trust_score(auction_stage_hours_remaining: Optional[float] = None,
                              pricing_maturity: str = "proxy") -> float:
    base = {"live_market": 0.9, "market_comp": 0.75, "proxy": 0.5}.get(pricing_maturity, 0.5)
    if auction_stage_hours_remaining is not None:
        if auction_stage_hours_remaining <= 6:
            base = min(1.0, base + 0.2)
        elif auction_stage_hours_remaining <= 24:
            base = min(1.0, base + 0.1)
    return round(base, 3)


def _round_price_basis(price: float) -> float:
    if price <= 0:
        return 0
    magnitude = 10 ** (len(str(int(price))) - 2)
    return round(price / magnitude) * magnitude


COST_TO_MARKET_MAX = 0.88
MIN_GROSS_MARGIN = 1500


def score_deal(
    bid: float,
    mmr_ca: Optional[float],
    state: str = "",
    source_site: str = "",
    model: str = "",
    make: str = "",
    year: Optional[int] = None,
    mileage: Optional[float] = None,
    is_police_or_fleet: bool = False,
    auction_end=None,
    mmr_lookup_basis: Optional[str] = None,
    mmr_confidence_proxy: Optional[float] = None,
    retail_comp_price_estimate: Optional[float] = None,
    retail_comp_low: Optional[float] = None,
    retail_comp_high: Optional[float] = None,
    retail_comp_count: int = 0,
    retail_comp_confidence: Optional[float] = None,
    pricing_source: Optional[str] = None,
    pricing_updated_at=None,
    manheim_mmr_mid: Optional[float] = None,
    manheim_mmr_low: Optional[float] = None,
    manheim_mmr_high: Optional[float] = None,
    manheim_range_width_pct: Optional[float] = None,
    manheim_confidence: Optional[float] = None,
    manheim_source_status: Optional[str] = None,
    manheim_updated_at=None,
) -> dict:
    """
    Primary DOS scoring function.
    Returns full scoring dict compatible with save_opportunity_to_supabase.
    """
    mmr = manheim_mmr_mid or mmr_ca or 0

    # Gross margin
    gross_margin = mmr - bid if mmr > 0 else 0
    wholesale_margin = gross_margin
    retail_price = retail_comp_price_estimate or (mmr * 1.35 if mmr > 0 else 0)

    # Pricing maturity
    if manheim_source_status == "live":
        pricing_maturity = "live_market"
    elif retail_comp_count and retail_comp_count > 0:
        pricing_maturity = "market_comp"
    else:
        pricing_maturity = "proxy"

    # Trust score
    hours_remaining = _auction_stage_hours_remaining(auction_end)
    trust_score = _current_bid_trust_score(hours_remaining, pricing_maturity)

    # Bid ceiling
    max_bid = mmr * COST_TO_MARKET_MAX if mmr > 0 else 0
    bid_headroom = max_bid - bid
    ceiling_pass = bid <= max_bid and gross_margin >= MIN_GROSS_MARGIN

    # DOS score using v2 formula
    vehicle_proxy = {
        "make": make, "model": model, "source_site": source_site,
        "auction_end_time": auction_end,
    }
    dos = _compute_dos_v2(vehicle_proxy, gross_margin)

    # Investment grade
    roi_pct = (gross_margin / bid * 100) if bid > 0 else 0
    if dos >= 80 and roi_pct >= 20 and ceiling_pass:
        investment_grade = "Platinum"
    elif dos >= 65 and roi_pct >= 12 and ceiling_pass:
        investment_grade = "Gold"
    elif dos >= 50 and ceiling_pass:
        investment_grade = "Silver"
    else:
        investment_grade = "Bronze"

    # Bid ceiling pct
    bid_ceiling_pct = (bid / mmr) if mmr > 0 else None

    # CTM
    total_cost = bid
    ctm_pct = (total_cost / mmr) if mmr > 0 else None

    acquisition_price_basis = _round_price_basis(bid)

    return {
        "dos_score": dos,
        "score": dos,
        "legacy_dos_score": dos,
        "score_version": "v2",
        "mmr_estimated": mmr,
        "margin": gross_margin,
        "gross_margin": gross_margin,
        "wholesale_margin": wholesale_margin,
        "retail_asking_price_estimate": retail_price,
        "retail_comp_price_estimate": retail_comp_price_estimate,
        "retail_comp_low": retail_comp_low,
        "retail_comp_high": retail_comp_high,
        "retail_comp_count": retail_comp_count or 0,
        "retail_comp_confidence": retail_comp_confidence,
        "pricing_source": pricing_source or mmr_lookup_basis or "mmr_proxy",
        "pricing_maturity": pricing_maturity,
        "pricing_updated_at": pricing_updated_at,
        "expected_close_bid": acquisition_price_basis,
        "expected_close_source": "current_bid",
        "current_bid_trust_score": trust_score,
        "auction_stage_hours_remaining": hours_remaining,
        "acquisition_price_basis": acquisition_price_basis,
        "acquisition_basis_source": "current_bid",
        "projected_total_cost": total_cost,
        "manheim_mmr_mid": manheim_mmr_mid,
        "manheim_mmr_low": manheim_mmr_low,
        "manheim_mmr_high": manheim_mmr_high,
        "manheim_range_width_pct": manheim_range_width_pct,
        "manheim_confidence": manheim_confidence,
        "manheim_source_status": manheim_source_status or "unavailable",
        "manheim_updated_at": manheim_updated_at,
        "retail_proxy_multiplier": 1.35,
        "wholesale_ctm_pct": ctm_pct,
        "retail_ctm_pct": None,
        "ctm_pct": ctm_pct,
        "estimated_days_to_sale": None,
        "roi_per_day": None,
        "investment_grade": investment_grade,
        "bid_ceiling_pct": bid_ceiling_pct,
        "max_bid": max_bid,
        "bid_headroom": bid_headroom,
        "ceiling_reason": "score_deal_v2",
        "ceiling_pass": ceiling_pass,
    }


def _fallback_score() -> tuple:
    ceiling_pass = False
    return ceiling_pass
