from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Iterable

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ace.repository import ItemRepository, ValidationError
from ace.autonomy_lane import intake_autonomy_eligible_direct_work, mark_item_autonomy_eligible
from ace.governed_run_runtime import get_governed_cycle_run_status
from ace.governed_run_runtime import correct_governed_run_trigger_kind
from ace.supervisor_runtime import (
    RUNTIME_FAMILY_SINGLE_TENANT,
    get_supervisor_runtime_status,
    request_supervisor_shutdown,
    run_supervisor_runtime,
)
from ace.supervisor_acceptance_monitor import run_supervisor_acceptance_monitor
from ace.storage import DB_PATH, bootstrap_db
from ace.sweep import SweepThresholds, run_sweep
from ace.briefing import generate_briefing, render_briefing_text
from ace.cycle import BRIEFING_PATH, run_cycle
from ace.drift import compute_item_drift
from ace.workflow import AceError, normalize_state


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

    evidence = subparsers.add_parser("add-evidence", help="Add evidence for an item")
    evidence.add_argument("item_id")
    evidence.add_argument("evidence_text")
    evidence.add_argument("--evidence-uri")
    evidence.add_argument("--created-by")
    evidence.add_argument("--actor")

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
