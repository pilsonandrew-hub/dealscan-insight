from datetime import datetime
import re
from typing import Optional

from backend.ingest.transport import calc_transport_cost

try:
    from backend.ingest.condition import compute_condition_grade as _compute_condition_grade
except ImportError:  # pragma: no cover - exercised in minimal local environments
    def _compute_condition_grade(**kwargs):
        return None


def _current_year() -> int:
    return datetime.now().year


CURRENT_YEAR = _current_year()

HIGH_RUST_STATES = {
    "OH", "MI", "PA", "NY", "WI", "MN", "IL", "IN", "MO", "IA", "ND", "SD", "NE", "KS", "WV",
    "ME", "NH", "VT", "MA", "RI", "CT", "NJ", "MD", "DE",
}

HIGH_DEMAND_MODELS = {
    "camry",
    "corolla",
    "civic",
    "accord",
    "f-150",
    "f150",
    "f-250",
    "f250",
    "silverado",
    "rav4",
    "cr-v",
    "crv",
    "highlander",
    "tacoma",
    "wrangler",
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
    if 1980 <= year <= _current_year() + 1:
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
    current_year = _current_year()
    # Two-lane system:
    # Premium: 1-4 years old (model_year >= current_year - 4)
    # Standard: 5-10 years old (model_year >= current_year - 10)
    # Rejected: >10 years old
    premium_year_cutoff = current_year - 4   # model_year >= this -> premium
    standard_year_cutoff = current_year - 10  # model_year >= this -> standard, else rejected
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
    if mileage_value is not None:
        if vehicle_tier == "premium" and mileage_value > 50000:
            return "rejected"
        if vehicle_tier == "standard":
            if mileage_value > 100000:
                return "rejected"
            age_years = max(1, current_year - model_year)
            if mileage_value / age_years > 18000:
                return "rejected"

    return vehicle_tier


def _mileage_per_year(vehicle: dict) -> Optional[float]:
    mileage = _coerce_float(vehicle.get("mileage"))
    year = _coerce_year(vehicle.get("year"))
    if mileage is None or year is None:
        return None
    age = max(1, _current_year() - year)
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
        "allsurplus": 68.0,
        "jjkane": 68.0,
        "hibid": 68.0,
        "proxibid": 68.0,
        "bidspotter": 60.0,
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
        age = max(1, _current_year() - year)
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


def _auction_stage_hours_remaining(auction_end: object) -> Optional[float]:
    """Return hours remaining until auction_end, or None if unparseable / already ended."""
    dt = _parse_datetime(auction_end)
    if dt is None:
        return None
    try:
        hours = (dt - datetime.now(dt.tzinfo)).total_seconds() / 3600
        return hours if hours >= 0 else None
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


def resolve_expected_close_bid(
    *,
    current_bid: Optional[float],
    max_bid: Optional[float],
    current_bid_trust_score: Optional[float] = None,
    auction_stage_hours_remaining: Optional[float] = None,
    pricing_maturity: str = "proxy",
    confidence_proxy: Optional[float] = None,
) -> dict:
    bid_value = _coerce_float(current_bid) or 0.0
    cap_value = _coerce_float(max_bid) or bid_value
    if bid_value <= 0:
        return {
            "expected_close_bid": 0.0,
            "expected_close_source": "zero_bid",
            "current_bid_trust_score": 0.0,
            "auction_stage_hours_remaining": auction_stage_hours_remaining,
        }

    trust_score = current_bid_trust_score
    if trust_score is None:
        trust_score = _current_bid_trust_score(auction_stage_hours_remaining, pricing_maturity)
    trust_score = max(0.0, min(1.0, float(trust_score)))

    confidence = _coerce_float(confidence_proxy)
    confidence_norm = 0.5 if confidence is None else max(0.0, min(1.0, confidence / 100.0 if confidence > 1 else confidence))
    maturity_bonus = {"live_market": 0.15, "market_comp": 0.08, "proxy": 0.0}.get(pricing_maturity, 0.0)
    confidence_strength = max(0.0, min(1.0, (trust_score * 0.6) + (confidence_norm * 0.4) + maturity_bonus))

    spread = max(0.0, cap_value - bid_value)
    conservative_factor = max(0.05, 1.0 - (confidence_strength * 0.85))
    expected_close_bid = bid_value + (spread * conservative_factor)
    expected_close_bid = min(cap_value, max(bid_value, expected_close_bid))

    return {
        "expected_close_bid": round(expected_close_bid, 2),
        "expected_close_source": "confidence_adjusted_current_bid",
        "current_bid_trust_score": round(trust_score, 3),
        "auction_stage_hours_remaining": auction_stage_hours_remaining,
    }


def _normalize_pct(value: Optional[float], default: float) -> float:
    pct = _coerce_float(value)
    if pct is None:
        pct = default
    if pct > 1:
        pct /= 100.0
    return max(0.0, pct)


def _normalized_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _segment_score_v2(vehicle: dict) -> float:
    segment = _normalized_text(
        vehicle.get("segment_tier")
        or vehicle.get("segmentTier")
        or vehicle.get("segment")
        or vehicle.get("body_type")
        or vehicle.get("bodyType")
        or vehicle.get("body_class")
        or vehicle.get("bodyClass")
        or vehicle.get("vehicle_type")
    )
    if not segment:
        return 0.4

    high_value_segments = (
        "truck",
        "pickup",
        "suv",
        "crossover",
        "utility",
        "wagon",
    )
    medium_value_segments = (
        "sedan",
        "coupe",
        "hatchback",
        "car",
        "van",
        "minivan",
    )

    if any(token in segment for token in high_value_segments):
        return 1.0
    if any(token in segment for token in medium_value_segments):
        return 0.65
    return 0.4


def _model_score_v2(vehicle: dict) -> float:
    make = _normalized_text(vehicle.get("make"))
    model = _normalized_text(vehicle.get("model"))
    if not make and not model:
        return 0.4

    model_blob = f"{make} {model}".strip()
    if any(token in model_blob for token in HIGH_DEMAND_MODELS):
        return 1.0

    if model and model not in {"unknown", "other", "n/a", "na", "none", "null"}:
        return 0.65
    return 0.4


def _source_score_v2(vehicle: dict) -> float:
    """Source reliability score — government sources scored on same scale as others (DEA-2)."""
    source = _normalized_text(vehicle.get("source_site") or vehicle.get("source"))
    if not source:
        return 0.4
    # DEA-2: Gov sources no longer get a perfect 1.0; scored fairly alongside others
    if any(token in source for token in ("govdeals", "govplanet", "gsaauctions", "publicsurplus", "municibid")):
        return 0.75
    if any(token in source for token in ("hibid", "proxibid", "bidspotter", "allsurplus", "jjkane", "usgovbid")):
        return 0.65
    return 0.4


def _compute_margin_score_v2(gross_margin: float) -> float:
    if gross_margin >= 10000:
        return 1.0
    if gross_margin >= 7000:
        return 0.85
    if gross_margin >= 4000:
        return 0.7
    if gross_margin >= 2000:
        return 0.55
    if gross_margin >= 1500:
        return 0.45
    if gross_margin >= 500:
        return 0.35
    return 0.1


def _compute_dos_v2(vehicle: dict, gross_margin: float) -> float:
    margin_score = _compute_margin_score_v2(gross_margin)
    velocity_score = _auction_velocity_score(vehicle) / 100.0
    segment_score = _segment_score_v2(vehicle)
    model_score = _model_score_v2(vehicle)
    source_score = _source_score_v2(vehicle)
    dos = (
        margin_score * 0.35
        + velocity_score * 0.25
        + segment_score * 0.20
        + model_score * 0.12
        + source_score * 0.08
    ) * 100.0
    return round(_clamp(dos), 2)


def _compute_gross_margin_v2(
    mmr: float,
    bid: float,
    state: str = "",
    buyer_premium_pct: Optional[float] = None,
    auction_fees: Optional[float] = None,
) -> float:
    del state
    if mmr is None or mmr <= 0:
        return 0.0
    bid_value = _coerce_float(bid) or 0.0
    premium_pct = _normalize_pct(buyer_premium_pct, 0.05)
    buyer_premium_amount = round(bid_value * premium_pct, 2)
    fees = _coerce_float(auction_fees)
    auction_fees_amount = round(fees if fees is not None else 200.0, 2)
    return round(mmr - bid_value - buyer_premium_amount - auction_fees_amount, 2)


def _compute_max_bid_v2(
    mmr: float,
    bid: Optional[float] = None,
    state: str = "",
    buyer_premium_pct: Optional[float] = None,
    auction_fees: Optional[float] = None,
    tier: str = "premium",
) -> float:
    del state
    if mmr is None or mmr <= 0:
        return 0.0
    ceiling = 0.80 if tier == "standard" else 0.88
    bid_value = _coerce_float(bid) if bid is not None else mmr * ceiling
    if bid_value is None or bid_value <= 0:
        bid_value = mmr * ceiling
    premium_pct = _normalize_pct(buyer_premium_pct, 0.05)
    fees = _coerce_float(auction_fees)
    auction_fees_amount = round(fees if fees is not None else 200.0, 2)
    buyer_premium_amount = round(bid_value * premium_pct, 2)
    return round((mmr * ceiling) - buyer_premium_amount - auction_fees_amount, 2)


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
    buyer_premium_pct: Optional[float] = None,
    auction_fees: Optional[float] = None,
    fees_cfg: Optional[dict] = None,
    rates_cfg: Optional[dict] = None,
    miles_cfg: Optional[dict] = None,
) -> dict:
    """
    Primary DOS scoring function.
    Returns full scoring dict compatible with save_opportunity_to_supabase.
    """
    mmr = manheim_mmr_mid or mmr_ca or 0
    bid_value = _coerce_float(bid)
    vehicle_tier = determine_vehicle_tier(year, mileage)

    source_key = (source_site or "").strip() or "GovDeals"
    fee_lookup = fees_cfg.get(source_key) if isinstance(fees_cfg, dict) and source_key in fees_cfg else None
    if fee_lookup is None and isinstance(fees_cfg, dict):
        fee_lookup = fees_cfg.get(source_key.lower())
    if buyer_premium_pct is None and isinstance(fee_lookup, dict):
        buyer_premium_pct = fee_lookup.get("buyers_premium_pct") or fee_lookup.get("buyer_premium_pct")
    if auction_fees is None and isinstance(fee_lookup, dict):
        auction_fees = fee_lookup.get("doc_fee") or fee_lookup.get("auction_fees")

    transport = calc_transport_cost(state, rates_cfg=rates_cfg, miles_cfg=miles_cfg) if state else 350.0
    condition_grade = _compute_condition_grade(
        title=f"{year or ''} {make or ''} {model or ''}".strip(),
        description="",
        mileage=mileage or 0,
        year=year or 0,
        damage_type="",
    )
    recon_reserve = 650.0
    if is_police_or_fleet:
        recon_reserve += 300.0
    if bid_value is None or bid_value <= 0:
        buyer_premium_pct_value = _normalize_pct(buyer_premium_pct, 0.05)
        bid_ceiling_pct = 0.80 if vehicle_tier == "standard" else 0.88 if vehicle_tier == "premium" else None
        return {
            "dos_score": 0.0,
            "score": 0.0,
            "legacy_dos_score": 0.0,
            "score_version": "v3_two_lane",
            "mmr_estimated": mmr,
            "margin": 0.0,
            "gross_margin": 0.0,
            "wholesale_margin": 0.0,
            "buyer_premium_pct": buyer_premium_pct_value,
            "mmr_confidence_proxy": mmr_confidence_proxy,
            "buyer_premium_amount": 0.0,
            "auction_fees": 0.0,
            "retail_asking_price_estimate": 0.0,
            "retail_comp_price_estimate": retail_comp_price_estimate,
            "retail_comp_low": retail_comp_low,
            "retail_comp_high": retail_comp_high,
            "retail_comp_count": retail_comp_count or 0,
            "retail_comp_confidence": retail_comp_confidence,
            "pricing_source": pricing_source or mmr_lookup_basis or "mmr_proxy",
            "pricing_maturity": "proxy",
            "pricing_updated_at": pricing_updated_at,
            "expected_close_bid": 0.0,
            "expected_close_source": "zero_bid",
            "current_bid_trust_score": 0.0,
            "auction_stage_hours_remaining": None,
            "acquisition_price_basis": 0.0,
            "acquisition_basis_source": "zero_bid",
            "transport": transport,
            "recon_reserve": recon_reserve,
            "condition_grade": condition_grade,
            "total_cost": 0.0,
            "projected_total_cost": 0.0,
            "manheim_mmr_mid": manheim_mmr_mid,
            "manheim_mmr_low": manheim_mmr_low,
            "manheim_mmr_high": manheim_mmr_high,
            "manheim_range_width_pct": manheim_range_width_pct,
            "manheim_confidence": manheim_confidence,
            "manheim_source_status": manheim_source_status or "unavailable",
            "manheim_updated_at": manheim_updated_at,
            "retail_proxy_multiplier": 1.35,
            "wholesale_ctm_pct": None,
            "retail_ctm_pct": None,
            "ctm_pct": None,
            "estimated_days_to_sale": None,
            "roi_per_day": None,
            "roi_pct": 0.0,
            "investment_grade": "Rejected" if vehicle_tier == "rejected" else "Bronze",
            "bid_ceiling_pct": bid_ceiling_pct,
            "max_bid": 0.0,
            "bid_headroom": 0.0,
            "min_margin_target": 2500.0 if vehicle_tier == "standard" else 1500.0 if vehicle_tier == "premium" else None,
            "ceiling_reason": "zero_bid",
            "ceiling_pass": False,
            "designated_lane": vehicle_tier,
            "vehicle_tier": vehicle_tier,
            "dos_premium": 0.0,
            "dos_standard": 0.0,
            "risk_flags": compute_risk_flags(
                {
                    "bid": bid_value,
                    "current_bid": bid_value,
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
                },
                vehicle_tier,
            ),
            "ai_confidence_score": 0.0,
        }

    vehicle_proxy = {
        "bid": bid_value,
        "current_bid": bid_value,
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

    buyer_premium_pct_value = _normalize_pct(buyer_premium_pct, 0.05)
    buyer_premium_amount = round((bid_value or 0) * buyer_premium_pct_value, 2) if bid_value and bid_value > 0 else 0.0
    auction_fees_value = _coerce_float(auction_fees)
    auction_fees_amount = round(auction_fees_value if auction_fees_value is not None else 200.0, 2)
    gross_margin = round(mmr - bid_value - buyer_premium_amount - auction_fees_amount - transport - recon_reserve, 2) if mmr > 0 else 0.0
    wholesale_margin = gross_margin
    retail_price = retail_comp_price_estimate or (mmr * 1.35 if mmr > 0 else 0)

    if manheim_source_status == "live":
        pricing_maturity = "live_market"
    elif retail_comp_count and retail_comp_count > 0:
        pricing_maturity = "market_comp"
    else:
        pricing_maturity = "proxy"

    auction_stage_hours_remaining = _auction_stage_hours_remaining(auction_end)

    trust_score = _current_bid_trust_score(auction_stage_hours_remaining, pricing_maturity)

    bid_ceiling_pct = 0.80 if vehicle_tier == "standard" else 0.88
    max_bid = _compute_max_bid_v2(
        mmr,
        bid=bid_value,
        state=state,
        buyer_premium_pct=buyer_premium_pct_value,
        auction_fees=auction_fees,
        tier=vehicle_tier,
    )
    bid_headroom = max_bid - bid_value
    min_margin_target = 2500.0 if vehicle_tier == "standard" else 1500.0
    ceiling_pass = bid_value <= max_bid and gross_margin >= min_margin_target and vehicle_tier != "rejected"

    all_in_cost = bid_value + buyer_premium_amount + auction_fees_amount + transport + recon_reserve
    roi_pct = (gross_margin / all_in_cost * 100) if all_in_cost > 0 else 0
    if vehicle_tier == "rejected":
        investment_grade = "Rejected"
    elif selected_dos >= 80 and roi_pct >= 20 and ceiling_pass:
        investment_grade = "Platinum"
    elif selected_dos >= 65 and roi_pct >= 12 and ceiling_pass:
        investment_grade = "Gold"
    elif selected_dos >= 50 and ceiling_pass:
        investment_grade = "Silver"
    else:
        investment_grade = "Bronze"

    acquisition_price_basis = _round_price_basis(bid_value)
    ctm_pct = (bid_value / mmr) if mmr > 0 else None

    ai_confidence_score = round(
        _clamp((trust_score * 100.0 * 0.35) + ((100.0 - len(risk_flags) * 15.0) * 0.25) + (_condition_score(vehicle_proxy) * 0.40)),
        1,
    )

    # AI confidence gate — lane-aware thresholds
    # Premium >= 70, Standard >= 80
    # Note: standard max possible score on proxy pricing = (0.5*100*0.35)+(100*0.25)+(100*0.40) = 82.5
    # The prior threshold of 85 (tightened 2026-03-27) made it mathematically impossible
    # for standard-tier proxy-priced vehicles to pass, filtering ~458 legit deals/day.
    # Recalibrated to 80 on 2026-04-05 (Codex audit finding).
    ai_conf_threshold = 0.0
    if vehicle_tier == "premium":
        ai_conf_threshold = 70.0
    elif vehicle_tier == "standard":
        ai_conf_threshold = 80.0

    # Strong-structural-economics bypass: if bid is <=50% of max_bid (extreme headroom),
    # the deal economics are so compelling that a weak AI confidence score on proxy
    # pricing is not a meaningful signal — it just means no comps exist yet (early auction).
    # We still require ceiling_pass (bid <= max_bid, margin >= floor) to be True.
    _strong_structural = (
        ceiling_pass
        and max_bid > 0
        and bid_value > 0
        and (bid_value / max_bid) <= 0.50
    )
    ceiling_pass = ceiling_pass and (
        vehicle_tier == "rejected"
        or ai_confidence_score >= ai_conf_threshold
        or _strong_structural
    )

    return {
        "dos_score": selected_dos,
        "score": selected_dos,
        "legacy_dos_score": selected_dos,
        "score_version": "v3_two_lane",
        "mmr_estimated": mmr,
        "mmr_confidence_proxy": mmr_confidence_proxy,
        "margin": gross_margin,
        "gross_margin": gross_margin,
        "wholesale_margin": wholesale_margin,
        "buyer_premium_pct": buyer_premium_pct_value,
        "buyer_premium_amount": buyer_premium_amount,
        "auction_fees": auction_fees_amount,
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
        "transport": transport,
        "recon_reserve": recon_reserve,
        "condition_grade": condition_grade,
        "total_cost": all_in_cost,
        "projected_total_cost": all_in_cost,
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
        "roi_pct": roi_pct,
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
