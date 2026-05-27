from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ace.repository import ItemRepository, ValidationError
from ace.autonomy_lane import intake_autonomy_eligible_direct_work, mark_item_autonomy_eligible
from ace.governed_run_runtime import get_governed_cycle_run_status
from ace.health import render_health_summary_lines
from ace.governed_run_runtime import correct_governed_run_trigger_kind
from ace.supervisor_runtime import (
    RUNTIME_FAMILY_SINGLE_TENANT,
    get_supervisor_runtime_status,
    request_supervisor_shutdown,
    run_supervisor_runtime,
)
from ace.supervisor_acceptance_monitor import run_supervisor_acceptance_monitor
from ace.storage import DB_PATH, bootstrap_db, connect_readonly, verify_audit_integrity
from ace.sweep import SweepThresholds, run_sweep
from ace.briefing import generate_briefing, render_briefing_text
from ace.cycle import BRIEFING_PATH, run_cycle
from ace.drift import compute_item_drift
from ace.workflow import AceError, normalize_state
from ace.cost_guardrails import (
    CostGuardrailPolicy,
    get_cost_guardrail_status,
    record_cost_usage,
)
from ace.action_runtime import send_jace_status_message
from ace.telegram_runtime import load_ace_telegram_env_file
import ace.action_runtime as action_runtime
from ace.jace_audit import audit_jace_delivery_history
from ace.attestation.backblaze import B2AttestationClient, B2Config, B2ConfigurationError
from ace.attestation.sync import sync_attestation_records
from ace.attestation.verify import EXTERNAL_ATTESTATION_NOT_CONFIGURED, verify_external_attestation


EXIT_OK = 0
EXIT_FAILED = 1
EXIT_NOT_CONFIGURED = 2
TELEGRAM_MESSAGE_LIMIT = 4096


def _normalize_optional_text(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        raise ValidationError(f"{field_name} must not be empty or whitespace-only")
    return normalized


def _normalize_required_text(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValidationError(f"{field_name} must not be empty or whitespace-only")
    return normalized


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ace", description="Super A.C.E. governed foundation operator entrypoint")
    parser.add_argument("--db", default=str(DB_PATH), help="Path to the ACE SQLite database")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("init", help="Initialize the local ACE database")
    subparsers.add_parser("bootstrap", help="Alias for init")

    intake = subparsers.add_parser("intake", help="Create a new TRIAGE item")
    intake.add_argument("item_type")
    intake.add_argument("title")
    intake.add_argument("--description")
    intake.add_argument("--priority-hint")
    intake.add_argument("--confidence-tier")
    intake.add_argument("--verdict")
    intake.add_argument("--source")
    intake.add_argument("--session")
    intake.add_argument("--deadline")
    intake.add_argument("--owner")
    intake.add_argument("--actor")

    list_cmd = subparsers.add_parser("list", help="List items")
    list_cmd.add_argument("--state")

    stale = subparsers.add_parser("stale", help="List work items idle longer than N days")
    stale.add_argument("--days", type=int, default=7)

    subparsers.add_parser("loose-ends", help="List recent ACE evidence and workflow gaps")

    digest = subparsers.add_parser("digest", help="Send weekly ACE stale and loose-ends digest via JACE Telegram")
    digest.add_argument("--days", type=int, default=7)
    digest.add_argument("--chat-id")
    digest.add_argument("--actor")
    digest.add_argument("--dry-run", action="store_true", help="Print the formatted digest message without sending Telegram")

    contradictions = subparsers.add_parser(
        "contradictions",
        help="Compare high-value ACE documentation claims to verifiable CLI, git, and CI state",
    )
    contradictions.add_argument(
        "--repo-root",
        help="Repository root for git tags, workflow paths, and optional CI probes (default: parent of ace/)",
    )
    contradictions.add_argument("--readme", help="README path (default: <repo-root>/ace/README.md)")
    contradictions.add_argument("--status", help="STATUS path (default: <repo-root>/ace/STATUS.md)")
    contradictions.add_argument(
        "--skip-ci",
        action="store_true",
        help="Skip CI badge comparison (offline runs and tests)",
    )

    hooks = subparsers.add_parser(
        "hooks",
        help="Install operational ACE git hooks (false-closure advisory)",
    )
    hooks_subparsers = hooks.add_subparsers(dest="hooks_command")
    hooks_subparsers.add_parser(
        "install",
        help="Set core.hooksPath to ace/hooks/operational (non-blocking commit-msg advisory)",
    )
    hooks_subparsers.add_parser("status", help="Show whether operational ACE hooks are installed")

    propose = subparsers.add_parser(
        "propose",
        help="Scan OpenClaw Telegram session stream for first-person commitment proposals",
    )
    propose.add_argument(
        "propose_action",
        nargs="?",
        choices=["accept", "reject"],
        help="accept or reject a TRIAGE commitment proposal item",
    )
    propose.add_argument("item_id", nargs="?", help="Proposal item id for accept/reject")
    propose.add_argument(
        "--session-file",
        help="OpenClaw session JSONL path (default: resolve from ACE_OPENCLAW_SESSION_FILE or sessions index)",
    )
    propose.add_argument("--actor", help="Actor label for accept/reject decisions")

    filter_health = subparsers.add_parser(
        "filter-health",
        help="Monthly signal-to-noise summary for ACE intake and proposal filters",
    )
    filter_health.add_argument("--month", help="Report month as YYYY-MM (default: current UTC month)")
    filter_health.add_argument(
        "--decisions-log",
        help="Proposal decision log path (default: ace/state/propose_filter_decisions.jsonl)",
    )

    show = subparsers.add_parser("show", help="Show a single item")
    show.add_argument("item_id")
    show.add_argument("--event-type")
    show.add_argument("--event-limit", type=int)

    inspect = subparsers.add_parser("inspect", help="Inspect one item with drift dimensions")
    inspect.add_argument("item_id")
    inspect.add_argument("--event-type")
    inspect.add_argument("--event-limit", type=int)
    inspect.add_argument("--drift-window", type=int, default=20)

    record_verdict = subparsers.add_parser("record-verdict", help="Record an append-only item verdict")
    record_verdict.add_argument("item_id")
    record_verdict.add_argument("verdict")
    record_verdict.add_argument("--reason")
    record_verdict.add_argument("--actor")
    record_verdict.add_argument("--source")
    record_verdict.add_argument("--session")

    sweep = subparsers.add_parser("sweep", help="Classify stale bounded work from live ACE state")
    sweep.add_argument("--triage-after-hours", type=int, default=24)
    sweep.add_argument("--approved-after-hours", type=int, default=72)
    sweep.add_argument("--blocked-after-hours", type=int, default=24)
    sweep.add_argument("--claimed-done-after-hours", type=int, default=24)
    sweep.add_argument("--active-after-hours", type=int, default=72)
    sweep.add_argument("--actor")

    briefing = subparsers.add_parser("briefing", help="Generate bounded operator briefing from live ACE state")
    briefing.add_argument("--triage-after-hours", type=int, default=24)
    briefing.add_argument("--approved-after-hours", type=int, default=72)
    briefing.add_argument("--blocked-after-hours", type=int, default=24)
    briefing.add_argument("--claimed-done-after-hours", type=int, default=24)
    briefing.add_argument("--active-after-hours", type=int, default=72)

    cycle = subparsers.add_parser("cycle", help="Run one bounded autonomous ACE operator cycle")
    cycle.add_argument("--triage-after-hours", type=int, default=24)
    cycle.add_argument("--approved-after-hours", type=int, default=72)
    cycle.add_argument("--blocked-after-hours", type=int, default=24)
    cycle.add_argument("--claimed-done-after-hours", type=int, default=24)
    cycle.add_argument("--active-after-hours", type=int, default=72)
    cycle.add_argument("--notification-channel")
    cycle.add_argument("--notification-target")
    cycle.add_argument("--notification-thread-id")
    cycle.add_argument("--disable-notifications", action="store_true")
    cycle.add_argument("--briefing-path", default=str(BRIEFING_PATH))
    cycle.add_argument("--actor")

    subparsers.add_parser("cycle-status", help="Show current active and last terminal governed cycle run")
    correct_governed_run = subparsers.add_parser(
        "correct-governed-run-trigger",
        help="Apply an audited trigger_kind correction to a historical governed run",
    )
    correct_governed_run.add_argument("run_id")
    correct_governed_run.add_argument("trigger_kind")
    correct_governed_run.add_argument("--reason", required=True)
    correct_governed_run.add_argument("--actor")
    correct_governed_run.add_argument("--source")
    correct_governed_run.add_argument("--session")
    supervisor_run = subparsers.add_parser(
        "supervisor-run",
        help="Run one bounded resident supervisor-runtime slice",
    )
    supervisor_run.add_argument("--runtime-family", default=RUNTIME_FAMILY_SINGLE_TENANT)
    supervisor_run.add_argument("--stale-after-seconds", type=int, default=60)
    supervisor_run.add_argument("--heartbeat-count", type=int, default=0)
    supervisor_run.add_argument("--heartbeat-interval-seconds", type=float, default=0.0)
    supervisor_run.add_argument("--host-identity")
    supervisor_run.add_argument(
        "--run-until-shutdown",
        action="store_true",
        help="Keep the resident supervisor live until an explicit shutdown request is recorded",
    )
    subparsers.add_parser(
        "supervisor-status",
        help="Show current active and last terminal resident supervisor runtime",
    )
    supervisor_monitor = subparsers.add_parser(
        "supervisor-acceptance-monitor",
        help="Run a governed acceptance monitor for the resident supervisor seam",
    )
    supervisor_monitor.add_argument("--service-target", required=True)
    supervisor_monitor.add_argument("--log-path", required=True)
    supervisor_monitor.add_argument("--err-path", required=True)
    supervisor_monitor.add_argument("--pid-path", required=True)
    supervisor_monitor.add_argument("--iterations", type=int, default=65)
    supervisor_monitor.add_argument("--sleep-seconds", type=float, default=60.0)
    supervisor_monitor.add_argument(
        "--truncate-on-start",
        action="store_true",
        help="Start a brand new log instead of appending to an existing lineage",
    )
    supervisor_shutdown = subparsers.add_parser(
        "supervisor-shutdown",
        help="Request shutdown for the current live/stale resident supervisor runtime",
    )
    supervisor_shutdown.add_argument("--runtime-instance-id")
    subparsers.add_parser(
        "gate4-inspection",
        help="Show bounded operator-facing Gate 4 inspection artifacts already governed on disk",
    )

    audit = subparsers.add_parser("audit", help="Run first-class ACE audit checks")
    audit_subparsers = audit.add_subparsers(dest="audit_command")
    audit_subparsers.add_parser("verify", help="Verify append-only event hash chain integrity")
    jace_audit = audit_subparsers.add_parser("jace", help="Read-only cross-table JACE delivery audit")
    jace_audit.add_argument("--json", action="store_true", help="Emit full JSON audit records")

    attestation = subparsers.add_parser("attestation", help="Operate ACE V1.1 external attestation")
    attestation_subparsers = attestation.add_subparsers(dest="attestation_command")
    attestation_subparsers.add_parser("status", help="Read-only external attestation status")
    attestation_sync = attestation_subparsers.add_parser(
        "sync",
        help="Synchronize post-cutover hashes to configured B2 attestation store",
    )
    attestation_sync.add_argument(
        "--progress-every",
        type=int,
        default=100,
        help="Print attestation sync progress every N objects",
    )

    cost = subparsers.add_parser("cost", help="Inspect and record local ACE cost guardrails")
    cost_subparsers = cost.add_subparsers(dest="cost_command")
    cost_status = cost_subparsers.add_parser("status", help="Show local ACE cost guardrail status")
    cost_status.add_argument("--cost-limit-cents", type=int)
    cost_status.add_argument("--token-limit", type=int)
    cost_status.add_argument("--session-count-limit", type=int)
    cost_record = cost_subparsers.add_parser("record", help="Record local ACE cost usage")
    cost_record.add_argument("--cost-cents", type=int, default=0)
    cost_record.add_argument("--tokens", type=int, default=0)
    cost_record.add_argument("--session-count", type=int, default=0)
    cost_record.add_argument("--source", default="manual")
    cost_record.add_argument("--session")

    evidence = subparsers.add_parser("add-evidence", help="Add evidence for an item")
    evidence.add_argument("item_id")
    evidence.add_argument("evidence_text")
    evidence.add_argument("--evidence-uri")
    evidence.add_argument("--created-by")
    evidence.add_argument("--actor")

    jace_status = subparsers.add_parser(
        "jace-status-send",
        help="Send a JACE-owned outbound status message and record delivery evidence",
    )
    jace_status.add_argument("item_id")
    jace_status.add_argument("message")
    jace_status.add_argument("--chat-id")
    jace_status.add_argument("--actor")

    autonomy_eligible = subparsers.add_parser(
        "mark-autonomy-eligible",
        help="Mark a direct work item as explicitly eligible for governed autonomy",
    )
    autonomy_eligible.add_argument("item_id")
    autonomy_eligible.add_argument("--reason", required=True)
    autonomy_eligible.add_argument("--actor")

    intake_direct_work = subparsers.add_parser(
        "intake-direct-work",
        help="Create a governed direct-work item already marked eligible for autonomy",
    )
    intake_direct_work.add_argument("title")
    intake_direct_work.add_argument("--reason", required=True)
    intake_direct_work.add_argument("--session", required=True)
    intake_direct_work.add_argument("--description")
    intake_direct_work.add_argument("--priority-hint")
    intake_direct_work.add_argument("--owner")
    intake_direct_work.add_argument("--actor")

    obligation = subparsers.add_parser("add-obligation", help="Add an obligation for an item")
    obligation.add_argument("item_id")
    obligation.add_argument("obligation_type")
    obligation.add_argument("--status", default="open")
    obligation.add_argument("--target-surface")
    obligation.add_argument("--notes")
    obligation.add_argument("--actor")

    contradiction = subparsers.add_parser("add-contradiction", help="Add a contradiction for an item")
    contradiction.add_argument("item_id", help="The item being contradicted")
    contradiction.add_argument("source_item_id", help="The item that contradicts it")
    contradiction.add_argument("--status", default="open")
    contradiction.add_argument("--reason")
    contradiction.add_argument("--actor")

    record_correction = subparsers.add_parser(
        "record-correction",
        help="Record that one item corrects another without rewriting original truth",
    )
    record_correction.add_argument("item_id", help="The original item being corrected")
    record_correction.add_argument("corrected_item_id", help="The correcting item")
    record_correction.add_argument("--reason", required=True)
    record_correction.add_argument("--actor")


    correction_submit = subparsers.add_parser(
        "correction",
        help="Submit audited ACE state corrections",
    )
    correction_subparsers = correction_submit.add_subparsers(dest="correction_command")
    closeout_correction = correction_subparsers.add_parser(
        "submit",
        help="Submit an audited closeout metadata correction",
    )
    closeout_correction.add_argument("item_id")
    closeout_correction.add_argument("--closed-at", required=True)
    closeout_correction.add_argument("--closed-by", required=True)
    closeout_correction.add_argument("--closed-reason", required=True)
    closeout_correction.add_argument("--reason", required=True)
    closeout_correction.add_argument("--actor")

    resolve_contradiction = subparsers.add_parser(
        "resolve-contradiction",
        help="Resolve an existing contradiction",
    )
    resolve_contradiction.add_argument("contradiction_id")
    resolve_contradiction.add_argument("--reason")
    resolve_contradiction.add_argument("--actor")

    resolve_obligation = subparsers.add_parser(
        "resolve-obligation",
        help="Resolve an existing obligation",
    )
    resolve_obligation.add_argument("obligation_id")
    resolve_obligation.add_argument("--reason")
    resolve_obligation.add_argument("--actor")

    for name in ("approve", "block", "done", "resolve", "drop"):
        command = subparsers.add_parser(name, help=f"Apply the {name} transition")
        command.add_argument("item_id")
        command.add_argument("--reason")
        command.add_argument("--actor")
        command.add_argument("--source")
        command.add_argument("--session")
        if name == "resolve":
            command.add_argument("--verdict", help="Append a verdict before closeout; must be pass to close")

    return parser


def _print_item(item) -> None:
    print(
        "item_id={id} item_type={item_type} state={state} title={title}".format(
            id=item.id,
            item_type=item.item_type,
            state=item.state,
            title=item.title,
        )
    )
    if item.description:
        print(f"description={item.description}")
    if item.priority_hint:
        print(f"priority_hint={item.priority_hint}")
    if item.confidence_tier:
        print(f"confidence_tier={item.confidence_tier}")
    if item.verdict:
        print(f"verdict={item.verdict}")
    if item.source:
        print(f"source={item.source}")
    if item.source_session:
        print(f"session={item.source_session}")
    if item.deadline_at:
        print(f"deadline={item.deadline_at}")
    if item.owner:
        print(f"owner={item.owner}")
    if item.closed_at:
        print(f"closed_at={item.closed_at}")
    if item.closed_by:
        print(f"closed_by={item.closed_by}")
    if item.closed_reason:
        print(f"closed_reason={item.closed_reason}")
    if item.last_event_id:
        print(f"last_event_id={item.last_event_id}")


def _print_drift_report(report) -> None:
    print(f"drift.item_id={report.item_id}")
    print(f"drift.composite_score={report.composite_score}")
    for index, dimension in enumerate(report.dimensions):
        print(f"drift.dimension[{index}].name={dimension.name}")
        print(f"drift.dimension[{index}].score={dimension.score}")
        print(f"drift.dimension[{index}].sample_count={dimension.sample_count}")
        print(f"drift.dimension[{index}].status={dimension.status}")
        print(f"drift.dimension[{index}].detail={dimension.detail}")


def _print_item_events(events: Iterable) -> None:
    events = list(events)
    print(f"event_count={len(events)}")
    for index, event in enumerate(events):
        print(f"event[{index}].id={event.event_id}")
        print(f"event[{index}].type={event.event_type}")
        print(f"event[{index}].created_at={event.created_at}")
        if event.actor:
            print(f"event[{index}].actor={event.actor}")
        if event.source:
            print(f"event[{index}].source={event.source}")
        if event.session_id:
            print(f"event[{index}].session={event.session_id}")
        print(f"event[{index}].payload_status={event.payload_status}")
        if event.payload_json is not None:
            print(f"event[{index}].payload={event.payload_json}")
        if event.payload_raw is not None:
            print(f"event[{index}].payload_raw={event.payload_raw}")


def _print_items(items: Iterable) -> None:
    items = list(items)
    print(f"count={len(items)}")
    for item in items:
        print(
            "item_id={id} state={state} title={title}".format(
                id=item.id,
                state=item.state,
                title=item.title,
            )
        )


def _parse_ace_timestamp(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _stale_rows(db_path: Path | str, *, days: int) -> list[dict[str, object]]:
    if days < 0:
        raise ValidationError("days must be greater than or equal to 0")
    now = datetime.now(timezone.utc)
    with connect_readonly(db_path) as connection:
        rows = connection.execute(
            """
            SELECT
                items.id AS item_id,
                items.state AS state,
                events.event_type AS last_event_type,
                events.created_at AS last_event_at
            FROM items
            LEFT JOIN events ON events.event_id = items.last_event_id
            WHERE events.created_at IS NOT NULL
              AND items.state IN ('TRIAGE', 'APPROVED', 'CLAIMED_DONE')
            ORDER BY events.created_at ASC, items.id ASC
            """
        ).fetchall()
    stale: list[dict[str, object]] = []
    for row in rows:
        last_event_at = _parse_ace_timestamp(row["last_event_at"])
        age_seconds = max(0.0, (now - last_event_at).total_seconds())
        days_idle = int(age_seconds // 86400)
        if days_idle >= days:
            stale.append(
                {
                    "item_id": row["item_id"],
                    "state": row["state"],
                    "days_idle": days_idle,
                    "last_event_type": row["last_event_type"],
                }
            )
    stale.sort(key=lambda item: (-int(item["days_idle"]), str(item["item_id"])))
    return stale


def _print_stale_rows(rows: list[dict[str, object]]) -> None:
    print(f"{'item_id':<36} {'current_state':<14} {'days_idle':>9} {'last_event_type':<32}")
    for row in rows:
        print(
            f"{str(row['item_id']):<36} "
            f"{str(row['state']):<14} "
            f"{int(row['days_idle']):>9} "
            f"{str(row['last_event_type']):<32}"
        )


def _event_payload(row: object) -> dict[str, object]:
    try:
        raw = row["payload_json"]  # type: ignore[index]
    except (KeyError, TypeError):
        raw = None
    if not raw:
        return {}
    try:
        parsed = json.loads(str(raw))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _is_supporting_evidence_row(row: object) -> bool:
    try:
        evidence_uri = row["evidence_uri"]  # type: ignore[index]
        evidence_text = row["evidence_text"]  # type: ignore[index]
    except (KeyError, TypeError):
        return False
    payload: dict[str, object] = {}
    if evidence_text:
        try:
            parsed = json.loads(str(evidence_text))
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            payload = parsed
    from ace.drift import is_claim_supporting_evidence_uri

    return is_claim_supporting_evidence_uri(evidence_uri, payload=payload)


def _transition_states(row: object) -> tuple[str | None, str | None]:
    payload = _event_payload(row)
    from_state = payload.get("from_state")
    to_state = payload.get("to_state")
    return (str(from_state) if from_state is not None else None, str(to_state) if to_state is not None else None)


def _is_operator_initiated_source(source: object) -> bool:
    if source is None:
        return False
    normalized = str(source).strip().lower()
    if not normalized:
        return False
    if normalized in {"ace.internal", "ace.self-test", "ace.sweep"}:
        return False
    return normalized.startswith("telegram") or normalized.startswith("jace") or normalized in {
        "cli",
        "manual",
        "manual/cli",
        "cli/manual",
        "ace.cli",
    }


def _is_cleanup_residue_evidence_row(row: object) -> bool:
    try:
        evidence_uri = row["evidence_uri"]  # type: ignore[index]
        evidence_text = row["evidence_text"]  # type: ignore[index]
    except (KeyError, TypeError):
        return False
    marker_text = f"{evidence_uri or ''} {evidence_text or ''}".lower().replace("-", "_")
    return "cleanup" in marker_text or "historical_residue" in marker_text or "historical residue" in marker_text


def _state_predecessor_gap_suppressed_item_ids(connection: object) -> set[str]:
    rows = connection.execute(
        """
        SELECT DISTINCT items.id AS item_id
        FROM items
        JOIN events ON events.item_id = items.id
        JOIN evidence ON evidence.item_id = items.id
        WHERE items.state = 'VERIFIED_DONE'
          AND events.event_type = 'item.state_changed'
          AND events.source = 'ace/self-supervision'
        """
    ).fetchall()
    suppressed: set[str] = set()
    for row in rows:
        evidence_rows = connection.execute(
            "SELECT evidence_uri, evidence_text FROM evidence WHERE item_id = ?",
            (row["item_id"],),
        ).fetchall()
        if any(_is_cleanup_residue_evidence_row(evidence_row) for evidence_row in evidence_rows):
            suppressed.add(str(row["item_id"]))
    return suppressed


def _loose_end_rows(db_path: Path | str) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    with connect_readonly(db_path) as connection:
        claimed_items = connection.execute(
            "SELECT id, updated_at FROM items WHERE state = 'CLAIMED_DONE' ORDER BY updated_at DESC, id ASC"
        ).fetchall()
        for item in claimed_items:
            evidence_rows = connection.execute(
                "SELECT evidence_uri, evidence_text FROM evidence WHERE item_id = ?",
                (item["id"],),
            ).fetchall()
            if not any(_is_supporting_evidence_row(row) for row in evidence_rows):
                findings.append(
                    {
                        "pattern_name": "claimed_done_missing_evidence",
                        "item_id": str(item["id"]),
                        "detected_at": str(item["updated_at"]),
                        "evidence_gap": "no_supporting_evidence",
                    }
                )

        state_gap_suppressed_item_ids = _state_predecessor_gap_suppressed_item_ids(connection)
        transition_rows = connection.execute(
            """
            SELECT id, event_id, item_id, event_type, payload_json, created_at, source
            FROM events
            WHERE item_id IS NOT NULL AND event_type = 'item.state_changed'
            ORDER BY item_id ASC, created_at ASC, id ASC
            """
        ).fetchall()
        previous_transition_by_item: dict[str, object] = {}
        for row in transition_rows:
            item_id = str(row["item_id"])
            from_state, to_state = _transition_states(row)
            previous = previous_transition_by_item.get(item_id)
            if previous is None:
                if from_state != "TRIAGE" and item_id not in state_gap_suppressed_item_ids:
                    findings.append(
                        {
                            "pattern_name": "state_predecessor_gap",
                            "item_id": item_id,
                            "detected_at": str(row["created_at"]),
                            "evidence_gap": f"missing_predecessor_for_{from_state or 'unknown'}",
                        }
                    )
            else:
                _prev_from, previous_to = _transition_states(previous)
                if from_state != previous_to and item_id not in state_gap_suppressed_item_ids:
                    findings.append(
                        {
                            "pattern_name": "state_predecessor_gap",
                            "item_id": item_id,
                            "detected_at": str(row["created_at"]),
                            "evidence_gap": f"expected_from_{previous_to or 'unknown'}_got_{from_state or 'unknown'}",
                        }
                    )
            previous_transition_by_item[item_id] = row

        item_rows = connection.execute(
            """
            SELECT id, state, source, updated_at
            FROM items
            WHERE state IN ('APPROVED', 'CLAIMED_DONE')
            ORDER BY updated_at DESC, id ASC
            """
        ).fetchall()
        for item in item_rows:
            if not _is_operator_initiated_source(item["source"]):
                continue
            approval = connection.execute(
                """
                SELECT 1
                FROM events
                WHERE item_id = ? AND event_type = 'operator_approval'
                LIMIT 1
                """,
                (item["id"],),
            ).fetchone()
            if approval is None:
                findings.append(
                    {
                        "pattern_name": "missing_operator_approval",
                        "item_id": str(item["id"]),
                        "detected_at": str(item["updated_at"]),
                        "evidence_gap": "moved_past_triage_without_operator_approval",
                    }
                )

    findings.sort(key=lambda row: (row["detected_at"], row["pattern_name"], row["item_id"]), reverse=True)
    return findings


def _print_loose_end_rows(rows: list[dict[str, str]]) -> None:
    print(f"{'pattern_name':<31} {'item_id':<36} {'detected_at':<27} {'evidence_gap':<48}")
    for row in rows:
        print(
            f"{row['pattern_name']:<31} "
            f"{row['item_id']:<36} "
            f"{row['detected_at']:<27} "
            f"{row['evidence_gap']:<48}"
        )


def _render_stale_table(rows: list[dict[str, object]]) -> str:
    lines = [f"{'item_id':<36} {'current_state':<14} {'days_idle':>9} {'last_event_type':<32}"]
    for row in rows:
        lines.append(
            f"{str(row['item_id']):<36} "
            f"{str(row['state']):<14} "
            f"{int(row['days_idle']):>9} "
            f"{str(row['last_event_type']):<32}"
        )
    return "\n".join(lines)


def _render_loose_end_table(rows: list[dict[str, str]]) -> str:
    lines = [f"{'pattern_name':<31} {'item_id':<36} {'detected_at':<27} {'evidence_gap':<48}"]
    for row in rows:
        lines.append(
            f"{row['pattern_name']:<31} "
            f"{row['item_id']:<36} "
            f"{row['detected_at']:<27} "
            f"{row['evidence_gap']:<48}"
        )
    return "\n".join(lines)


def _truncate_telegram_message(message: str, *, total_count: int, cap: int = TELEGRAM_MESSAGE_LIMIT) -> str:
    if len(message) <= cap:
        return message
    note = f"\n\n[truncated for Telegram 4096-char cap; total findings={total_count}]"
    if len(note) >= cap:
        return note[:cap]
    return message[: cap - len(note)].rstrip() + note


def _format_digest_message(
    *,
    stale_rows: list[dict[str, object]],
    loose_rows: list[dict[str, str]],
    stale_resume_context: str = "",
    generated_at: datetime | None = None,
) -> str:
    generated_at = generated_at or datetime.now(timezone.utc)
    date_label = generated_at.astimezone().strftime("%Y-%m-%d")
    total_count = len(stale_rows) + len(loose_rows)
    if total_count == 0:
        return f"ACE weekly digest — {date_label}\n\nNo stale work items or loose-end findings."

    sections = [
        f"ACE weekly digest — {date_label}",
        f"Total findings: {total_count}",
        "",
        f"Stale items ({len(stale_rows)})",
        _render_stale_table(stale_rows) if stale_rows else "none",
    ]
    if stale_resume_context:
        sections.append(stale_resume_context)
    sections.extend(
        [
            "",
            f"Loose ends ({len(loose_rows)})",
            _render_loose_end_table(loose_rows) if loose_rows else "none",
        ]
    )
    return _truncate_telegram_message("\n".join(sections), total_count=total_count)


def _send_jace_digest_message(message: str, *, chat_id: str | None = None) -> dict[str, object]:
    load_ace_telegram_env_file()
    token = os.environ.get("ACE_TELEGRAM_BOT_TOKEN")
    if not token or not token.strip():
        raise ValidationError("ACE_TELEGRAM_BOT_TOKEN is not configured")
    target_chat_id = (chat_id or os.environ.get("ACE_TELEGRAM_CHAT_ID") or "").strip()
    if not target_chat_id:
        raise ValidationError("ACE_TELEGRAM_CHAT_ID is not configured")
    delivery = action_runtime._telegram_bot_api_send_message(  # type: ignore[attr-defined]
        token=token.strip(),
        chat_id=target_chat_id,
        text=message,
    )
    result = delivery.get("result") if isinstance(delivery, dict) else None
    message_id = result.get("message_id") if isinstance(result, dict) else None
    return {"chat_id": target_chat_id, "message_id": message_id, "delivery_state": "sent"}


def _send_digest(
    db_path: Path | str,
    *,
    days: int,
    chat_id: str | None = None,
    dry_run: bool = False,
) -> dict[str, object]:
    from ace.digest_resume_context import load_stale_resume_contexts, render_stale_resume_context

    stale_rows = _stale_rows(db_path, days=days)
    loose_rows = _loose_end_rows(db_path)
    resume_contexts = load_stale_resume_contexts(db_path, stale_rows)
    stale_resume_context = render_stale_resume_context(stale_rows, resume_contexts)
    message = _format_digest_message(
        stale_rows=stale_rows,
        loose_rows=loose_rows,
        stale_resume_context=stale_resume_context,
    )
    delivery: dict[str, object]
    if dry_run:
        delivery = {"delivery_state": "dry_run", "message": message}
    else:
        delivery = _send_jace_digest_message(message, chat_id=chat_id)
    return {
        "stale_count": len(stale_rows),
        "loose_end_count": len(loose_rows),
        "message_length": len(message),
        "delivery": delivery,
    }


def _print_sweep_result(result: dict[str, object]) -> None:
    print(f"run_id={result['run_id']}")
    print(f"created_at={result['created_at']}")
    print(f"finding_count={result['finding_count']}")
    print(f"emitted_count={result['emitted_count']}")
    print(f"suppressed_count={result['suppressed_count']}")
    findings = result.get('findings', [])
    for index, finding in enumerate(findings):
        print(f"finding[{index}].item_id={finding['item_id']}")
        print(f"finding[{index}].classification={finding['classification']}")
        print(f"finding[{index}].state={finding['state']}")
        print(f"finding[{index}].title={finding['title']}")
        print(f"finding[{index}].activity_at={finding['activity_at']}")
        print(f"finding[{index}].age_seconds={finding['age_seconds']}")
        print(f"finding[{index}].stale_after_seconds={finding['stale_after_seconds']}")
        print(f"finding[{index}].evidence_count={finding['evidence_count']}")
        print(f"finding[{index}].open_obligation_count={finding['open_obligation_count']}")
        print(f"finding[{index}].open_contradiction_count={finding['open_contradiction_count']}")
        print(f"finding[{index}].fingerprint={finding['fingerprint']}")
        print(f"finding[{index}].suppressed={str(finding['suppressed']).lower()}")


def _print_briefing_result(briefing: dict[str, object]) -> None:
    print(render_briefing_text(briefing))


def _print_cycle_result(result: dict[str, object]) -> None:
    governed_run = result.get("governed_run")
    if isinstance(governed_run, dict):
        print(f"run_id={governed_run['run_id']}")
        print(f"run_status={governed_run['status']}")
    print(f"briefing_path={result['briefing_path']}")
    print(f"actionable_finding_count={result['actionable_finding_count']}")
    print(f"notification_count={result['notification_count']}")
    if "notifications_suppressed" in result:
        print(f"notifications_suppressed={str(result['notifications_suppressed']).lower()}")
    briefing = result.get("briefing")
    if isinstance(briefing, dict) and isinstance(briefing.get("health_summary"), dict):
        for line in render_health_summary_lines(briefing["health_summary"]):
            print(line)
    print("sweep:")
    _print_sweep_result(result["sweep"])
    print("briefing:")
    _print_briefing_result(result["briefing"])


def _print_governed_run_status(result: dict[str, object]) -> None:
    current_run = result.get("current_run")
    last_terminal_run = result.get("last_terminal_run")
    print(f"current_run_present={str(current_run is not None).lower()}")
    if isinstance(current_run, dict):
        for key, value in current_run.items():
            print(f"current_run.{key}={value}")
    print(f"last_terminal_run_present={str(last_terminal_run is not None).lower()}")
    if isinstance(last_terminal_run, dict):
        for key, value in last_terminal_run.items():
            print(f"last_terminal_run.{key}={value}")


def _print_governed_run(result: dict[str, object]) -> None:
    for key, value in result.items():
        print(f"{key}={value}")


def _print_supervisor_run_result(result: dict[str, object]) -> None:
    runtime = result.get("runtime")
    if isinstance(runtime, dict):
        print(f"runtime_instance_id={runtime['runtime_instance_id']}")
        print(f"runtime_status={runtime['status']}")
    print(f"heartbeat_count={result['heartbeat_count']}")
    print(f"duplicate_start={str(result['duplicate_start']).lower()}")
    print(f"auto_stopped={str(result['auto_stopped']).lower()}")


def _print_supervisor_runtime_status(result: dict[str, object]) -> None:
    print(f"inspection_family={result['inspection_family']}")
    inspection_scope = result.get("inspection_scope")
    bounded_runtime_claims = result.get("bounded_runtime_claims")
    anti_inflation_non_claims = result.get("anti_inflation_non_claims")
    minimal_slice_definition = result.get("minimal_slice_definition")
    evidence_artifact_bundle = result.get("evidence_artifact_bundle")
    non_reduction_proof = result.get("non_reduction_proof")
    current_runtime = result.get("current_runtime")
    last_terminal_runtime = result.get("last_terminal_runtime")
    runtime_transition_history = result.get("runtime_transition_history")
    if inspection_scope is not None:
        print(f"inspection_scope={inspection_scope}")
    if isinstance(bounded_runtime_claims, list):
        print(f"bounded_runtime_claims_count={len(bounded_runtime_claims)}")
        for index, value in enumerate(bounded_runtime_claims):
            print(f"bounded_runtime_claims.{index}={value}")
    if isinstance(anti_inflation_non_claims, list):
        print(f"anti_inflation_non_claims_count={len(anti_inflation_non_claims)}")
        for index, value in enumerate(anti_inflation_non_claims):
            print(f"anti_inflation_non_claims.{index}={value}")
    if isinstance(minimal_slice_definition, list):
        print(f"minimal_slice_definition_count={len(minimal_slice_definition)}")
        for index, value in enumerate(minimal_slice_definition):
            print(f"minimal_slice_definition.{index}={value}")
    if isinstance(evidence_artifact_bundle, list):
        print(f"evidence_artifact_bundle_count={len(evidence_artifact_bundle)}")
        for index, value in enumerate(evidence_artifact_bundle):
            print(f"evidence_artifact_bundle.{index}={value}")
    if isinstance(non_reduction_proof, list):
        print(f"non_reduction_proof_count={len(non_reduction_proof)}")
        for index, value in enumerate(non_reduction_proof):
            print(f"non_reduction_proof.{index}={value}")
    print(f"current_runtime_present={str(current_runtime is not None).lower()}")
    if isinstance(current_runtime, dict):
        for key, value in current_runtime.items():
            print(f"current_runtime.{key}={value}")
    print(f"last_terminal_runtime_present={str(last_terminal_runtime is not None).lower()}")
    if isinstance(last_terminal_runtime, dict):
        for key, value in last_terminal_runtime.items():
            print(f"last_terminal_runtime.{key}={value}")
    if isinstance(runtime_transition_history, list):
        print(f"runtime_transition_history_count={len(runtime_transition_history)}")
        for index, entry in enumerate(runtime_transition_history):
            if isinstance(entry, dict):
                for key, value in entry.items():
                    print(f"runtime_transition_history.{index}.{key}={value}")


GATE4_OPERATOR_ARTIFACTS: tuple[tuple[str, str], ...] = (
    ("inspection_surface", "reports/ace-gate4-operator-inspection-surface-2026-05-06.md"),
    ("review_checklist", "reports/ace-gate4-operator-review-checklist-2026-05-06.md"),
    ("one_page_runbook", "reports/ace-gate4-one-page-operator-runbook-2026-05-06.md"),
    ("phase1_note", "reports/ace-gate4-phase1-operator-inspection-note-2026-05-06.md"),
    ("recovery_note", "reports/ace-gate4-recovery-operator-inspection-note-2026-05-06.md"),
    ("composition_note", "reports/ace-gate4-composition-seam-contradiction-note-2026-05-06.md"),
    ("contradiction_matrix", "reports/ace-gate4-contradiction-matrix-2026-05-06.md"),
    ("recovery_taxonomy", "reports/ace-gate4-recovery-failure-taxonomy-2026-05-06.md"),
)



def _cost_policy_from_args(args: argparse.Namespace) -> CostGuardrailPolicy | None:
    if (
        args.cost_limit_cents is None
        and args.token_limit is None
        and args.session_count_limit is None
    ):
        return None
    return CostGuardrailPolicy(
        cost_limit_cents=args.cost_limit_cents or 0,
        token_limit=args.token_limit or 0,
        session_count_limit=args.session_count_limit or 0,
    )


def _print_cost_status(status) -> None:
    print(f"cost.status.blocked={str(status.blocked).lower()}")
    if status.reason is not None:
        print(f"cost.status.reason={status.reason}")
    print(f"cost.status.used_cost_cents={status.used_cost_cents}")
    print(f"cost.status.cost_limit_cents={status.cost_limit_cents}")
    print(f"cost.status.used_tokens={status.used_tokens}")
    print(f"cost.status.token_limit={status.token_limit}")
    print(f"cost.status.used_session_count={status.used_session_count}")
    print(f"cost.status.session_count_limit={status.session_count_limit}")


def _print_gate4_inspection_surface() -> int:
    workspace_root = Path(__file__).resolve().parent.parent
    missing: list[str] = []
    print("gate4_scope=bounded_operator_inspection_only")
    print("gate4_claim=inspection_centralization_not_v1_promotion")
    for label, relative_path in GATE4_OPERATOR_ARTIFACTS:
        artifact_path = workspace_root / relative_path
        exists = artifact_path.exists()
        print(f"artifact.{label}.path={relative_path}")
        print(f"artifact.{label}.present={str(exists).lower()}")
        if exists:
            print(f"artifact.{label}.bytes={artifact_path.stat().st_size}")
        else:
            missing.append(relative_path)
    print(f"artifact_missing_count={len(missing)}")
    if missing:
        for index, relative_path in enumerate(missing):
            print(f"artifact_missing[{index}]={relative_path}")
        return 1
    print("operator_status_family[0]=explicit_bounded_failure")
    print("operator_status_family[1]=replay_safe_bounded_no_op")
    print("operator_status_family[2]=healed_interrupted_split_success")
    print("operator_status_family[3]=acceptable_bounded_filtering")
    print("operator_status_family[4]=under_classified_ambiguity_debt")
    print("operator_status_family[5]=prevented_contradiction")
    print("operator_status_family[6]=partial_under_centralized_family")
    print("remaining_partial_count=0")
    print("composition_truth[0]=decision_top_level_rejection_and_replay_are_bounded")
    print("composition_truth[1]=sweep_duplicate_suppression_and_changed_truth_re_emission_are_bounded")
    print("composition_truth[2]=briefing_section_de_duplication_and_live_state_rendering_are_bounded")
    print("composition_truth[3]=phase1_pending_rows_now_use_governed_normalization")
    print("phase1_truth[0]=non_pending_rows_are_acceptable_bounded_filtering")
    print("phase1_truth[1]=non_object_rows_fail_loudly_as_schema_error")
    print("phase1_truth[2]=invalid_or_missing_status_rows_fail_loudly_as_schema_error")
    print("phase1_truth[3]=pending_rows_failing_required_field_normalization_fail_loudly_as_schema_error")
    print("phase1_truth[4]=later_missing_source_row_is_explicit_bounded_failure")
    print("recovery_truth[0]=stale_or_deleted_target_is_explicit_bounded_failure")
    print("recovery_truth[1]=malformed_session_metadata_and_ownership_payload_are_explicit_bounded_failure")
    print("recovery_truth[2]=candidate_session_or_cross_seam_identity_mismatch_is_explicit_bounded_failure")
    print("recovery_truth[3]=duplicate_dismissal_release_and_finalize_are_replay_safe_bounded_no_op")
    print("recovery_truth[4]=interrupted_split_success_replay_heals_without_duplicate_evidence")
    return 0


def _print_supervisor_shutdown_result(result: dict[str, object]) -> None:
    print(f"runtime_instance_id={result['runtime_instance_id']}")
    print(f"runtime_status={result['status']}")
    print(f"shutdown_status={result['shutdown_status']}")
    if result.get("shutdown_requested_at") is not None:
        print(f"shutdown_requested_at={result['shutdown_requested_at']}")


def _print_evidence_added(*, item_id: str, evidence_id: str) -> None:
    print(f"item_id={item_id} evidence_id={evidence_id}")


def _print_jace_status_delivery(result: dict[str, object]) -> None:
    print(f"jace_status.item_id={result['item_id']}")
    print(f"jace_status.alert_id={result['alert_id']}")
    print(f"jace_status.evidence_id={result['evidence_id']}")
    print(f"jace_status.message_id={result['message_id']}")
    print(f"jace_status.chat_id={result['chat_id']}")
    print(f"jace_status.delivery_state={result['delivery_state']}")
    print(f"jace_status.evidence_written={str(result['evidence_written']).lower()}")
    if result.get("bot_username") is not None:
        print(f"jace_status.bot_username={result['bot_username']}")


def _print_jace_audit(audit_result: dict[str, object]) -> None:
    print(f"jace.audit.actual_send_count={audit_result['actual_send_count']}")
    print(f"jace.audit.support_record_count={audit_result['support_record_count']}")
    print(f"jace.audit.normalized_record_count={audit_result['normalized_record_count']}")
    print(f"jace.audit.source_counts={audit_result['source_counts']}")
    print(f"jace.audit.classification_counts={audit_result['classification_counts']}")
    print(f"jace.audit.missing_message_ids={audit_result['missing_message_ids']}")


def _attestation_client_from_env() -> B2AttestationClient:
    return B2AttestationClient(B2Config.from_env())


def _verify_audit_integrity_for_cli(db_path: Path | str):
    return verify_audit_integrity(db_path)


def _verify_external_attestation_for_cli(db_path: Path | str):
    return verify_external_attestation(db_path, client_factory=_attestation_client_from_env)


def _exit_code_for_external_attestation(ok: bool, detail: str | None) -> int:
    if ok:
        return EXIT_OK
    if detail and EXTERNAL_ATTESTATION_NOT_CONFIGURED in detail:
        return EXIT_NOT_CONFIGURED
    return EXIT_FAILED


def _print_attestation_status_result(ok: bool, detail: str | None, *, db_path: Path | str) -> None:
    print(f"attestation.status={'ok' if ok else 'failed'}")
    if detail is not None:
        print(f"attestation.status_detail={detail}")
    print(f"attestation.db_path={db_path}")


def _print_attestation_sync_result(result) -> None:
    print("attestation.sync=ok")
    print(f"attestation.sync.expected_count={result.expected_count}")
    print(f"attestation.sync.uploaded_count={result.uploaded_count}")
    print(f"attestation.sync.existing_count={result.existing_count}")
    print(f"attestation.sync.prefix={result.prefix}")
    print(f"attestation.sync.cutover_event_id={result.cutover_event_id}")


def _print_attestation_sync_failure(exc: Exception) -> None:
    print("attestation.sync=failed")
    print(f"attestation.sync_detail={exc}")


def _print_attestation_sync_progress(message: str) -> None:
    print(f"attestation.sync.progress={message}", flush=True)


def _print_autonomy_eligibility_marked(*, item_id: str, evidence_id: str) -> None:
    print(f"item_id={item_id} autonomy_eligibility_evidence_id={evidence_id}")


def _print_direct_work_intake(*, item, evidence_id: str) -> None:
    _print_item(item)
    print(f"autonomy_eligibility_evidence_id={evidence_id}")


def _print_obligation_added(*, item_id: str, obligation_id: str) -> None:
    print(f"item_id={item_id} obligation_id={obligation_id}")


def _print_contradiction_added(*, item_id: str, contradiction_id: str) -> None:
    print(f"item_id={item_id} contradiction_id={contradiction_id}")


def _print_contradiction_resolved(*, contradiction_id: str, item_id: str, status: str) -> None:
    print(f"contradiction_id={contradiction_id} item_id={item_id} status={status}")


def _print_correction_recorded(
    *, item_id: str, corrected_item_id: str, contradiction_id: str
) -> None:
    print(
        f"item_id={item_id} corrected_item_id={corrected_item_id} contradiction_id={contradiction_id}"
    )


def _print_obligation_resolved(*, obligation_id: str, item_id: str, status: str) -> None:
    print(f"obligation_id={obligation_id} item_id={item_id} status={status}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    db_path = Path(args.db)

    command = args.command or "init"
    if command in {"init", "bootstrap"}:
        bootstrap_db(db_path)
        print(f"Initialized ACE state at {db_path}")
        return 0

    if command == "stale":
        try:
            _print_stale_rows(_stale_rows(db_path, days=args.days))
            return 0
        except ValidationError as exc:
            print(f"error={exc}")
            return 1

    if command == "loose-ends":
        _print_loose_end_rows(_loose_end_rows(db_path))
        return 0

    if command == "contradictions":
        from ace.doc_contradictions import default_repo_root, run_contradictions_command

        repo_root = Path(args.repo_root) if args.repo_root else default_repo_root()
        readme_path = Path(args.readme) if args.readme else None
        status_path = Path(args.status) if args.status else None
        return run_contradictions_command(
            repo_root=repo_root,
            readme_path=readme_path,
            status_path=status_path,
            parser=parser,
            skip_ci=args.skip_ci,
        )

    if command == "hooks":
        from ace.hooks_install import run_hooks_command

        hooks_command = getattr(args, "hooks_command", None)
        if not hooks_command:
            print("error=hooks command required (install, status)", file=sys.stderr)
            return 1
        return run_hooks_command(hooks_command)

    if command == "propose":
        from ace.propose_commitments import run_propose_command

        session_file = Path(args.session_file) if getattr(args, "session_file", None) else None
        return run_propose_command(
            db_path=db_path,
            propose_action=getattr(args, "propose_action", None),
            item_id=getattr(args, "item_id", None),
            session_file=session_file,
            actor=getattr(args, "actor", None),
        )

    if command == "filter-health":
        from ace.filter_health import run_filter_health_command

        decisions_log = Path(args.decisions_log) if getattr(args, "decisions_log", None) else None
        return run_filter_health_command(
            db_path=db_path,
            month=getattr(args, "month", None),
            decisions_log=decisions_log,
        )

    if command == "digest":
        try:
            result = _send_digest(
                db_path,
                days=args.days,
                chat_id=_normalize_optional_text(args.chat_id, field_name="chat_id"),
                dry_run=args.dry_run,
            )
        except ValidationError as exc:
            print(f"error={exc}")
            return 1
        print(f"digest.stale_count={result['stale_count']}")
        print(f"digest.loose_end_count={result['loose_end_count']}")
        print(f"digest.message_length={result['message_length']}")
        delivery = result["delivery"]
        if isinstance(delivery, dict):
            print(f"digest.delivery_state={delivery.get('delivery_state')}")
            if args.dry_run:
                print("digest.message:")
                print(delivery.get("message", ""))
            if delivery.get("message_id") is not None:
                print(f"digest.message_id={delivery.get('message_id')}")
        return 0

    repo = ItemRepository(db_path)

    try:
        if command == "intake":
            item = repo.create_item(
                item_type=_normalize_required_text(args.item_type, field_name="item_type"),
                title=_normalize_required_text(args.title, field_name="title"),
                description=_normalize_optional_text(args.description, field_name="description"),
                priority_hint=_normalize_optional_text(args.priority_hint, field_name="priority_hint"),
                confidence_tier=_normalize_optional_text(args.confidence_tier, field_name="confidence_tier"),
                verdict=_normalize_optional_text(args.verdict, field_name="verdict"),
                source=_normalize_optional_text(args.source, field_name="source"),
                source_session=_normalize_optional_text(args.session, field_name="source_session"),
                deadline_at=args.deadline,
                owner=_normalize_optional_text(args.owner, field_name="owner"),
                actor=args.actor,
            )
            _print_item(item)
            return 0

        if command == "list":
            normalized_state = normalize_state(args.state) if args.state is not None else None
            items = repo.list_items(state=normalized_state)
            _print_items(items)
            return 0

        if command in {"show", "inspect"}:
            if args.event_limit is not None and args.event_limit <= 0:
                print(f"error=invalid_event_limit event_limit={args.event_limit}")
                return 1
            if command == "inspect" and args.drift_window <= 0:
                print(f"error=invalid_drift_window drift_window={args.drift_window}")
                return 1
            normalized_event_type = args.event_type
            if normalized_event_type is not None:
                normalized_event_type = normalized_event_type.strip()
                if not normalized_event_type:
                    print(f"error=invalid_event_type event_type={args.event_type}")
                    return 1
            item = repo.get_item(args.item_id)
            if item is None:
                print(f"error=unknown_item_id item_id={args.item_id}")
                return 1
            _print_item(item)
            all_events = repo.list_item_events(args.item_id)
            if command == "inspect":
                _print_drift_report(compute_item_drift(args.item_id, all_events, window=args.drift_window))
            events_to_print = all_events
            if normalized_event_type is not None:
                events_to_print = [event for event in events_to_print if event.event_type == normalized_event_type]
            if args.event_limit is not None:
                events_to_print = events_to_print[-args.event_limit:]
            _print_item_events(events_to_print)
            return 0

        if command == "record-verdict":
            item = repo.record_verdict(
                args.item_id,
                _normalize_required_text(args.verdict, field_name="verdict"),
                actor=_normalize_optional_text(args.actor, field_name="actor"),
                source=_normalize_optional_text(args.source, field_name="source"),
                source_session=_normalize_optional_text(args.session, field_name="source_session"),
                reason=_normalize_optional_text(args.reason, field_name="reason"),
            )
            _print_item(item)
            return 0

        if command == "sweep":
            thresholds = SweepThresholds(
                triage_after_seconds=args.triage_after_hours * 3600,
                approved_after_seconds=args.approved_after_hours * 3600,
                blocked_after_seconds=args.blocked_after_hours * 3600,
                claimed_done_after_seconds=args.claimed_done_after_hours * 3600,
                active_after_seconds=args.active_after_hours * 3600,
            )
            result = run_sweep(db_path, thresholds=thresholds, actor=args.actor)
            _print_sweep_result(result)
            return 0

        if command == "briefing":
            thresholds = SweepThresholds(
                triage_after_seconds=args.triage_after_hours * 3600,
                approved_after_seconds=args.approved_after_hours * 3600,
                blocked_after_seconds=args.blocked_after_hours * 3600,
                claimed_done_after_seconds=args.claimed_done_after_hours * 3600,
                active_after_seconds=args.active_after_hours * 3600,
            )
            briefing = generate_briefing(db_path, thresholds=thresholds)
            _print_briefing_result(briefing)
            return 0

        if command == "cycle":
            thresholds = SweepThresholds(
                triage_after_seconds=args.triage_after_hours * 3600,
                approved_after_seconds=args.approved_after_hours * 3600,
                blocked_after_seconds=args.blocked_after_hours * 3600,
                claimed_done_after_seconds=args.claimed_done_after_hours * 3600,
                active_after_seconds=args.active_after_hours * 3600,
            )
            result = run_cycle(
                db_path,
                thresholds=thresholds,
                actor=args.actor,
                notification_channel=_normalize_optional_text(args.notification_channel, field_name="notification_channel"),
                notification_target=_normalize_optional_text(args.notification_target, field_name="notification_target"),
                notification_thread_id=_normalize_optional_text(args.notification_thread_id, field_name="notification_thread_id"),
                briefing_path=args.briefing_path,
                disable_notifications=args.disable_notifications,
            )
            _print_cycle_result(result)
            return 0

        if command == "cycle-status":
            result = get_governed_cycle_run_status(db_path)
            _print_governed_run_status(result)
            return 0

        if command == "correct-governed-run-trigger":
            result = correct_governed_run_trigger_kind(
                db_path,
                args.run_id,
                trigger_kind=_normalize_required_text(args.trigger_kind, field_name="trigger_kind"),
                actor=_normalize_optional_text(args.actor, field_name="actor"),
                source=_normalize_optional_text(args.source, field_name="source"),
                source_session=_normalize_optional_text(args.session, field_name="source_session"),
                reason=_normalize_required_text(args.reason, field_name="reason"),
            )
            _print_governed_run(result)
            return 0

        if command == "supervisor-run":
            result = run_supervisor_runtime(
                db_path,
                runtime_family=_normalize_required_text(args.runtime_family, field_name="runtime_family"),
                stale_after_seconds=args.stale_after_seconds,
                heartbeat_count=args.heartbeat_count,
                heartbeat_interval_seconds=args.heartbeat_interval_seconds,
                host_identity=_normalize_optional_text(args.host_identity, field_name="host_identity"),
                metadata={"process_pid": os.getpid()},
                run_until_shutdown=args.run_until_shutdown,
            )
            _print_supervisor_run_result(result)
            return 0

        if command == "supervisor-status":
            result = get_supervisor_runtime_status(db_path)
            _print_supervisor_runtime_status(result)
            return 0

        if command == "supervisor-acceptance-monitor":
            return run_supervisor_acceptance_monitor(
                db_path,
                service_target=_normalize_required_text(args.service_target, field_name="service_target"),
                log_path=_normalize_required_text(args.log_path, field_name="log_path"),
                err_path=_normalize_required_text(args.err_path, field_name="err_path"),
                pid_path=_normalize_required_text(args.pid_path, field_name="pid_path"),
                iterations=args.iterations,
                sleep_seconds=args.sleep_seconds,
                append=not args.truncate_on_start,
            )

        if command == "supervisor-shutdown":
            runtime_instance_id = _normalize_optional_text(
                args.runtime_instance_id,
                field_name="runtime_instance_id",
            )
            if runtime_instance_id is None:
                status = get_supervisor_runtime_status(db_path)
                current_runtime = status.get("current_runtime")
                if not isinstance(current_runtime, dict):
                    print("error=no_active_supervisor_runtime")
                    return 1
                runtime_instance_id = current_runtime["runtime_instance_id"]
            result = request_supervisor_shutdown(db_path, runtime_instance_id)
            _print_supervisor_shutdown_result(result)
            return 0

        if command == "gate4-inspection":
            return _print_gate4_inspection_surface()

        if command == "audit":
            if args.audit_command == "verify":
                results = _verify_audit_integrity_for_cli(db_path)
                all_ok = True
                first_reason: str | None = None
                for check_name, (ok, reason) in results.items():
                    print(f"audit.verify.{check_name}={'ok' if ok else 'failed'}")
                    if reason is not None:
                        print(f"audit.verify.{check_name}_detail={reason}")
                    if not ok:
                        all_ok = False
                        if first_reason is None:
                            first_reason = reason
                local_ok = all_ok
                external_ok = False
                external_detail: str | None = "external_attestation_skipped: local audit checks failed"
                if local_ok:
                    external_ok, external_detail = _verify_external_attestation_for_cli(db_path)
                print(f"audit.verify.external_attestation={'ok' if external_ok else 'failed'}")
                if external_detail is not None:
                    print(f"audit.verify.external_attestation_detail={external_detail}")
                if not external_ok:
                    all_ok = False
                    if first_reason is None:
                        first_reason = external_detail
                print(f"audit.verify.db_path={db_path}")
                if first_reason is not None:
                    print(f"audit.verify.reason={first_reason}")
                return EXIT_OK if all_ok else _exit_code_for_external_attestation(False, first_reason)
            if args.audit_command == "jace":
                audit_result = audit_jace_delivery_history(db_path)
                if args.json:
                    import json
                    print(json.dumps(audit_result, sort_keys=True, indent=2))
                else:
                    _print_jace_audit(audit_result)
                return 0
            parser.error("audit requires a subcommand: verify or jace")

        if command == "attestation":
            if args.attestation_command == "status":
                ok, detail = verify_external_attestation(db_path, client_factory=_attestation_client_from_env)
                _print_attestation_status_result(ok, detail, db_path=db_path)
                return _exit_code_for_external_attestation(ok, detail)
            if args.attestation_command == "sync":
                try:
                    result = sync_attestation_records(
                        _attestation_client_from_env(),
                        db_path,
                        progress_callback=_print_attestation_sync_progress,
                        progress_every=args.progress_every,
                    )
                except B2ConfigurationError as exc:
                    _print_attestation_sync_failure(exc)
                    return EXIT_NOT_CONFIGURED
                except Exception as exc:
                    _print_attestation_sync_failure(exc)
                    return EXIT_FAILED
                _print_attestation_sync_result(result)
                return EXIT_OK
            parser.error("attestation requires a subcommand: status or sync")

        if command == "cost":
            if args.cost_command == "status":
                policy = _cost_policy_from_args(args)
                status = get_cost_guardrail_status(db_path, policy=policy)
                _print_cost_status(status)
                return 1 if status.blocked else 0
            if args.cost_command == "record":
                record = record_cost_usage(
                    db_path,
                    cost_cents=args.cost_cents,
                    tokens=args.tokens,
                    session_count=args.session_count,
                    source=args.source,
                    source_session=args.session,
                )
                print(f"cost.record.recorded_at={record['recorded_at']}")
                print(f"cost.record.cost_cents={record['cost_cents']}")
                print(f"cost.record.tokens={record['tokens']}")
                print(f"cost.record.session_count={record['session_count']}")
                print(f"cost.record.source={record['source']}")
                if record["source_session"] is not None:
                    print(f"cost.record.source_session={record['source_session']}")
                return 0
            parser.error("cost requires a subcommand: status or record")

        if command == "add-evidence":
            evidence_id = repo.add_evidence(
                args.item_id,
                evidence_text=_normalize_required_text(args.evidence_text, field_name="evidence_text"),
                evidence_uri=_normalize_optional_text(args.evidence_uri, field_name="evidence_uri"),
                created_by=_normalize_optional_text(args.created_by, field_name="created_by"),
                actor=args.actor,
            )
            _print_evidence_added(item_id=args.item_id, evidence_id=evidence_id)
            return 0

        if command == "jace-status-send":
            result = send_jace_status_message(
                db_path,
                args.item_id,
                message=_normalize_required_text(args.message, field_name="message"),
                chat_id=_normalize_optional_text(args.chat_id, field_name="chat_id"),
                actor=_normalize_optional_text(args.actor, field_name="actor"),
            )
            _print_jace_status_delivery(result)
            return 0

        if command == "mark-autonomy-eligible":
            evidence_id = mark_item_autonomy_eligible(
                db_path,
                args.item_id,
                reason=_normalize_required_text(args.reason, field_name="reason"),
                actor=_normalize_optional_text(args.actor, field_name="actor"),
            )
            _print_autonomy_eligibility_marked(item_id=args.item_id, evidence_id=evidence_id)
            return 0

        if command == "intake-direct-work":
            item, evidence_id = intake_autonomy_eligible_direct_work(
                db_path,
                title=_normalize_required_text(args.title, field_name="title"),
                reason=_normalize_required_text(args.reason, field_name="reason"),
                source_session=_normalize_required_text(args.session, field_name="source_session"),
                description=_normalize_optional_text(args.description, field_name="description"),
                priority_hint=_normalize_optional_text(args.priority_hint, field_name="priority_hint"),
                owner=_normalize_optional_text(args.owner, field_name="owner"),
                actor=_normalize_optional_text(args.actor, field_name="actor"),
            )
            _print_direct_work_intake(item=item, evidence_id=evidence_id)
            return 0

        if command == "add-obligation":
            obligation_id = repo.add_obligation(
                args.item_id,
                obligation_type=_normalize_required_text(args.obligation_type, field_name="obligation_type"),
                status=_normalize_required_text(args.status, field_name="status").lower(),
                target_surface=_normalize_optional_text(args.target_surface, field_name="target_surface"),
                notes=_normalize_optional_text(args.notes, field_name="notes"),
                actor=args.actor,
            )
            _print_obligation_added(item_id=args.item_id, obligation_id=obligation_id)
            return 0

        if command == "add-contradiction":
            contradiction_id = repo.add_contradiction(
                args.item_id,
                source_item_id=args.source_item_id,
                status=args.status,
                reason=_normalize_optional_text(args.reason, field_name="reason"),
                actor=args.actor,
            )
            _print_contradiction_added(item_id=args.item_id, contradiction_id=contradiction_id)
            return 0


        if command == "correction":
            if args.correction_command == "submit":
                result = repo.submit_closeout_metadata_correction(
                    args.item_id,
                    closed_at=args.closed_at,
                    closed_by=args.closed_by,
                    closed_reason=args.closed_reason,
                    reason=args.reason,
                    actor=args.actor,
                )
                print(
                    f"item_id={result['item_id']} event_id={result['event_id']} "
                    f"closed_at={result['closed_at']} closed_by={result['closed_by']}"
                )
                return 0
            raise ValidationError("correction subcommand is required")

        if command == "resolve-contradiction":
            result = repo.resolve_contradiction(
                args.contradiction_id,
                reason=_normalize_required_text(args.reason, field_name="reason") if args.reason is not None else None,
                actor=args.actor,
            )
            _print_contradiction_resolved(
                contradiction_id=result["contradiction_id"],
                item_id=result["item_id"],
                status=result["status"],
            )
            return 0

        if command == "record-correction":
            result = repo.record_correction(
                args.item_id,
                corrected_item_id=args.corrected_item_id,
                reason=_normalize_required_text(args.reason, field_name="reason") if args.reason is not None else None,
                actor=args.actor,
            )
            _print_correction_recorded(
                item_id=result["item_id"],
                corrected_item_id=result["corrected_item_id"],
                contradiction_id=result["contradiction_id"],
            )
            return 0

        if command == "resolve-obligation":
            result = repo.resolve_obligation(
                args.obligation_id,
                reason=_normalize_required_text(args.reason, field_name="reason") if args.reason is not None else None,
                actor=args.actor,
            )
            _print_obligation_resolved(
                obligation_id=result["obligation_id"],
                item_id=result["item_id"],
                status=result["status"],
            )
            return 0

        if command in {"approve", "block", "done", "resolve", "drop"}:
            if command == "resolve" and getattr(args, "verdict", None) is not None:
                repo.record_verdict(
                    args.item_id,
                    _normalize_required_text(args.verdict, field_name="verdict"),
                    actor=_normalize_optional_text(args.actor, field_name="actor"),
                    source=_normalize_optional_text(args.source, field_name="source"),
                    source_session=_normalize_optional_text(args.session, field_name="source_session"),
                    reason=_normalize_optional_text(args.reason, field_name="reason"),
                )
            item = repo.apply_action(
                args.item_id,
                command,
                actor=args.actor,
                source=_normalize_optional_text(args.source, field_name="source"),
                source_session=_normalize_optional_text(args.session, field_name="source_session"),
                reason=_normalize_optional_text(args.reason, field_name="reason"),
            )
            _print_item(item)
            return 0
    except AceError as exc:
        print(f"error={exc}")
        return 1
    except KeyError as exc:
        message = exc.args[0] if exc.args else str(exc)
        print(f"error={message}")
        return 1
    except ValidationError as exc:
        print(f"error={exc}")
        return 1

    parser.error(f"unknown command: {command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
