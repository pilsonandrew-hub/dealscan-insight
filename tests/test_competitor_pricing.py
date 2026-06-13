import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.ingest.competitor_pricing import (
    COMPETITOR_COMP_MIN_COUNT,
    competitor_comp_is_usable,
    compute_divergence,
    get_competitor_comps,
    normalize_vehicle_class,
    summarize_comps,
)


def _row(price, year=2022, mileage=40000, source="govdeals", end="2026-05-01T00:00:00Z"):
    return {
        "sale_price": price,
        "year": year,
        "mileage": mileage,
        "source": source,
        "auction_end_date": end,
    }


def test_normalize_vehicle_class_matches_target_classes():
    assert normalize_vehicle_class("Ford", "F-150") == "f-150"
    assert normalize_vehicle_class("Ford", "F150 XLT") == "f-150"
    assert normalize_vehicle_class("Ford", "F-250 Super Duty") == "f-250"
    assert normalize_vehicle_class("Chevrolet", "Silverado 1500 LT") == "silverado-1500"
    assert normalize_vehicle_class("Chevrolet", "Silverado") == "silverado-1500"


def test_normalize_vehicle_class_returns_none_for_untracked():
    assert normalize_vehicle_class("Toyota", "Camry") is None
    assert normalize_vehicle_class("", "") is None
    # F-250 must not be misread as F-150.
    assert normalize_vehicle_class("Ford", "F-250") == "f-250"


def test_summarize_comps_computes_median_count_and_date_range():
    rows = [
        _row(18000, end="2026-01-01T00:00:00Z"),
        _row(19000, end="2026-02-01T00:00:00Z"),
        _row(20000, end="2026-03-01T00:00:00Z"),
        _row(21000, source="publicsurplus", end="2026-04-01T00:00:00Z"),
        _row(22000, source="govplanet", end="2026-05-01T00:00:00Z"),
    ]
    summary = summarize_comps(rows, year=2022, mileage=40000)

    assert summary["competitor_comp_count"] == 5
    assert summary["competitor_comp_price"] == 20000.0
    assert summary["competitor_comp_low"] <= 20000.0 <= summary["competitor_comp_high"]
    assert summary["competitor_comp_date_start"].startswith("2026-01-01")
    assert summary["competitor_comp_date_end"].startswith("2026-05-01")
    assert summary["competitor_comp_sources"] == ["govdeals", "govplanet", "publicsurplus"]
    assert summary["pricing_source"] == "competitor_sales"


def test_summarize_comps_filters_out_of_window_year_and_mileage():
    rows = [
        _row(20000, year=2022, mileage=40000),
        _row(99000, year=2010, mileage=40000),   # year out of +/-2 window
        _row(98000, year=2022, mileage=200000),  # mileage out of +/-25k window
    ]
    summary = summarize_comps(rows, year=2022, mileage=40000)
    assert summary["competitor_comp_count"] == 1
    assert summary["competitor_comp_price"] == 20000.0


def test_summarize_comps_keeps_rows_with_missing_mileage():
    rows = [_row(20000, mileage=None), _row(22000, mileage=None)]
    summary = summarize_comps(rows, year=2022, mileage=40000)
    assert summary["competitor_comp_count"] == 2


def test_summarize_comps_drops_nonpositive_prices():
    rows = [_row(0), _row(-5), _row(20000)]
    summary = summarize_comps(rows, year=2022, mileage=40000)
    assert summary["competitor_comp_count"] == 1


def test_competitor_comp_is_usable_requires_min_count():
    usable = {"competitor_comp_price": 20000, "competitor_comp_count": COMPETITOR_COMP_MIN_COUNT}
    too_few = {"competitor_comp_price": 20000, "competitor_comp_count": COMPETITOR_COMP_MIN_COUNT - 1}
    no_price = {"competitor_comp_price": 0, "competitor_comp_count": 10}
    assert competitor_comp_is_usable(usable) is True
    assert competitor_comp_is_usable(too_few) is False
    assert competitor_comp_is_usable(no_price) is False
    assert competitor_comp_is_usable(None) is False


def test_compute_divergence_flags_above_threshold():
    flagged = compute_divergence(20000, 24000)  # +20%
    assert flagged["divergence_pct"] == 0.2
    assert flagged["divergence_flag"] is True

    within = compute_divergence(20000, 21000)  # +5%
    assert within["divergence_flag"] is False

    assert compute_divergence(0, 20000)["divergence_pct"] is None
    assert compute_divergence(None, 20000)["divergence_flag"] is False


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def select(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def ilike(self, *a, **k):
        return self

    def gte(self, *a, **k):
        return self

    def lte(self, *a, **k):
        return self

    def order(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def execute(self):
        return type("Resp", (), {"data": self._rows})()


class _FakeClient:
    def __init__(self, rows):
        self._rows = rows
        self.calls = 0

    def table(self, name):
        self.calls += 1
        assert name == "competitor_sales"
        return _FakeQuery(self._rows)


def test_get_competitor_comps_with_client_returns_summary():
    rows = [
        {"id": i, "sale_price": 18000 + i * 1000, "year": 2022, "mileage": 40000,
         "source": "govdeals", "make": "Ford", "model": "F-150",
         "vehicle_class": "f-150", "auction_end_date": f"2026-0{i+1}-01T00:00:00Z"}
        for i in range(5)
    ]
    client = _FakeClient(rows)
    result = get_competitor_comps(year=2022, make="Ford", model="F-150", mileage=40000, supabase_client=client)
    assert result["competitor_comp_count"] == 5
    assert result["vehicle_class"] == "f-150"
    assert result["pricing_source"] == "competitor_sales"


def test_get_competitor_comps_without_client_is_safe():
    result = get_competitor_comps(year=2022, make="Ford", model="F-150", mileage=40000, supabase_client=None)
    assert result["competitor_comp_count"] == 0
    assert result["vehicle_class"] == "f-150"
    assert result["pricing_source"] is None
