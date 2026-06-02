import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "report_pricing_blocked_source_candidates.py"
sys.path.insert(0, str(SCRIPT_PATH.parent))
SPEC = importlib.util.spec_from_file_location("report_pricing_blocked_source_candidates", SCRIPT_PATH)
report_pricing_blocked_source_candidates = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(report_pricing_blocked_source_candidates)


def test_parse_proxy_skip_reason_extracts_bid_mmr_and_tier():
    parsed = report_pricing_blocked_source_candidates.parse_proxy_skip_reason(
        "pricing_maturity_proxy | bid=$22,000 max_bid=$0 mmr=$31,000 headroom=$-22,000 tier=premium"
    )

    assert parsed == {
        "bid": 22000.0,
        "mmr": 31000.0,
        "headroom": -22000.0,
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
