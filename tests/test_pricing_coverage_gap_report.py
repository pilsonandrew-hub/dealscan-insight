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

    assert "evidence=blocked_no_internal_comp_evidence" in formatted
    assert "expected_close=16162.13" in formatted
    assert "retail_proxy=40500" in formatted
