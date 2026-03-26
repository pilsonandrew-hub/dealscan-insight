from datetime import datetime
from typing import Optional


CURRENT_YEAR = datetime.now().year
PREMIUM_YEAR_CUTOFF = CURRENT_YEAR - 4
STANDARD_YEAR_CUTOFF = CURRENT_YEAR - 10

HIGH_RUST_STATES = {
    "OH", "MI", "PA", "NY", "WI", "MN", "IL", "IN", "MO", "IA", "ND", "SD", "NE", "KS", "WV",
    "ME", "NH", "VT", "MA", "RI", "CT", "NJ", "MD", "DE",
}


def _coerce_float(value: object) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_year(value: object) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        year = int(float(value))
    except (TypeError, ValueError):
        return None
    if 1980 <= year <= CURRENT_YEAR + 1:
        return year
    return None


def _clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    return max(minimum, min(maximum, value))


def _parse_datetime(value: object) -> Optional[datetime]:
    if not value:
        return None
    try:
        text = str(value).strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text)
    except Exception:
        return None


def determine_vehicle_tier(year, mileage) -> str:
    model_year = _coerce_year(year)
    if model_year is None:
        return "unassigned"
    if model_year >= PREMIUM_YEAR_CUTOFF:
        return "premium"
    if model_year >= STANDARD_YEAR_CUTOFF:
        return "standard"
    return "rejected"


def _mileage_per_year(vehicle: dict) -> Optional[float]:
    mileage = _coerce_float(vehicle.get("mileage"))
    year = _coerce_year(vehicle.get("year"))
    if mileage is None or year is None:
        return None
    age = max(1, CURRENT_YEAR - year)
    return mileage / age


def _auction_velocity_score(vehicle: dict) -> float:
    auction_end = (
        vehicle.get("auction_end")
        or vehicle.get("auction_end_time")
        or vehicle.get("auction_end_date")
        or vehicle.get("auction_end")
    )
    end_dt = _parse_datetime(auction_end)
    if not end_dt:
        return 50.0
    try:
        hours = (end_dt - datetime.now(end_dt.tzinfo)).total_seconds() / 3600
    except Exception:
        return 50.0
    if hours <= 6:
        return 100.0
    if hours <= 24:
        return 85.0
    if hours <= 72:
        return 65.0
    if hours <= 168:
        return 45.0
    return 25.0


def _listing_freshness_score(vehicle: dict) -> float:
    timestamp = (
        vehicle.get("pricing_updated_at")
        or vehicle.get("updated_at")
        or vehicle.get("scraped_at")
        or vehicle.get("scrapedAt")
        or vehicle.get("createdAt")
    )
    dt = _parse_datetime(timestamp)
    if not dt:
        return 50.0
    try:
        hours = (datetime.now(dt.tzinfo) - dt).total_seconds() / 3600
    except Exception:
        return 50.0
    if hours <= 24:
        return 100.0
    if hours <= 72:
        return 85.0
    if hours <= 168:
        return 65.0
    if hours <= 336:
        return 45.0
    return 25.0


def _make_velocity_score(vehicle: dict) -> float:
    source = (vehicle.get("source_site") or vehicle.get("source") or "").lower()
    source_scores = {
        "govdeals": 80.0,
        "govdeals-sold": 70.0,
        "publicsurplus": 72.0,
        "gsaauctions": 75.0,
        "municibid": 70.0,
        "govplanet": 82.0,
        "allsurplus": 65.0,
        "jjkane": 68.0,
        "hibid": 60.0,
        "proxibid": 58.0,
        "bidspotter": 55.0,
        "usgovbid": 74.0,
    }
    return source_scores.get(source, 55.0)


def _condition_score(vehicle: dict) -> float:
    title_status = str(vehicle.get("title_status") or vehicle.get("titleStatus") or "").strip().lower()
    damage_type = str(vehicle.get("damage_type") or "").strip().lower()
    description = str(vehicle.get("description") or vehicle.get("title") or "").strip().lower()
    risk_flags = {str(flag).lower() for flag in (vehicle.get("risk_flags") or [])}

    if "frame_damage" in risk_flags or ("frame" in damage_type and "damage" in damage_type):
        return 20.0
    if any(term in description for term in ("salvage", "rebuilt", "flood", "hail damage", "fire damage")):
        return 35.0
    if title_status in {"salvage", "rebuilt", "flood", "damaged"}:
        return 40.0
    if title_status in {"clean", "clear"}:
        return 90.0
    return 65.0


def _mileage_score(vehicle: dict) -> float:
    mileage = _coerce_float(vehicle.get("mileage"))
    if mileage is None:
        return 55.0
    if mileage <= 30000:
        return 100.0
    if mileage <= 60000:
        return 80.0
    if mileage <= 100000:
        return 60.0
    if mileage <= 150000:
        return 40.0
    return 20.0


def _risk_penalty_score(vehicle: dict, tier: str) -> float:
    flags = compute_risk_flags(vehicle, tier)
    penalty = 0.0
    for flag in flags:
        if flag == "rust_state_source":
            penalty += 25.0
        elif flag == "mileage_per_year_gt_18000":
            penalty += 20.0
        elif flag == "missing_photos":
            penalty += 10.0
        elif flag == "frame_damage":
            penalty += 35.0
    return _clamp(100.0 - penalty)


def _mmr_proximity_score(vehicle: dict) -> float:
    mmr = _coerce_float(vehicle.get("mmr_estimated") or vehicle.get("manheim_mmr_mid") or vehicle.get("mmr"))
    bid = _coerce_float(vehicle.get("bid") or vehicle.get("current_bid"))
    if mmr is None or mmr <= 0:
        return 40.0
    if bid is None or bid <= 0:
        return 55.0
    ratio = bid / mmr
    if ratio <= 0.50:
        return 100.0
    if ratio <= 0.60:
        return 90.0
    if ratio <= 0.70:
        return 75.0
    if ratio <= 0.80:
        return 60.0
    if ratio <= 0.90:
        return 40.0
    if ratio <= 1.00:
        return 20.0
    return 0.0


def _discount_pct_score(vehicle: dict) -> float:
    mmr = _coerce_float(vehicle.get("mmr_estimated") or vehicle.get("manheim_mmr_mid") or vehicle.get("mmr"))
    bid = _coerce_float(vehicle.get("bid") or vehicle.get("current_bid"))
    if mmr is None or mmr <= 0 or bid is None:
        return 35.0
    discount_pct = (mmr - bid) / mmr
    if discount_pct >= 0.50:
        return 100.0
    if discount_pct >= 0.35:
        return 85.0
    if discount_pct >= 0.25:
        return 70.0
    if discount_pct >= 0.15:
        return 55.0
    if discount_pct >= 0.05:
        return 35.0
    return 15.0


def _net_margin_score(vehicle: dict) -> float:
    mmr = _coerce_float(vehicle.get("mmr_estimated") or vehicle.get("manheim_mmr_mid") or vehicle.get("mmr"))
    bid = _coerce_float(vehicle.get("bid") or vehicle.get("current_bid"))
    if mmr is None or mmr <= 0 or bid is None:
        return 35.0
    gross_margin = mmr - bid
    margin_pct = gross_margin / mmr
    if gross_margin >= 10000 or margin_pct >= 0.40:
        return 100.0
    if gross_margin >= 7000 or margin_pct >= 0.30:
        return 85.0
    if gross_margin >= 4000 or margin_pct >= 0.20:
        return 70.0
    if gross_margin >= 2000 or margin_pct >= 0.10:
        return 55.0
    if gross_margin >= 500 or margin_pct >= 0.03:
        return 35.0
    return 10.0


def _recon_efficiency_score(vehicle: dict) -> float:
    condition_score = _condition_score(vehicle)
    mileage_score = _mileage_score(vehicle)
    if condition_score <= 20.0:
        return 15.0
    if condition_score <= 40.0:
        return 30.0
    return _clamp((condition_score * 0.6) + (mileage_score * 0.4))


def _risk_score(vehicle: dict, tier: str) -> float:
    return _risk_penalty_score(vehicle, tier)


def compute_risk_flags(vehicle: dict, tier) -> list[str]:
    flags: list[str] = []
    state = str(vehicle.get("state") or "").upper().strip()
    if state in HIGH_RUST_STATES:
        flags.append("rust_state_source")

    mileage = _coerce_float(vehicle.get("mileage"))
    year = _coerce_year(vehicle.get("year"))
    if mileage is not None and year is not None:
        age = max(1, CURRENT_YEAR - year)
        mileage_per_year = mileage / age
        if mileage_per_year > 18000:
            flags.append("mileage_per_year_gt_18000")

    photos = vehicle.get("photos") or vehicle.get("photo_urls") or vehicle.get("image_url") or vehicle.get("photo_url")
    if not photos:
        flags.append("missing_photos")

    title_blob = " ".join(
        str(vehicle.get(field) or "").lower()
        for field in ("title", "description", "damage_type", "title_status")
    )
    if "frame" in title_blob and "damage" in title_blob:
        flags.append("frame_damage")

    return flags


def score_deal_premium(vehicle: dict) -> float:
    mmr_proximity = _mmr_proximity_score(vehicle)
    demand_velocity = (_make_velocity_score(vehicle) * 0.6) + (_auction_velocity_score(vehicle) * 0.4)
    low_mileage = _mileage_score(vehicle)
    condition = _condition_score(vehicle)
    freshness = _listing_freshness_score(vehicle)
    score = (
        mmr_proximity * 0.40
        + demand_velocity * 0.25
        + low_mileage * 0.15
        + condition * 0.10
        + freshness * 0.10
    )
    return round(_clamp(score), 1)


def score_deal_standard(vehicle: dict) -> float:
    tier = determine_vehicle_tier(vehicle.get("year"), vehicle.get("mileage"))
    net_margin = _net_margin_score(vehicle)
    discount_pct = _discount_pct_score(vehicle)
    wholesale_velocity = (_make_velocity_score(vehicle) * 0.4) + (_auction_velocity_score(vehicle) * 0.6)
    risk_score = _risk_score(vehicle, tier)
    recon_efficiency = _recon_efficiency_score(vehicle)
    score = (
        net_margin * 0.35
        + discount_pct * 0.25
        + wholesale_velocity * 0.20
        + risk_score * 0.15
        + recon_efficiency * 0.05
    )
    return round(_clamp(score), 1)


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
    vehicle_tier = determine_vehicle_tier(year, mileage)

    vehicle_proxy = {
        "bid": bid,
        "current_bid": bid,
        "mmr_estimated": mmr,
        "manheim_mmr_mid": manheim_mmr_mid,
        "state": state,
        "source_site": source_site,
        "model": model,
        "make": make,
        "year": year,
        "mileage": mileage,
        "auction_end": auction_end,
        "auction_end_time": auction_end,
        "auction_end_date": auction_end,
        "pricing_updated_at": pricing_updated_at,
        "scraped_at": pricing_updated_at,
        "title_status": "unknown",
        "description": "",
    }

    risk_flags = compute_risk_flags(vehicle_proxy, vehicle_tier)
    vehicle_proxy["risk_flags"] = risk_flags

    dos_premium = score_deal_premium(vehicle_proxy)
    dos_standard = score_deal_standard(vehicle_proxy)

    selected_dos = dos_premium if vehicle_tier == "premium" else dos_standard if vehicle_tier == "standard" else max(dos_premium, dos_standard)

    gross_margin = mmr - bid if mmr > 0 else 0
    wholesale_margin = gross_margin
    retail_price = retail_comp_price_estimate or (mmr * 1.35 if mmr > 0 else 0)

    if manheim_source_status == "live":
        pricing_maturity = "live_market"
    elif retail_comp_count and retail_comp_count > 0:
        pricing_maturity = "market_comp"
    else:
        pricing_maturity = "proxy"

    hours_remaining = _parse_datetime(auction_end)
    auction_stage_hours_remaining = None
    if hours_remaining is not None:
        try:
            auction_stage_hours_remaining = (hours_remaining - datetime.now(hours_remaining.tzinfo)).total_seconds() / 3600
        except Exception:
            auction_stage_hours_remaining = None

    trust_score = _current_bid_trust_score(auction_stage_hours_remaining, pricing_maturity)

    bid_ceiling_pct = 0.88 if vehicle_tier == "premium" else 0.80 if vehicle_tier == "standard" else 0.0
    max_bid = mmr * bid_ceiling_pct if mmr > 0 else 0
    bid_headroom = max_bid - bid
    min_margin_target = 500.0
    ceiling_pass = bid <= max_bid and gross_margin >= min_margin_target

    roi_pct = (gross_margin / bid * 100) if bid > 0 else 0
    if selected_dos >= 80 and roi_pct >= 20 and ceiling_pass:
        investment_grade = "Platinum"
    elif selected_dos >= 65 and roi_pct >= 12 and ceiling_pass:
        investment_grade = "Gold"
    elif selected_dos >= 50 and ceiling_pass:
        investment_grade = "Silver"
    else:
        investment_grade = "Bronze"

    acquisition_price_basis = _round_price_basis(bid)
    ctm_pct = (bid / mmr) if mmr > 0 else None

    ai_confidence_score = round(
        _clamp((trust_score * 100.0 * 0.35) + ((100.0 - len(risk_flags) * 15.0) * 0.25) + (_condition_score(vehicle_proxy) * 0.40)),
        1,
    )

    return {
        "dos_score": selected_dos,
        "score": selected_dos,
        "legacy_dos_score": selected_dos,
        "score_version": "v3_two_lane",
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
        "auction_stage_hours_remaining": auction_stage_hours_remaining,
        "acquisition_price_basis": acquisition_price_basis,
        "acquisition_basis_source": "current_bid",
        "total_cost": bid,
        "projected_total_cost": bid,
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
        "min_margin_target": min_margin_target,
        "ceiling_reason": "score_deal_v3_two_lane",
        "ceiling_pass": ceiling_pass,
        "designated_lane": vehicle_tier,
        "vehicle_tier": vehicle_tier,
        "dos_premium": dos_premium,
        "dos_standard": dos_standard,
        "risk_flags": risk_flags,
        "ai_confidence_score": ai_confidence_score,
    }


def _fallback_score() -> tuple:
    ceiling_pass = False
    return ceiling_pass
