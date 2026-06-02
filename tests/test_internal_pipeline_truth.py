from fastapi import HTTPException
from types import SimpleNamespace

from webapp.routers import internal


def test_internal_secret_rejects_missing(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_SECRET", "internal-secret")
    try:
        internal.verify_internal_secret(None)
    except HTTPException as exc:
        assert exc.status_code == 401
    else:
        raise AssertionError("missing internal secret should reject")


def test_internal_secret_accepts(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_SECRET", "internal-secret")
    internal.verify_internal_secret("internal-secret")


class _Query:
    def __init__(self, rows, count=None):
        self.rows = rows
        self.count = count if count is not None else len(rows)
        self.filters = []
        self._limit = None
        self._order = None

    def select(self, *_args, **_kwargs): return self
    def eq(self, column, value):
        self.filters.append(("eq", column, value))
        return self
    def gt(self, column, value):
        self.filters.append(("gt", column, value))
        return self
    def gte(self, column, value):
        self.filters.append(("gte", column, value))
        return self
    def not_(self, column, operator, value):
        self.filters.append(("not_", column, operator, value))
        return self
    def limit(self, value):
        self._limit = value
        return self
    def order(self, column, desc=False, **_kwargs):
        self._order = (column, desc)
        return self
    def execute(self):
        rows = list(self.rows)
        for filter_spec in self.filters:
            method, column, *values = filter_spec
            if method == "eq":
                rows = [row for row in rows if row.get(column) == values[0]]
            elif method == "gt":
                rows = [row for row in rows if row.get(column) is not None and row.get(column) > values[0]]
            elif method == "gte":
                rows = [row for row in rows if row.get(column) is not None and str(row.get(column)) >= str(values[0])]
            elif method == "not_":
                operator, value = values
                if operator == "is" and value == "null":
                    rows = [row for row in rows if row.get(column) is not None]
        if self._order:
            column, desc = self._order
            rows = sorted(rows, key=lambda row: row.get(column) or "", reverse=desc)
        count = len(rows)
        if self._limit is not None:
            rows = rows[: self._limit]
        return SimpleNamespace(data=rows, count=count)


class _Supabase:
    def __init__(self, overrides=None):
        self.overrides = overrides or {}

    def table(self, name):
        if name in self.overrides:
            rows = self.overrides[name]
            if rows is None:
                raise RuntimeError(f"{name} missing")
            return _Query(rows)
        rows = {
            "opportunities": [
                {
                    "id": "1",
                    "is_active": True,
                    "dos_score": 90,
                    "mileage": None,
                    "year": 2018,
                    "title": "2018 Ford Transit",
                    "pricing_maturity": "proxy",
                    "vin": None,
                    "condition_grade": "Poor",
                    "source_site": "govdeals",
                    "investment_grade": "Rejected",
                    "roi_per_day": 300,
                    "bid_headroom": 1000,
                    "current_bid_trust_score": 0.9,
                    "mmr_confidence_proxy": 90,
                    "pricing_source": "proxy",
                },
                {
                    "id": "2",
                    "is_active": True,
                    "dos_score": 91,
                    "mileage": 25000,
                    "year": 2025,
                    "title": "2025 Honda Accord",
                    "pricing_maturity": "market_comp",
                    "vin": "1HGCM82633A004352",
                    "condition_grade": "Good",
                    "source_site": "govdeals",
                    "investment_grade": "Platinum",
                    "roi_per_day": 300,
                    "bid_headroom": 1000,
                    "current_bid_trust_score": 0.9,
                    "mmr_confidence_proxy": 90,
                    "pricing_source": "market_comp",
                    "retail_comp_count": 5,
                    "retail_comp_confidence": 0.9,
                    "projected_total_cost": 10000,
                    "max_bid": 12000,
                    "expected_close_bid": 10000,
                },
            ],
            "webhook_log": [{"id": "w1", "processing_status": "processed", "source": "govdeals"}],
            "alert_log": [{"id": "a1", "sent_at": "2026-05-20T02:11:32Z", "delivery_state": "sent"}],
            "ingest_delivery_log": [{"id": "d1", "created_at": "2026-05-20T02:11:32Z", "channel": "telegram_alert", "status": "sent"}],
            "dealer_sales": [
                {"id": "sale-1", "sale_date": None, "make": "Ford", "model": "F150 HAS"},
                {"id": "sale-2", "sale_date": None, "make": "Ford", "model": "F-550"},
            ],
            "market_prices": None,
        }[name]
        if rows is None:
            raise RuntimeError(f"{name} missing")
        return _Query(rows)


def test_pipeline_truth_returns_aggregate_only(monkeypatch):
    monkeypatch.setattr(internal, "supabase_client", _Supabase())
    result = internal.build_pipeline_truth()
    assert result["status"] == "ok"
    assert result["opportunities"]["active_dos80_sample"] == 2
    assert result["opportunities"]["active_dos80_missing_mileage_sample"] == 1
    breakdown = result["opportunities"]["active_dos80_gate_breakdown"]
    assert len(breakdown) == 2
    blocked = next(item for item in breakdown if item["id"] == "1")
    assert blocked["eligible"] is False
    assert "mileage_missing" in blocked["blocking_reasons"]
    assert "pricing_maturity=proxy" in blocked["blocking_reasons"]
    assert "grade=Rejected" in blocked["blocking_reasons"]
    allowed = next(item for item in breakdown if item["id"] == "2")
    assert allowed["eligible"] is True
    assert allowed["blocking_reasons"] == []
    assert result["opportunities"]["active_dos80_gate_blocker_counts_sample"] == {
        "mileage_missing": 1,
        "pricing_maturity=proxy": 1,
        "insufficient_pricing": 1,
        "vin_unverified": 1,
        "grade=Rejected": 1,
        "condition_unverified": 1,
    }
    assert result["opportunities"]["active_dos80_alert_eligible_sample"] == 1
    assert result["opportunities"]["active_dos80_condition_counts_sample"] == {
        "Poor": 1,
        "Good": 1,
    }
    assert result["opportunities"]["active_dos80_condition_blocker_basis_counts_sample"] == {
        "age_mileage_heuristic": 1,
    }
    assert result["opportunities"]["active_dos80_pricing_maturity_counts_sample"] == {
        "proxy": 1,
        "market_comp": 1,
    }
    assert "latest" in result["webhooks"]
    assert result["pricing_substrate"] == {
        "market_prices_table": "missing",
        "market_prices_rows": 0,
        "market_prices_usable_rows": 0,
        "dealer_sales_table": "present",
        "dealer_sales_rows": 2,
        "dealer_sales_usable_rows": 0,
        "latest_dealer_sale_date": None,
        "ready_for_market_comp_pricing": False,
    }


def test_pipeline_truth_distinguishes_explicit_condition_damage_from_heuristic(monkeypatch):
    monkeypatch.setattr(internal, "supabase_client", _Supabase({
        "opportunities": [
            {
                "id": "explicit-damage",
                "is_active": True,
                "dos_score": 92,
                "mileage": 30000,
                "year": 2024,
                "title": "2024 Ford F-150",
                "pricing_maturity": "market_comp",
                "vin": "1FTFW1E50PFA12345",
                "condition_grade": "Poor",
                "source_site": "gsaauctions",
                "investment_grade": "Platinum",
                "roi_per_day": 300,
                "bid_headroom": 1000,
                "current_bid_trust_score": 0.9,
                "mmr_confidence_proxy": 90,
                "pricing_source": "market_comp",
                "retail_comp_count": 5,
                "retail_comp_confidence": 0.9,
                "projected_total_cost": 10000,
                "max_bid": 12000,
                "expected_close_bid": 10000,
                "raw_data": {
                    "description": "Runs but has frame damage.",
                    "damage_type": "frame damage",
                },
            },
            {
                "id": "old-mileage",
                "is_active": True,
                "dos_score": 89,
                "mileage": 87540,
                "year": 2017,
                "title": "2017 Chevrolet Tahoe",
                "pricing_maturity": "market_comp",
                "vin": "1GNSKCKC0HR123456",
                "condition_grade": "Poor",
                "source_site": "jjkane",
                "investment_grade": "Platinum",
                "roi_per_day": 300,
                "bid_headroom": 1000,
                "current_bid_trust_score": 0.9,
                "mmr_confidence_proxy": 90,
                "pricing_source": "market_comp",
                "retail_comp_count": 5,
                "retail_comp_confidence": 0.9,
                "projected_total_cost": 10000,
                "max_bid": 12000,
                "expected_close_bid": 10000,
            },
        ],
        "market_prices": [],
        "dealer_sales": [],
    }))

    result = internal.build_pipeline_truth()

    assert result["opportunities"]["active_dos80_condition_blocker_basis_counts_sample"] == {
        "explicit_negative_condition_signal": 1,
        "age_mileage_heuristic": 1,
    }
    breakdown_by_id = {
        item["id"]: item
        for item in result["opportunities"]["active_dos80_gate_breakdown"]
    }
    assert breakdown_by_id["explicit-damage"]["signals"]["condition_blocker_basis"] == "explicit_negative_condition_signal"
    assert breakdown_by_id["old-mileage"]["signals"]["condition_blocker_basis"] == "age_mileage_heuristic"


def test_pipeline_truth_requires_usable_market_prices(monkeypatch):
    monkeypatch.setattr(internal, "supabase_client", _Supabase({
        "market_prices": [
            {
                "id": "market-1",
                "avg_price": 25000,
                "low_price": 23000,
                "high_price": 27000,
                "sample_size": 3,
                "expires_at": "2099-01-01T00:00:00+00:00",
                "source": "seeded_market_comp",
            },
        ],
    }))

    result = internal.build_pipeline_truth()

    assert result["pricing_substrate"]["market_prices_table"] == "present"
    assert result["pricing_substrate"]["market_prices_rows"] == 1
    assert result["pricing_substrate"]["market_prices_usable_rows"] == 1
    assert result["pricing_substrate"]["ready_for_market_comp_pricing"] is True


def test_pipeline_truth_rejects_empty_or_stale_market_prices(monkeypatch):
    monkeypatch.setattr(internal, "supabase_client", _Supabase({
        "market_prices": [
            {
                "id": "market-1",
                "avg_price": 25000,
                "low_price": 23000,
                "high_price": 27000,
                "sample_size": 3,
                "expires_at": "2020-01-01T00:00:00+00:00",
                "source": "seeded_market_comp",
            },
            {
                "id": "market-2",
                "avg_price": 25000,
                "low_price": 23000,
                "high_price": 27000,
                "sample_size": 3,
                "expires_at": "2099-01-01T00:00:00+00:00",
                "source": None,
            },
        ],
    }))

    result = internal.build_pipeline_truth()

    assert result["pricing_substrate"]["market_prices_table"] == "present"
    assert result["pricing_substrate"]["market_prices_rows"] == 2
    assert result["pricing_substrate"]["market_prices_usable_rows"] == 0
    assert result["pricing_substrate"]["ready_for_market_comp_pricing"] is False


def test_pipeline_truth_accepts_recent_positive_dealer_sales(monkeypatch):
    monkeypatch.setattr(internal, "supabase_client", _Supabase({
        "market_prices": [],
        "dealer_sales": [
            {"id": "sale-1", "sale_price": 22000, "sale_date": "2099-01-01T00:00:00+00:00"},
            {"id": "sale-2", "sale_price": 23000, "sale_date": "2099-01-02T00:00:00+00:00"},
        ],
    }))

    result = internal.build_pipeline_truth()

    assert result["pricing_substrate"]["market_prices_table"] == "present"
    assert result["pricing_substrate"]["market_prices_rows"] == 0
    assert result["pricing_substrate"]["dealer_sales_rows"] == 2
    assert result["pricing_substrate"]["dealer_sales_usable_rows"] == 2
    assert result["pricing_substrate"]["latest_dealer_sale_date"] == "2099-01-02T00:00:00+00:00"
    assert result["pricing_substrate"]["ready_for_market_comp_pricing"] is True


def test_pipeline_truth_reports_alerts_runtime_status(monkeypatch):
    from webapp.routers import internal

    monkeypatch.setenv("ALERTS_ENABLED", "false")
    status = internal._alerts_runtime_status()

    assert status == {
        "enabled": False,
        "source": "env",
        "raw_value": "false",
        "production_default": "true",
    }

    monkeypatch.delenv("ALERTS_ENABLED", raising=False)
    status = internal._alerts_runtime_status()

    assert status["enabled"] is True
    assert status["source"] == "production_default"
