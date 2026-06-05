import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "report_delivery_rejection_candidates.py"
sys.path.insert(0, str(SCRIPT_PATH.parent))
SPEC = importlib.util.spec_from_file_location("report_delivery_rejection_candidates", SCRIPT_PATH)
report_delivery_rejection_candidates = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(report_delivery_rejection_candidates)


def test_classify_margin_row_as_clean_margin_rejection():
    row = {
        "status": "skipped_margin",
        "error_message": "margin_below_floor",
        "year": 2024,
        "mileage": 12000,
        "vin_present": True,
        "auction_active": True,
    }

    assert report_delivery_rejection_candidates.classify_rejection(row, now_year=2026) == "clean_margin_rejection"


def test_classify_clean_age_mileage_gate_as_unexpected():
    row = {
        "status": "skipped_gate",
        "error_message": "age_or_mileage_exceeded",
        "year": 2024,
        "mileage": 12000,
        "vin_present": True,
        "auction_active": True,
    }

    assert (
        report_delivery_rejection_candidates.classify_rejection(row, now_year=2026)
        == "unexpected_clean_age_mileage_gate"
    )


def test_classify_policy_gate_and_dirty_rows():
    policy = {
        "status": "skipped_gate",
        "error_message": "title_brand_rejected (listing_text matched 'rebuilt')",
        "year": 2024,
        "mileage": 12000,
        "vin_present": True,
        "auction_active": True,
    }
    dirty = {
        "status": "skipped_gate",
        "error_message": "age_or_mileage_exceeded",
        "year": 2024,
        "mileage": None,
        "vin_present": False,
        "auction_active": True,
    }

    assert report_delivery_rejection_candidates.classify_rejection(policy, now_year=2026) == "policy_gate_rejection"
    assert report_delivery_rejection_candidates.classify_rejection(dirty, now_year=2026) == "dirty_source_row"


def test_fetch_rows_via_rest_joins_delivery_rows_to_listing_facts(monkeypatch):
    def fake_fetch(base_url, service_role_key, table, query):
        if table == "ingest_delivery_log":
            return [
                {
                    "run_id": "run-1",
                    "listing_id": "asset-1",
                    "listing_url": "https://example.com/asset-1",
                    "status": "skipped_margin",
                    "error_message": "margin_below_floor",
                    "created_at": "2026-06-05T01:00:00+00:00",
                }
            ]
        if table == "sonar_listings":
            return [
                {
                    "source_site": "govdeals",
                    "year": 2024,
                    "make": "Toyota",
                    "model": "Tacoma",
                    "state": "TX",
                    "mileage": 12000,
                    "vin": "3TMAZ5CN0PM202309",
                    "current_bid": 22000,
                    "auction_end_date": "2026-06-06T01:00:00+00:00",
                    "created_at": "2026-06-05T00:59:00+00:00",
                    "listing_id": "asset-1",
                    "listing_url": "https://example.com/asset-1",
                }
            ]
        raise AssertionError(table)

    monkeypatch.setattr(report_delivery_rejection_candidates, "_fetch_postgrest_rows", fake_fetch)
    rows = report_delivery_rejection_candidates.fetch_rows_via_rest(
        "https://example.supabase.co",
        "service-key",
        lookback_hours=4,
        max_mileage=50000,
        max_age_years=4,
        include_dirty=False,
        limit=50,
        now=datetime(2026, 6, 5, 1, 30, tzinfo=timezone.utc),
    )

    assert len(rows) == 1
    assert rows[0]["source_site"] == "govdeals"
    assert rows[0]["classification"] == "clean_margin_rejection"

