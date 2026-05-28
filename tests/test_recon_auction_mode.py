import asyncio
from types import SimpleNamespace

from webapp.routers import recon


class _Query:
    def __init__(self, data):
        self.data = data

    def select(self, *_args, **_kwargs): return self
    def eq(self, *_args, **_kwargs): return self
    def ilike(self, *_args, **_kwargs): return self
    def gte(self, *_args, **_kwargs): return self
    def lte(self, *_args, **_kwargs): return self
    def or_(self, *_args, **_kwargs): return self
    def gt(self, *_args, **_kwargs): return self
    def limit(self, *_args, **_kwargs): return self
    def execute(self): return SimpleNamespace(data=self.data)


class _Supabase:
    def __init__(self, comp_rows):
        self.comp_rows = comp_rows

    def table(self, name):
        assert name == "dealer_sales"
        return _Query(self.comp_rows)


def test_auction_mode_with_market_value_does_not_pass_fake_zero_bid_to_score_deal(monkeypatch):
    monkeypatch.setattr(recon, "_verify_auth", lambda _authorization: "operator-user")
    monkeypatch.setattr(recon, "_supabase_client", _Supabase([]))
    async def fake_retail_market_value(*_args, **_kwargs):
        return {
            "retail_value": 30000,
            "retail_low": 28000,
            "retail_high": 33000,
            "retail_count": 8,
            "retail_source": "marketcheck",
        }

    monkeypatch.setattr(recon, "get_retail_market_value", fake_retail_market_value)

    def fail_if_called(**_kwargs):
        raise AssertionError("score_deal should not be called with a synthetic zero bid")

    monkeypatch.setattr("backend.ingest.score.score_deal", fail_if_called)

    req = recon.EvaluateRequest(
        vin="1HGCM82633A004352",
        mileage=42000,
        year=2023,
        make="Toyota",
        model="Camry",
        asking_price=None,
        title_status="clean",
        condition="Good",
        source="recon",
        state="CA",
    )

    result = asyncio.run(recon.evaluate_vehicle(req, authorization="Bearer test"))

    assert result["auction_mode"] is True
    assert result["verdict"] == "INSUFFICIENT_BID_DATA"
    assert result["dos"] is None
    assert result["adjusted_dos"] is None
    assert result["retail_market_value"] == 30000
    assert "insufficient bid data" in result["verdict_reason"].lower()


class _SupabaseWithInsert(_Supabase):
    def __init__(self, comp_rows):
        super().__init__(comp_rows)
        self.insert_result = SimpleNamespace(data=[{"id": "eval-1"}])

    def table(self, name):
        if name == "dealer_sales":
            return super().table(name)
        if name == "recon_evaluations":
            query = _Query([])
            query.insert = lambda *_a, **_k: query
            query.execute = lambda: self.insert_result
            return query
        raise AssertionError(name)


def test_evaluate_with_asking_price_calls_score_deal_with_actual_bid(monkeypatch):
    monkeypatch.setattr(recon, "_verify_auth", lambda _authorization: "operator-user")
    monkeypatch.setattr(recon, "_supabase_client", _SupabaseWithInsert([]))

    async def fake_retail_market_value(*_args, **_kwargs):
        return {
            "retail_value": 28000,
            "retail_low": 26000,
            "retail_high": 30000,
            "retail_count": 12,
            "retail_source": "marketcheck",
        }

    monkeypatch.setattr(recon, "get_retail_market_value", fake_retail_market_value)

    score_calls = []

    def capture_score_deal(**kwargs):
        score_calls.append(kwargs)
        return {"dos_score": 72.0, "vehicle_tier": "premium", "wholesale_margin": 2500.0}

    monkeypatch.setattr("backend.ingest.score.score_deal", capture_score_deal)

    req = recon.EvaluateRequest(
        mileage=45000,
        year=2021,
        make="Toyota",
        model="Camry",
        asking_price=12000.0,
        title_status="clean",
        condition="Good",
        source="govdeals",
        state="TX",
    )

    result = asyncio.run(recon.evaluate_vehicle(req, authorization="Bearer test"))

    assert len(score_calls) == 1
    assert score_calls[0]["bid"] == 12000.0
    assert score_calls[0]["bid"] != 0
    assert result["dos"] == 72.0
