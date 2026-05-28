import os

import httpx

from backend.ingest import tavily_enrichment as tavily


def test_tavily_unavailable_without_key(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    assert tavily.is_available() is False


def test_should_not_enrich_unless_explicitly_enabled(monkeypatch):
    monkeypatch.delenv("TAVILY_ENRICHMENT_ENABLED", raising=False)
    vehicle = {
        "title": "2024 Ford F-150",
        "listing_url": "https://example.com/lot/1",
        "dos_score": 95,
        "vin": None,
        "mileage": None,
    }

    assert tavily.should_enrich_vehicle(vehicle) is False


def test_should_enrich_only_high_value_rows_with_major_truth_gaps(monkeypatch):
    monkeypatch.setenv("TAVILY_ENRICHMENT_ENABLED", "true")
    complete = {
        "title": "2024 Ford F-150",
        "listing_url": "https://example.com/lot/1",
        "dos_score": 95,
        "vin": "1FTFW1E50RFA12345",
        "mileage": 12000,
        "description": "Clean title, runs and drives.",
        "photos": ["https://example.com/photo.jpg"],
        "condition_grade": "Good",
    }
    low_score_missing_identity = dict(complete, dos_score=65, vin=None, mileage=None)
    high_score_missing_identity = dict(complete, vin=None, mileage=None)

    assert tavily.should_enrich_vehicle(complete) is False
    assert tavily.should_enrich_vehicle(low_score_missing_identity) is False
    assert tavily.should_enrich_vehicle(high_score_missing_identity) is True


def test_build_vehicle_query_is_compact_and_public():
    vehicle = {
        "vin": "1FTFW1E50RFA12345",
        "year": 2024,
        "make": "Ford",
        "model": "F-150",
        "title": "2024 Ford F-150 XL SuperCrew " + ("x" * 400),
        "state": "CA",
        "source_site": "proxibid",
    }

    query = tavily.build_vehicle_query(vehicle)

    assert query.startswith("1FTFW1E50RFA12345 2024 Ford F-150")
    assert "proxibid" in query
    assert len(query) <= 220


def test_search_vehicle_context_posts_compact_query(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    monkeypatch.setenv("TAVILY_ENRICHMENT_ENABLED", "true")
    calls = []

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "results": [
                    {
                        "title": "Lot detail",
                        "url": "https://example.com/detail",
                        "content": "VIN and mileage corroborating snippet",
                        "score": 0.9,
                    }
                ]
            }

    def fake_post(url, *, json, timeout):
        calls.append({"url": url, "json": json, "timeout": timeout})
        return FakeResponse()

    monkeypatch.setattr(tavily.httpx, "post", fake_post)

    result = tavily.search_vehicle_context({
        "title": "2024 Ford F-150",
        "listing_url": "https://example.com/lot/1",
        "dos_score": 95,
        "vin": None,
        "mileage": None,
    })

    assert result["source"] == "tavily"
    assert result["result_count"] == 1
    assert result["results"][0]["url"] == "https://example.com/detail"
    assert calls[0]["url"] == tavily.TAVILY_SEARCH_URL
    assert calls[0]["json"]["api_key"] == "tvly-test"
    assert calls[0]["json"]["include_raw_content"] is False
    assert calls[0]["json"]["max_results"] == 2


def test_apply_tavily_enrichment_is_nonblocking_on_http_error(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    monkeypatch.setenv("TAVILY_ENRICHMENT_ENABLED", "true")

    def fake_post(*args, **kwargs):
        raise httpx.TimeoutException("slow")

    monkeypatch.setattr(tavily.httpx, "post", fake_post)
    vehicle = {
        "title": "2024 Ford F-150",
        "listing_url": "https://example.com/lot/1",
        "dos_score": 95,
        "vin": None,
        "mileage": None,
    }

    enriched = tavily.apply_tavily_enrichment(vehicle)

    assert enriched == vehicle
    assert enriched is not vehicle
