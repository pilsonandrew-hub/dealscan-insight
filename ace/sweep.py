from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .repository import Item, ItemRepository
from .storage import DB_PATH, append_event, bootstrap_db, connect, utc_now

SWEEP_EVENT_TYPE = "ace.sweep.completed"
ITEM_SWEEP_FLAGGED_EVENT_TYPE = "item.sweep_flagged"
SWEEP_SOURCE = "ace/sweep.py"

DEFAULT_TRIAGE_AFTER_HOURS = 24
DEFAULT_APPROVED_AFTER_HOURS = 72
DEFAULT_BLOCKED_AFTER_HOURS = 24
DEFAULT_CLAIMED_DONE_AFTER_HOURS = 24
DEFAULT_ACTIVE_AFTER_HOURS = 72


@dataclass(frozen=True)
class SweepThresholds:
    triage_after_seconds: int = DEFAULT_TRIAGE_AFTER_HOURS * 3600
    approved_after_seconds: int = DEFAULT_APPROVED_AFTER_HOURS * 3600
    blocked_after_seconds: int = DEFAULT_BLOCKED_AFTER_HOURS * 3600
    claimed_done_after_seconds: int = DEFAULT_CLAIMED_DONE_AFTER_HOURS * 3600
    active_after_seconds: int = DEFAULT_ACTIVE_AFTER_HOURS * 3600

    def as_dict(self) -> dict[str, int]:
        return {
            "triage_after_seconds": self.triage_after_seconds,
            "approved_after_seconds": self.approved_after_seconds,
            "blocked_after_seconds": self.blocked_after_seconds,
            "claimed_done_after_seconds": self.claimed_done_after_seconds,
            "active_after_seconds": self.active_after_seconds,
        }


@dataclass(frozen=True)
class SweepFinding:
    item_id: str
    classification: str
    state: str
    title: str
    activity_at: str
    age_seconds: int
    stale_after_seconds: int
    evidence_count: int
    open_obligation_count: int
    open_contradiction_count: int
    fingerprint: str
    suppressed: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "classification": self.classification,
            "state": self.state,
            "title": self.title,
            "activity_at": self.activity_at,
            "age_seconds": self.age_seconds,
            "stale_after_seconds": self.stale_after_seconds,
            "evidence_count": self.evidence_count,
            "open_obligation_count": self.open_obligation_count,
            "open_contradiction_count": self.open_contradiction_count,
            "fingerprint": self.fingerprint,
            "suppressed": self.suppressed,
        }


def collect_sweep_findings(
    db_path: Path | str = DB_PATH,
    *,
    thresholds: SweepThresholds | None = None,
    now: str | None = None,
) -> list[SweepFinding]:
    bootstrap_db(db_path)
    repo = ItemRepository(db_path)
    thresholds = thresholds or SweepThresholds()
    run_started_at = now or utc_now()
    return _collect_findings_from_repo(repo, thresholds=thresholds, now=run_started_at)


def run_sweep(
    db_path: Path | str = DB_PATH,
    *,
    thresholds: SweepThresholds | None = None,
    actor: str | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    bootstrap_db(db_path)
    repo = ItemRepository(db_path)
    thresholds = thresholds or SweepThresholds()
    run_started_at = now or utc_now()
    run_id = f"sweep:{run_started_at}"

    findings = _collect_findings_from_repo(repo, thresholds=thresholds, now=run_started_at)
    emitted_count = 0
    suppressed_count = 0
    final_findings: list[SweepFinding] = []

    for finding in findings:
        previous_fingerprint = _latest_sweep_fingerprint(repo, finding.item_id)
        suppressed = previous_fingerprint == finding.fingerprint
        final_finding = SweepFinding(
            item_id=finding.item_id,
            classification=finding.classification,
            state=finding.state,
            title=finding.title,
            activity_at=finding.activity_at,
            age_seconds=finding.age_seconds,
            stale_after_seconds=finding.stale_after_seconds,
            evidence_count=finding.evidence_count,
            open_obligation_count=finding.open_obligation_count,
            open_contradiction_count=finding.open_contradiction_count,
            fingerprint=finding.fingerprint,
            suppressed=suppressed,
        )
        final_findings.append(final_finding)

        if suppressed:
            suppressed_count += 1
            continue

        _append_item_sweep_event(
            db_path,
            finding=final_finding,
            actor=actor,
            run_id=run_id,
            created_at=run_started_at,
        )
        emitted_count += 1

    _append_sweep_summary_event(
        db_path,
        run_id=run_id,
        actor=actor,
        created_at=run_started_at,
        thresholds=thresholds,
        findings=final_findings,
        emitted_count=emitted_count,
        suppressed_count=suppressed_count,
    )

    return {
        "run_id": run_id,
        "created_at": run_started_at,
        "thresholds": thresholds.as_dict(),
        "finding_count": len(final_findings),
        "emitted_count": emitted_count,
        "suppressed_count": suppressed_count,
        "findings": [finding.as_dict() for finding in final_findings],
    }


def _collect_findings_from_repo(
    repo: ItemRepository,
    *,
    thresholds: SweepThresholds,
    now: str,
) -> list[SweepFinding]:
    findings: list[SweepFinding] = []
    for item in repo.list_items():
        finding = _classify_item(repo, item, thresholds=thresholds, now=now)
        if finding is not None:
            findings.append(finding)
    return findings


def _classify_item(
    repo: ItemRepository,
    item: Item,
    *,
    thresholds: SweepThresholds,
    now: str,
) -> SweepFinding | None:
    classification, stale_after_seconds = _classification_for_state(item.state, thresholds)
    if classification is None or stale_after_seconds is None:
        return None

    activity_at = _latest_activity_at(repo, item)
    age_seconds = _age_seconds(activity_at, now)
    if age_seconds < stale_after_seconds:
        return None

    evidence_count = repo.item_evidence_count(item.id)
    open_obligation_count = repo.item_open_obligation_count(item.id)
    open_contradiction_count = repo.item_open_contradiction_count(item.id)
    fingerprint = _fingerprint(
        {
            "item_id": item.id,
            "classification": classification,
            "state": item.state,
            "activity_at": activity_at,
            "last_event_id": item.last_event_id,
            "age_seconds": age_seconds,
            "stale_after_seconds": stale_after_seconds,
            "evidence_count": evidence_count,
            "open_obligation_count": open_obligation_count,
            "open_contradiction_count": open_contradiction_count,
        }
    )

    return SweepFinding(
        item_id=item.id,
        classification=classification,
        state=item.state,
        title=item.title,
        activity_at=activity_at,
        age_seconds=age_seconds,
        stale_after_seconds=stale_after_seconds,
        evidence_count=evidence_count,
        open_obligation_count=open_obligation_count,
        open_contradiction_count=open_contradiction_count,
        fingerprint=fingerprint,
        suppressed=False,
    )


def _classification_for_state(
    state: str,
    thresholds: SweepThresholds,
) -> tuple[str | None, int | None]:
    mapping = {
        "TRIAGE": ("stale_triage", thresholds.triage_after_seconds),
        "APPROVED": ("stale_approved", thresholds.approved_after_seconds),
        "BLOCKED": ("stale_blocked", thresholds.blocked_after_seconds),
        "CLAIMED_DONE": ("stale_claimed_done", thresholds.claimed_done_after_seconds),
        "ACTIVE": ("stale_active_legacy", thresholds.active_after_seconds),
    }
    return mapping.get(state, (None, None))


def _latest_activity_at(repo: ItemRepository, item: Item) -> str:
    latest = item.updated_at or item.created_at
    events = repo.list_item_events(item.id, limit=1)
    if events:
        latest = _max_timestamp(latest, events[-1].created_at)
    return latest


def _max_timestamp(left: str, right: str) -> str:
    return left if _parse_timestamp(left) >= _parse_timestamp(right) else right


def _age_seconds(activity_at: str, now: str) -> int:
    delta = _parse_timestamp(now) - _parse_timestamp(activity_at)
    seconds = int(delta.total_seconds())
    return max(seconds, 0)


def _parse_timestamp(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _latest_sweep_fingerprint(repo: ItemRepository, item_id: str) -> str | None:
    events = repo.list_item_events(item_id, event_type=ITEM_SWEEP_FLAGGED_EVENT_TYPE, limit=1)
    if not events:
        return None
    event = events[-1]
    if event.payload_json is None:
        return None
    payload = json.loads(event.payload_json)
    fingerprint = payload.get("fingerprint")
    return fingerprint if isinstance(fingerprint, str) and fingerprint else None


def _append_item_sweep_event(
    db_path: Path | str,
    *,
    finding: SweepFinding,
    actor: str | None,
    run_id: str,
    created_at: str,
) -> None:
    payload = finding.as_dict()
    with connect(db_path) as connection:
        append_event(
            connection,
            event_type=ITEM_SWEEP_FLAGGED_EVENT_TYPE,
            payload=payload,
            item_id=finding.item_id,
            actor=actor,
            source=SWEEP_SOURCE,
            session_id=run_id,
            created_at=created_at,
        )
        connection.commit()


def _append_sweep_summary_event(
    db_path: Path | str,
    *,
    run_id: str,
    actor: str | None,
    created_at: str,
    thresholds: SweepThresholds,
    findings: list[SweepFinding],
    emitted_count: int,
    suppressed_count: int,
) -> None:
    summary_payload = {
        "run_id": run_id,
        "thresholds": thresholds.as_dict(),
        "finding_count": len(findings),
        "emitted_count": emitted_count,
        "suppressed_count": suppressed_count,
        "findings": [
            {
                "item_id": finding.item_id,
                "classification": finding.classification,
                "state": finding.state,
                "activity_at": finding.activity_at,
                "age_seconds": finding.age_seconds,
                "suppressed": finding.suppressed,
            }
            for finding in findings
        ],
    }
    with connect(db_path) as connection:
        append_event(
            connection,
            event_type=SWEEP_EVENT_TYPE,
            payload=summary_payload,
            actor=actor,
            source=SWEEP_SOURCE,
            session_id=run_id,
            created_at=created_at,
        )
        connection.commit()
