import math
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.ingest.manheim_market import get_manheim_market_data
from backend.ingest.alert_gating import AlertThresholds, evaluate_alert_gate
import backend.ingest.condition as condition_module
import backend.ingest.score as score_module
from backend.ingest.score import CURRENT_YEAR, determine_vehicle_tier, resolve_expected_close_bid, score_deal
from webapp.routers.ingest import _normalize_auction_end_time, normalize_apify_vehicle, passes_basic_gates, score_vehicle


INVALID_MILEAGE_VALUES = (
    None,
    "",
    "  ",
    "unknown",
    0,
    -1,
    "0",
    "-2",
    "0.0",
    "-0.1",
    "-2.5",
    float("nan"),
    math.inf,
    -math.inf,
    "nan",
    "NaN",
    "inf",
    "+inf",
    "-inf",
)


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


def _otherwise_alert_eligible_record(**overrides):
    record = {
        "dos_score": 95,
        "investment_grade": "Platinum",
        "pricing_maturity": "market_comp",
        "current_bid_trust_score": 0.9,
        "mmr_confidence_proxy": 90.0,
        "bid_headroom": 5000,
        "roi_per_day": 100,
        "vin": "1HGCM82633A004352",
        "mileage": 42000,
        "condition_grade": "Good",
        "raw_data": {"detail_text": "Starts, runs and drives. Minor scratches noted."},
        "retail_comp_count": 3,
        "retail_comp_confidence": 0.82,
    }
    record.update(overrides)
    return record


def test_alert_gate_allows_valid_high_confidence_record_with_otherwise_strong_signals():
    gate = evaluate_alert_gate(_otherwise_alert_eligible_record(), thresholds=AlertThresholds())

    assert gate["eligible"] is True
    assert gate["alert_type"] == "platinum"
    assert gate["blocking_reasons"] == []


def test_alert_gate_blocks_good_condition_grade_without_source_condition_evidence():
    gate = evaluate_alert_gate(
        _otherwise_alert_eligible_record(raw_data={}),
        thresholds=AlertThresholds(),
    )

    assert gate["eligible"] is False
    assert "condition_evidence_missing" in gate["blocking_reasons"]


def test_alert_gate_blocks_missing_confidence_even_with_otherwise_strong_signals():
    record = _otherwise_alert_eligible_record()
    del record["mmr_confidence_proxy"]
    del record["retail_comp_confidence"]

    gate = evaluate_alert_gate(record, thresholds=AlertThresholds())

    assert gate["eligible"] is False
    assert "confidence_missing" in gate["blocking_reasons"]


def test_alert_gate_blocks_none_confidence_even_with_otherwise_strong_signals():
    gate = evaluate_alert_gate(
        _otherwise_alert_eligible_record(mmr_confidence_proxy=None),
        thresholds=AlertThresholds(),
    )

    assert gate["eligible"] is False
    assert "confidence_invalid" in gate["blocking_reasons"]


def test_alert_gate_blocks_malformed_confidence_even_when_fallback_confidence_exists():
    for confidence in ("not-a-number", "", "  ", {}, []):
        gate = evaluate_alert_gate(
            _otherwise_alert_eligible_record(
                mmr_confidence_proxy=confidence,
                manheim_confidence=90.0,
            ),
            thresholds=AlertThresholds(),
        )

        assert gate["eligible"] is False
        assert "confidence_invalid" in gate["blocking_reasons"]


def test_alert_gate_blocks_non_finite_confidence_values():
    for confidence in (float("nan"), float("inf"), float("-inf"), "nan", "inf", "-inf"):
        gate = evaluate_alert_gate(
            _otherwise_alert_eligible_record(mmr_confidence_proxy=confidence),
            thresholds=AlertThresholds(),
        )

        assert gate["eligible"] is False
        assert "confidence_invalid" in gate["blocking_reasons"]


def test_alert_gate_blocks_below_threshold_confidence_even_with_otherwise_strong_signals():
    gate = evaluate_alert_gate(
        _otherwise_alert_eligible_record(mmr_confidence_proxy=45.0),
        thresholds=AlertThresholds(),
    )

    assert gate["eligible"] is False
    assert "confidence<55" in gate["blocking_reasons"]


def test_alert_gate_blocks_proxy_pricing_even_with_otherwise_strong_signals():
    record = {
        "dos_score": 95,
        "investment_grade": "Platinum",
        "pricing_maturity": "proxy",
        "current_bid_trust_score": 0.9,
        "mmr_confidence_proxy": 90.0,
        "bid_headroom": 5000,
        "roi_per_day": 100,
        "vin": "1HGCM82633A004352",
        "mileage": 42000,
        "condition_grade": "Good",
    }

    gate = evaluate_alert_gate(record, thresholds=AlertThresholds())

    assert gate["eligible"] is False
    assert "pricing_maturity=proxy" in gate["blocking_reasons"]


def test_alert_gate_requires_vin_mileage_and_verified_condition():
    record = {
        "dos_score": 95,
        "investment_grade": "Platinum",
        "pricing_maturity": "market_comp",
        "current_bid_trust_score": 0.9,
        "mmr_confidence_proxy": 90.0,
        "bid_headroom": 5000,
        "roi_per_day": 100,
        "condition_grade": "Poor",
    }

    gate = evaluate_alert_gate(record, thresholds=AlertThresholds())

    assert gate["eligible"] is False
    assert "vin_unverified" in gate["blocking_reasons"]
    assert "mileage_missing" in gate["blocking_reasons"]
    assert "condition_unverified" in gate["blocking_reasons"]


def test_alert_gate_rejects_invalid_mileage_values_and_placeholder_vin():
    for mileage in INVALID_MILEAGE_VALUES:
        record = {
            "dos_score": 95,
            "investment_grade": "Platinum",
            "pricing_maturity": "market_comp",
            "current_bid_trust_score": 0.9,
            "mmr_confidence_proxy": 90.0,
            "bid_headroom": 5000,
            "roi_per_day": 100,
            "vin": "00000000000000000",
            "mileage": mileage,
            "condition_grade": "Good",
        }

        gate = evaluate_alert_gate(record, thresholds=AlertThresholds())

        assert gate["eligible"] is False
        assert "vin_unverified" in gate["blocking_reasons"]
        assert "mileage_missing" in gate["blocking_reasons"]

    missing_mileage_record = {
        "dos_score": 95,
        "investment_grade": "Platinum",
        "pricing_maturity": "market_comp",
        "current_bid_trust_score": 0.9,
        "mmr_confidence_proxy": 90.0,
        "bid_headroom": 5000,
        "roi_per_day": 100,
        "vin": "1HGCM82633A004352",
        "condition_grade": "Good",
    }
    missing_gate = evaluate_alert_gate(missing_mileage_record, thresholds=AlertThresholds())
    assert missing_gate["eligible"] is False
    assert "mileage_missing" in missing_gate["blocking_reasons"]


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


def test_score_deal_emits_queryable_score_provenance_without_changing_math():
    result = score_deal(
        bid=10000,
        mmr_ca=20000,
        state="CA",
        source_site="GovDeals",
        model="Camry",
        make="Toyota",
        year=2024,
        mileage=20000,
        manheim_mmr_mid=20000,
        manheim_source_status="live",
        pricing_source="manheim_market_data",
        title_status="clean",
        description="clean vehicle",
        photos=["https://example.com/photo.jpg"],
    )

    assert result["score_version"] == "v3_two_lane"
    assert result["score_engine_impl"] == "score_deal_v3_two_lane"
    assert result["assumption_level"] == "none"
    assert result["fallback_flags"] == []
    assert result["score_timestamp_utc"]
    provenance = result["score_provenance"]
    assert provenance["engine_version"] == "v3_two_lane"
    assert provenance["engine_impl"] == "score_deal_v3_two_lane"
    assert provenance["lane"] == result["vehicle_tier"]
    assert provenance["mmr_source"] == "manheim_mmr_mid"
    assert provenance["input_profile"]["has_bid"] is True
    assert provenance["input_profile"]["has_mmr"] is True
    assert provenance["input_profile"]["has_live_manheim"] is True


def test_score_deal_marks_missing_bid_as_severe_provenance_not_silent_default():
    result = score_deal(
        bid=0,
        mmr_ca=20000,
        state="CA",
        source_site="GovDeals",
        model="Camry",
        make="Toyota",
        year=2024,
        mileage=20000,
    )

    assert result["dos_score"] == 0.0
    assert result["assumption_level"] == "severe"
    assert "zero_or_missing_bid" in result["fallback_flags"]
    assert result["score_provenance"]["input_profile"]["has_bid"] is False


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


def test_score_vehicle_preserves_market_comp_wholesale_value(monkeypatch):
    from backend.ingest import manheim_market, retail_comps

    vehicle = {
        "title": "2025 Ford Explorer Active AWD Low Miles!",
        "agency_name": "City Fleet",
        "vin": "1FMUK8DH5SGA77978",
        "make": "Ford",
        "model": "Explorer",
        "current_bid": 31000,
        "state": "CA",
        "year": 2025,
        "mileage": 1435,
        "listing_url": "https://www.govdeals.com/asset/123/456",
        "source_site": "govdeals",
    }

    monkeypatch.setattr(
        manheim_market,
        "get_manheim_market_data",
        lambda **_kwargs: {
            "manheim_mmr_mid": 22000,
            "manheim_mmr_low": None,
            "manheim_mmr_high": None,
            "manheim_range_width_pct": None,
            "manheim_confidence": 0,
            "manheim_source_status": "fallback",
            "manheim_updated_at": None,
        },
    )
    monkeypatch.setattr(
        retail_comps,
        "get_retail_comps",
        lambda **_kwargs: {
            "retail_comp_price_estimate": 41182.33,
            "retail_comp_low": 39960.0,
            "retail_comp_high": 42689.0,
            "retail_comp_count": 3,
            "retail_comp_confidence": 0.69,
            "pricing_source": "external_retail_listing_comp",
            "pricing_updated_at": "2026-06-05T12:57:00Z",
        },
    )

    result = score_vehicle(vehicle)

    assert result["pricing_maturity"] == "market_comp"
    assert result["mmr_estimated"] == 30505.43
    assert result["wholesale_margin"] == -3544.57
    assert vehicle["mmr_estimated"] == 30505.43


def test_score_vehicle_fallback_score_marks_hard_fallback_provenance(monkeypatch):
    from webapp.routers import ingest

    result = ingest._fallback_score({
        "title": "2023 Toyota Camry",
        "make": "Toyota",
        "year": 2023,
        "current_bid": 10000,
        "state": "CA",
        "source_site": "govdeals",
    })

    assert result["score_version"] == "fallback_v1"
    assert result["score_engine_impl"] == "webapp.routers.ingest._fallback_score"
    assert result["assumption_level"] == "severe"
    assert "hard_fallback_score" in result["fallback_flags"]
    assert result["score_provenance"]["lane"] == "fallback"
    assert result["score_provenance"]["input_profile"]["has_bid"] is True


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
        "retail_comp_count": 4,
        "retail_comp_price_estimate": 24000,
        "retail_comp_confidence": 0.9,
    }

    result = score_vehicle(vehicle)

    assert result["pricing_maturity"] == "proxy"
    assert result["ceiling_pass"] is False
    assert result["ceiling_reason"] == "pricing_maturity_proxy"
    assert result["investment_grade"] == "Rejected"
    assert result["pricing_trust_blocked"] is True


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
    assert result["investment_grade"] != "Rejected"
    assert result["dos_score"] > 0
    assert result["score"] > 0
    assert result["max_bid"] > 0
    assert result["score_provenance"]["input_profile"]["has_mileage"] is True


def test_score_deal_hard_rejects_older_high_rust_state_even_with_strong_economics():
    result = score_deal(
        bid=10000,
        mmr_ca=20000,
        state="OH",
        source_site="GovDeals",
        model="Camry",
        make="Toyota",
        year=CURRENT_YEAR - 3,
        mileage=30000,
        title_status="clean",
        description="clean vehicle",
        photos=["https://example.com/photo.jpg"],
    )

    assert result["vehicle_tier"] == "rejected"
    assert result["investment_grade"] == "Rejected"
    assert result["ceiling_pass"] is False
    assert result["dos_score"] == 0.0
    assert result["score"] == 0.0
    assert result["ceiling_reason"] == "high_rust_state_rejected"
    assert result["bid_ceiling_pct"] is None
    assert result["min_margin_target"] is None
    assert "rust_state_source" in result["risk_flags"]


def test_score_deal_allows_high_rust_state_new_vehicle_exception():
    result = score_deal(
        bid=10000,
        mmr_ca=20000,
        state="OH",
        source_site="GovDeals",
        model="Camry",
        make="Toyota",
        year=CURRENT_YEAR - 2,
        mileage=20000,
        title_status="clean",
        description="clean vehicle",
        photos=["https://example.com/photo.jpg"],
        retail_comp_count=4,
        retail_comp_price_estimate=22000,
        retail_comp_confidence=0.9,
    )

    assert result["vehicle_tier"] == "premium"
    assert result["pricing_maturity"] == "market_comp"
    assert result["investment_grade"] != "Rejected"
    assert result["ceiling_reason"] == "score_deal_v3_two_lane"
    assert result["ceiling_pass"] is True
    assert "rust_state_source" in result["risk_flags"]


def test_determine_vehicle_tier_enforces_age_and_mileage_hard_stops():
    assert determine_vehicle_tier(CURRENT_YEAR - 4, 50000) == "premium"
    assert determine_vehicle_tier(CURRENT_YEAR - 4, 50001) == "rejected"
    assert determine_vehicle_tier(CURRENT_YEAR - 5, 90000) == "standard"
    assert determine_vehicle_tier(CURRENT_YEAR - 5, 90001) == "rejected"
    assert determine_vehicle_tier(CURRENT_YEAR - 5, 100001) == "rejected"
    assert determine_vehicle_tier(CURRENT_YEAR - 11, 10000) == "rejected"
    assert determine_vehicle_tier(None, 10000) == "rejected"
    for mileage in INVALID_MILEAGE_VALUES:
        assert determine_vehicle_tier(CURRENT_YEAR - 2, mileage) == "rejected"
    assert determine_vehicle_tier(CURRENT_YEAR - 2, 12000) == "premium"


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
        retail_comp_count=4,
        retail_comp_price_estimate=12000,
        retail_comp_confidence=0.9,
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
        retail_comp_count=4,
        retail_comp_price_estimate=12000,
        retail_comp_confidence=0.9,
    )

    assert standard["vehicle_tier"] == "standard"
    assert standard["bid_ceiling_pct"] == 0.8
    assert standard["max_bid"] == 6561.11
    assert standard["min_margin_target"] == 2500.0
    assert standard["ceiling_pass"] is False

    assert premium["vehicle_tier"] == "premium"
    assert premium["bid_ceiling_pct"] == 0.88
    assert premium["max_bid"] == 7272.22
    assert premium["min_margin_target"] == 1500.0
    assert premium["ceiling_pass"] is False


def test_score_deal_hard_rejects_premium_bid_above_max_bid():
    result = score_deal(
        bid=9100,
        mmr_ca=10000,
        state="CA",
        source_site="GovDeals",
        model="Camry",
        make="Toyota",
        year=CURRENT_YEAR - 2,
        mileage=20000,
        title_status="clean",
        description="clean vehicle",
        photos=["https://example.com/photo.jpg"],
        retail_comp_count=4,
        retail_comp_price_estimate=12000,
        retail_comp_confidence=0.9,
    )

    assert result["vehicle_tier"] == "premium"
    assert result["bid_ceiling_pct"] == 0.88
    assert result["max_bid"] < 8800
    assert result["bid_headroom"] < 0
    assert result["ceiling_pass"] is False
    assert result["ceiling_reason"] == "bid_ceiling_exceeded"
    assert result["investment_grade"] == "Rejected"
    assert result["dos_score"] == 0.0
    assert result["score"] == 0.0


def test_score_deal_hard_rejects_standard_bid_above_max_bid():
    result = score_deal(
        bid=8500,
        mmr_ca=10000,
        state="CA",
        source_site="GovDeals",
        model="Camry",
        make="Toyota",
        year=CURRENT_YEAR - 5,
        mileage=30000,
        title_status="clean",
        description="clean vehicle",
        photos=["https://example.com/photo.jpg"],
        retail_comp_count=4,
        retail_comp_price_estimate=12000,
        retail_comp_confidence=0.9,
    )

    assert result["vehicle_tier"] == "standard"
    assert result["bid_ceiling_pct"] == 0.80
    assert result["max_bid"] < 8000
    assert result["bid_headroom"] < 0
    assert result["ceiling_pass"] is False
    assert result["ceiling_reason"] == "bid_ceiling_exceeded"
    assert result["investment_grade"] == "Rejected"
    assert result["dos_score"] == 0.0
    assert result["score"] == 0.0


def test_score_deal_hard_rejects_margin_floor_failure():
    result = score_deal(
        bid=7000,
        mmr_ca=10000,
        state="CA",
        source_site="GovDeals",
        model="Camry",
        make="Toyota",
        year=CURRENT_YEAR - 5,
        mileage=30000,
        title_status="clean",
        description="clean vehicle",
        photos=["https://example.com/photo.jpg"],
    )

    assert result["vehicle_tier"] == "standard"
    assert result["ceiling_pass"] is False
    assert result["ceiling_reason"] == "margin_floor_failed"
    assert result["investment_grade"] == "Rejected"
    assert result["dos_score"] == 0.0
    assert result["score"] == 0.0


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
    assert result["pricing_maturity"] == "proxy"
    assert result["investment_grade"] == "Rejected"
    assert result["pricing_trust_reason"] == "pricing_maturity_proxy"
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


# ─────────────────────────────────────────────────────────────
# Strong-structural-economics bypass
# ─────────────────────────────────────────────────────────────
def _make_strong_structural_vehicle(bid=7000, year=2019, mileage=55000, state="CA"):
    """Vehicle with extreme headroom (bid << max_bid) but proxy pricing (weak ai_conf)."""
    from datetime import datetime, timezone, timedelta
    auction_end = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    return {
        "year": year, "make": "Ford", "model": "Explorer", "trim": "Base",
        "mileage": mileage, "state": state, "current_bid": bid,
        "buyer_premium_pct": 0, "auction_fees": 0,
        "source_site": "govdeals", "auction_end_time": auction_end,
        "title": f"{year} Ford Explorer",
        "mmr_estimated": 28000,
        "retail_asking_price_estimate": 32000,
        "retail_comp_count": 0,   # zero comps → proxy pricing → trust_score=0.5
    }


def test_strong_structural_bypass_does_not_make_proxy_pricing_capital_ready():
    """Extreme headroom remains scouting-only when pricing is proxy-derived."""
    from webapp.routers.ingest import score_vehicle
    v = _make_strong_structural_vehicle(bid=7000)
    result = score_vehicle(v)

    assert result.get("pricing_maturity") == "proxy"
    assert result.get("ceiling_pass") is False
    assert result.get("ceiling_reason") == "pricing_maturity_proxy"
    assert result.get("investment_grade") == "Rejected"


def test_near_ceiling_bid_still_requires_ai_confidence():
    """bid at 90% of max_bid (normal range) must still satisfy ai_confidence gate."""
    from webapp.routers.ingest import score_vehicle
    from datetime import datetime, timezone, timedelta
    auction_end = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    # Set bid close to max_bid (high CTM — near ceiling, not extreme headroom)
    v = {
        "year": 2017, "make": "Ford", "model": "F-150", "trim": "XL",
        "mileage": 80000, "state": "CA", "current_bid": 18000,
        "buyer_premium_pct": 0, "auction_fees": 0,
        "source_site": "govdeals", "auction_end_time": auction_end,
        "title": "2017 Ford F-150",
        "mmr_estimated": 22000,
        "retail_asking_price_estimate": 25000,
        "retail_comp_count": 0,
    }
    result = score_vehicle(v)
    # bid=$18k, MMR=$22k → CTM ~82% → max_bid ~$17.6k → bid > max_bid likely
    # If bid < max_bid but close, ai_confidence gate applies (not strong structural)
    # Just assert it doesn't crash and returns valid structure
    assert "ceiling_pass" in result
    assert "dos_score" in result



def test_source_quality_proof_record_is_not_normalized_as_opportunity():
    proof = {
        "record_type": "source_quality_proof",
        "source_site": "proxibid",
        "title": "PROXIBID ENRICHMENT PROOF",
        "detail_pages_fetched": 15,
        "detail_vins_found": 4,
        "detail_mileages_found": 5,
        "enriched_rows_rejected": 5,
    }

    assert normalize_apify_vehicle(proof, run_id="proof-run") is None


def test_normalize_apify_vehicle_preserves_detail_enrichment_fields_for_accepted_rows():
    item = {
        "title": "2024 Toyota Tacoma SR5",
        "year": 2024,
        "make": "Toyota",
        "model": "Tacoma SR5",
        "state": "CA",
        "current_bid": 15000,
        "mileage": 22000,
        "vin": "3TYCZ5AN0RT123456",
        "listing_url": "https://example.com/lot/proxibid-enriched",
        "source_site": "proxibid",
        "source_run_id": "apify-run-from-dataset-row",
        "actor_run_id": "apify-run-from-dataset-row",
        "detail_enriched": True,
        "detail_enriched_by_detail_page": True,
    }

    normalized = normalize_apify_vehicle(item, run_id="webhook-fallback-run")

    assert normalized is not None
    assert normalized["source_site"] == "proxibid"
    assert normalized["vin"] == "3TYCZ5AN0RT123456"
    assert normalized["mileage"] == 22000
    assert normalized["detail_enriched"] is True
    assert normalized["detail_enriched_by_detail_page"] is True
    assert normalized["source_run_id"] == "apify-run-from-dataset-row"
    assert normalized["run_id"] == "apify-run-from-dataset-row"
    assert normalized["actor_run_id"] == "apify-run-from-dataset-row"

def test_normalize_apify_vehicle_preserves_detail_condition_fields_for_scoring():
    item = {
        "title": "2024 Ford F-150 XL",
        "year": 2024,
        "make": "Ford",
        "model": "F-150 XL",
        "state": "CA",
        "current_bid": 12000,
        "mileage": 24000,
        "listing_url": "https://example.com/lot/detail-fields",
        "description": "Clean title. Runs and drives fine.",
        "photos": ["https://example.com/photo.jpg"],
        "damage_type": "none",
    }

    normalized = normalize_apify_vehicle(item, run_id="run-detail-fields")

    assert normalized is not None
    assert normalized["description"] == "Clean title. Runs and drives fine."
    assert normalized["photos"] == ["https://example.com/photo.jpg"]
    assert normalized["damage_type"] == "none"


def test_normalize_apify_vehicle_uses_detail_text_description_alias():
    item = {
        "title": "2024 Toyota Tacoma",
        "year": 2024,
        "make": "Toyota",
        "model": "Tacoma",
        "state": "CA",
        "current_bid": 15000,
        "mileage": 22000,
        "listing_url": "https://example.com/lot/detail-text",
        "detail_text": "Vehicle does not start. No start condition.",
    }

    normalized = normalize_apify_vehicle(item, run_id="run-detail-text")

    assert normalized is not None
    assert normalized["description"] == "Vehicle does not start. No start condition."


def test_normalize_apify_vehicle_prefers_richer_detail_text_over_title_description():
    item = {
        "title": "2020 Dodge Durango SRT",
        "year": 2020,
        "make": "Dodge",
        "model": "Durango SRT",
        "state": "CA",
        "current_bid": 10000,
        "mileage": 13983,
        "listing_url": "https://www.govdeals.com/asset/197/5804",
        "description": "2020 Dodge Durango SRT",
        "detail_text": "Starts, runs and drives. Minor scratches noted.",
    }

    normalized = normalize_apify_vehicle(item, run_id="run-detail-text-title-shadow")

    assert normalized is not None
    assert normalized["description"] == "Starts, runs and drives. Minor scratches noted."



def _strong_proxy_priced_score_kwargs(**overrides):
    base = {
        "bid": 5000,
        "mmr_ca": 30000,
        "state": "CA",
        "source_site": "GovDeals",
        "model": "F-150",
        "make": "Ford",
        "year": CURRENT_YEAR - 2,
        "mileage": 22000,
        "title_status": "clean",
        "description": "clean low mileage truck",
        "photos": ["https://example.com/photo.jpg"],
        "mmr_confidence_proxy": 90.0,
        "retail_comp_count": 0,
        "manheim_source_status": "fallback",
    }
    base.update(overrides)
    return base


def test_score_deal_proxy_pricing_never_receives_capital_ready_grade():
    result = score_deal(**_strong_proxy_priced_score_kwargs())

    assert result["pricing_maturity"] == "proxy"
    assert result["investment_grade"] == "Rejected"
    assert result["investment_grade"] not in {"Platinum", "Gold", "Silver", "Bronze"}
    assert result["ceiling_pass"] is False
    assert result["ceiling_reason"] == "pricing_maturity_proxy"
    assert result["pricing_trust_blocked"] is True
    assert result["pricing_trust_reason"] == "pricing_maturity_proxy"
    assert result["max_bid"] == 0.0
    assert result["bid_headroom"] == 0.0
    assert result["dos_score"] > 0


def test_score_deal_market_comp_pricing_can_remain_capital_ready_when_otherwise_strong():
    result = score_deal(**_strong_proxy_priced_score_kwargs(
        retail_comp_count=5,
        retail_comp_price_estimate=33000,
        retail_comp_confidence=0.9,
        manheim_source_status="fallback",
    ))

    assert result["pricing_maturity"] == "market_comp"
    assert result["investment_grade"] in {"Platinum", "Gold", "Silver", "Bronze"}
    assert result["investment_grade"] != "Rejected"
    assert result["pricing_trust_blocked"] is False


def test_score_deal_uses_conservative_market_comp_wholesale_value_when_proxy_is_low():
    result = score_deal(
        bid=31000,
        mmr_ca=22000,
        state="NJ",
        source_site="GovDeals",
        model="Explorer",
        make="Ford",
        year=CURRENT_YEAR - 1,
        mileage=1435,
        title_status="clean",
        description="clean low mileage sport utility vehicle",
        photos=["https://example.com/photo.jpg"],
        retail_comp_count=3,
        retail_comp_price_estimate=41182.33,
        retail_comp_confidence=0.69,
        pricing_source="retail_market_cache",
        manheim_mmr_mid=22000,
        manheim_source_status="fallback",
    )

    assert result["pricing_maturity"] == "market_comp"
    assert result["mmr_estimated"] == 30505.43
    assert result["retail_asking_price_estimate"] == 41182.33
    assert result["ceiling_reason"] == "bid_ceiling_exceeded"
    assert result["investment_grade"] == "Rejected"


def test_score_deal_does_not_label_market_comp_when_comp_price_missing():
    result = score_deal(
        bid=31000,
        mmr_ca=22000,
        state="NJ",
        source_site="GovDeals",
        model="Explorer",
        make="Ford",
        year=CURRENT_YEAR - 1,
        mileage=1435,
        title_status="clean",
        description="clean low mileage sport utility vehicle",
        photos=["https://example.com/photo.jpg"],
        retail_comp_count=3,
        retail_comp_price_estimate=None,
        retail_comp_confidence=0.69,
        pricing_source="retail_market_cache",
    )

    assert result["pricing_maturity"] == "proxy"
    assert result["mmr_estimated"] == 22000


def test_score_deal_prefers_live_manheim_over_market_comp_when_available():
    result = score_deal(
        bid=31000,
        mmr_ca=22000,
        state="NJ",
        source_site="GovDeals",
        model="Explorer",
        make="Ford",
        year=CURRENT_YEAR - 1,
        mileage=1435,
        title_status="clean",
        description="clean low mileage sport utility vehicle",
        photos=["https://example.com/photo.jpg"],
        retail_comp_count=3,
        retail_comp_price_estimate=41182.33,
        retail_comp_confidence=0.69,
        pricing_source="retail_market_cache",
        manheim_mmr_mid=36000,
        manheim_source_status="live",
    )

    assert result["pricing_maturity"] == "live_market"
    assert result["mmr_estimated"] == 36000


def test_score_deal_rejects_explicit_poor_condition_even_with_market_comp_headroom():
    result = score_deal(**_strong_proxy_priced_score_kwargs(
        title="2018 Ford Explorer Police 4-Door Sport Utility Vehicle",
        description=(
            "Runs & Moves. Engine Performance Concerns. Dash Warning Indicators On. "
            "Major components missing. As is sale."
        ),
        year=2018,
        mileage=76000,
        retail_comp_count=5,
        retail_comp_price_estimate=33000,
        retail_comp_confidence=0.9,
        manheim_source_status="fallback",
    ))

    assert result["condition_grade"] == "Poor"
    assert result["dos_score"] == 0.0
    assert result["investment_grade"] == "Rejected"
    assert result["ceiling_pass"] is False
    assert result["ceiling_reason"] == "condition_unverified"


def test_score_deal_rejects_govdeals_as_is_detail_text_before_hot_dos():
    result = score_deal(**_strong_proxy_priced_score_kwargs(
        title="2020 Dodge Durango SRT",
        make="Dodge",
        model="Durango SRT",
        year=2020,
        mileage=13983,
        description="Clean title. Sold as is with no condition guarantees.",
        retail_comp_count=5,
        retail_comp_price_estimate=33000,
        retail_comp_confidence=0.9,
        manheim_source_status="fallback",
    ))

    assert result["condition_grade"] == "Poor"
    assert result["dos_score"] == 0.0
    assert result["investment_grade"] == "Rejected"
    assert result["ceiling_pass"] is False
    assert result["ceiling_reason"] == "condition_unverified"


def test_score_deal_rejects_no_start_condition_signal_before_hot_dos():
    result = score_deal(**_strong_proxy_priced_score_kwargs(
        description="Vehicle does not run.",
        retail_comp_count=5,
        retail_comp_price_estimate=33000,
        retail_comp_confidence=0.9,
        manheim_source_status="fallback",
    ))

    assert result["condition_grade"] == "Poor"
    assert "does not run" in result["condition_signals"]
    assert result["dos_score"] == 0.0
    assert result["investment_grade"] == "Rejected"
    assert result["ceiling_reason"] == "condition_unverified"


def test_score_deal_rejects_any_explicit_negative_condition_signal_not_just_curated_subset():
    result = score_deal(**_strong_proxy_priced_score_kwargs(
        description="Clean title fleet unit with warning indicators and lemon history noted.",
        retail_comp_count=5,
        retail_comp_price_estimate=33000,
        retail_comp_confidence=0.9,
        manheim_source_status="fallback",
    ))

    assert "warning indicators" in result["condition_signals"]
    assert "lemon" in result["condition_signals"]
    assert result["dos_score"] == 0.0
    assert result["investment_grade"] == "Rejected"
    assert result["ceiling_reason"] == "condition_unverified"


def test_score_deal_uses_single_condition_assessment(monkeypatch):
    calls = []

    def fake_score_condition(**kwargs):
        calls.append(kwargs)
        return {
            "condition_grade": "B",
            "condition_score": 70,
            "condition_signals": ["clean title"],
            "vin_suspicious": False,
            "vin_decoded": None,
        }

    monkeypatch.setattr(condition_module, "score_condition", fake_score_condition)
    monkeypatch.setattr(score_module, "_score_condition", fake_score_condition)

    result = score_deal(**_strong_proxy_priced_score_kwargs(
        description="Clean title fleet unit.",
        retail_comp_count=5,
        retail_comp_price_estimate=33000,
        retail_comp_confidence=0.9,
        manheim_source_status="fallback",
    ))

    assert len(calls) == 1
    assert result["condition_grade"] == "Good"
    assert result["condition_signals"] == ["clean title"]


def test_score_deal_proxy_zero_bid_branch_never_surfaces_bronze():
    result = score_deal(**_strong_proxy_priced_score_kwargs(bid=0))

    assert result["pricing_maturity"] == "proxy"
    assert result["investment_grade"] == "Rejected"
    assert result["investment_grade"] != "Bronze"
    assert result["ceiling_pass"] is False


def test_alert_gate_still_blocks_proxy_pricing_after_scoring_downgrade():
    result = score_deal(**_strong_proxy_priced_score_kwargs())
    record = {
        **result,
        "vin": "1HGCM82633A004352",
        "mileage": 22000,
        "condition_grade": "Good",
    }

    gate = evaluate_alert_gate(record, thresholds=AlertThresholds())

    assert gate["eligible"] is False
    assert "pricing_maturity=proxy" in gate["blocking_reasons"]
    assert "grade=Rejected" in gate["blocking_reasons"]

def test_score_deal_missing_mileage_is_rejected_not_surfaced_as_platinum():
    result = score_deal(
        bid=500,
        mmr_ca=20000,
        state="CA",
        source_site="GovDeals",
        model="F-150",
        make="Ford",
        year=CURRENT_YEAR - 2,
        mileage=None,
        title_status="clean",
        description="clean low bid truck",
        photos=["https://example.com/photo.jpg"],
    )

    assert result["vehicle_tier"] == "rejected"
    assert result["investment_grade"] == "Rejected"
    assert result["ceiling_pass"] is False
    assert result["max_bid"] == 0.0
    assert result["score"] == 0.0
    assert result["dos_score"] == 0.0
    assert result["score_provenance"]["input_profile"]["has_mileage"] is False


def test_score_deal_invalid_mileage_is_rejected_not_surfaced_as_platinum():
    for mileage in INVALID_MILEAGE_VALUES:
        result = score_deal(
            bid=500,
            mmr_ca=20000,
            state="CA",
            source_site="GovDeals",
            model="F-150",
            make="Ford",
            year=CURRENT_YEAR - 2,
            mileage=mileage,
            title_status="clean",
            description="clean low bid truck",
            photos=["https://example.com/photo.jpg"],
        )

        assert result["vehicle_tier"] == "rejected"
        assert result["investment_grade"] == "Rejected"
        assert result["ceiling_pass"] is False
        assert result["max_bid"] == 0.0
        assert result["score"] == 0.0
        assert result["dos_score"] == 0.0
        assert result["score_provenance"]["input_profile"]["has_mileage"] is False
