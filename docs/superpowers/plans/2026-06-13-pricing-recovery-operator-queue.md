# Pricing Recovery Operator Queue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Materialize grouped pricing recovery proof into a governed, sanitized operator queue with lifecycle status, audit events, dry-run proof, and confirmation-gated sync.

**Architecture:** Add a narrow queue module that consumes existing `report_pricing_coverage_gaps.group_recovery_rows()` output and builds sanitized queue records. Add Supabase migration/schema tests, a repository abstraction for dry-run and REST sync, workflow proof that defaults read-only, and live gates proving queue state separately from pricing-quality state.

**Tech Stack:** Python scripts, pytest, GitHub Actions YAML, Supabase SQL migrations, Supabase REST service-role calls, existing pricing coverage proof helpers.

---

## File Map

- Create `scripts/pricing_recovery_operator_queue.py`: queue record builder, status validation, dry-run/apply sync, REST repository, audit event writer, CLI.
- Create `tests/test_pricing_recovery_operator_queue.py`: pure queue contract tests, fake repository sync tests, sanitizer tests.
- Create `supabase/migrations/20260614_pricing_recovery_operator_queue.sql`: `pricing_recovery_requests` and `pricing_recovery_request_events`.
- Create `tests/test_pricing_recovery_operator_queue_schema.py`: migration contract tests.
- Modify `.github/workflows/pricing-coverage-gap-proof.yml`: optional queue proof/sync inputs while preserving read-only default.
- Modify `.github/workflows/pricing-substrate-recovery.yml`: print queue proof before recovery preview/apply.
- Modify `tests/workflows/test_pricing_coverage_gap_proof_workflow.py`: queue proof default and confirmation assertions.
- Modify `tests/workflows/test_pricing_substrate_recovery_workflow.py`: queue proof presence and read-only default assertions.
- Do not modify `backend/ingest/score.py`, alert gating, or pricing thresholds.

## Task 1: Queue Contract And Sanitized Records

**Files:**
- Create `tests/test_pricing_recovery_operator_queue.py`
- Create `scripts/pricing_recovery_operator_queue.py`

- [ ] **Step 1: Write RED tests for deterministic queue records**

Create `tests/test_pricing_recovery_operator_queue.py`:

```python
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
```

- [ ] **Step 2: Run RED test**

Run:

```bash
/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/.venv/bin/python -m pytest tests/test_pricing_recovery_operator_queue.py -q
```

Expected: fail because `scripts/pricing_recovery_operator_queue.py` does not exist.

- [ ] **Step 3: Implement queue record builder**

Create `scripts/pricing_recovery_operator_queue.py`:

```python
#!/usr/bin/env python3
"""Materialize sanitized pricing recovery groups into an operator queue."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol


RECOVERY_STATUSES = {
    "covered_by_market_prices",
    "covered_by_dealer_sales",
    "covered_by_competitor_sales",
    "seedable_from_internal_history",
    "insufficient_dealer_sales",
    "insufficient_internal_history",
    "insufficient_competitor_sales",
    "blocked_no_internal_comp_evidence",
    "dirty_source_row",
    "expired_pricing_gap",
}
RECOMMENDED_ACTIONS = {
    "none",
    "refresh_market_prices_from_dealer_sales",
    "refresh_market_prices_from_competitor_sales",
    "review_internal_history_for_completed_sales_evidence",
    "request_completed_sales_evidence",
    "wait_for_more_internal_history",
    "ignore_dirty_source_row",
    "ignore_expired_listing",
}
QUEUE_STATUSES = {
    "open",
    "evidence_requested",
    "evidence_received",
    "preview_ready",
    "applied",
    "blocked",
    "dismissed",
}
APPLY_CONFIRMATION = "SYNC_PRICING_RECOVERY_OPERATOR_QUEUE"
VIN_LIKE_RE = re.compile(r"\b(?:vin\s*#?\s*)?[A-HJ-NPR-Z0-9]{17}\b", re.IGNORECASE)


def _norm_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _clean_int(value: Any) -> int:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return max(parsed, 0)


def _iso(value: datetime) -> str:
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()


def _validate_choice(value: str, allowed: set[str], label: str) -> str:
    if value not in allowed:
        raise ValueError(f"unknown {label}: {value}")
    return value


def build_queue_record(group: dict[str, Any], *, proof_run_id: str, head_sha: str, now: datetime) -> dict[str, Any]:
    key = group.get("key") or {}
    sources = sorted(_norm_text(source) for source in (group.get("source_counts") or {}) if _norm_text(source))
    year = _clean_int(key.get("year")) or None
    make = _norm_text(key.get("make"))
    model = _norm_text(key.get("model"))
    state = _norm_text(key.get("state")) or None
    if not year or not make or not model:
        raise ValueError("queue record requires year, make, and model")

    status = _validate_choice(str(group.get("status") or ""), RECOVERY_STATUSES, "recovery status")
    action = _validate_choice(str(group.get("recommended_action") or ""), RECOMMENDED_ACTIONS, "recommended action")
    evidence = group.get("evidence_counts") or {}
    return {
        "group_key": "|".join([str(year), make, model, state or "", ",".join(sources)]),
        "year": year,
        "make": VIN_LIKE_RE.sub("[redacted]", make),
        "model": VIN_LIKE_RE.sub("[redacted]", model),
        "state": state,
        "source_families": sources,
        "candidate_count": _clean_int(group.get("candidate_count")),
        "status": status,
        "recommended_action": action,
        "queue_status": "open",
        "market_prices_usable": _clean_int(evidence.get("usable_market_prices")),
        "market_prices_total": _clean_int(evidence.get("market_prices")),
        "dealer_sales_usable": _clean_int(evidence.get("usable_dealer_sales")),
        "dealer_sales_total": _clean_int(evidence.get("dealer_sales")),
        "competitor_sales_usable": _clean_int(evidence.get("usable_competitor_sales")),
        "competitor_sales_total": _clean_int(evidence.get("competitor_sales")),
        "internal_history_usable": _clean_int(evidence.get("usable_internal_history")),
        "internal_history_total": _clean_int(evidence.get("internal_history")),
        "latest_proof_run_id": str(proof_run_id),
        "latest_proof_head_sha": str(head_sha),
        "last_seen_at": _iso(now),
    }
```

- [ ] **Step 4: Run GREEN test**

Run:

```bash
/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/.venv/bin/python -m pytest tests/test_pricing_recovery_operator_queue.py -q
```

Expected: tests pass.

- [ ] **Step 5: Commit Task 1**

```bash
git add scripts/pricing_recovery_operator_queue.py tests/test_pricing_recovery_operator_queue.py
git commit -m "feat: build pricing recovery queue records"
```

## Task 2: Schema And Audit Contract

**Files:**
- Create `supabase/migrations/20260614_pricing_recovery_operator_queue.sql`
- Create `tests/test_pricing_recovery_operator_queue_schema.py`

- [ ] **Step 1: Write RED schema tests**

Create `tests/test_pricing_recovery_operator_queue_schema.py`:

```python
from pathlib import Path


MIGRATION = Path(__file__).resolve().parents[1] / "supabase" / "migrations" / "20260614_pricing_recovery_operator_queue.sql"


def test_pricing_recovery_queue_schema_exists_with_safe_columns():
    sql = MIGRATION.read_text()

    assert "create table if not exists public.pricing_recovery_requests" in sql.lower()
    assert "create table if not exists public.pricing_recovery_request_events" in sql.lower()
    assert "group_key text not null unique" in sql.lower()
    assert "queue_status text not null" in sql.lower()
    assert "latest_proof_run_id text" in sql.lower()
    assert "latest_proof_head_sha text" in sql.lower()
    forbidden = ["vin ", "listing_url", "title ", "description ", "raw_payload", "token", "secret"]
    lowered = sql.lower()
    for word in forbidden:
        assert word not in lowered


def test_pricing_recovery_queue_schema_has_status_constraints_and_audit_indexes():
    sql = MIGRATION.read_text().lower()

    assert "check (queue_status in (" in sql
    assert "'open'" in sql
    assert "'evidence_requested'" in sql
    assert "'preview_ready'" in sql
    assert "'applied'" in sql
    assert "check (status in (" in sql
    assert "blocked_no_internal_comp_evidence" in sql
    assert "create index if not exists idx_pricing_recovery_requests_queue_status" in sql
    assert "create index if not exists idx_pricing_recovery_request_events_request_id" in sql
```

- [ ] **Step 2: Run RED test**

Run:

```bash
/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/.venv/bin/python -m pytest tests/test_pricing_recovery_operator_queue_schema.py -q
```

Expected: fail because the migration file does not exist.

- [ ] **Step 3: Add migration**

Create `supabase/migrations/20260614_pricing_recovery_operator_queue.sql`:

```sql
create table if not exists public.pricing_recovery_requests (
  id uuid primary key default gen_random_uuid(),
  group_key text not null unique,
  year integer not null,
  make text not null,
  model text not null,
  state text,
  source_families text[] not null default '{}',
  candidate_count integer not null default 0 check (candidate_count >= 0),
  status text not null,
  recommended_action text not null,
  queue_status text not null default 'open',
  owner text,
  priority integer not null default 0,
  blocked_reason text,
  resolution_notes text,
  market_prices_usable integer not null default 0 check (market_prices_usable >= 0),
  market_prices_total integer not null default 0 check (market_prices_total >= 0),
  dealer_sales_usable integer not null default 0 check (dealer_sales_usable >= 0),
  dealer_sales_total integer not null default 0 check (dealer_sales_total >= 0),
  competitor_sales_usable integer not null default 0 check (competitor_sales_usable >= 0),
  competitor_sales_total integer not null default 0 check (competitor_sales_total >= 0),
  internal_history_usable integer not null default 0 check (internal_history_usable >= 0),
  internal_history_total integer not null default 0 check (internal_history_total >= 0),
  latest_proof_run_id text,
  latest_proof_head_sha text,
  last_seen_at timestamptz not null default timezone('utc', now()),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  resolved_at timestamptz,
  check (queue_status in ('open','evidence_requested','evidence_received','preview_ready','applied','blocked','dismissed')),
  check (status in ('covered_by_market_prices','covered_by_dealer_sales','covered_by_competitor_sales','seedable_from_internal_history','insufficient_dealer_sales','insufficient_internal_history','insufficient_competitor_sales','blocked_no_internal_comp_evidence','dirty_source_row','expired_pricing_gap')),
  check (recommended_action in ('none','refresh_market_prices_from_dealer_sales','refresh_market_prices_from_competitor_sales','review_internal_history_for_completed_sales_evidence','request_completed_sales_evidence','wait_for_more_internal_history','ignore_dirty_source_row','ignore_expired_listing'))
);

create table if not exists public.pricing_recovery_request_events (
  id uuid primary key default gen_random_uuid(),
  request_id uuid not null references public.pricing_recovery_requests(id) on delete cascade,
  event_type text not null,
  previous_queue_status text,
  next_queue_status text,
  actor text,
  reason text,
  proof_run_id text,
  head_sha text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now())
);

create index if not exists idx_pricing_recovery_requests_queue_status
  on public.pricing_recovery_requests(queue_status);

create index if not exists idx_pricing_recovery_requests_status
  on public.pricing_recovery_requests(status);

create index if not exists idx_pricing_recovery_request_events_request_id
  on public.pricing_recovery_request_events(request_id);
```

- [ ] **Step 4: Run GREEN test**

Run:

```bash
/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/.venv/bin/python -m pytest tests/test_pricing_recovery_operator_queue_schema.py -q
```

Expected: tests pass.

- [ ] **Step 5: Commit Task 2**

```bash
git add supabase/migrations/20260614_pricing_recovery_operator_queue.sql tests/test_pricing_recovery_operator_queue_schema.py
git commit -m "feat: add pricing recovery queue schema"
```

## Task 3: Dry-Run And Confirmation-Gated Sync

**Files:**
- Modify `scripts/pricing_recovery_operator_queue.py`
- Modify `tests/test_pricing_recovery_operator_queue.py`

- [ ] **Step 1: Add RED sync tests with a fake repository**

Append to `tests/test_pricing_recovery_operator_queue.py`:

```python
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
```

- [ ] **Step 2: Run RED test**

Run:

```bash
/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/.venv/bin/python -m pytest tests/test_pricing_recovery_operator_queue.py -q
```

Expected: fail because `sync_queue_records` does not exist.

- [ ] **Step 3: Implement repository protocol and sync**

Add to `scripts/pricing_recovery_operator_queue.py`:

```python
class QueueRepository(Protocol):
    def get_by_group_key(self, group_key: str) -> dict[str, Any] | None: ...
    def upsert_request(self, record: dict[str, Any]) -> dict[str, Any]: ...
    def insert_event(self, event: dict[str, Any]) -> None: ...


def sync_queue_records(
    records: list[dict[str, Any]],
    *,
    repo: QueueRepository,
    apply: bool,
    confirmation: str,
    actor: str = "local",
) -> dict[str, int]:
    if apply and confirmation != APPLY_CONFIRMATION:
        raise ValueError(f"queue sync requires confirmation={APPLY_CONFIRMATION}")

    summary = {"would_insert": 0, "would_update": 0, "inserted": 0, "updated": 0}
    for record in records:
        existing = repo.get_by_group_key(record["group_key"])
        if not apply:
            summary["would_update" if existing else "would_insert"] += 1
            continue
        saved = repo.upsert_request(record)
        event_type = "updated" if existing else "inserted"
        summary[event_type] += 1
        repo.insert_event(
            {
                "request_id": saved["id"],
                "event_type": event_type,
                "previous_queue_status": (existing or {}).get("queue_status"),
                "next_queue_status": saved["queue_status"],
                "actor": actor,
                "reason": record["recommended_action"],
                "proof_run_id": record.get("latest_proof_run_id"),
                "head_sha": record.get("latest_proof_head_sha"),
                "metadata": {"group_key": record["group_key"], "status": record["status"]},
            }
        )
    return summary
```

- [ ] **Step 4: Run GREEN test**

Run:

```bash
/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/.venv/bin/python -m pytest tests/test_pricing_recovery_operator_queue.py -q
```

Expected: tests pass.

- [ ] **Step 5: Commit Task 3**

```bash
git add scripts/pricing_recovery_operator_queue.py tests/test_pricing_recovery_operator_queue.py
git commit -m "feat: sync pricing recovery queue records"
```

## Task 4: Workflow Proof And Verification

**Files:**
- Modify `.github/workflows/pricing-coverage-gap-proof.yml`
- Modify `.github/workflows/pricing-substrate-recovery.yml`
- Modify `tests/workflows/test_pricing_coverage_gap_proof_workflow.py`
- Modify `tests/workflows/test_pricing_substrate_recovery_workflow.py`

- [ ] **Step 1: Add RED workflow tests**

Append focused assertions:

```python
def test_pricing_coverage_gap_proof_supports_queue_dry_run():
    text = WORKFLOW.read_text()

    assert "sync_queue" in text
    assert "SYNC_PRICING_RECOVERY_OPERATOR_QUEUE" in text
    assert "--queue-dry-run" in text
    assert "--queue-apply" in text


def test_pricing_substrate_recovery_prints_queue_proof_before_apply():
    text = WORKFLOW.read_text()

    assert "Print pricing recovery operator queue proof" in text
    assert "scripts/pricing_recovery_operator_queue.py" in text
    assert "--queue-dry-run" in text
```

Adjust the variable name to match each workflow test file's existing `WORKFLOW` constant.

- [ ] **Step 2: Run RED workflow tests**

Run:

```bash
/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/.venv/bin/python -m pytest tests/workflows/test_pricing_coverage_gap_proof_workflow.py tests/workflows/test_pricing_substrate_recovery_workflow.py -q
```

Expected: fail because queue workflow options do not exist.

- [ ] **Step 3: Add workflow queue proof mode**

In `.github/workflows/pricing-coverage-gap-proof.yml`, add inputs:

```yaml
      sync_queue:
        description: "Dry-run or sync pricing recovery operator queue"
        required: true
        default: "false"
        type: choice
        options:
          - "false"
          - "dry-run"
          - "apply"
      queue_confirmation:
        description: "Required only when sync_queue=apply: SYNC_PRICING_RECOVERY_OPERATOR_QUEUE"
        required: false
        default: ""
```

Add a step after grouped proof:

```yaml
      - name: Print pricing recovery operator queue proof
        if: ${{ inputs.sync_queue != 'false' }}
        run: |
          set -euo pipefail
          args=(--from-live-pricing-proof --proof-run-id "${{ github.run_id }}" --head-sha "${{ github.sha }}" --queue-dry-run)
          if [[ "${{ inputs.sync_queue }}" == "apply" ]]; then
            if [[ "${{ inputs.queue_confirmation }}" != "SYNC_PRICING_RECOVERY_OPERATOR_QUEUE" ]]; then
              echo "Queue sync requires confirmation=SYNC_PRICING_RECOVERY_OPERATOR_QUEUE" >&2
              exit 2
            fi
            args=(--from-live-pricing-proof --proof-run-id "${{ github.run_id }}" --head-sha "${{ github.sha }}" --queue-apply --confirmation "${{ inputs.queue_confirmation }}")
          fi
          python3 scripts/pricing_recovery_operator_queue.py "${args[@]}"
```

In `.github/workflows/pricing-substrate-recovery.yml`, add a read-only queue proof step before market-price preview/apply.

- [ ] **Step 4: Run GREEN workflow tests and focused slice**

Run:

```bash
/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/.venv/bin/python -m pytest tests/test_pricing_recovery_operator_queue.py tests/test_pricing_recovery_operator_queue_schema.py tests/workflows/test_pricing_coverage_gap_proof_workflow.py tests/workflows/test_pricing_substrate_recovery_workflow.py -q
```

Expected: tests pass.

- [ ] **Step 5: Commit Task 4**

```bash
git add .github/workflows/pricing-coverage-gap-proof.yml .github/workflows/pricing-substrate-recovery.yml tests/workflows/test_pricing_coverage_gap_proof_workflow.py tests/workflows/test_pricing_substrate_recovery_workflow.py
git commit -m "feat: prove pricing recovery queue workflow"
```

## Task 5: Local, PR, And Live Gates

**Files:**
- No new files unless review feedback requires RED/GREEN regressions.

- [ ] **Step 1: Run focused queue and recovery proof**

Run:

```bash
/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/.venv/bin/python -m pytest tests/test_pricing_recovery_operator_queue.py tests/test_pricing_recovery_operator_queue_schema.py tests/test_pricing_coverage_gap_report.py tests/test_refresh_market_prices_from_completed_sales.py tests/workflows/test_pricing_coverage_gap_proof_workflow.py tests/workflows/test_pricing_substrate_recovery_workflow.py -q
```

Expected: all focused tests pass.

- [ ] **Step 2: Run adjacent proof**

Run:

```bash
/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/.venv/bin/python -m pytest tests/test_supabase_live_inspection.py tests/test_internal_pipeline_truth.py tests/test_competitor_sales_schema.py tests/test_competitor_sales_scraper_runner.py -q
```

Expected: all adjacent tests pass.

- [ ] **Step 3: Run full suite and diff check**

Run:

```bash
/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/.venv/bin/python -m pytest tests -q
git diff --check
```

Expected: full suite passes and diff check is clean.

- [ ] **Step 4: Publish PR**

Run:

```bash
git status --short
git push -u origin fix/pricing-recovery-operator-queue
gh pr create --title "Add pricing recovery operator queue" --body "Adds a governed, sanitized operator queue contract for pricing recovery groups. No scoring gates are changed and no market-price writes occur without explicit confirmation."
```

Expected: PR opens against main.

- [ ] **Step 5: Review gate**

Wait for:

- DealerScope CI
- Cursor Code Review
- Vercel Deploy Gate
- fresh Cursor/Bugbot review

If any review finding is valid, add a RED regression first, fix it, rerun focused and full verification, then push. Do not merge on green CI alone if review has current findings.

- [ ] **Step 6: Merge and live proof**

After PR checks and review are clean, merge. Then run/verify:

```bash
gh run list --branch main --limit 8 --json databaseId,name,headSha,status,conclusion,url
```

Trigger or inspect:

- DealerScope Supabase Live Inspection
- Pricing Coverage Gap Proof
- Pricing Coverage Gap Proof with queue dry-run
- Railway `/healthz`

Expected: all current-main proof is green. The closeout status is `live-confirmed` only for operator queue governance if queue proof passes; pricing quality remains `live-improved but pending` unless evidence acquisition and confirmed market-price refresh actually improve `market_data_quality`.
