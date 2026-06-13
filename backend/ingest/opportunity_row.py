"""Build Supabase opportunity rows from normalized/scored ingest vehicles.

Extracted from the FastAPI ingest router without changing row semantics. External
helpers are dependency-injected so the row builder stays pure and testable.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Optional

from backend.business_rules.gates import bid_ceiling_pct_for_tier, min_margin_for_tier
from backend.ingest.lifecycle_memory import build_initial_lifecycle_fields


def _resolve_buyer_premium(score_result: dict[str, Any], current_bid: float) -> tuple[float, float]:
    buyer_premium = score_result.get("buyer_premium_amount")
    if buyer_premium is None:
        buyer_premium = score_result.get("buyer_premium")
    if buyer_premium is None:
        buyer_premium = score_result.get("premium")
    if buyer_premium is None:
        buyer_premium = current_bid * 0.05

    buyer_premium_pct = score_result.get("buyer_premium_pct")
    if buyer_premium_pct is None:
        premium_basis = score_result.get("buyer_premium_amount")
        if premium_basis is None:
            premium_basis = score_result.get("buyer_premium")
        if premium_basis is None:
            premium_basis = score_result.get("premium")
        if premium_basis is not None and current_bid > 0:
            buyer_premium_pct = float(premium_basis) / current_bid
        else:
            buyer_premium_pct = 0.05
    else:
        buyer_premium_pct = float(buyer_premium_pct)
        if buyer_premium_pct > 1:
            buyer_premium_pct /= 100.0

    projected_buyer_premium = score_result.get("buyer_premium_amount")
    if projected_buyer_premium is None:
        projected_buyer_premium = score_result.get("buyer_premium")
    if projected_buyer_premium is None:
        projected_buyer_premium = score_result.get("premium")
    if projected_buyer_premium is not None:
        buyer_premium = round(float(projected_buyer_premium), 2)
    else:
        buyer_premium = round(current_bid * buyer_premium_pct, 2)

    return buyer_premium, buyer_premium_pct


def _resolve_photo_count(vehicle: dict[str, Any]) -> int:
    photos = vehicle.get("photos")
    if photos is None:
        photos = vehicle.get("photo_urls")

    if isinstance(photos, list):
        count = len([photo for photo in photos if photo])
        if count:
            return count
    if isinstance(photos, tuple):
        count = len([photo for photo in photos if photo])
        if count:
            return count
    if isinstance(photos, str) and photos.strip():
        return 1

    if vehicle.get("photo_url") or vehicle.get("image_url"):
        return 1
    return 0


def build_opportunity_row(
    vehicle: dict[str, Any],
    *,
    canonical_source_site: Callable[[Any], Optional[str]],
    compute_listing_id: Callable[[Optional[str], str], str],
    compute_condition_grade: Callable[..., Any],
    now_utc: Optional[Callable[[], datetime]] = None,
) -> dict[str, Any]:
    score_result = vehicle.get("score_breakdown", {})
    current_bid = float(vehicle.get("current_bid") or 0)
    source_site = canonical_source_site(vehicle.get("source_site") or vehicle.get("source")) or None
    buyer_premium, _buyer_premium_pct = _resolve_buyer_premium(score_result, current_bid)

    doc_fee = score_result.get("auction_fees")
    if doc_fee is None:
        doc_fee = score_result.get("doc_fee")
    if doc_fee is None:
        doc_fee = 200
    doc_fee = float(doc_fee)
    auction_fees = round(doc_fee, 2)
    condition_grade = compute_condition_grade(
        title=vehicle.get("title") or "",
        description=vehicle.get("description") or "",
        mileage=vehicle.get("mileage") or 0,
        year=vehicle.get("year") or 0,
        damage_type=vehicle.get("damage_type") or "",
    )
    pricing_source = score_result.get("pricing_source")
    pricing_maturity = score_result.get("pricing_maturity") or "unknown"
    vehicle_tier = score_result.get("vehicle_tier") or vehicle.get("vehicle_tier") or "unassigned"
    designated_lane = score_result.get("designated_lane") or vehicle.get("designated_lane") or vehicle_tier
    bid_ceiling_pct = score_result.get("bid_ceiling_pct")
    if bid_ceiling_pct is None:
        bid_ceiling_pct = bid_ceiling_pct_for_tier(vehicle_tier)
    min_margin_target = score_result.get("min_margin_target")
    if min_margin_target is None:
        min_margin_target = min_margin_for_tier(vehicle_tier)
    now = now_utc or (lambda: datetime.now(timezone.utc))
    now_iso = now().isoformat()
    row = {
        "listing_id": compute_listing_id(source_site, vehicle.get("listing_url") or ""),
        "listing_url": vehicle.get("listing_url", ""),
        "source": source_site,
        "source_site": source_site,
        "title": vehicle.get("title"),
        "year": vehicle.get("year"),
        "make": vehicle.get("make"),
        "model": vehicle.get("model"),
        "mileage": vehicle.get("mileage"),
        "state": vehicle.get("state"),
        "city": vehicle.get("city") or vehicle.get("location_city") or "",
        "vin": vehicle.get("vin"),
        "current_bid": vehicle.get("current_bid"),
        "mmr": score_result.get("mmr_estimated"),
        "estimated_transport": score_result.get("transport"),
        "buyer_premium": buyer_premium,
        "auction_fees": auction_fees,
        "recon_reserve": score_result.get("recon_reserve"),
        "total_cost": score_result.get("total_cost"),
        "projected_total_cost": score_result.get("projected_total_cost", score_result.get("total_cost")),
        "acquisition_price_basis": score_result.get("acquisition_price_basis"),
        "acquisition_basis_source": score_result.get("acquisition_basis_source"),
        "gross_margin": score_result.get("gross_margin", score_result.get("margin")),
        "retail_asking_price_estimate": score_result.get("retail_asking_price_estimate"),
        "retail_comp_price_estimate": score_result.get("retail_comp_price_estimate"),
        "retail_comp_low": score_result.get("retail_comp_low"),
        "retail_comp_high": score_result.get("retail_comp_high"),
        "retail_comp_count": score_result.get("retail_comp_count"),
        "retail_comp_confidence": score_result.get("retail_comp_confidence"),
        "pricing_source": pricing_source,
        "pricing_maturity": pricing_maturity,
        "pricing_updated_at": score_result.get("pricing_updated_at"),
        "expected_close_bid": score_result.get("expected_close_bid"),
        "current_bid_trust_score": score_result.get("current_bid_trust_score"),
        "expected_close_source": score_result.get("expected_close_source"),
        "auction_stage_hours_remaining": score_result.get("auction_stage_hours_remaining"),
        "manheim_mmr_mid": score_result.get("manheim_mmr_mid"),
        "manheim_mmr_low": score_result.get("manheim_mmr_low"),
        "manheim_mmr_high": score_result.get("manheim_mmr_high"),
        "manheim_range_width_pct": score_result.get("manheim_range_width_pct"),
        "manheim_confidence": score_result.get("manheim_confidence"),
        "manheim_source_status": score_result.get("manheim_source_status"),
        "manheim_updated_at": score_result.get("manheim_updated_at"),
        "retail_proxy_multiplier": score_result.get("retail_proxy_multiplier"),
        "dos_score": vehicle.get("dos_score"),
        "ctm_pct": score_result.get("ctm_pct"),
        "wholesale_ctm_pct": score_result.get("wholesale_ctm_pct"),
        "retail_ctm_pct": score_result.get("retail_ctm_pct"),
        "segment_tier": score_result.get("segment_tier"),
        "estimated_days_to_sale": score_result.get("estimated_days_to_sale"),
        "roi_per_day": score_result.get("roi_per_day"),
        "mmr_lookup_basis": score_result.get("mmr_lookup_basis"),
        "mmr_confidence_proxy": score_result.get("mmr_confidence_proxy"),
        "investment_grade": score_result.get("investment_grade"),
        "max_bid": score_result.get("max_bid"),
        "bid_headroom": score_result.get("bid_headroom"),
        "ceiling_reason": score_result.get("ceiling_reason"),
        "score_version": score_result.get("score_version"),
        "legacy_dos_score": score_result.get("legacy_dos_score"),
        "condition_grade": condition_grade,
        "auction_end_date": vehicle.get("auction_end_time"),
        "image_url": vehicle.get("photo_url"),
        "photo_count": _resolve_photo_count(vehicle),
        "designated_lane": designated_lane,
        "dos_premium": score_result.get("dos_premium"),
        "dos_standard": score_result.get("dos_standard"),
        "risk_flags": score_result.get("risk_flags") or vehicle.get("risk_flags") or [],
        "vehicle_tier": vehicle_tier,
        "bid_ceiling_pct": bid_ceiling_pct,
        "min_margin_target": min_margin_target,
        "raw_data": vehicle,
        "canonical_id": vehicle.get("canonical_id"),
        "is_duplicate": vehicle.get("is_duplicate", False),
        "canonical_record_id": vehicle.get("canonical_record_id"),
        "all_sources": vehicle.get("all_sources", []),
        "duplicate_count": vehicle.get("duplicate_count", 0),
        "run_id": vehicle.get("run_id"),
        "source_run_id": vehicle.get("source_run_id"),
        "pipeline_step": "saved",
        "step_status": "complete",
        "processed_at": vehicle.get("processed_at") or now_iso,
    }
    row.update(build_initial_lifecycle_fields(row, now_iso=now_iso))
    return row
