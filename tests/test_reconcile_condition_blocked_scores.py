from scripts.reconcile_condition_blocked_scores import (
    is_explicit_condition_blocked_hot_row,
    is_recovered_source_condition_blocked_hot_row,
    rejection_payload,
)


def test_targets_active_hot_rows_with_explicit_negative_condition_signal():
    row = {
        "id": "opp-1",
        "is_active": True,
        "dos_score": 85.1,
        "score": 85.1,
        "title": "2018 Ford Explorer Police",
        "condition_grade": "Poor",
        "mileage": 87540,
        "year": 2018,
        "source_site": "jjkane",
        "raw_data": {
            "detail_text": (
                "Runs & Moves. Engine Performance Concerns. "
                "Dash Warning Indicators On. Major components missing."
            )
        },
    }

    assert is_explicit_condition_blocked_hot_row(row) is True


def test_does_not_target_age_mileage_only_poor_rows():
    row = {
        "id": "opp-2",
        "is_active": True,
        "dos_score": 81.3,
        "score": 81.3,
        "title": "2018 Ford F-150",
        "condition_grade": "Poor",
        "mileage": 94998,
        "year": 2018,
        "source_site": "jjkane",
        "raw_data": {"detail_text": "Clean fleet unit with service records."},
    }

    assert is_explicit_condition_blocked_hot_row(row) is False


def test_does_not_target_inactive_or_non_hot_rows():
    explicit_negative = {
        "id": "opp-3",
        "is_active": True,
        "dos_score": 79.9,
        "score": 79.9,
        "title": "2020 Dodge Durango",
        "condition_grade": "Poor",
        "mileage": 20000,
        "year": 2020,
        "raw_data": {"detail_text": "Sold as is."},
    }
    inactive = dict(explicit_negative, is_active=False, dos_score=92.0, score=92.0)

    assert is_explicit_condition_blocked_hot_row(explicit_negative) is False
    assert is_explicit_condition_blocked_hot_row(inactive) is False


def test_rejection_payload_removes_hot_scoring_and_capital_ready_grade():
    payload = rejection_payload()

    assert payload["dos_score"] == 0.0
    assert payload["score"] == 0.0
    assert payload["legacy_dos_score"] == 0.0
    assert payload["investment_grade"] == "Rejected"
    assert payload["max_bid"] == 0.0
    assert payload["bid_headroom"] == 0.0
    assert payload["ceiling_reason"] == "condition_unverified"


def test_targets_single_hot_storage_gap_row_with_recovered_negative_source_evidence():
    row = {
        "id": "durango-row",
        "is_active": True,
        "dos_score": 86.9,
        "score": 86.9,
        "investment_grade": "Platinum",
        "source_site": "govdeals",
        "title": "2020 Dodge Durango SRT",
        "year": 2020,
        "mileage": 13983,
        "condition_grade": "Poor",
        "raw_data": {
            "description": "2020 Dodge Durango SRT",
            "listing_url": "https://www.govdeals.com/asset/197/5804",
            "vin": "1C4SDJGJ6LC324462",
            "actor_run_id": "4bCfV8noqOLBAPiyX",
        },
    }
    dataset_items = [
        {
            "listing_url": "https://www.govdeals.com/asset/197/5804",
            "vin": "1C4SDJGJ6LC324462",
            "title": "2020 Dodge Durango SRT",
            "description": "2020 Dodge Durango SRT",
            "detail_text": "UNKNOWN MECHANICAL HISTORY. Sold as is. Clean title.",
        }
    ]

    result = is_recovered_source_condition_blocked_hot_row(row, dataset_items)

    assert result["target"] is True
    assert result["reason"] == "recovered_source_condition_negative"
    assert result["trace"]["source_trace"]["matched"] is True
    assert result["trace"]["recovered_source_condition"]["condition_grade"] in {"D", "F"}


def test_does_not_target_storage_gap_row_without_matching_source_evidence():
    row = {
        "id": "durango-row",
        "is_active": True,
        "dos_score": 86.9,
        "score": 86.9,
        "source_site": "govdeals",
        "title": "2020 Dodge Durango SRT",
        "year": 2020,
        "mileage": 13983,
        "condition_grade": "Poor",
        "raw_data": {
            "description": "2020 Dodge Durango SRT",
            "listing_url": "https://www.govdeals.com/asset/197/5804",
            "vin": "1C4SDJGJ6LC324462",
        },
    }

    result = is_recovered_source_condition_blocked_hot_row(
        row,
        [{"listing_url": "https://www.govdeals.com/asset/999/9999"}],
    )

    assert result["target"] is False
    assert result["reason"] == "source_trace_not_negative"
