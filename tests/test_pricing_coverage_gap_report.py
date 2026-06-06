import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "report_pricing_coverage_gaps.py"
sys.path.insert(0, str(SCRIPT_PATH.parent))
SPEC = importlib.util.spec_from_file_location("report_pricing_coverage_gaps", SCRIPT_PATH)
report_pricing_coverage_gaps = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(report_pricing_coverage_gaps)


def test_classify_gap_reports_existing_market_price_coverage():
    row = {
        "usable_market_prices_matches": 1,
        "usable_dealer_sales_matches": 0,
        "usable_opportunity_history": 0,
    }

    assert report_pricing_coverage_gaps.classify_gap(row) == "covered_by_market_prices"


def test_classify_gap_requires_two_dealer_sales_before_coverage():
    row = {
        "usable_market_prices_matches": 0,
        "usable_dealer_sales_matches": 2,
        "usable_opportunity_history": 0,
    }

    assert report_pricing_coverage_gaps.classify_gap(row) == "covered_by_dealer_sales"


def test_classify_gap_separates_seedable_and_insufficient_history():
    seedable = {
        "usable_market_prices_matches": 0,
        "usable_dealer_sales_matches": 0,
        "usable_opportunity_history": 5,
    }
    insufficient = {
        "usable_market_prices_matches": 0,
        "usable_dealer_sales_matches": 0,
        "usable_opportunity_history": 1,
    }

    assert report_pricing_coverage_gaps.classify_gap(seedable) == "seedable_from_internal_history"
    assert report_pricing_coverage_gaps.classify_gap(insufficient) == "insufficient_internal_history"


def test_classify_gap_blocks_when_no_internal_comp_evidence_exists():
    row = {
        "usable_market_prices_matches": 0,
        "usable_dealer_sales_matches": 0,
        "usable_opportunity_history": 0,
    }

    assert report_pricing_coverage_gaps.classify_gap(row) == "blocked_no_internal_comp_evidence"


def test_market_and_dealer_sales_matches_allow_runtime_fallback_beyond_exact_state():
    row = {
        "year": 2023,
        "make": "toyota",
        "model": "camry",
        "state": "va",
    }
    now = report_pricing_coverage_gaps.datetime.fromisoformat("2026-06-05T07:00:00+00:00")

    market_total, market_usable = report_pricing_coverage_gaps._market_price_matches(
        row,
        [
            {
                "year": 2023,
                "make": "toyota",
                "model": "camry",
                "state": None,
                "avg_price": 26000,
                "low_price": 24000,
                "high_price": 28000,
                "sample_size": 3,
                "expires_at": "2026-06-19T00:00:00+00:00",
                "source": "external_retail_listing_comp",
            }
        ],
        now,
    )
    sales_total, sales_usable = report_pricing_coverage_gaps._dealer_sales_matches(
        row,
        [
            {"year": 2023, "make": "toyota", "model": "camry", "state": "md", "sale_price": 25000, "sale_date": "2026-05-01T00:00:00+00:00"},
            {"year": 2022, "make": "toyota", "model": "camry", "state": "dc", "sale_price": 24000, "sale_date": "2026-04-01T00:00:00+00:00"},
        ],
        now,
    )

    assert (market_total, market_usable) == (1, 1)
    assert (sales_total, sales_usable) == (2, 2)


def test_format_gap_row_includes_evidence_and_economics():
    row = {
        "year": 2020,
        "make": "dodge",
        "model": "durango",
        "state": "ms",
        "source": "govdeals",
        "source_site": None,
        "is_active": True,
        "dos_score": 86.9,
        "investment_grade": "Platinum",
        "bid_headroom": 12670,
        "current_bid": 10600,
        "expected_close_bid": 16162.13,
        "retail_asking_price_estimate": 40500,
        "usable_market_prices_matches": 0,
        "market_prices_matches": 0,
        "usable_dealer_sales_matches": 0,
        "dealer_sales_matches": 0,
        "usable_opportunity_history": 0,
        "market_comp_opportunity_history": 1,
        "title": "2020 Dodge Durango SRT",
    }

    formatted = report_pricing_coverage_gaps.format_gap_row(row)

    assert "origin=opportunity_proxy" in formatted
    assert "opportunity_active=True" in formatted
    assert "auction_active=None" in formatted
    assert "evidence=blocked_no_internal_comp_evidence" in formatted
    assert "expected_close=16162.13" in formatted
    assert "retail_proxy=40500" in formatted


def test_report_sql_labels_opportunity_proxy_activity_explicitly():
    assert "'opportunity_proxy' as candidate_origin" in report_pricing_coverage_gaps.REPORT_SQL
    assert "is_active as opportunity_active" in report_pricing_coverage_gaps.REPORT_SQL
    assert "null::boolean as auction_active" in report_pricing_coverage_gaps.REPORT_SQL


def test_fetch_gap_rows_via_rest_classifies_live_coverage_sources(monkeypatch):
    def fake_fetch(base_url, service_role_key, table, query):
        assert base_url == "https://example.supabase.co/rest/v1"
        assert service_role_key == "service-key"
        if table == "opportunities":
            return [
                {
                    "id": "proxy-covered-market",
                    "source": "govdeals",
                    "source_site": "govdeals",
                    "title": "2022 BMW X1",
                    "year": 2022,
                    "make": "BMW",
                    "model": "X1",
                    "state": "TN",
                    "mileage": 40718,
                    "vin": "WBXJG7C02N5U88160",
                    "pricing_maturity": "proxy",
                    "pricing_source": "proxy",
                    "is_active": True,
                    "dos_score": 0,
                    "processed_at": "2026-06-05T03:41:16+00:00",
                    "bid_headroom": -1,
                    "investment_grade": "Rejected",
                    "current_bid": 20900,
                    "expected_close_bid": 20900,
                    "acquisition_price_basis": "current_bid",
                    "projected_total_cost": 25675,
                    "max_bid": 0,
                    "retail_asking_price_estimate": 26000,
                    "listing_url": "https://example.test/1",
                    "retail_comp_price_estimate": 0,
                    "retail_comp_count": 0,
                    "retail_comp_confidence": 0,
                },
                {
                    "id": "proxy-seedable-history",
                    "source": "govdeals",
                    "source_site": "govdeals",
                    "title": "2022 Dodge Durango",
                    "year": 2022,
                    "make": "Dodge",
                    "model": "Durango",
                    "state": "MS",
                    "mileage": 43092,
                    "vin": "1C4RDJFG5NC184072",
                    "pricing_maturity": "proxy",
                    "pricing_source": "proxy",
                    "is_active": True,
                    "dos_score": 0,
                    "processed_at": "2026-06-02T20:16:08+00:00",
                    "bid_headroom": -1,
                    "investment_grade": "Rejected",
                    "current_bid": 20000,
                    "expected_close_bid": 20000,
                    "acquisition_price_basis": "current_bid",
                    "projected_total_cost": 24000,
                    "max_bid": 0,
                    "retail_asking_price_estimate": 30000,
                    "listing_url": "https://example.test/2",
                    "retail_comp_price_estimate": 0,
                    "retail_comp_count": 0,
                    "retail_comp_confidence": 0,
                },
                *[
                    {
                        "id": f"history-{index}",
                        "source": "govdeals",
                        "source_site": "govdeals",
                        "title": "Historical Durango",
                        "year": 2022,
                        "make": "Dodge",
                        "model": "Durango",
                        "state": "MS",
                        "mileage": 30000,
                        "vin": f"HISTORY{index}",
                        "pricing_maturity": "market_comp",
                        "pricing_source": "dealer_sales_history",
                        "is_active": False,
                        "dos_score": 82,
                        "processed_at": "2026-05-01T00:00:00+00:00",
                        "bid_headroom": 1000,
                        "investment_grade": "Gold",
                        "current_bid": 15000,
                        "expected_close_bid": 15000,
                        "acquisition_price_basis": "current_bid",
                        "projected_total_cost": 18000,
                        "max_bid": 17000,
                        "retail_asking_price_estimate": 30000,
                        "listing_url": f"https://example.test/history/{index}",
                        "retail_comp_price_estimate": 30000,
                        "retail_comp_count": 2,
                        "retail_comp_confidence": 0.7,
                    }
                    for index in range(5)
                ],
            ]
        if table == "market_prices":
            return [
                {
                    "id": "market-1",
                    "year": 2022,
                    "make": "bmw",
                    "model": "x1",
                    "state": "tn",
                    "avg_price": 26000,
                    "low_price": 23000,
                    "high_price": 29000,
                    "sample_size": 3,
                    "expires_at": "2026-07-01T00:00:00+00:00",
                    "source": "seeded_market_comp",
                }
            ]
        if table == "dealer_sales":
            return []
        if table == "ingest_delivery_log":
            return []
        raise AssertionError(table)

    monkeypatch.setattr(report_pricing_coverage_gaps, "_fetch_postgrest_rows", fake_fetch)

    rows = report_pricing_coverage_gaps.fetch_gap_rows_via_rest(
        "https://example.supabase.co",
        "service-key",
        lookback_days=14,
        max_mileage=50000,
        max_age_years=4,
        limit=20,
        now=report_pricing_coverage_gaps.datetime.fromisoformat("2026-06-05T04:00:00+00:00"),
    )

    by_id = {row["id"]: row for row in rows}
    assert by_id["proxy-covered-market"]["candidate_origin"] == "opportunity_proxy"
    assert by_id["proxy-covered-market"]["opportunity_active"] is True
    assert by_id["proxy-covered-market"]["auction_active"] is None
    assert report_pricing_coverage_gaps.classify_gap(by_id["proxy-covered-market"]) == "covered_by_market_prices"
    assert report_pricing_coverage_gaps.classify_gap(by_id["proxy-seedable-history"]) == "seedable_from_internal_history"


def test_fetch_gap_rows_via_rest_excludes_over_age_proxy_opportunities(monkeypatch):
    def fake_fetch(base_url, service_role_key, table, query):
        if table == "opportunities":
            return [
                {
                    "id": "over-age-proxy",
                    "source": "proxibid",
                    "source_site": "proxibid",
                    "title": "2019 Ford Escape",
                    "year": 2019,
                    "make": "Ford",
                    "model": "Escape",
                    "state": "AL",
                    "mileage": 30000,
                    "vin": "1FMCU9GD0KUA00001",
                    "pricing_maturity": "proxy",
                    "pricing_source": "proxy",
                    "is_active": True,
                    "processed_at": "2026-06-05T12:00:00+00:00",
                },
                {
                    "id": "governed-age-proxy",
                    "source": "proxibid",
                    "source_site": "proxibid",
                    "title": "2022 Ford Escape",
                    "year": 2022,
                    "make": "Ford",
                    "model": "Escape",
                    "state": "AL",
                    "mileage": 30000,
                    "vin": "1FMCU9GD0NUA00001",
                    "pricing_maturity": "proxy",
                    "pricing_source": "proxy",
                    "is_active": True,
                    "processed_at": "2026-06-05T12:00:00+00:00",
                },
            ]
        if table in {"market_prices", "dealer_sales", "ingest_delivery_log"}:
            return []
        raise AssertionError(table)

    monkeypatch.setattr(report_pricing_coverage_gaps, "_fetch_postgrest_rows", fake_fetch)

    rows = report_pricing_coverage_gaps.fetch_gap_rows_via_rest(
        "https://example.supabase.co",
        "service-key",
        lookback_days=1,
        max_mileage=50000,
        max_age_years=4,
        limit=20,
        now=report_pricing_coverage_gaps.datetime.fromisoformat("2026-06-05T12:00:00+00:00"),
    )

    assert [row["id"] for row in rows] == ["governed-age-proxy"]


def test_fetch_gap_rows_via_rest_includes_active_delivery_pricing_skips(monkeypatch):
    def fake_fetch(base_url, service_role_key, table, query):
        assert base_url == "https://example.supabase.co/rest/v1"
        assert service_role_key == "service-key"
        if table == "opportunities":
            return []
        if table == "ingest_delivery_log":
            return [
                {
                    "run_id": "source-run-1",
                    "listing_id": "publicsurplus:auction-1",
                    "listing_url": "https://example.test/auction-1",
                    "status": "skipped_ceiling",
                    "error_message": "pricing_maturity_proxy | bid=$8,300 mmr=$22,000 tier=premium",
                    "created_at": "2026-06-05T06:25:44+00:00",
                }
            ]
        if table == "sonar_listings":
            return [
                {
                    "source_site": "publicsurplus",
                    "year": 2023,
                    "make": "Toyota",
                    "model": "Camry",
                    "state": "VA",
                    "mileage": 7812,
                    "vin": "4T1C31AK9PU056835",
                    "current_bid": 8300,
                    "auction_end_date": "2026-06-05T12:00:00+00:00",
                    "created_at": "2026-06-05T06:25:44+00:00",
                    "title": "2023 Toyota Camry",
                    "listing_id": "publicsurplus:auction-1",
                    "listing_url": "https://example.test/auction-1",
                }
            ]
        if table == "market_prices":
            return []
        if table == "dealer_sales":
            return []
        raise AssertionError(table)

    monkeypatch.setattr(report_pricing_coverage_gaps, "_fetch_postgrest_rows", fake_fetch)

    rows = report_pricing_coverage_gaps.fetch_gap_rows_via_rest(
        "https://example.supabase.co",
        "service-key",
        lookback_days=1,
        max_mileage=50000,
        max_age_years=4,
        limit=20,
        now=report_pricing_coverage_gaps.datetime.fromisoformat("2026-06-05T07:00:00+00:00"),
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["candidate_origin"] == "delivery_pricing_skip"
    assert row["source_site"] == "publicsurplus"
    assert "is_active" not in row
    assert row["opportunity_active"] is None
    assert row["auction_active"] is True
    assert report_pricing_coverage_gaps.classify_gap(row) == "blocked_no_internal_comp_evidence"


def test_format_delivery_pricing_skip_does_not_label_it_as_active_opportunity():
    row = {
        "candidate_origin": "delivery_pricing_skip",
        "year": 2023,
        "make": "toyota",
        "model": "camry",
        "state": "va",
        "source": "publicsurplus",
        "source_site": "publicsurplus",
        "is_active": True,
        "auction_active": True,
        "opportunity_active": None,
        "dos_score": None,
        "investment_grade": None,
        "bid_headroom": None,
        "current_bid": 8300,
        "expected_close_bid": 8300,
        "retail_asking_price_estimate": 22000,
        "usable_market_prices_matches": 0,
        "market_prices_matches": 0,
        "usable_dealer_sales_matches": 0,
        "dealer_sales_matches": 0,
        "usable_opportunity_history": 0,
        "market_comp_opportunity_history": 0,
        "title": "2023 Toyota Camry",
    }

    formatted = report_pricing_coverage_gaps.format_gap_row(row)

    assert "origin=delivery_pricing_skip" in formatted
    assert "opportunity_active=None" in formatted
    assert "auction_active=True" in formatted
    assert " active=True " not in formatted
