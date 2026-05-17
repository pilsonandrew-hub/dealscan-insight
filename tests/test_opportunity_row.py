from datetime import datetime, timezone

from backend.ingest.opportunity_row import build_opportunity_row


def _build(vehicle):
    return build_opportunity_row(
        vehicle,
        canonical_source_site=lambda source: "govdeals" if source in {"GovDeals", "govdeals"} else source,
        compute_listing_id=lambda source, url: f"{source}:{url}",
        compute_condition_grade=lambda **kwargs: "Good",
        now_utc=lambda: datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc),
    )


def test_build_opportunity_row_preserves_core_mapping_and_defaults():
    vehicle = {
        "listing_url": "https://example.test/listing/1",
        "source_site": "GovDeals",
        "title": "2024 Toyota Camry",
        "year": 2024,
        "make": "Toyota",
        "model": "Camry",
        "mileage": 12000,
        "state": "CA",
        "location_city": "Irvine",
        "vin": "1HGCM82633A004352",
        "current_bid": 10000,
        "dos_score": 81,
        "auction_end_time": "2026-05-20T00:00:00+00:00",
        "photo_url": "https://example.test/photo.jpg",
        "canonical_id": "canon-1",
        "all_sources": ["govdeals"],
        "run_id": "run-1",
        "source_run_id": "source-run-1",
        "score_breakdown": {
            "mmr_estimated": 22000,
            "transport": 600,
            "total_cost": 11300,
            "gross_margin": 5000,
            "score_version": "v-test",
            "vehicle_tier": "premium",
        },
    }

    row = _build(vehicle)

    assert row["listing_id"] == "govdeals:https://example.test/listing/1"
    assert row["source"] == "govdeals"
    assert row["source_site"] == "govdeals"
    assert row["buyer_premium"] == 500.0
    assert row["auction_fees"] == 200.0
    assert row["condition_grade"] == "Good"
    assert row["designated_lane"] == "premium"
    assert row["bid_ceiling_pct"] == 0.88
    assert row["min_margin_target"] == 1500
    assert row["processed_at"] == "2026-05-17T12:00:00+00:00"
    assert row["raw_data"] is vehicle


def test_build_opportunity_row_keeps_explicit_premium_and_fee_semantics():
    row = _build({
        "listing_url": "u",
        "source": "govdeals",
        "current_bid": 10000,
        "score_breakdown": {
            "buyer_premium_pct": 10,
            "auction_fees": 325.25,
            "vehicle_tier": "standard",
            "designated_lane": "standard",
        },
    })

    assert row["buyer_premium"] == 1000.0
    assert row["auction_fees"] == 325.25
    assert row["bid_ceiling_pct"] == 0.80
    assert row["min_margin_target"] == 2500


def test_build_opportunity_row_prefers_projected_buyer_premium_amount():
    row = _build({
        "listing_url": "u",
        "source_site": "govdeals",
        "current_bid": 10000,
        "score_breakdown": {
            "buyer_premium_pct": 20,
            "buyer_premium_amount": 125.55,
        },
    })

    assert row["buyer_premium"] == 125.55
