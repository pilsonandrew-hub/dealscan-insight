import importlib.util
import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

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


class _FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_insert_seed_row_via_rest_posts_when_no_existing_row(monkeypatch):
    seed = prepare_external_market_comp_seed.validate_external_comp_document(_evidence())
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(request)
        if request.get_method() == "GET":
            parsed = urlparse(request.full_url)
            query = parse_qs(parsed.query)
            assert query["year"] == ["eq.2020"]
            assert query["make"] == ["eq.dodge"]
            assert query["model"] == ["eq.durango"]
            assert query["state"] == ["eq.ms"]
            assert query["source"] == ["eq.external_retail_listing_comp"]
            assert query["source_run_id"] == ["eq.manual-2026-06-02-durango"]
            return _FakeResponse([])
        assert request.get_method() == "POST"
        payload = json.loads(request.data.decode("utf-8"))
        assert payload["year"] == 2020
        assert payload["make"] == "dodge"
        assert payload["model"] == "durango"
        assert payload["source"] == "external_retail_listing_comp"
        assert payload["metadata"]["evidence_count"] == 3
        assert "last_updated" in payload
        assert "expires_at" in payload
        return _FakeResponse([{"id": "row-1", "avg_price": "47468.33", "sample_size": 3}])

    monkeypatch.setattr(prepare_external_market_comp_seed.urllib_request, "urlopen", fake_urlopen)

    inserted = prepare_external_market_comp_seed.insert_seed_row_via_rest(
        "https://example.supabase.co",
        "service-key",
        seed,
        ttl_days=14,
    )

    assert inserted == {"id": "row-1", "avg_price": "47468.33", "sample_size": 3}
    assert [call.get_method() for call in calls] == ["GET", "POST"]


def test_insert_seed_row_via_rest_noops_when_existing_row_found(monkeypatch):
    seed = prepare_external_market_comp_seed.validate_external_comp_document(_evidence())
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(request)
        return _FakeResponse([{"id": "existing-row"}])

    monkeypatch.setattr(prepare_external_market_comp_seed.urllib_request, "urlopen", fake_urlopen)

    inserted = prepare_external_market_comp_seed.insert_seed_row_via_rest(
        "https://example.supabase.co",
        "service-key",
        seed,
        ttl_days=14,
    )

    assert inserted is None
    assert [call.get_method() for call in calls] == ["GET"]
