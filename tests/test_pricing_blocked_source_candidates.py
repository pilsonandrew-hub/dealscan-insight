import importlib.util
import sys
from pathlib import Path
from datetime import datetime, timezone
from urllib import error as urllib_error


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "report_pricing_blocked_source_candidates.py"
sys.path.insert(0, str(SCRIPT_PATH.parent))
SPEC = importlib.util.spec_from_file_location("report_pricing_blocked_source_candidates", SCRIPT_PATH)
report_pricing_blocked_source_candidates = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(report_pricing_blocked_source_candidates)


def test_parse_proxy_skip_reason_extracts_bid_mmr_and_tier():
    parsed = report_pricing_blocked_source_candidates.parse_proxy_skip_reason(
        "margin_below_floor | margin=$325 floor=$1500 tier=premium bid=$20900 mmr=$26000 cost=$25675 max_bid=$0 headroom=$0 pricing=proxy"
    )

    assert parsed == {
        "bid": 20900.0,
        "cost": 25675.0,
        "floor": 1500.0,
        "headroom": 0.0,
        "margin": 325.0,
        "max_bid": 0.0,
        "mmr": 26000.0,
        "pricing": "proxy",
        "tier": "premium",
    }


def test_classify_source_candidate_marks_active_clean_pricing_gap():
    row = {
        "year": 2023,
        "make": "Toyota",
        "model": "Tacoma",
        "state": "FL",
        "mileage": 16808,
        "vin": "3TMAZ5CN0PM202309",
        "auction_active": True,
        "has_market_price": False,
        "has_usable_dealer_sales": False,
    }

    assert (
        report_pricing_blocked_source_candidates.classify_source_candidate(row)
        == "active_clean_pricing_gap"
    )


def test_classify_source_candidate_marks_margin_floor_reject():
    row = {
        "year": 2022,
        "make": "BMW",
        "model": "X1",
        "state": "TN",
        "mileage": 40718,
        "vin": "WBXJG9C02N5P20226",
        "auction_active": True,
        "has_market_price": False,
        "has_usable_dealer_sales": False,
        "error_message": "margin_below_floor | margin=$325 floor=$1500 tier=premium bid=$20900 mmr=$26000 cost=$25675 max_bid=$0 headroom=$0 pricing=proxy",
    }

    assert (
        report_pricing_blocked_source_candidates.classify_source_candidate(row)
        == "below_margin_floor"
    )


def test_classify_source_candidate_marks_proxy_margin_row_covered_after_market_price():
    row = {
        "year": 2025,
        "make": "Ford",
        "model": "Mustang 60th Anniv Editio",
        "state": "GA",
        "mileage": 104,
        "vin": "1FA6P8CF3S5407587",
        "auction_active": True,
        "has_market_price": True,
        "has_usable_dealer_sales": False,
        "error_message": "margin_below_floor | margin=$-38795 floor=$1500 tier=premium bid=$59433 mmr=$30000 cost=$66295 max_bid=$21600 headroom=$-37833 pricing=proxy",
    }

    assert (
        report_pricing_blocked_source_candidates.classify_source_candidate(row)
        == "covered_after_skip"
    )


def test_classify_source_candidate_marks_brightdrop_as_source_policy_reject():
    row = {
        "year": 2024,
        "make": "BrightDrop",
        "model": "Zevo 400 Base AWD Cargo Delivery Van",
        "state": "FL",
        "mileage": 10,
        "vin": "1GCDE0ED5R7001954",
        "auction_active": True,
        "has_market_price": False,
        "has_usable_dealer_sales": False,
        "error_message": "margin_below_floor | margin=$-30300 floor=$1500 tier=premium bid=$32000 mmr=$15000 cost=$35300 max_bid=$8100 headroom=$-23900 pricing=proxy",
        "title": "2024 BrightDrop Zevo 400 Base AWD Cargo Delivery Van",
    }

    assert (
        report_pricing_blocked_source_candidates.classify_source_candidate(row)
        == "source_policy_reject"
    )


def test_classify_source_candidate_marks_newer_non_proxy_delivery_as_superseded():
    row = {
        "year": 2025,
        "make": "Ford",
        "model": "Explorer",
        "state": "NJ",
        "mileage": 1435,
        "vin": "1FMUK8DH5SGA77978",
        "auction_active": True,
        "has_market_price": False,
        "has_usable_dealer_sales": False,
        "error_message": "margin_below_floor | margin=$-13300 floor=$1500 tier=premium bid=$31000 mmr=$22000 cost=$35300 max_bid=$17600 headroom=$-13400 pricing=proxy",
        "skip_created_at": "2026-06-05T12:05:52.18536+00:00",
        "latest_delivery_created_at": "2026-06-05T15:26:12.090049+00:00",
        "latest_delivery_error_message": "margin_below_floor | margin=$-4795 floor=$1500 tier=premium bid=$31000 mmr=$30505 cost=$35300 max_bid=$25095 headroom=$-5905 pricing=market_comp comp_price=$41182 comp_count=3 comp_conf=0.73",
    }

    assert (
        report_pricing_blocked_source_candidates.classify_source_candidate(row)
        == "superseded_after_skip"
    )


def test_classify_source_candidate_separates_expired_and_dirty_rows():
    expired = {
        "year": 2023,
        "make": "Toyota",
        "model": "Tacoma",
        "state": "FL",
        "mileage": 16808,
        "vin": "3TMAZ5CN0PM202309",
        "auction_active": False,
        "has_market_price": False,
        "has_usable_dealer_sales": False,
    }
    missing_identity = {
        "year": 2023,
        "make": "Toyota",
        "model": "Tacoma",
        "state": "FL",
        "mileage": None,
        "vin": None,
        "auction_active": True,
        "has_market_price": False,
        "has_usable_dealer_sales": False,
    }

    assert report_pricing_blocked_source_candidates.classify_source_candidate(expired) == "expired_pricing_gap"
    assert report_pricing_blocked_source_candidates.classify_source_candidate(missing_identity) == "dirty_source_row"


def test_format_candidate_includes_status_and_source_fields():
    row = {
        "source_site": "allsurplus",
        "year": 2023,
        "make": "Toyota",
        "model": "Tacoma",
        "state": "FL",
        "mileage": 16808,
        "vin": "3TMAZ5CN0PM202309",
        "current_bid": 22000,
        "auction_active": True,
        "has_market_price": False,
        "has_usable_dealer_sales": False,
        "skip_created_at": "2026-05-31T07:01:36+00:00",
        "title": "2023 Toyota Tacoma",
        "listing_url": "https://www.allsurplus.com/asset/2306/26960",
    }

    formatted = report_pricing_blocked_source_candidates.format_candidate(row)

    assert "status=active_clean_pricing_gap" in formatted
    assert "source=allsurplus" in formatted
    assert "2023 Toyota Tacoma" in formatted


def test_fetch_rows_via_rest_marks_candidate_covered_after_market_price(monkeypatch):
    calls = []

    def fake_fetch(base_url, service_role_key, table, query):
        calls.append((base_url, service_role_key, table, query))
        if table == "ingest_delivery_log":
            return [
                {
                    "run_id": "run-1",
                    "listing_id": "asset-1",
                    "listing_url": "https://example.com/asset-1",
                    "status": "skipped_ceiling",
                    "error_message": "pricing_maturity_proxy | bid=$22,000 mmr=$31,000 tier=premium",
                    "created_at": "2026-06-02T12:00:00+00:00",
                }
            ]
        if table == "sonar_listings":
            return [
                {
                    "source_site": "allsurplus",
                    "year": 2023,
                    "make": "Toyota",
                    "model": "Tacoma",
                    "state": "FL",
                    "mileage": 16808,
                    "vin": "3TMAZ5CN0PM202309",
                    "current_bid": 22000,
                    "auction_end_date": None,
                    "created_at": "2026-06-02T11:59:00+00:00",
                    "title": "2023 Toyota Tacoma",
                    "listing_id": "asset-1",
                    "listing_url": "https://example.com/asset-1",
                }
            ]
        if table == "market_prices":
            return [
                {
                    "year": 2023,
                    "make": "toyota",
                    "model": "tacoma",
                    "state": "fl",
                    "avg_price": 36001,
                    "low_price": 31343,
                    "high_price": 40944,
                    "sample_size": 4,
                    "expires_at": "2026-06-16T12:00:00+00:00",
                }
            ]
        if table == "dealer_sales":
            return []
        raise AssertionError(table)

    monkeypatch.setattr(report_pricing_blocked_source_candidates, "_fetch_postgrest_rows", fake_fetch)
    rows = report_pricing_blocked_source_candidates.fetch_rows_via_rest(
        "https://example.supabase.co",
        "service-key",
        lookback_days=14,
        max_mileage=50000,
        max_age_years=4,
        include_dirty=False,
        limit=50,
        now=datetime(2026, 6, 2, 12, 30, tzinfo=timezone.utc),
    )

    assert len(rows) == 1
    assert rows[0]["has_market_price"] is True
    assert rows[0]["has_usable_dealer_sales"] is False
    assert report_pricing_blocked_source_candidates.classify_source_candidate(rows[0]) == "covered_after_skip"
    assert calls[0][0] == "https://example.supabase.co/rest/v1"


def test_fetch_rows_via_rest_uses_separate_proxy_and_latest_delivery_queries(monkeypatch):
    def fake_fetch(base_url, service_role_key, table, query):
        query_values = dict(query)
        if table == "ingest_delivery_log":
            if query_values.get("status") == "in.(skipped_ceiling,skipped_margin)":
                return [
                    {
                        "run_id": "old-run",
                        "listing_id": "asset-explorer",
                        "listing_url": "https://example.com/explorer",
                        "status": "skipped_margin",
                        "error_message": "margin_below_floor | margin=$-13300 floor=$1500 tier=premium bid=$31000 mmr=$22000 cost=$35300 max_bid=$17600 headroom=$-13400 pricing=proxy",
                        "created_at": "2026-06-05T12:05:52+00:00",
                    }
                ]
            if query_values.get("status") == "in.(skipped_ceiling,skipped_margin,saved_sonar)":
                return [
                    {
                        "run_id": "fresh-run",
                        "listing_id": "asset-explorer",
                        "listing_url": "https://example.com/explorer",
                        "status": "skipped_margin",
                        "error_message": "margin_below_floor | margin=$-4795 floor=$1500 tier=premium bid=$31000 mmr=$30505 cost=$35300 max_bid=$25095 headroom=$-5905 pricing=market_comp",
                        "created_at": "2026-06-05T15:26:12+00:00",
                    }
                ]
            raise AssertionError(query_values.get("status"))
        if table == "sonar_listings":
            return [
                {
                    "source_site": "govdeals",
                    "year": 2025,
                    "make": "Ford",
                    "model": "Explorer",
                    "state": "NJ",
                    "mileage": 1435,
                    "vin": "1FMUK8DH5SGA77978",
                    "current_bid": 31000,
                    "auction_end_date": "2026-06-12T00:00:00+00:00",
                    "created_at": "2026-06-05T12:05:51+00:00",
                    "title": "2025 Ford Explorer Active AWD Low Miles!",
                    "listing_id": "asset-explorer",
                    "listing_url": "https://example.com/explorer",
                }
            ]
        if table in {"market_prices", "dealer_sales"}:
            return []
        raise AssertionError(table)

    monkeypatch.setattr(report_pricing_blocked_source_candidates, "_fetch_postgrest_rows", fake_fetch)
    rows = report_pricing_blocked_source_candidates.fetch_rows_via_rest(
        "https://example.supabase.co/rest/v1",
        "service-key",
        lookback_days=1,
        max_mileage=50000,
        max_age_years=4,
        include_dirty=False,
        limit=50,
        now=datetime(2026, 6, 5, 16, 0, tzinfo=timezone.utc),
    )

    assert len(rows) == 1
    assert rows[0]["latest_delivery_created_at"] == "2026-06-05T15:26:12+00:00"
    assert report_pricing_blocked_source_candidates.classify_source_candidate(rows[0]) == "superseded_after_skip"


def test_fetch_rows_via_rest_reports_dirty_rows_by_default(monkeypatch):
    def fake_fetch(base_url, service_role_key, table, query):
        if table == "ingest_delivery_log":
            return [
                {
                    "listing_id": "asset-dirty",
                    "listing_url": "https://example.com/dirty",
                    "status": "skipped_ceiling",
                    "error_message": "pricing_maturity_proxy | bid=$10,000 mmr=$20,000 tier=standard",
                    "created_at": "2026-06-02T12:00:00+00:00",
                }
            ]
        if table == "sonar_listings":
            return [
                {
                    "source_site": "allsurplus",
                    "year": 2023,
                    "make": "Toyota",
                    "model": "Tacoma",
                    "state": "FL",
                    "mileage": None,
                    "vin": None,
                    "current_bid": 10000,
                    "auction_end_date": None,
                    "created_at": "2026-06-02T11:59:00+00:00",
                    "title": "Dirty Tacoma",
                    "listing_id": "asset-dirty",
                    "listing_url": "https://example.com/dirty",
                }
            ]
        return []

    monkeypatch.setattr(report_pricing_blocked_source_candidates, "_fetch_postgrest_rows", fake_fetch)

    clean_only = report_pricing_blocked_source_candidates.fetch_rows_via_rest(
        "https://example.supabase.co/rest/v1",
        "service-key",
        lookback_days=14,
        max_mileage=50000,
        max_age_years=4,
        include_dirty=False,
        limit=50,
        now=datetime(2026, 6, 2, 12, 30, tzinfo=timezone.utc),
    )
    dirty_included = report_pricing_blocked_source_candidates.fetch_rows_via_rest(
        "https://example.supabase.co/rest/v1",
        "service-key",
        lookback_days=14,
        max_mileage=50000,
        max_age_years=4,
        include_dirty=True,
        limit=50,
        now=datetime(2026, 6, 2, 12, 30, tzinfo=timezone.utc),
    )

    assert len(clean_only) == 1
    assert report_pricing_blocked_source_candidates.classify_source_candidate(clean_only[0]) == "dirty_source_row"
    assert len(dirty_included) == 1
    assert report_pricing_blocked_source_candidates.classify_source_candidate(dirty_included[0]) == "dirty_source_row"


def test_fetch_rows_via_rest_reports_age_mileage_excluded_proxy_rows_by_default(monkeypatch):
    def fake_fetch(base_url, service_role_key, table, query):
        if table == "ingest_delivery_log":
            return [
                {
                    "run_id": "proxibid-run",
                    "listing_id": "proxibid-escape",
                    "listing_url": "https://www.proxibid.com/lotInformation/101102033",
                    "status": "skipped_ceiling",
                    "error_message": "pricing_maturity_proxy | bid=$4,000 mmr=$20,000 tier=standard",
                    "created_at": "2026-06-05T19:13:22+00:00",
                }
            ]
        if table == "sonar_listings":
            return [
                {
                    "source_site": "proxibid",
                    "year": 2019,
                    "make": "Ford",
                    "model": "Escape",
                    "state": "AL",
                    "mileage": 49237,
                    "vin": "1FMCU9GDXKUB65351",
                    "current_bid": 4000,
                    "auction_end_date": "2026-06-10T00:00:00+00:00",
                    "created_at": "2026-06-05T19:13:20+00:00",
                    "title": "2019 Ford Escape 4x4",
                    "listing_id": "proxibid-escape",
                    "listing_url": "https://www.proxibid.com/lotInformation/101102033",
                }
            ]
        return []

    monkeypatch.setattr(report_pricing_blocked_source_candidates, "_fetch_postgrest_rows", fake_fetch)

    rows = report_pricing_blocked_source_candidates.fetch_rows_via_rest(
        "https://example.supabase.co/rest/v1",
        "service-key",
        lookback_days=1,
        max_mileage=50000,
        max_age_years=4,
        include_dirty=False,
        limit=50,
        now=datetime(2026, 6, 6, 1, 0, tzinfo=timezone.utc),
    )

    assert len(rows) == 1
    assert rows[0]["clean_filter_exclusion"] == "age_or_mileage_exceeded"
    assert (
        report_pricing_blocked_source_candidates.classify_source_candidate(rows[0])
        == "age_mileage_excluded_pricing_gap"
    )


def test_fetch_rows_via_rest_reports_proxy_skip_without_listing_evidence(monkeypatch):
    def fake_fetch(base_url, service_role_key, table, query):
        if table == "ingest_delivery_log":
            return [
                {
                    "run_id": "run-proxy",
                    "listing_id": "proxibid-asset",
                    "listing_url": "https://example.com/proxibid-asset",
                    "status": "skipped_ceiling",
                    "error_message": "pricing_maturity_proxy | bid=$18,000 mmr=$22,000 tier=premium",
                    "created_at": "2026-06-05T23:00:00+00:00",
                }
            ]
        if table == "sonar_listings":
            return []
        if table in {"market_prices", "dealer_sales"}:
            return []
        raise AssertionError(table)

    monkeypatch.setattr(report_pricing_blocked_source_candidates, "_fetch_postgrest_rows", fake_fetch)

    rows = report_pricing_blocked_source_candidates.fetch_rows_via_rest(
        "https://example.supabase.co/rest/v1",
        "service-key",
        lookback_days=1,
        max_mileage=50000,
        max_age_years=4,
        include_dirty=False,
        limit=50,
        now=datetime(2026, 6, 6, 1, 0, tzinfo=timezone.utc),
    )

    assert len(rows) == 1
    assert rows[0]["listing_found"] is False
    assert rows[0]["listing_id"] == "proxibid-asset"
    assert (
        report_pricing_blocked_source_candidates.classify_source_candidate(rows[0])
        == "listing_evidence_missing"
    )


def test_fetch_rows_via_rest_reports_proxy_skip_without_listing_key(monkeypatch):
    def fake_fetch(base_url, service_role_key, table, query):
        if table == "ingest_delivery_log":
            return [
                {
                    "run_id": "proxibid-run",
                    "listing_id": "",
                    "listing_url": "",
                    "status": "skipped_ceiling",
                    "error_message": "pricing_maturity_proxy | bid=$18,000 mmr=$22,000 tier=premium",
                    "created_at": "2026-06-05T23:00:00+00:00",
                }
            ]
        if table in {"sonar_listings", "market_prices", "dealer_sales"}:
            return []
        raise AssertionError(table)

    monkeypatch.setattr(report_pricing_blocked_source_candidates, "_fetch_postgrest_rows", fake_fetch)

    rows = report_pricing_blocked_source_candidates.fetch_rows_via_rest(
        "https://example.supabase.co/rest/v1",
        "service-key",
        lookback_days=1,
        max_mileage=50000,
        max_age_years=4,
        include_dirty=False,
        limit=50,
        now=datetime(2026, 6, 6, 1, 0, tzinfo=timezone.utc),
    )

    assert len(rows) == 1
    assert rows[0]["listing_key_present"] is False
    assert rows[0]["listing_found"] is False
    assert (
        report_pricing_blocked_source_candidates.classify_source_candidate(rows[0])
        == "listing_key_missing"
    )


def test_fetch_rows_via_rest_includes_proxy_margin_floor_rows(monkeypatch):
    def fake_fetch(base_url, service_role_key, table, query):
        if table == "ingest_delivery_log":
            return [
                {
                    "listing_id": "asset-margin",
                    "listing_url": "https://example.com/margin",
                    "status": "skipped_margin",
                    "error_message": "margin_below_floor | margin=$325 floor=$1500 tier=premium bid=$20900 mmr=$26000 cost=$25675 max_bid=$0 headroom=$0 pricing=proxy",
                    "created_at": "2026-06-05T03:41:16+00:00",
                }
            ]
        if table == "sonar_listings":
            return [
                {
                    "source_site": "govdeals",
                    "year": 2022,
                    "make": "BMW",
                    "model": "X1",
                    "state": "TN",
                    "mileage": 40718,
                    "vin": "WBXJG9C02N5P20226",
                    "current_bid": 20900,
                    "auction_end_date": "2026-06-10T00:00:00+00:00",
                    "created_at": "2026-06-05T03:41:15+00:00",
                    "title": "2022 BMW X1",
                    "listing_id": "asset-margin",
                    "listing_url": "https://example.com/margin",
                }
            ]
        return []

    monkeypatch.setattr(report_pricing_blocked_source_candidates, "_fetch_postgrest_rows", fake_fetch)

    rows = report_pricing_blocked_source_candidates.fetch_rows_via_rest(
        "https://example.supabase.co/rest/v1",
        "service-key",
        lookback_days=1,
        max_mileage=50000,
        max_age_years=4,
        include_dirty=False,
        limit=50,
        now=datetime(2026, 6, 5, 4, 0, tzinfo=timezone.utc),
    )

    assert len(rows) == 1
    assert report_pricing_blocked_source_candidates.classify_source_candidate(rows[0]) == "below_margin_floor"


def test_postgrest_416_range_is_treated_as_empty_page(monkeypatch):
    class EmptyBody:
        def read(self):
            return b'{"code":"PGRST103","message":"Requested range not satisfiable"}'

        def close(self):
            return None

    def fake_urlopen(request, timeout):
        raise urllib_error.HTTPError(
            request.full_url,
            416,
            "Range Not Satisfiable",
            hdrs={},
            fp=EmptyBody(),
        )

    monkeypatch.setattr(report_pricing_blocked_source_candidates.urllib_request, "urlopen", fake_urlopen)

    rows = report_pricing_blocked_source_candidates._postgrest_get_json(
        "https://example.supabase.co/rest/v1",
        "service-key",
        "sonar_listings",
        [("select", "*")],
        offset=1000,
        limit=1000,
    )

    assert rows == []
