import importlib.util
import sys
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "prepare_external_market_comp_seed.py"
sys.path.insert(0, str(SCRIPT_PATH.parent))
SPEC = importlib.util.spec_from_file_location("prepare_external_market_comp_seed", SCRIPT_PATH)
prepare_external_market_comp_seed = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(prepare_external_market_comp_seed)


def _evidence():
    return {
        "source_run_id": "manual-2026-06-02-durango",
        "source_url": "https://example.com/reports/durango",
        "vehicle": {
            "year": 2020,
            "make": "Dodge",
            "model": "Durango",
            "state": "MS",
        },
        "comps": [
            {
                "source_url": "https://example.com/listing/1",
                "captured_at": "2026-06-02T09:35:00Z",
                "price": 45250,
                "mileage": 34718,
                "vin": "1C4SDJGJ4LC171581",
                "title": "2020 Dodge Durango SRT",
            },
            {
                "source_url": "https://example.com/listing/2",
                "captured_at": "2026-06-02T09:35:00+00:00",
                "price": 41984,
                "mileage": 40992,
                "listing_id": "listing-2",
                "title": "2020 Dodge Durango SRT AWD",
            },
            {
                "source_url": "https://example.com/listing/3",
                "captured_at": "2026-06-02T09:35:00+00:00",
                "price": "55171",
                "mileage": 16988,
                "listing_id": "listing-3",
                "title": "2020 Dodge Durango SRT AWD",
            },
        ],
    }


def test_validate_external_comp_document_builds_dry_run_seed_row():
    seed = prepare_external_market_comp_seed.validate_external_comp_document(_evidence())

    assert seed["year"] == 2020
    assert seed["make"] == "dodge"
    assert seed["model"] == "durango"
    assert seed["state"] == "ms"
    assert seed["source"] == "external_retail_listing_comp"
    assert seed["sample_size"] == 3
    assert str(seed["avg_price"]) == "47468.33"
    assert str(seed["low_price"]) == "41984.00"
    assert str(seed["high_price"]) == "55171.00"
    assert seed["metadata"]["evidence_count"] == 3


def test_validate_external_comp_document_rejects_too_few_samples():
    evidence = _evidence()
    evidence["comps"] = evidence["comps"][:2]

    with pytest.raises(prepare_external_market_comp_seed.ExternalCompError, match="at least 3 comps"):
        prepare_external_market_comp_seed.validate_external_comp_document(evidence)


def test_validate_external_comp_document_rejects_missing_url_or_timestamp():
    evidence = _evidence()
    evidence["comps"][0]["source_url"] = "not-a-url"

    with pytest.raises(prepare_external_market_comp_seed.ExternalCompError, match="source_url"):
        prepare_external_market_comp_seed.validate_external_comp_document(evidence)

    evidence = _evidence()
    evidence["comps"][0]["captured_at"] = "2026-06-02 09:35:00"

    with pytest.raises(prepare_external_market_comp_seed.ExternalCompError, match="timezone"):
        prepare_external_market_comp_seed.validate_external_comp_document(evidence)


def test_validate_external_comp_document_rejects_duplicate_listing_evidence():
    evidence = _evidence()
    evidence["comps"][1]["source_url"] = evidence["comps"][0]["source_url"]
    evidence["comps"][1]["vin"] = evidence["comps"][0]["vin"]
    evidence["comps"][1].pop("listing_id")

    with pytest.raises(prepare_external_market_comp_seed.ExternalCompError, match="duplicate"):
        prepare_external_market_comp_seed.validate_external_comp_document(evidence)


def test_validate_external_comp_document_rejects_proxy_like_bad_values():
    evidence = _evidence()
    evidence["comps"][0]["price"] = 0

    with pytest.raises(prepare_external_market_comp_seed.ExternalCompError, match="positive"):
        prepare_external_market_comp_seed.validate_external_comp_document(evidence)

    evidence = _evidence()
    evidence["comps"][0]["mileage"] = None

    with pytest.raises(prepare_external_market_comp_seed.ExternalCompError, match="mileage"):
        prepare_external_market_comp_seed.validate_external_comp_document(evidence)
