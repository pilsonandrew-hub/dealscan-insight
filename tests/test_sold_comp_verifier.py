from datetime import date

from scripts import verify_sold_comp_candidates as verifier


def _candidate(**overrides):
    base = {
        "id": "candidate-1",
        "run_id": "run-1",
        "source_name": "govdeals-sold",
        "source_listing_id": "asset-1",
        "listing_url": "https://www.govdeals.com/asset/1/2",
        "evidence_ref": "https://www.govdeals.com/asset/1/2",
        "sale_status_normalized": "candidate_completed",
        "sale_date": "2026-06-01",
        "sold_price_hammer": 12400,
        "buyer_premium": 0,
        "fees": 0,
        "sold_price_all_in": 12400,
        "price_basis": "source_reported",
        "currency": "USD",
        "year": 2019,
        "make": "Ford",
        "model": "F-150",
        "trim": "XL",
        "vin": "1FTEW1E50KFA00001",
        "mileage": 82210,
        "channel": "gov",
        "dedup_key": "dedup-1",
        "extractor_version": "apify-webhook-govdeals-sold",
        "source_policy_version": "govdeals-sold-alpha-v1",
        "candidate_status": "candidate",
        "rejection_reason": None,
    }
    base.update(overrides)
    return base


def test_verifier_accepts_clean_approved_truck_candidate_for_promotion():
    decision = verifier.evaluate_candidate(_candidate(), today=date(2026, 6, 3))

    assert decision.review_status == "accepted"
    assert decision.rejection_reason is None
    assert decision.human_required is False
    assert decision.deterministic_checks["approved_vehicle_scope"] is True

    review_row = verifier.build_review_row(
        _candidate(),
        decision,
        reviewer="market_scout_verifier",
        reviewer_version="test-v1",
    )
    verified_row = verifier.build_verified_comp_row(
        _candidate(),
        decision,
        verifier_version="test-v1",
    )

    assert review_row["review_status"] == "accepted"
    assert review_row["candidate_id"] == "candidate-1"
    assert verified_row["source_name"] == "govdeals-sold"
    assert verified_row["sold_price_all_in"] == 12400
    assert verified_row["normalized_make"] == "Ford"
    assert verified_row["normalized_model"] == "F-150"
    assert "raw_payload" not in verified_row


def test_verifier_preserves_deterministic_staging_rejections():
    candidate = _candidate(
        candidate_status="rejected",
        rejection_reason="missing_year_make_model",
        year=None,
        make=None,
        model=None,
    )

    decision = verifier.evaluate_candidate(candidate, today=date(2026, 6, 3))

    assert decision.review_status == "rejected"
    assert decision.rejection_reason == "missing_year_make_model"
    assert decision.human_required is False
    assert verifier.build_verified_comp_row(candidate, decision, verifier_version="test-v1") is None


def test_verifier_routes_out_of_scope_vehicle_to_review_not_market_truth():
    candidate = _candidate(
        source_listing_id="asset-g-class",
        year=2021,
        make="Mercedes-Benz",
        model="G-Class",
        sold_price_all_in=99000,
        sold_price_hammer=99000,
        vin=None,
    )

    decision = verifier.evaluate_candidate(candidate, today=date(2026, 6, 3))

    assert decision.review_status == "needs_review"
    assert decision.rejection_reason == "outside_approved_vehicle_scope"
    assert decision.human_required is True
    assert decision.deterministic_checks["approved_vehicle_scope"] is False
    assert verifier.build_verified_comp_row(candidate, decision, verifier_version="test-v1") is None


def test_verifier_rejects_duplicate_source_listing_before_promotion():
    candidate = _candidate()

    decision = verifier.evaluate_candidate(
        candidate,
        today=date(2026, 6, 3),
        existing_verified_source_listing_ids={"govdeals-sold:asset-1"},
    )

    assert decision.review_status == "rejected"
    assert decision.rejection_reason == "duplicate_source_listing"
    assert decision.deterministic_checks["duplicate_source_listing"] is True


def test_verifier_rejects_invalid_vin_when_present():
    candidate = _candidate(vin="BADVIN")

    decision = verifier.evaluate_candidate(candidate, today=date(2026, 6, 3))

    assert decision.review_status == "rejected"
    assert decision.rejection_reason == "invalid_vin"
    assert decision.deterministic_checks["valid_vin"] is False
