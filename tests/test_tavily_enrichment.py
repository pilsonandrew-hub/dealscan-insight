import os

import httpx

from backend.ingest import tavily_enrichment as tavily


def test_tavily_unavailable_without_key(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    assert tavily.is_available() is False


def test_should_enrich_only_when_truth_fields_missing():
    complete = {
        "title": "2024 Ford F-150",
        "listing_url": "https://example.com/lot/1",
        "vin": "1FTFW1E50RFA12345",
        "mileage": 12000,
        "description": "Clean title, runs and drives.",
        "photos": ["https://example.com/photo.jpg"],
        "condition_grade": "Good",
    }
    missing_mileage = dict(complete, mileage=None)

    assert tavily.should_enrich_vehicle(complete) is False
    assert tavily.should_enrich_vehicle(missing_mileage) is True


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
        "mileage": None,
    })

    assert result["source"] == "tavily"
    assert result["result_count"] == 1
    assert result["results"][0]["url"] == "https://example.com/detail"
    assert calls[0]["url"] == tavily.TAVILY_SEARCH_URL
    assert calls[0]["json"]["api_key"] == "tvly-test"
    assert calls[0]["json"]["include_raw_content"] is False


def test_apply_tavily_enrichment_is_nonblocking_on_http_error(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

    def fake_post(*args, **kwargs):
        raise httpx.TimeoutException("slow")

    monkeypatch.setattr(tavily.httpx, "post", fake_post)
    vehicle = {
        "title": "2024 Ford F-150",
        "listing_url": "https://example.com/lot/1",
        "mileage": None,
    }

    enriched = tavily.apply_tavily_enrichment(vehicle)

    assert enriched == vehicle
    assert enriched is not vehicle
