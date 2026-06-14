import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "refresh_market_prices_from_completed_sales.py"
sys.path.insert(0, str(SCRIPT_PATH.parent))
SPEC = importlib.util.spec_from_file_location("refresh_market_prices_from_completed_sales", SCRIPT_PATH)
refresh_market_prices_from_completed_sales = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(refresh_market_prices_from_completed_sales)


def test_preview_market_price_from_competitor_sales_group():
    rows = [
        {
            "year": 2020,
            "make": "Ford",
            "model": "Escape",
            "state": "SC",
            "sale_price": price,
            "auction_end_date": "2026-05-01T00:00:00+00:00",
            "source": "proxibid",
        }
        for price in (17000, 18000, 19000, 20000, 21000)
    ]

    preview = refresh_market_prices_from_completed_sales.build_market_price_preview(
        rows,
        source="competitor_sales",
        source_run_id="pricing-recovery-test",
        now=datetime(2026, 6, 14, tzinfo=timezone.utc),
        ttl_days=14,
        min_sample_size=5,
    )

    assert preview["year"] == 2020
    assert preview["make"] == "ford"
    assert preview["model"] == "escape"
    assert preview["state"] == "sc"
    assert preview["avg_price"] == 19000.0
    assert preview["low_price"] == 17000.0
    assert preview["high_price"] == 21000.0
    assert preview["sample_size"] == 5
    assert preview["source"] == "competitor_sales"
    assert preview["source_run_id"] == "pricing-recovery-test"
    assert preview["last_updated"] == "2026-05-01T00:00:00+00:00"
    assert preview["expires_at"] == "2026-06-28T00:00:00+00:00"
    assert "proxy" not in preview["confidence_notes"].lower()


def test_preview_market_price_preserves_dealer_sales_source():
    rows = [
        {
            "year": 2020,
            "make": "Ford",
            "model": "Escape",
            "state": "SC",
            "sale_price": price,
            "sale_date": "2026-05-01T00:00:00+00:00",
        }
        for price in (17000, 18000, 19000, 20000, 21000)
    ]

    preview = refresh_market_prices_from_completed_sales.build_market_price_preview(
        rows,
        source="dealer_sales",
        source_run_id="pricing-recovery-test",
        now=datetime(2026, 6, 14, tzinfo=timezone.utc),
        ttl_days=14,
        min_sample_size=5,
    )

    assert preview["source"] == "dealer_sales"
    assert preview["metadata"]["seed_basis"] == "dealer_sales"


def test_preview_rejects_untrusted_source_names():
    rows = [
        {
            "year": 2020,
            "make": "Ford",
            "model": "Escape",
            "state": "SC",
            "sale_price": price,
            "auction_end_date": "2026-05-01T00:00:00+00:00",
        }
        for price in (17000, 18000, 19000, 20000, 21000)
    ]

    assert refresh_market_prices_from_completed_sales.build_market_price_preview(
        rows,
        source="active_bid_proxy",
        source_run_id="pricing-recovery-test",
        now=datetime(2026, 6, 14, tzinfo=timezone.utc),
        ttl_days=14,
        min_sample_size=5,
    ) is None


def test_preview_rejects_sparse_or_zero_completed_sales():
    sparse_rows = [
        {
            "year": 2020,
            "make": "Ford",
            "model": "Escape",
            "state": "SC",
            "sale_price": price,
            "auction_end_date": "2026-05-01T00:00:00+00:00",
            "source": "proxibid",
        }
        for price in (17000, 18000)
    ]
    zero_rows = [
        {
            "year": 2020,
            "make": "Ford",
            "model": "Escape",
            "state": "SC",
            "sale_price": 0,
            "auction_end_date": "2026-05-01T00:00:00+00:00",
            "source": "proxibid",
        }
        for _ in range(5)
    ]

    now = datetime(2026, 6, 14, tzinfo=timezone.utc)

    assert refresh_market_prices_from_completed_sales.build_market_price_preview(
        sparse_rows,
        source="competitor_sales",
        source_run_id="pricing-recovery-test",
        now=now,
        ttl_days=14,
        min_sample_size=5,
    ) is None
    assert refresh_market_prices_from_completed_sales.build_market_price_preview(
        zero_rows,
        source="competitor_sales",
        source_run_id="pricing-recovery-test",
        now=now,
        ttl_days=14,
        min_sample_size=5,
    ) is None


def test_preview_rejects_stale_completed_sales():
    rows = [
        {
            "year": 2020,
            "make": "Ford",
            "model": "Escape",
            "state": "SC",
            "sale_price": price,
            "auction_end_date": "2024-01-01T00:00:00+00:00",
            "source": "proxibid",
        }
        for price in (17000, 18000, 19000, 20000, 21000)
    ]

    assert refresh_market_prices_from_completed_sales.build_market_price_preview(
        rows,
        source="competitor_sales",
        source_run_id="pricing-recovery-test",
        now=datetime(2026, 6, 14, tzinfo=timezone.utc),
        ttl_days=14,
        min_sample_size=5,
    ) is None


def test_preview_rejects_mixed_vehicle_groups():
    rows = [
        {
            "year": 2020,
            "make": "Ford",
            "model": "Escape",
            "state": "SC",
            "sale_price": price,
            "auction_end_date": "2026-05-01T00:00:00+00:00",
            "source": "proxibid",
        }
        for price in (17000, 18000, 19000, 20000, 21000)
    ]
    rows.append(
        {
            "year": 2020,
            "make": "Ford",
            "model": "Explorer",
            "state": "SC",
            "sale_price": 30000,
            "auction_end_date": "2026-05-01T00:00:00+00:00",
            "source": "proxibid",
        }
    )

    assert refresh_market_prices_from_completed_sales.build_market_price_preview(
        rows,
        source="competitor_sales",
        source_run_id="pricing-recovery-test",
        now=datetime(2026, 6, 14, tzinfo=timezone.utc),
        ttl_days=14,
        min_sample_size=5,
    ) is None


def test_apply_requires_confirmation():
    assert refresh_market_prices_from_completed_sales.confirm_apply(apply=True, confirmation="") is False
    assert (
        refresh_market_prices_from_completed_sales.confirm_apply(
            apply=True,
            confirmation="REFRESH_MARKET_PRICES_FROM_COMPLETED_SALES",
        )
        is True
    )
    assert refresh_market_prices_from_completed_sales.confirm_apply(apply=False, confirmation="") is True
