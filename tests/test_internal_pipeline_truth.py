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

    def select(self, *_args, **_kwargs): return self
    def eq(self, *_args, **_kwargs): return self
    def limit(self, *_args, **_kwargs): return self
    def order(self, *_args, **_kwargs): return self
    def execute(self): return SimpleNamespace(data=self.rows, count=self.count)


class _Supabase:
    def table(self, name):
        rows = {
            "opportunities": [
                {
                    "id": "1",
                    "is_active": True,
                    "dos_score": 90,
                    "mileage": None,
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
        }[name]
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
    assert "latest" in result["webhooks"]


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
