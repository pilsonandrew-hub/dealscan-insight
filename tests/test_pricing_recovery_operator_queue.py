from datetime import datetime, timezone

import pytest

from scripts import pricing_recovery_operator_queue as queue


NOW = datetime(2026, 6, 14, 6, 50, tzinfo=timezone.utc)


def recovery_group(**overrides):
    group = {
        "key": {"year": 2020, "make": "ford", "model": "escape", "state": "sc"},
        "candidate_count": 3,
        "source_counts": {"proxibid": 2, "gsaauctions": 1},
        "status": "blocked_no_internal_comp_evidence",
        "recommended_action": "request_completed_sales_evidence",
        "evidence_counts": {
            "usable_market_prices": 0,
            "market_prices": 0,
            "usable_dealer_sales": 0,
            "dealer_sales": 0,
            "usable_competitor_sales": 0,
            "competitor_sales": 0,
            "usable_internal_history": 0,
            "internal_history": 0,
        },
    }
    group.update(overrides)
    return group


def test_build_queue_record_is_sanitized_and_deterministic():
    record = queue.build_queue_record(
        recovery_group(
            title="private title 1FMCU0F60LUB43858",
            listing_url="https://example.test/private",
        ),
        proof_run_id="27490986854",
        head_sha="c6c3643e4266f4d948a55c75e92c5b870829d559",
        now=NOW,
    )

    assert record["group_key"] == "2020|ford|escape|sc|gsaauctions,proxibid"
    assert record["queue_status"] == "open"
    assert record["status"] == "blocked_no_internal_comp_evidence"
    assert record["recommended_action"] == "request_completed_sales_evidence"
    assert record["candidate_count"] == 3
    assert record["source_families"] == ["gsaauctions", "proxibid"]
    assert record["latest_proof_run_id"] == "27490986854"
    assert record["latest_proof_head_sha"] == "c6c3643e4266f4d948a55c75e92c5b870829d559"
    assert "title" not in record
    assert "listing_url" not in record
    assert "vin" not in record
    assert "1FMCU0F60LUB43858" not in repr(record)
    assert "https://example.test/private" not in repr(record)


def test_build_queue_record_rejects_unknown_statuses():
    with pytest.raises(ValueError, match="unknown recovery status"):
        queue.build_queue_record(
            recovery_group(status="probably_ok"),
            proof_run_id="run",
            head_sha="sha",
            now=NOW,
        )

    with pytest.raises(ValueError, match="unknown recommended action"):
        queue.build_queue_record(
            recovery_group(recommended_action="invent_evidence"),
            proof_run_id="run",
            head_sha="sha",
            now=NOW,
        )


class FakeQueueRepository:
    def __init__(self, existing=None):
        self.existing = existing or {}
        self.upserts = []
        self.events = []

    def get_by_group_key(self, group_key):
        return self.existing.get(group_key)

    def save_request_with_event(self, record, event):
        row = {"id": self.existing.get(record["group_key"], {}).get("id", "req-1"), **record}
        self.upserts.append(row)
        self.existing[record["group_key"]] = row
        event = {"request_id": row["id"], **event}
        self.events.append(event)
        return row


def test_sync_dry_run_does_not_write():
    repo = FakeQueueRepository()
    records = [
        queue.build_queue_record(recovery_group(), proof_run_id="run", head_sha="sha", now=NOW)
    ]

    summary = queue.sync_queue_records(records, repo=repo, apply=False, confirmation="")

    assert summary["would_insert"] == 1
    assert repo.upserts == []
    assert repo.events == []


def test_sync_apply_requires_confirmation():
    repo = FakeQueueRepository()
    records = [
        queue.build_queue_record(recovery_group(), proof_run_id="run", head_sha="sha", now=NOW)
    ]

    with pytest.raises(ValueError, match="requires confirmation"):
        queue.sync_queue_records(records, repo=repo, apply=True, confirmation="wrong")


def test_sync_apply_writes_insert_event():
    repo = FakeQueueRepository()
    records = [
        queue.build_queue_record(recovery_group(), proof_run_id="run", head_sha="sha", now=NOW)
    ]

    summary = queue.sync_queue_records(
        records,
        repo=repo,
        apply=True,
        confirmation=queue.APPLY_CONFIRMATION,
        actor="github-actions",
    )

    assert summary["inserted"] == 1
    assert repo.upserts[0]["group_key"] == "2020|ford|escape|sc|gsaauctions,proxibid"
    assert repo.events[0]["event_type"] == "inserted"
    assert repo.events[0]["next_queue_status"] == "open"
    assert repo.events[0]["actor"] == "github-actions"


def test_sync_apply_preserves_existing_operator_status():
    existing = {
        "2020|ford|escape|sc|gsaauctions,proxibid": {
            "id": "req-2",
            "group_key": "2020|ford|escape|sc|gsaauctions,proxibid",
            "queue_status": "evidence_requested",
            "owner": "operator-1",
            "priority": 7,
            "blocked_reason": None,
            "resolution_notes": "requested completed sales",
            "resolved_at": None,
        }
    }
    repo = FakeQueueRepository(existing=existing)
    records = [
        queue.build_queue_record(recovery_group(), proof_run_id="run-2", head_sha="sha-2", now=NOW)
    ]

    summary = queue.sync_queue_records(
        records,
        repo=repo,
        apply=True,
        confirmation=queue.APPLY_CONFIRMATION,
        actor="github-actions",
    )

    assert summary["updated"] == 1
    assert repo.upserts[0]["queue_status"] == "evidence_requested"
    assert repo.upserts[0]["owner"] == "operator-1"
    assert repo.upserts[0]["priority"] == 7
    assert repo.upserts[0]["resolution_notes"] == "requested completed sales"
    assert repo.events[0]["previous_queue_status"] == "evidence_requested"
    assert repo.events[0]["next_queue_status"] == "evidence_requested"


def test_sync_apply_reopens_terminal_rows_when_group_reappears():
    existing = {
        "2020|ford|escape|sc|gsaauctions,proxibid": {
            "id": "req-3",
            "group_key": "2020|ford|escape|sc|gsaauctions,proxibid",
            "queue_status": "dismissed",
            "owner": "operator-1",
            "priority": 7,
            "blocked_reason": None,
            "resolution_notes": "not enough evidence last run",
            "resolved_at": "2026-06-13T20:00:00+00:00",
        }
    }
    repo = FakeQueueRepository(existing=existing)
    records = [
        queue.build_queue_record(recovery_group(), proof_run_id="run-3", head_sha="sha-3", now=NOW)
    ]

    summary = queue.sync_queue_records(
        records,
        repo=repo,
        apply=True,
        confirmation=queue.APPLY_CONFIRMATION,
        actor="github-actions",
    )

    assert summary["updated"] == 1
    assert repo.upserts[0]["queue_status"] == "open"
    assert repo.upserts[0]["resolved_at"] is None
    assert repo.upserts[0]["owner"] == "operator-1"
    assert repo.upserts[0]["priority"] == 7
    assert repo.events[0]["previous_queue_status"] == "dismissed"
    assert repo.events[0]["next_queue_status"] == "open"
    assert repo.events[0]["event_type"] == "reopened"


def test_supabase_rest_apply_uses_atomic_queue_sync_rpc(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"id": "req-1", "queue_status": "open"}'

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["method"] = request.get_method()
        captured["payload"] = request.data.decode("utf-8")
        return FakeResponse()

    monkeypatch.setattr(queue.urllib_request, "urlopen", fake_urlopen)
    repo = queue.SupabaseRestQueueRepository(
        supabase_url="https://example.supabase.co",
        service_role_key="service-role",
    )

    record = queue.build_queue_record(recovery_group(), proof_run_id="run", head_sha="sha", now=NOW)
    row = repo.save_request_with_event(
        record,
        {
            "event_type": "inserted",
            "previous_queue_status": None,
            "next_queue_status": "open",
            "actor": "github-actions",
            "reason": record["recommended_action"],
            "proof_run_id": record["latest_proof_run_id"],
            "head_sha": record["latest_proof_head_sha"],
            "metadata": {"group_key": record["group_key"], "status": record["status"]},
        },
    )

    assert row["id"] == "req-1"
    assert captured["method"] == "POST"
    assert captured["url"].endswith("/rest/v1/rpc/sync_pricing_recovery_request")
    assert "return=representation" in captured["headers"]["Prefer"]
    payload = captured["payload"]
    assert "request_payload" in payload
    assert "event_payload" in payload
    assert "pricing_recovery_requests?on_conflict" not in captured["url"]


def test_supabase_rest_lookup_fetches_lifecycle_fields(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'[{"id": "req-1", "queue_status": "evidence_requested", "owner": "operator"}]'

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        return FakeResponse()

    monkeypatch.setattr(queue.urllib_request, "urlopen", fake_urlopen)
    repo = queue.SupabaseRestQueueRepository(
        supabase_url="https://example.supabase.co",
        service_role_key="service-role",
    )

    row = repo.get_by_group_key("2020|ford|escape|sc|gsaauctions,proxibid")

    assert row["queue_status"] == "evidence_requested"
    assert "group_key=eq.%22" in captured["url"]
    assert "gsaauctions%2Cproxibid%22" in captured["url"]
    assert "owner" in captured["url"]
    assert "priority" in captured["url"]
    assert "blocked_reason" in captured["url"]
    assert "resolution_notes" in captured["url"]
    assert "resolved_at" in captured["url"]


def test_dry_run_uses_live_repository_when_credentials_exist():
    repo = queue.repository_for_sync(
        apply=False,
        rest_base_url="https://example.supabase.co/rest/v1",
        service_role_key="service-role",
    )

    assert isinstance(repo, queue.SupabaseRestQueueRepository)


def test_dry_run_without_credentials_uses_local_empty_repository():
    repo = queue.repository_for_sync(
        apply=False,
        rest_base_url=None,
        service_role_key=None,
    )

    assert isinstance(repo, queue.DryRunQueueRepository)
