import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.ingest.manheim_market import get_manheim_market_data
from backend.ingest.alert_gating import AlertThresholds, evaluate_alert_gate
from backend.ingest.score import CURRENT_YEAR, determine_vehicle_tier, resolve_expected_close_bid, score_deal
from webapp.routers.ingest import _normalize_auction_end_time, normalize_apify_vehicle, passes_basic_gates, score_vehicle


def test_passes_basic_gates_rejects_title_brand_keywords():
    vehicle = {
        "title": "2024 Toyota Camry Salvage Title",
        "title_status": "clean",
        "vin": "4T1C11AK0RU000001",
        "make": "Toyota",
        "model": "Camry",
        "current_bid": 10000,
        "state": "CA",
        "year": 2024,
        "mileage": 25000,
        "listing_url": "https://example.com/vehicle/1",
        "source_site": "govdeals",
    }

    result = passes_basic_gates(vehicle)

    assert result["pass"] is False
    assert result["reason"] == "title_brand_rejected (listing_text matched 'salvage')"


def test_passes_basic_gates_checks_vin_for_title_brand_keywords():
    vehicle = {
        "title": "2024 Honda Accord",
        "vin": "FLOOD123456789XYZ",
        "make": "Honda",
        "model": "Accord",
        "current_bid": 10000,
        "state": "CA",
        "year": 2024,
        "mileage": 15000,
        "listing_url": "https://example.com/vehicle/2",
        "source_site": "govdeals",
    }

    result = passes_basic_gates(vehicle)

    assert result["pass"] is False
    assert result["reason"] == "title_brand_rejected (vin matched 'flood')"


def test_passes_basic_gates_rejects_zero_bid():
    vehicle = {
        "title": "2024 Toyota Camry",
        "vin": "4T1C11AK0RU000002",
        "make": "Toyota",
        "model": "Camry",
        "current_bid": 0,
        "state": "CA",
        "year": 2024,
        "mileage": 25000,
        "listing_url": "https://example.com/vehicle/zero-bid",
        "source_site": "govdeals",
    }

    result = passes_basic_gates(vehicle)

    assert result["pass"] is False
    assert result["reason"] == "bid_not_positive ($0)"


def test_passes_basic_gates_allows_positive_bid_when_other_rules_pass():
    vehicle = {
        "title": "2024 Toyota Camry",
        "vin": "4T1C11AK0RU000003",
        "make": "Toyota",
        "model": "Camry",
        "current_bid": 500,
        "state": "CA",
        "year": 2024,
        "mileage": 25000,
        "listing_url": "https://example.com/vehicle/positive-bid",
        "source_site": "publicsurplus",
    }

    result = passes_basic_gates(vehicle)

    assert result == {"pass": True, "reason": "ok"}


def test_normalize_apify_vehicle_keeps_percent_and_flat_fee_fields_separate():
    item = {
        "title": "2024 Toyota Camry",
        "currentBid": 10000,
        "meterCount": 25000,
        "locationState": "CA",
        "auctionEndUtc": "2026-03-26T18:00:00Z",
        "url": "https://example.com/lot/1",
        "seller": "Example Auctions",
        "buyer_premium_pct": "12.5",
        "buyers_premium_pct": "11.0",
        "buyer_premium": "1250",
        "doc_fee": "75",
        "auction_fees": "150",
    }

    normalized = normalize_apify_vehicle(item, run_id="run-1")

    assert normalized is not None
    assert normalized["buyer_premium_pct"] == 12.5
    assert normalized["buyer_premium"] == 1250.0
    assert normalized["doc_fee"] == 75.0
    assert normalized["auction_fees"] == 150.0


def test_normalize_apify_vehicle_reads_actor_end_date_alias():
    item = {
        "title": "2024 Toyota Camry",
        "current_bid": 10000,
        "mileage": 25000,
        "state": "CA",
        "auction_end_date": "2026-03-26T18:00:00.000Z",
        "listing_url": "https://example.com/lot/1",
        "source_site": "allsurplus",
    }

    normalized = normalize_apify_vehicle(item, run_id="run-1")

    assert normalized is not None
    assert normalized["auction_end_time"] == "2026-03-26T18:00:00+00:00"


def test_normalize_auction_end_time_handles_actor_iso_and_compact_relative_formats():
    reference = datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc)

    assert _normalize_auction_end_time("2026-03-26T18:00:00.000Z") == "2026-03-26T18:00:00+00:00"
    assert _normalize_auction_end_time("1d 2h", reference_dt=reference) == "2026-04-04T14:00:00+00:00"
    assert _normalize_auction_end_time("45:00", reference_dt=reference) == "2026-04-03T12:45:00+00:00"


def test_alert_gate_blocks_proxy_only_low_confidence_rows():
    record = {
        "dos_score": 85,
        "investment_grade": "Gold",
        "pricing_maturity": "proxy",
        "current_bid_trust_score": 0.5,
        "mmr_confidence_proxy": 45.0,
        "bid_headroom": 500,
        "roi_per_day": 80,
    }

    gate = evaluate_alert_gate(record, thresholds=AlertThresholds())

    assert gate["eligible"] is False
    assert "confidence<55" in gate["blocking_reasons"]


def test_score_deal_subtracts_recon_reserve_from_margin():
    result = score_deal(
        bid=10000,
        mmr_ca=20000,
        state="CA",
        source_site="GovDeals",
        model="Camry",
        make="Toyota",
        year=2024,
        mileage=50000,
        fees_cfg={"GovDeals": {"buyers_premium_pct": 10.0, "doc_fee": 50}},
        rates_cfg={"mileage_bands": [{"max_miles": 5000, "rate_per_mile": 1.0}]},
        miles_cfg={"CA": 100},
    )

    assert result["recon_reserve"] == 650.0
    assert result["transport"] == 350.0
    assert result["total_cost"] == 12050.0
    assert result["margin"] == 7950.0


def test_score_vehicle_adds_police_fleet_recon_buffer():
    vehicle = {
        "title": "2023 Ford Explorer Police Interceptor Utility",
        "agency_name": "City Fleet Services",
        "vin": "1FM5K8AR5PGA00001",
        "make": "Ford",
        "model": "Explorer Interceptor",
        "current_bid": 10000,
        "state": "CA",
        "year": 2023,
        "mileage": 50000,
        "listing_url": "https://example.com/vehicle/3",
        "source_site": "govdeals",
    }

    result = score_vehicle(vehicle)

    assert result["recon_reserve"] == 950.0
    assert result["manheim_source_status"] == "fallback"


def test_score_vehicle_boosts_govdeals_near_close_when_structurally_viable():
    vehicle = {
        "title": "2023 Toyota Camry LE",
        "agency_name": "City of Irvine",
        "vin": "4T1G11AK0PU000001",
        "make": "Toyota",
        "model": "Camry",
        "current_bid": 10000,
        "state": "CA",
        "year": 2023,
        "mileage": 25000,
        "listing_url": "https://example.com/vehicle/gd-near-close",
        "source_site": "govdeals",
        "auction_end_time": (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat(),
    }

    result = score_vehicle(vehicle)

    assert result["ceiling_pass"] is True
    assert result["ceiling_reason"] == "govdeals_live_bid_near_close"
    assert float(result["current_bid_trust_score"]) >= 0.85
    assert result["pricing_maturity"] == "market_comp"


def test_manheim_market_data_uses_proxy_fallback_without_live_config(monkeypatch):
    monkeypatch.delenv("MANHEIM_MARKET_DATA_URL", raising=False)
    result = get_manheim_market_data(
        year=2024,
        make="Toyota",
        model="Camry",
        state="CA",
        mileage=12000,
        proxy_mmr=20000,
        proxy_basis="model:camry",
        proxy_confidence=90.0,
    )

    assert result["manheim_source_status"] == "fallback"
    assert result["manheim_mmr_mid"] == 20000.0
    assert result["manheim_mmr_low"] < result["manheim_mmr_mid"] < result["manheim_mmr_high"]


def test_score_deal_uses_premium_lane_defaults_for_recent_vehicle():
    result = score_deal(
        bid=10000,
        mmr_ca=20000,
        state="CA",
        source_site="GovDeals",
        model="Camry",
        make="Toyota",
        year=2024,
        mileage=20000,
        fees_cfg={"GovDeals": {"buyers_premium_pct": 10.0, "doc_fee": 50}},
        rates_cfg={"mileage_bands": [{"max_miles": 5000, "rate_per_mile": 1.0}]},
        miles_cfg={"CA": 100},
        manheim_mmr_mid=20000,
        manheim_mmr_low=18000,
        manheim_mmr_high=22000,
        manheim_range_width_pct=20.0,
        manheim_confidence=0.82,
        manheim_source_status="live",
    )

    assert result["vehicle_tier"] == "premium"
    assert result["bid_ceiling_pct"] == 0.88
    assert result["min_margin_target"] == 1500.0
    assert result["ceiling_pass"] is True


def test_determine_vehicle_tier_enforces_age_and_mileage_hard_stops():
    assert determine_vehicle_tier(CURRENT_YEAR - 4, 50000) == "premium"
    assert determine_vehicle_tier(CURRENT_YEAR - 4, 50001) == "rejected"
    assert determine_vehicle_tier(CURRENT_YEAR - 5, 90000) == "standard"
    assert determine_vehicle_tier(CURRENT_YEAR - 5, 90001) == "rejected"
    assert determine_vehicle_tier(CURRENT_YEAR - 5, 100001) == "rejected"
    assert determine_vehicle_tier(CURRENT_YEAR - 11, 10000) == "rejected"
    assert determine_vehicle_tier(None, 10000) == "rejected"


def test_score_deal_uses_lane_specific_ceiling_and_margin_floor():
    standard = score_deal(
        bid=7000,
        mmr_ca=10000,
        state="CA",
        source_site="GovDeals",
        model="Camry",
        make="Toyota",
        year=CURRENT_YEAR - 5,
        mileage=30000,
    )

    premium = score_deal(
        bid=7000,
        mmr_ca=10000,
        state="CA",
        source_site="GovDeals",
        model="Camry",
        make="Toyota",
        year=CURRENT_YEAR - 2,
        mileage=30000,
    )

    assert standard["vehicle_tier"] == "standard"
    assert standard["bid_ceiling_pct"] == 0.8
    assert standard["max_bid"] == 7450.0
    assert standard["min_margin_target"] == 2500.0
    assert standard["ceiling_pass"] is False

    assert premium["vehicle_tier"] == "premium"
    assert premium["bid_ceiling_pct"] == 0.88
    assert premium["max_bid"] == 8250.0
    assert premium["min_margin_target"] == 1500.0
    assert premium["ceiling_pass"] is False
    assert premium["ai_confidence_score"] < 70


def test_score_deal_keeps_weak_retail_evidence_on_proxy_path():
    result = score_deal(
        bid=10000,
        mmr_ca=20000,
        state="CA",
        source_site="GovDeals",
        model="Camry",
        make="Toyota",
        year=2024,
        mileage=20000,
        fees_cfg={"GovDeals": {"buyers_premium_pct": 10.0, "doc_fee": 50}},
        rates_cfg={"mileage_bands": [{"max_miles": 5000, "rate_per_mile": 1.0}]},
        miles_cfg={"CA": 100},
        mmr_lookup_basis="model:camry",
        mmr_confidence_proxy=90.0,
        retail_comp_price_estimate=27000,
        retail_comp_count=1,
        retail_comp_confidence=0.55,
        pricing_source="retail_market_cache",
    )

    assert result["pricing_source"] == "retail_market_cache"
    assert result["pricing_maturity"] == "market_comp"
    assert result["retail_proxy_multiplier"] is not None
    assert result["retail_asking_price_estimate"] == 27000
    assert result["mmr_confidence_proxy"] == 90.0


def test_expected_close_gets_more_conservative_when_confidence_is_weak():
    low_confidence = resolve_expected_close_bid(
        current_bid=10000,
        max_bid=15000,
        current_bid_trust_score=0.2,
        auction_stage_hours_remaining=36,
        pricing_maturity="proxy",
        confidence_proxy=35.0,
    )
    high_confidence = resolve_expected_close_bid(
        current_bid=10000,
        max_bid=15000,
        current_bid_trust_score=0.2,
        auction_stage_hours_remaining=36,
        pricing_maturity="proxy",
        confidence_proxy=85.0,
    )

    assert low_confidence["expected_close_bid"] >= high_confidence["expected_close_bid"]
    assert low_confidence["expected_close_bid"] > 10000


# ─────────────────────────────────────────────────────────────
# _auction_stage_hours_remaining — must be importable and correct
# ─────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────
# _auction_stage_hours_remaining — must be importable and correct
# ─────────────────────────────────────────────────────────────
# Regression: function must exist as a standalone export in score.py.
# The near-close trust boost in ingest.py silently broke when this
# function was not exported — auction_stage_hours_remaining stayed
# None forever, so govdeals/govplanet/gsaauctions/proxibid/hibid
# near-close trust boost NEVER fired.

from backend.ingest.score import _auction_stage_hours_remaining


def test_auction_hours_remaining_importable():
    """Must be importable directly — ingest.py relies on this."""
    assert callable(_auction_stage_hours_remaining)


def test_auction_hours_remaining_future():
    future = (datetime.now(timezone.utc) + timedelta(hours=18)).isoformat()
    result = _auction_stage_hours_remaining(future)
    assert result is not None
    assert result > 0
    assert abs(result - 18.0) < 0.1


def test_auction_hours_remaining_past_returns_none():
    past = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    assert _auction_stage_hours_remaining(past) is None, "past time must return None"


def test_auction_hours_remaining_none_input():
    assert _auction_stage_hours_remaining(None) is None


def test_auction_hours_remaining_garbage_input():
    assert _auction_stage_hours_remaining("not-a-date") is None


def test_auction_hours_remaining_within_24h():
    close_in_12h = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
    result = _auction_stage_hours_remaining(close_in_12h)
    assert result is not None
    assert result <= 24


def test_auction_hours_remaining_far_future_above_24h():
    far = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    result = _auction_stage_hours_remaining(far)
    assert result is not None
    assert result > 24
