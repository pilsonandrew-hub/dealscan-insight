from types import SimpleNamespace

import asyncio

import pytest
from fastapi import HTTPException

from webapp.routers import outcomes


class _Auth:
    def __init__(self, user_id="user-1", fail=False):
        self.user_id = user_id
        self.fail = fail

    def get_user(self, _token):
        if self.fail:
            raise RuntimeError("bad token")
        return SimpleNamespace(user=SimpleNamespace(id=self.user_id))


class _Query:
    def __init__(self, client, table_name):
        self.client = client
        self.table_name = table_name
        self.filters = []
        self._limit = None
        self.payload = None
        self.operation = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, key, value):
        self.filters.append((key, value))
        return self

    def limit(self, value):
        self._limit = value
        return self

    def update(self, payload):
        self.payload = payload
        self.operation = "update"
        return self

    def upsert(self, payload, on_conflict=None):
        if self.client.fail_dealer_sales and self.table_name == "dealer_sales":
            raise RuntimeError("dealer_sales write failed")
        self.client.upserts.setdefault(self.table_name, []).append((payload, on_conflict))
        return self

    def execute(self):
        rows = list(self.client.rows.get(self.table_name, []))
        for key, value in self.filters:
            rows = [row for row in rows if row.get(key) == value]

        if getattr(self, "operation", None) == "update":
            if self.client.fail_updates and self.table_name == "opportunities":
                return SimpleNamespace(data=[])
            self.client.updates.setdefault(self.table_name, []).append((self.payload, tuple(self.filters)))
            return SimpleNamespace(data=[{**row, **self.payload} for row in rows])

        if self._limit is not None:
            rows = rows[: self._limit]
        return SimpleNamespace(data=rows)


class _Supabase:
    def __init__(self, opportunity=None, user_id="user-1", fail_dealer_sales=False, fail_updates=False):
        self.auth = _Auth(user_id=user_id)
        self.rows = {
            "opportunities": [opportunity or {
                "id": "opp-1",
                "user_id": user_id,
                "make": "Ford",
                "model": "F-150",
                "year": 2023,
                "mileage": 18000,
                "current_bid": 10000,
                "state": "CA",
            }],
            "dealer_sales": [],
        }
        self.upserts = {}
        self.updates = {}
        self.fail_dealer_sales = fail_dealer_sales
        self.fail_updates = fail_updates

    def table(self, name):
        return _Query(self, name)


def _auth_header():
    return "Bearer valid-token"


def _run(coro):
    return asyncio.run(coro)


def test_summary_requires_auth(monkeypatch):
    async def run():
        monkeypatch.setattr(outcomes, "supabase_client", _Supabase())

        with pytest.raises(HTTPException) as exc:
            await outcomes.get_outcomes_summary(authorization=None)

        assert exc.value.status_code == 401

    _run(run())


def test_create_outcome_requires_auth(monkeypatch):
    client = _Supabase()
    monkeypatch.setattr(outcomes, "supabase_client", client)
    payload = outcomes.OutcomePayload(opportunity_id="opp-1", sale_price=14000, sale_date="2026-05-29", days_to_sale=12)

    with pytest.raises(HTTPException) as exc:
        _run(outcomes.create_outcome(payload, authorization=None))

    assert exc.value.status_code == 401
    assert "dealer_sales" not in client.upserts


def test_patch_outcome_requires_auth(monkeypatch):
    client = _Supabase()
    monkeypatch.setattr(outcomes, "supabase_client", client)
    payload = outcomes.OutcomePatchPayload(outcome="lost")

    with pytest.raises(HTTPException) as exc:
        _run(outcomes.patch_outcome("opp-1", payload, authorization=None))

    assert exc.value.status_code == 401
    assert "dealer_sales" not in client.upserts


def test_bid_outcome_requires_auth(monkeypatch):
    client = _Supabase()
    monkeypatch.setattr(outcomes, "supabase_client", client)
    payload = outcomes.BidOutcomePayload(opportunity_id="opp-1", bid=True, won=False)

    with pytest.raises(HTTPException) as exc:
        _run(outcomes.create_bid_outcome(payload, authorization=None))

    assert exc.value.status_code == 401
    assert "dealer_sales" not in client.upserts


def test_dealer_sales_payload_rejects_unknown_schema_columns(monkeypatch):
    monkeypatch.setattr(outcomes, "supabase_client", _Supabase())

    with pytest.raises(HTTPException) as exc:
        outcomes._upsert_dealer_sales_outcome({"opportunity_id": "opp-1", "user_id": "user-1", "recorded_at": "bad"})

    assert exc.value.status_code == 500
    assert exc.value.detail == "Outcome evidence payload does not match schema"


def test_foreign_owned_opportunity_rejects_bid_outcome(monkeypatch):
    async def run():
        client = _Supabase(opportunity={
            "id": "opp-1",
            "user_id": "other-user",
            "make": "Ford",
            "model": "F-150",
            "year": 2023,
            "mileage": 18000,
            "current_bid": 10000,
            "state": "CA",
        })
        monkeypatch.setattr(outcomes, "supabase_client", client)

        payload = outcomes.BidOutcomePayload(opportunity_id="opp-1", bid=True, won=False)
        with pytest.raises(HTTPException) as exc:
            await outcomes.create_bid_outcome(payload, authorization=_auth_header())

        assert exc.value.status_code == 403
        assert "dealer_sales" not in client.upserts

    _run(run())


def test_operator_can_record_bid_outcome_for_user_owned_opportunity(monkeypatch):
    async def run():
        client = _Supabase(
            opportunity={
                "id": "opp-1",
                "user_id": "other-user",
                "make": "Ford",
                "model": "F-150",
                "year": 2023,
                "mileage": 18000,
                "current_bid": 10000,
                "state": "CA",
            },
            user_id="operator-user",
        )
        monkeypatch.setattr(outcomes, "supabase_client", client)
        monkeypatch.setenv("DEALERSCOPE_OPERATOR_USER_ID", "operator-user")

        payload = outcomes.BidOutcomePayload(opportunity_id="opp-1", bid=True, won=False)
        result = await outcomes.create_bid_outcome(payload, authorization=_auth_header())

        assert result["success"] is True
        dealer_payload, _conflict = client.upserts["dealer_sales"][0]
        assert dealer_payload["user_id"] == "operator-user"

    _run(run())


def test_bid_outcome_persists_queryable_dealer_sales_and_updates_opportunity(monkeypatch):
    client = _Supabase()
    monkeypatch.setattr(outcomes, "supabase_client", client)

    payload = outcomes.BidOutcomePayload(opportunity_id="opp-1", bid=True, won=False, notes="too high")
    result = _run(outcomes.create_bid_outcome(payload, authorization=_auth_header()))

    assert result["success"] is True
    assert result["outcome"] == "lost"
    assert result["outcome_persisted"] is True
    dealer_payload, conflict = client.upserts["dealer_sales"][0]
    assert conflict == "opportunity_id,user_id"
    assert dealer_payload["opportunity_id"] == "opp-1"
    assert dealer_payload["user_id"] == "user-1"
    assert dealer_payload["outcome"] == "lost"
    assert dealer_payload["sale_price"] == 10000
    assert dealer_payload["asking_price"] == 10000
    assert dealer_payload["source"] == "bid_outcome_tracking"
    assert "recorded_at" not in dealer_payload
    assert dealer_payload["updated_at"]
    assert dealer_payload["metadata"]["type"] == "bid_outcome"
    assert dealer_payload["metadata"]["user_notes"] == "too high"
    update_payload, filters = client.updates["opportunities"][0]
    assert update_payload["won"] is False
    assert ("id", "opp-1") in filters
    assert ("user_id", "user-1") in filters


def test_passed_bid_outcome_is_visible_to_summary(monkeypatch):
    client = _Supabase()
    monkeypatch.setattr(outcomes, "supabase_client", client)

    payload = outcomes.BidOutcomePayload(opportunity_id="opp-1", bid=False, notes="skip")
    _run(outcomes.create_bid_outcome(payload, authorization=_auth_header()))
    client.rows["dealer_sales"] = [client.upserts["dealer_sales"][0][0]]

    summary = _run(outcomes.get_outcomes_summary(authorization=_auth_header()))

    assert summary["count_by_outcome"] == {"pending": 0, "won": 0, "lost": 0, "passed": 1}
    assert summary["recent_outcomes"][0]["opportunity_id"] == "opp-1"
    assert summary["recent_outcomes"][0]["outcome"] == "passed"
    assert summary["recent_outcomes"][0]["source"] == "bid_outcome_tracking"


def test_won_bid_outcome_records_purchase_metrics(monkeypatch):
    client = _Supabase()
    monkeypatch.setattr(outcomes, "supabase_client", client)

    payload = outcomes.BidOutcomePayload(opportunity_id="opp-1", bid=True, won=True, purchase_price=12000)
    _run(outcomes.create_bid_outcome(payload, authorization=_auth_header()))

    dealer_payload = client.upserts["dealer_sales"][0][0]
    assert dealer_payload["outcome"] == "won"
    assert dealer_payload["sale_price"] == 12000
    assert dealer_payload["sold_price"] == 12000
    assert dealer_payload["gross_margin"] == 2000
    assert dealer_payload["roi_pct"] == 20


def test_sale_outcome_fails_closed_when_dealer_sales_persistence_fails(monkeypatch):
    client = _Supabase(fail_dealer_sales=True)
    monkeypatch.setattr(outcomes, "supabase_client", client)

    payload = outcomes.OutcomePayload(
        opportunity_id="opp-1",
        sale_price=14000,
        sale_date="2026-05-29",
        days_to_sale=12,
        notes="sold",
    )
    with pytest.raises(HTTPException) as exc:
        _run(outcomes.create_outcome(payload, authorization=_auth_header()))

    assert exc.value.status_code == 500
    assert exc.value.detail == "Failed to persist outcome evidence"


def test_bid_outcome_fails_closed_when_opportunity_update_matches_zero_rows(monkeypatch):
    client = _Supabase(fail_updates=True)
    monkeypatch.setattr(outcomes, "supabase_client", client)

    payload = outcomes.BidOutcomePayload(opportunity_id="opp-1", bid=True, won=False)
    with pytest.raises(HTTPException) as exc:
        _run(outcomes.create_bid_outcome(payload, authorization=_auth_header()))

    assert exc.value.status_code == 500
    assert exc.value.detail == "Failed to update opportunity outcome mirror"


def test_patch_outcome_writes_dealer_sales_and_fails_closed_on_update_miss(monkeypatch):
    client = _Supabase(fail_updates=True)
    monkeypatch.setattr(outcomes, "supabase_client", client)

    payload = outcomes.OutcomePatchPayload(outcome="lost")
    with pytest.raises(HTTPException) as exc:
        _run(outcomes.patch_outcome("opp-1", payload, authorization=_auth_header()))

    assert exc.value.status_code == 500
    assert exc.value.detail == "Failed to update opportunity outcome mirror"
    dealer_payload = client.upserts["dealer_sales"][0][0]
    assert dealer_payload["outcome"] == "lost"
    assert dealer_payload["source"] == "manual_outcome_tracking"


def test_sale_outcome_returns_explicit_persistence_success(monkeypatch):
    client = _Supabase()
    monkeypatch.setattr(outcomes, "supabase_client", client)

    payload = outcomes.OutcomePayload(
        opportunity_id="opp-1",
        sale_price=14000,
        sale_date="2026-05-29",
        days_to_sale=12,
        notes="sold",
    )
    result = _run(outcomes.create_outcome(payload, authorization=_auth_header()))

    assert result == {"success": True, "outcome_persisted": True}
    dealer_payload = client.upserts["dealer_sales"][0][0]
    assert dealer_payload["outcome"] == "won"
    assert dealer_payload["source"] == "outcome_tracking"
    assert "recorded_at" not in dealer_payload
    assert dealer_payload["updated_at"]
    assert dealer_payload["gross_margin"] == 4000
    assert dealer_payload["roi_pct"] == 40


def test_realized_sale_outcome_is_visible_to_summary(monkeypatch):
    client = _Supabase()
    monkeypatch.setattr(outcomes, "supabase_client", client)

    payload = outcomes.OutcomePayload(
        opportunity_id="opp-1",
        sale_price=14000,
        sale_date="2026-05-29",
        days_to_sale=12,
        notes="sold",
    )
    _run(outcomes.create_outcome(payload, authorization=_auth_header()))
    client.rows["dealer_sales"] = [client.upserts["dealer_sales"][0][0]]

    summary = _run(outcomes.get_outcomes_summary(authorization=_auth_header()))

    assert summary["count_by_outcome"]["won"] == 1
    assert summary["total_gross_margin"] == 4000
    assert summary["avg_roi"] == 40
    assert summary["recent_outcomes"][0]["opportunity_id"] == "opp-1"
    assert summary["recent_outcomes"][0]["outcome"] == "won"
    assert summary["recent_outcomes"][0]["source"] == "outcome_tracking"
