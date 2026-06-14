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

    def upsert_request(self, record):
        row = {"id": self.existing.get(record["group_key"], {}).get("id", "req-1"), **record}
        self.upserts.append(row)
        self.existing[record["group_key"]] = row
        return row

    def insert_event(self, event):
        self.events.append(event)


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
