import json

from scripts.trace_condition_source_evidence import (
    build_source_evidence_trace,
    select_dataset_item,
)


def test_selects_dataset_item_by_listing_url_and_vin_suffix():
    source_identity = {
        "listing_url": "https://www.govdeals.com/asset/197/5804",
        "listing_id": "stored-listing-id",
        "vin_suffix": "324462",
    }
    items = [
        {
            "listing_url": "https://www.govdeals.com/asset/111/2222",
            "vin": "1C4SDJGJ6LC000000",
        },
        {
            "listing_url": "https://www.govdeals.com/asset/197/5804",
            "vin": "1C4SDJGJ6LC324462",
            "detail_text": "UNKNOWN MECHANICAL HISTORY. Starts and drives fine.",
        },
    ]

    selected = select_dataset_item(items, source_identity)

    assert selected == items[1]


def test_trace_marks_recovered_poor_source_as_not_backfill_safe():
    condition_proof = {
        "selector": {"id": "durango-row"},
        "opportunity": {
            "id": "durango-row",
            "source_site": "govdeals",
            "title": "2020 Dodge Durango SRT",
            "year": 2020,
            "mileage": 13983,
            "condition_grade": "Poor",
            "condition_blocker_basis": "age_mileage_heuristic",
            "condition_signals": [],
            "condition_backfill_assessment": {
                "status": "blocked_missing_source_condition_evidence",
                "stored_source_condition_evidence": False,
            },
            "source_identity": {
                "listing_url": "https://www.govdeals.com/asset/197/5804",
                "actor_run_id": "4bCfV8noqOLBAPiyX",
                "vin_suffix": "324462",
            },
        },
    }
    dataset_items = [
        {
            "listing_url": "https://www.govdeals.com/asset/197/5804",
            "vin": "1C4SDJGJ6LC324462",
            "title": "2020 Dodge Durango SRT",
            "description": "2020 Dodge Durango SRT",
            "detail_text": (
                "UNKNOWN MECHANICAL HISTORY. Sold as is. Starts and drives fine. "
                "Clean title. Swapped Scat Pack motor noted."
            ),
        }
    ]

    trace = build_source_evidence_trace(
        condition_proof,
        dataset_items,
        dataset_id="nPJoGcQo7z4ZVYEoe",
    )

    assert trace["source_trace"]["matched"] is True
    assert trace["recovered_source_condition"]["condition_grade"] in {"D", "F"}
    assert "as is" in trace["recovered_source_condition"]["condition_signals"]
    assert trace["backfill_recommendation"]["status"] == "blocked_recovered_source_still_condition_negative"
    assert trace["backfill_recommendation"]["mutate_row"] is False


def test_trace_reports_missing_dataset_match_without_mutation_recommendation():
    condition_proof = {
        "opportunity": {
            "id": "durango-row",
            "title": "2020 Dodge Durango SRT",
            "source_identity": {
                "listing_url": "https://www.govdeals.com/asset/197/5804",
                "vin_suffix": "324462",
            },
        }
    }

    trace = build_source_evidence_trace(
        condition_proof,
        [{"listing_url": "https://www.govdeals.com/asset/999/9999"}],
    )

    assert trace["source_trace"]["matched"] is False
    assert trace["backfill_recommendation"] == {
        "status": "blocked_no_matching_source_item",
        "mutate_row": False,
    }


def test_trace_output_is_json_serializable():
    trace = build_source_evidence_trace({"opportunity": {"id": "row-1"}}, [])

    json.dumps(trace, sort_keys=True)
