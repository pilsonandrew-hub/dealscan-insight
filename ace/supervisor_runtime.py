"""Bounded resident supervisor runtime slice for Super A.C.E.

This module is intentionally narrow.

Non-claims:
- not a daemon/service/platform proof
- not a worker-pool runtime
- not multi-tenant runtime infrastructure
- not generalized scheduler/control-plane ownership
- not continuity-source write authority
- not V1/V2/V3 promotion by itself

What it does prove when exercised honestly:
- a distinct resident-runtime ledger independent of governed one-shot runs
- ACE-owned startup/live/stale/stopped/failed lifecycle state
- explicit startup/shutdown ownership metadata for the resident supervisor slice
- active inspection truth for current resident-runtime state
- append-only resident-runtime transition history distinct from governed-run history
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .repository import ValidationError
from .storage import DB_PATH, append_event, bootstrap_db, connect, new_id, utc_now


RUNTIME_FAMILY_SINGLE_TENANT = "single_tenant_local_supervisor"

STATUS_STARTING = "starting"
STATUS_LIVE = "live"
STATUS_STALE = "stale"
STATUS_STOPPED = "stopped"
STATUS_FAILED = "failed"

STARTUP_STATUS_STARTING = "starting"
STARTUP_STATUS_COMPLETED = "completed"
STARTUP_STATUS_FAILED = "failed"

SHUTDOWN_STATUS_NOT_REQUESTED = "not_requested"
SHUTDOWN_STATUS_REQUESTED = "requested"
SHUTDOWN_STATUS_COMPLETED = "completed"
SHUTDOWN_STATUS_FAILED = "failed"

RECOVERY_STATUS_NOT_REQUESTED = "not_requested"
RECOVERY_STATUS_REQUESTED = "requested"
RECOVERY_STATUS_COMPLETED = "completed"
RECOVERY_STATUS_FAILED = "failed"

FAILURE_PHASE_STARTUP = "startup"
FAILURE_PHASE_RUNTIME = "runtime"
FAILURE_PHASE_SHUTDOWN = "shutdown"

_ACTIVE_STATUSES = {STATUS_STARTING, STATUS_LIVE, STATUS_STALE}
_TERMINAL_STATUSES = {STATUS_STOPPED, STATUS_FAILED}
_RUNTIME_EVENT_SOURCE = "ace.supervisor_runtime"

_INSPECTION_SCOPE = "bounded_resident_supervisor_seam"
_BOUNDED_RUNTIME_CLAIMS = (
    "distinct_resident_runtime_ledger",
    "startup_shutdown_failure_recovery_truth",
    "append_only_transition_and_recovery_history",
    "operator_visible_inspection_distinct_from_governed_runs",
)
_ANTI_INFLATION_NON_CLAIMS = (
    "not_v1",
    "not_daemon_or_service_proof",
    "not_platform_or_runtime_fabric",
    "not_worker_pool_or_control_plane",
    "not_distributed_or_high_availability",
    "not_continuity_source_write_authority",
)

_MINIMAL_SLICE_DEFINITION = (
    "launchagent_scheduled_real_ace_cycle",
    "governed_run_lifecycle_for_local_cycle",
    "resident_supervisor_identity_startup_shutdown_inspection_failure_recovery",
    "inspection_surface_with_bounded_claims_and_explicit_non_claims",
)

_EVIDENCE_ARTIFACT_BUNDLE = (
    "reports/ace-e1-resident-supervisor-identity-verdict-2026-05-07.md",
    "reports/ace-e2-startup-shutdown-ownership-gate-2026-05-07.md",
    "reports/ace-e3-active-runtime-inspection-surface-verdict-2026-05-07.md",
    "reports/ace-e4-runtime-failure-recovery-contract-verdict-2026-05-07.md",
    "reports/ace-e5-anti-inflation-boundary-proof-verdict-2026-05-07.md",
)

_NON_REDUCTION_PROOF = (
    "runtime_identity_not_equal_to_launchd_wrapper_or_governed_run_timestamp",
    "startup_shutdown_truth_owned_on_runtime_instances_not_launchd",
    "failure_recovery_truth_owned_on_supervisor_runtime_not_governed_run_failed_interrupted",
    "inspection_surface_exposes_transition_recovery_history_and_non_claims_beyond_bounded_ace_cycle",
)


def start_supervisor_runtime(
    db_path: Path | str = DB_PATH,
    *,
    runtime_family: str = RUNTIME_FAMILY_SINGLE_TENANT,
    stale_after_seconds: int = 60,
    host_identity: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    bootstrap_db(db_path)
    normalized_runtime_family = _normalize_required_text(runtime_family, field_name="runtime_family")
    normalized_stale_after_seconds = _normalize_stale_after_seconds(stale_after_seconds)
    normalized_host_identity = _normalize_optional_text(host_identity)
    normalized_metadata = _normalize_metadata(metadata)

    with connect(db_path) as connection:
        existing = connection.execute(
            """
            SELECT *
            FROM runtime_instances
            WHERE runtime_family = ? AND status IN (?, ?, ?)
            ORDER BY created_at DESC, runtime_instance_id DESC
            LIMIT 1
            """,
            (normalized_runtime_family, STATUS_STARTING, STATUS_LIVE, STATUS_STALE),
        ).fetchone()
        if existing is not None:
            if existing["status"] == STATUS_STALE:
                if existing["shutdown_status"] == SHUTDOWN_STATUS_REQUESTED:
                    _terminalize_runtime(
                        db_path,
                        runtime_instance_id=existing["runtime_instance_id"],
                        target_status=STATUS_STOPPED,
                        failure_code=None,
                        failure_summary=None,
                        failure_phase=None,
                    )
                else:
                    _terminalize_runtime(
                        db_path,
                        runtime_instance_id=existing["runtime_instance_id"],
                        target_status=STATUS_FAILED,
                        failure_code="supervisor_stale_runtime_reconciled",
                        failure_summary="stale supervisor runtime was reconciled before creating a fresh runtime",
                        failure_phase=FAILURE_PHASE_RUNTIME,
                    )
                existing = None
            elif _runtime_process_is_missing(existing):
                _terminalize_runtime(
                    db_path,
                    runtime_instance_id=existing["runtime_instance_id"],
                    target_status=STATUS_FAILED,
                    failure_code="supervisor_process_missing",
                    failure_summary="resident supervisor process is no longer running for the current runtime row",
                    failure_phase=FAILURE_PHASE_RUNTIME,
                )
                existing = None
            else:
                result = _row_to_runtime(existing)
                result["created"] = False
                result["duplicate_start"] = True
                return result

        now = utc_now()
        runtime_instance_id = new_id("runtime")
        connection.execute(
            """
            INSERT INTO runtime_instances (
                runtime_instance_id, runtime_family, status, host_identity, metadata_json,
                stale_after_seconds, started_at, last_seen_at, ended_at,
                failure_code, failure_summary, failure_phase,
                startup_status, startup_completed_at,
                shutdown_status, shutdown_requested_at, shutdown_completed_at,
                recovery_status, recovery_attempt_count,
                recovery_last_requested_at, recovery_last_completed_at, recovery_last_result,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                runtime_instance_id,
                normalized_runtime_family,
                STATUS_STARTING,
                normalized_host_identity,
                _canonical_json(normalized_metadata),
                normalized_stale_after_seconds,
                now,
                now,
                None,
                None,
                None,
                None,
                STARTUP_STATUS_STARTING,
                None,
                SHUTDOWN_STATUS_NOT_REQUESTED,
                None,
                None,
                RECOVERY_STATUS_NOT_REQUESTED,
                0,
                None,
                None,
                None,
                now,
                now,
            ),
        )
        _append_runtime_event(
            connection,
            runtime_instance_id=runtime_instance_id,
            event_type="ace.supervisor.started",
            payload={
                "runtime_family": normalized_runtime_family,
                "status": STATUS_STARTING,
                "startup_status": STARTUP_STATUS_STARTING,
                "shutdown_status": SHUTDOWN_STATUS_NOT_REQUESTED,
                "host_identity": normalized_host_identity,
                "metadata": normalized_metadata,
            },
            actor="ace.supervisor_runtime.start_supervisor_runtime",
            created_at=now,
        )
        connection.commit()
        row = _fetch_runtime_row(connection, runtime_instance_id)
        assert row is not None, "runtime instance creation failed unexpectedly"

    result = _row_to_runtime(row)
    result["created"] = True
    result["duplicate_start"] = False
    return result


def mark_supervisor_runtime_live(
    db_path: Path | str = DB_PATH,
    runtime_instance_id: str | None = None,
) -> dict[str, Any]:
    return _transition_runtime(
        db_path,
        runtime_instance_id,
        expected_status=STATUS_STARTING,
        target_status=STATUS_LIVE,
        touch_last_seen=True,
        event_type="ace.supervisor.live",
    )


def heartbeat_supervisor_runtime(
    db_path: Path | str = DB_PATH,
    runtime_instance_id: str | None = None,
) -> dict[str, Any]:
    return _transition_runtime(
        db_path,
        runtime_instance_id,
        expected_status=STATUS_LIVE,
        target_status=STATUS_LIVE,
        touch_last_seen=True,
        event_type="ace.supervisor.heartbeat",
    )


def request_supervisor_shutdown(
    db_path: Path | str = DB_PATH,
    runtime_instance_id: str | None = None,
) -> dict[str, Any]:
    bootstrap_db(db_path)
    normalized_runtime_instance_id = _normalize_required_text(runtime_instance_id, field_name="runtime_instance_id")
    now = utc_now()

    with connect(db_path) as connection:
        row = _fetch_runtime_row(connection, normalized_runtime_instance_id)
        if row is None:
            raise KeyError(f"unknown runtime_instance_id: {normalized_runtime_instance_id}")

        current_status = row["status"]
        if current_status not in {STATUS_STARTING, STATUS_LIVE, STATUS_STALE}:
            raise ValidationError(
                f"illegal supervisor shutdown request: expected starting, live, or stale runtime, found {current_status}"
            )

        shutdown_status = row["shutdown_status"]
        if shutdown_status == SHUTDOWN_STATUS_REQUESTED:
            return _row_to_runtime(row)
        if shutdown_status in {SHUTDOWN_STATUS_COMPLETED, SHUTDOWN_STATUS_FAILED}:
            raise ValidationError(
                f"illegal supervisor shutdown request: shutdown already terminal with status {shutdown_status}"
            )

        connection.execute(
            """
            UPDATE runtime_instances
            SET shutdown_status = ?, shutdown_requested_at = ?, updated_at = ?
            WHERE runtime_instance_id = ?
            """,
            (SHUTDOWN_STATUS_REQUESTED, now, now, normalized_runtime_instance_id),
        )
        _append_runtime_event(
            connection,
            runtime_instance_id=normalized_runtime_instance_id,
            event_type="ace.supervisor.shutdown_requested",
            payload={
                "status": current_status,
                "shutdown_status": SHUTDOWN_STATUS_REQUESTED,
                "shutdown_requested_at": now,
            },
            actor="ace.supervisor_runtime.request_supervisor_shutdown",
            created_at=now,
        )
        connection.commit()
        row = _fetch_runtime_row(connection, normalized_runtime_instance_id)
        assert row is not None, "supervisor shutdown request failed unexpectedly"
    return _row_to_runtime(row)


def stop_supervisor_runtime(
    db_path: Path | str = DB_PATH,
    runtime_instance_id: str | None = None,
) -> dict[str, Any]:
    return _terminalize_runtime(db_path, runtime_instance_id, target_status=STATUS_STOPPED)


def request_supervisor_recovery(
    db_path: Path | str = DB_PATH,
    runtime_instance_id: str | None = None,
) -> dict[str, Any]:
    bootstrap_db(db_path)
    normalized_runtime_instance_id = _normalize_required_text(runtime_instance_id, field_name="runtime_instance_id")
    now = utc_now()

    with connect(db_path) as connection:
        row = _fetch_runtime_row(connection, normalized_runtime_instance_id)
        if row is None:
            raise KeyError(f"unknown runtime_instance_id: {normalized_runtime_instance_id}")

        current_status = row["status"]
        if current_status != STATUS_FAILED:
            raise ValidationError(
                f"illegal supervisor recovery request: expected failed runtime, found {current_status}"
            )

        recovery_status = row["recovery_status"]
        if recovery_status == RECOVERY_STATUS_REQUESTED:
            return _row_to_runtime(row)
        if recovery_status == RECOVERY_STATUS_COMPLETED:
            raise ValidationError("illegal supervisor recovery request: recovery already completed")

        next_attempt_count = int(row["recovery_attempt_count"] or 0) + 1
        connection.execute(
            """
            UPDATE runtime_instances
            SET recovery_status = ?, recovery_attempt_count = ?, recovery_last_requested_at = ?, updated_at = ?
            WHERE runtime_instance_id = ?
            """,
            (
                RECOVERY_STATUS_REQUESTED,
                next_attempt_count,
                now,
                now,
                normalized_runtime_instance_id,
            ),
        )
        _append_runtime_event(
            connection,
            runtime_instance_id=normalized_runtime_instance_id,
            event_type="ace.supervisor.recovery_requested",
            payload={
                "status": current_status,
                "recovery_status": RECOVERY_STATUS_REQUESTED,
                "recovery_attempt_count": next_attempt_count,
                "recovery_last_requested_at": now,
            },
            actor="ace.supervisor_runtime.request_supervisor_recovery",
            created_at=now,
        )
        connection.commit()
        row = _fetch_runtime_row(connection, normalized_runtime_instance_id)
        assert row is not None, "supervisor recovery request failed unexpectedly"
    return _row_to_runtime(row)


def complete_supervisor_recovery(
    db_path: Path | str = DB_PATH,
    runtime_instance_id: str | None = None,
    *,
    result_summary: str,
) -> dict[str, Any]:
    bootstrap_db(db_path)
    normalized_runtime_instance_id = _normalize_required_text(runtime_instance_id, field_name="runtime_instance_id")
    normalized_result_summary = _normalize_required_text(result_summary, field_name="result_summary")
    now = utc_now()

    with connect(db_path) as connection:
        row = _fetch_runtime_row(connection, normalized_runtime_instance_id)
        if row is None:
            raise KeyError(f"unknown runtime_instance_id: {normalized_runtime_instance_id}")
        if row["recovery_status"] != RECOVERY_STATUS_REQUESTED:
            raise ValidationError(
                f"illegal supervisor recovery completion: expected requested recovery, found {row['recovery_status']}"
            )

        connection.execute(
            """
            UPDATE runtime_instances
            SET recovery_status = ?, recovery_last_completed_at = ?, recovery_last_result = ?, updated_at = ?
            WHERE runtime_instance_id = ?
            """,
            (
                RECOVERY_STATUS_COMPLETED,
                now,
                normalized_result_summary,
                now,
                normalized_runtime_instance_id,
            ),
        )
        _append_runtime_event(
            connection,
            runtime_instance_id=normalized_runtime_instance_id,
            event_type="ace.supervisor.recovery_completed",
            payload={
                "status": row["status"],
                "recovery_status": RECOVERY_STATUS_COMPLETED,
                "recovery_last_completed_at": now,
                "recovery_last_result": normalized_result_summary,
            },
            actor="ace.supervisor_runtime.complete_supervisor_recovery",
            created_at=now,
        )
        connection.commit()
        row = _fetch_runtime_row(connection, normalized_runtime_instance_id)
        assert row is not None, "supervisor recovery completion failed unexpectedly"
    return _row_to_runtime(row)


def fail_supervisor_recovery(
    db_path: Path | str = DB_PATH,
    runtime_instance_id: str | None = None,
    *,
    result_summary: str,
) -> dict[str, Any]:
    bootstrap_db(db_path)
    normalized_runtime_instance_id = _normalize_required_text(runtime_instance_id, field_name="runtime_instance_id")
    normalized_result_summary = _normalize_required_text(result_summary, field_name="result_summary")
    now = utc_now()

    with connect(db_path) as connection:
        row = _fetch_runtime_row(connection, normalized_runtime_instance_id)
        if row is None:
            raise KeyError(f"unknown runtime_instance_id: {normalized_runtime_instance_id}")
        if row["recovery_status"] != RECOVERY_STATUS_REQUESTED:
            raise ValidationError(
                f"illegal supervisor recovery failure: expected requested recovery, found {row['recovery_status']}"
            )

        connection.execute(
            """
            UPDATE runtime_instances
            SET recovery_status = ?, recovery_last_completed_at = ?, recovery_last_result = ?, updated_at = ?
            WHERE runtime_instance_id = ?
            """,
            (
                RECOVERY_STATUS_FAILED,
                now,
                normalized_result_summary,
                now,
                normalized_runtime_instance_id,
            ),
        )
        _append_runtime_event(
            connection,
            runtime_instance_id=normalized_runtime_instance_id,
            event_type="ace.supervisor.recovery_failed",
            payload={
                "status": row["status"],
                "recovery_status": RECOVERY_STATUS_FAILED,
                "recovery_last_completed_at": now,
                "recovery_last_result": normalized_result_summary,
            },
            actor="ace.supervisor_runtime.fail_supervisor_recovery",
            created_at=now,
        )
        connection.commit()
        row = _fetch_runtime_row(connection, normalized_runtime_instance_id)
        assert row is not None, "supervisor recovery failure update failed unexpectedly"
    return _row_to_runtime(row)


def fail_supervisor_runtime(
    db_path: Path | str = DB_PATH,
    runtime_instance_id: str | None = None,
    *,
    failure_code: str,
    failure_summary: str,
    failure_phase: str | None = None,
) -> dict[str, Any]:
    normalized_failure_phase = None
    if failure_phase is not None:
        normalized_failure_phase = _normalize_failure_phase(failure_phase)
    return _terminalize_runtime(
        db_path,
        runtime_instance_id,
        target_status=STATUS_FAILED,
        failure_code=_normalize_required_text(failure_code, field_name="failure_code"),
        failure_summary=_normalize_required_text(failure_summary, field_name="failure_summary"),
        failure_phase=normalized_failure_phase,
    )


def get_supervisor_runtime_status(
    db_path: Path | str = DB_PATH,
    *,
    now: str | None = None,
) -> dict[str, Any]:
    bootstrap_db(db_path)
    inspection_now = now or utc_now()

    with connect(db_path) as connection:
        current_row = connection.execute(
            """
            SELECT *
            FROM runtime_instances
            WHERE status IN (?, ?, ?)
            ORDER BY created_at DESC, runtime_instance_id DESC
            LIMIT 1
            """,
            (STATUS_STARTING, STATUS_LIVE, STATUS_STALE),
        ).fetchone()

        if current_row is not None and current_row["status"] in {STATUS_STARTING, STATUS_LIVE}:
            if _is_stale(current_row["last_seen_at"], inspection_now, current_row["stale_after_seconds"]):
                connection.execute(
                    "UPDATE runtime_instances SET status = ?, updated_at = ? WHERE runtime_instance_id = ?",
                    (STATUS_STALE, inspection_now, current_row["runtime_instance_id"]),
                )
                _append_runtime_event(
                    connection,
                    runtime_instance_id=current_row["runtime_instance_id"],
                    event_type="ace.supervisor.stale",
                    payload={
                        "status": STATUS_STALE,
                        "inspected_at": inspection_now,
                    },
                    actor="ace.supervisor_runtime.get_supervisor_runtime_status",
                    created_at=inspection_now,
                )
                connection.commit()
                current_row = _fetch_runtime_row(connection, current_row["runtime_instance_id"])

        last_terminal_row = connection.execute(
            """
            SELECT *
            FROM runtime_instances
            WHERE status IN (?, ?)
            ORDER BY ended_at DESC, created_at DESC, runtime_instance_id DESC
            LIMIT 1
            """,
            (STATUS_STOPPED, STATUS_FAILED),
        ).fetchone()

        runtime_transition_history: list[dict[str, Any]] = []
        if current_row is not None:
            runtime_transition_history = _fetch_runtime_transition_history(
                connection,
                current_row["runtime_instance_id"],
            )
        elif last_terminal_row is not None:
            runtime_transition_history = _fetch_runtime_transition_history(
                connection,
                last_terminal_row["runtime_instance_id"],
            )

    return {
        "inspection_family": "resident_supervisor_runtime",
        "inspection_scope": _INSPECTION_SCOPE,
        "bounded_runtime_claims": list(_BOUNDED_RUNTIME_CLAIMS),
        "anti_inflation_non_claims": list(_ANTI_INFLATION_NON_CLAIMS),
        "minimal_slice_definition": list(_MINIMAL_SLICE_DEFINITION),
        "evidence_artifact_bundle": list(_EVIDENCE_ARTIFACT_BUNDLE),
        "non_reduction_proof": list(_NON_REDUCTION_PROOF),
        "current_runtime": _row_to_runtime(current_row) if current_row is not None else None,
        "last_terminal_runtime": _row_to_runtime(last_terminal_row) if last_terminal_row is not None else None,
        "runtime_transition_history": runtime_transition_history,
    }


def run_supervisor_runtime(
    db_path: Path | str = DB_PATH,
    *,
    runtime_family: str = RUNTIME_FAMILY_SINGLE_TENANT,
    stale_after_seconds: int = 60,
    heartbeat_count: int = 0,
    heartbeat_interval_seconds: float = 0.0,
    host_identity: str | None = None,
    metadata: dict[str, Any] | None = None,
    run_until_shutdown: bool = False,
) -> dict[str, Any]:
    normalized_heartbeat_count = _normalize_nonnegative_int(heartbeat_count, field_name="heartbeat_count")
    normalized_heartbeat_interval = _normalize_nonnegative_float(
        heartbeat_interval_seconds,
        field_name="heartbeat_interval_seconds",
    )
    if run_until_shutdown and normalized_heartbeat_interval <= 0:
        raise ValidationError("heartbeat_interval_seconds must be greater than zero when run_until_shutdown is enabled")

    runtime = start_supervisor_runtime(
        db_path,
        runtime_family=runtime_family,
        stale_after_seconds=stale_after_seconds,
        host_identity=host_identity,
        metadata=metadata,
    )
    runtime_instance_id = runtime["runtime_instance_id"]

    if runtime.get("duplicate_start"):
        return {
            "runtime": runtime,
            "heartbeat_count": 0,
            "duplicate_start": True,
            "auto_stopped": False,
        }

    live: dict[str, Any] | None = None
    shutdown_requested: dict[str, Any] | None = None
    try:
        live = mark_supervisor_runtime_live(db_path, runtime_instance_id)
        heartbeats_written = 0
        if run_until_shutdown:
            while True:
                current_runtime = _get_runtime_or_raise(db_path, runtime_instance_id)
                if current_runtime["shutdown_status"] == SHUTDOWN_STATUS_REQUESTED:
                    shutdown_requested = current_runtime
                    break
                time.sleep(normalized_heartbeat_interval)
                current_runtime = _get_runtime_or_raise(db_path, runtime_instance_id)
                if current_runtime["shutdown_status"] == SHUTDOWN_STATUS_REQUESTED:
                    shutdown_requested = current_runtime
                    break
                live = heartbeat_supervisor_runtime(db_path, runtime_instance_id)
                heartbeats_written += 1

            stopped = stop_supervisor_runtime(db_path, runtime_instance_id)
            return {
                "runtime": stopped,
                "heartbeat_count": heartbeats_written,
                "duplicate_start": False,
                "auto_stopped": False,
                "last_live_runtime": live,
                "shutdown_requested_runtime": shutdown_requested,
            }

        for _ in range(normalized_heartbeat_count):
            if normalized_heartbeat_interval > 0:
                time.sleep(normalized_heartbeat_interval)
            live = heartbeat_supervisor_runtime(db_path, runtime_instance_id)
            heartbeats_written += 1
        shutdown_requested = request_supervisor_shutdown(db_path, runtime_instance_id)
        stopped = stop_supervisor_runtime(db_path, runtime_instance_id)
        return {
            "runtime": stopped,
            "heartbeat_count": heartbeats_written,
            "duplicate_start": False,
            "auto_stopped": True,
            "last_live_runtime": live,
            "shutdown_requested_runtime": shutdown_requested,
        }
    except (KeyboardInterrupt, SystemExit):
        failed = fail_supervisor_runtime(
            db_path,
            runtime_instance_id,
            failure_code="supervisor_interrupted",
            failure_summary="resident supervisor runtime interrupted before orderly shutdown",
            failure_phase=FAILURE_PHASE_RUNTIME if live is not None else FAILURE_PHASE_STARTUP,
        )
        raise RuntimeError(json.dumps({"runtime_instance_id": failed["runtime_instance_id"], "status": failed["status"]}))
    except Exception as exc:
        fail_supervisor_runtime(
            db_path,
            runtime_instance_id,
            failure_code=_failure_code_for_exception(exc),
            failure_summary=str(exc) or exc.__class__.__name__,
            failure_phase=FAILURE_PHASE_RUNTIME if live is not None else FAILURE_PHASE_STARTUP,
        )
        raise


def _transition_runtime(
    db_path: Path | str,
    runtime_instance_id: str | None,
    *,
    expected_status: str,
    target_status: str,
    touch_last_seen: bool,
    event_type: str,
) -> dict[str, Any]:
    bootstrap_db(db_path)
    normalized_runtime_instance_id = _normalize_required_text(runtime_instance_id, field_name="runtime_instance_id")
    now = utc_now()

    with connect(db_path) as connection:
        row = _fetch_runtime_row(connection, normalized_runtime_instance_id)
        if row is None:
            raise KeyError(f"unknown runtime_instance_id: {normalized_runtime_instance_id}")
        current_status = row["status"]
        if current_status != expected_status:
            raise ValidationError(
                f"illegal supervisor runtime transition: expected {expected_status}, found {current_status}"
            )

        next_last_seen = now if touch_last_seen else row["last_seen_at"]
        startup_status = row["startup_status"]
        startup_completed_at = row["startup_completed_at"]
        if current_status == STATUS_STARTING and target_status == STATUS_LIVE:
            startup_status = STARTUP_STATUS_COMPLETED
            startup_completed_at = now

        connection.execute(
            """
            UPDATE runtime_instances
            SET status = ?, last_seen_at = ?, startup_status = ?, startup_completed_at = ?, updated_at = ?
            WHERE runtime_instance_id = ?
            """,
            (target_status, next_last_seen, startup_status, startup_completed_at, now, normalized_runtime_instance_id),
        )
        _append_runtime_event(
            connection,
            runtime_instance_id=normalized_runtime_instance_id,
            event_type=event_type,
            payload={
                "status": target_status,
                "startup_status": startup_status,
                "startup_completed_at": startup_completed_at,
                "last_seen_at": next_last_seen,
            },
            actor="ace.supervisor_runtime._transition_runtime",
            created_at=now,
        )
        connection.commit()
        row = _fetch_runtime_row(connection, normalized_runtime_instance_id)
        assert row is not None, "runtime instance transition failed unexpectedly"
    return _row_to_runtime(row)


def _terminalize_runtime(
    db_path: Path | str,
    runtime_instance_id: str | None,
    *,
    target_status: str,
    failure_code: str | None = None,
    failure_summary: str | None = None,
    failure_phase: str | None = None,
) -> dict[str, Any]:
    bootstrap_db(db_path)
    normalized_runtime_instance_id = _normalize_required_text(runtime_instance_id, field_name="runtime_instance_id")
    now = utc_now()

    with connect(db_path) as connection:
        row = _fetch_runtime_row(connection, normalized_runtime_instance_id)
        if row is None:
            raise KeyError(f"unknown runtime_instance_id: {normalized_runtime_instance_id}")

        current_status = row["status"]
        if current_status == target_status and target_status in _TERMINAL_STATUSES:
            return _row_to_runtime(row)
        if current_status in _TERMINAL_STATUSES:
            raise ValidationError(
                f"illegal supervisor runtime transition: terminal runtime cannot move from {current_status} to {target_status}"
            )
        if current_status not in _ACTIVE_STATUSES:
            raise ValidationError(
                f"illegal supervisor runtime terminalization: expected active runtime, found {current_status}"
            )

        startup_status = row["startup_status"]
        startup_completed_at = row["startup_completed_at"]
        shutdown_status = row["shutdown_status"]
        shutdown_requested_at = row["shutdown_requested_at"]
        shutdown_completed_at = row["shutdown_completed_at"]
        next_failure_phase = failure_phase

        if target_status == STATUS_STOPPED:
            if shutdown_requested_at is None:
                shutdown_requested_at = now
            shutdown_status = SHUTDOWN_STATUS_COMPLETED
            shutdown_completed_at = now
            event_type = "ace.supervisor.stopped"
        elif target_status == STATUS_FAILED:
            if next_failure_phase is None:
                next_failure_phase = FAILURE_PHASE_STARTUP if current_status == STATUS_STARTING else FAILURE_PHASE_RUNTIME
            if next_failure_phase == FAILURE_PHASE_STARTUP:
                startup_status = STARTUP_STATUS_FAILED
                startup_completed_at = None
            elif next_failure_phase == FAILURE_PHASE_SHUTDOWN:
                if shutdown_requested_at is None:
                    shutdown_requested_at = now
                shutdown_status = SHUTDOWN_STATUS_FAILED
                shutdown_completed_at = None
            event_type = "ace.supervisor.failed"
        else:
            raise ValidationError(f"unsupported terminal supervisor status: {target_status}")

        connection.execute(
            """
            UPDATE runtime_instances
            SET status = ?, ended_at = ?, failure_code = ?, failure_summary = ?, failure_phase = ?,
                startup_status = ?, startup_completed_at = ?,
                shutdown_status = ?, shutdown_requested_at = ?, shutdown_completed_at = ?,
                updated_at = ?
            WHERE runtime_instance_id = ?
            """,
            (
                target_status,
                now,
                failure_code,
                failure_summary,
                next_failure_phase,
                startup_status,
                startup_completed_at,
                shutdown_status,
                shutdown_requested_at,
                shutdown_completed_at,
                now,
                normalized_runtime_instance_id,
            ),
        )
        _append_runtime_event(
            connection,
            runtime_instance_id=normalized_runtime_instance_id,
            event_type=event_type,
            payload={
                "status": target_status,
                "failure_code": failure_code,
                "failure_summary": failure_summary,
                "failure_phase": next_failure_phase,
                "startup_status": startup_status,
                "startup_completed_at": startup_completed_at,
                "shutdown_status": shutdown_status,
                "shutdown_requested_at": shutdown_requested_at,
                "shutdown_completed_at": shutdown_completed_at,
                "ended_at": now,
            },
            actor="ace.supervisor_runtime._terminalize_runtime",
            created_at=now,
        )
        connection.commit()
        row = _fetch_runtime_row(connection, normalized_runtime_instance_id)
        assert row is not None, "runtime instance terminalization failed unexpectedly"
    return _row_to_runtime(row)


def _fetch_runtime_row(connection: Any, runtime_instance_id: str) -> Any:
    return connection.execute(
        """
        SELECT runtime_instance_id, runtime_family, status, host_identity, metadata_json,
               stale_after_seconds, started_at, last_seen_at, ended_at,
               failure_code, failure_summary, failure_phase,
               startup_status, startup_completed_at,
               shutdown_status, shutdown_requested_at, shutdown_completed_at,
               recovery_status, recovery_attempt_count,
               recovery_last_requested_at, recovery_last_completed_at, recovery_last_result,
               created_at, updated_at
        FROM runtime_instances
        WHERE runtime_instance_id = ?
        """,
        (runtime_instance_id,),
    ).fetchone()


def _get_runtime_or_raise(db_path: Path | str, runtime_instance_id: str) -> dict[str, Any]:
    bootstrap_db(db_path)
    with connect(db_path) as connection:
        row = _fetch_runtime_row(connection, runtime_instance_id)
    if row is None:
        raise KeyError(f"unknown runtime_instance_id: {runtime_instance_id}")
    return _row_to_runtime(row)


def _row_to_runtime(row: Any) -> dict[str, Any]:
    return {
        "runtime_instance_id": row["runtime_instance_id"],
        "runtime_family": row["runtime_family"],
        "status": row["status"],
        "host_identity": row["host_identity"],
        "metadata_json": row["metadata_json"],
        "stale_after_seconds": row["stale_after_seconds"],
        "started_at": row["started_at"],
        "last_seen_at": row["last_seen_at"],
        "ended_at": row["ended_at"],
        "failure_code": row["failure_code"],
        "failure_summary": row["failure_summary"],
        "failure_phase": row["failure_phase"],
        "startup_status": row["startup_status"],
        "startup_completed_at": row["startup_completed_at"],
        "shutdown_status": row["shutdown_status"],
        "shutdown_requested_at": row["shutdown_requested_at"],
        "shutdown_completed_at": row["shutdown_completed_at"],
        "recovery_status": row["recovery_status"],
        "recovery_attempt_count": row["recovery_attempt_count"],
        "recovery_last_requested_at": row["recovery_last_requested_at"],
        "recovery_last_completed_at": row["recovery_last_completed_at"],
        "recovery_last_result": row["recovery_last_result"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _fetch_runtime_transition_history(connection: Any, runtime_instance_id: str) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT event_id, event_type, payload_json, actor, source, session_id, created_at
        FROM events
        WHERE source = ?
          AND event_type LIKE 'ace.supervisor.%'
          AND json_extract(payload_json, '$.runtime_instance_id') = ?
        ORDER BY created_at ASC, event_id ASC
        """,
        (_RUNTIME_EVENT_SOURCE, runtime_instance_id),
    ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        result.append(
            {
                "event_id": row["event_id"],
                "event_type": row["event_type"],
                "payload_json": row["payload_json"],
                "actor": row["actor"],
                "source": row["source"],
                "session_id": row["session_id"],
                "created_at": row["created_at"],
            }
        )
    return result


def _append_runtime_event(
    connection: Any,
    *,
    runtime_instance_id: str,
    event_type: str,
    payload: dict[str, Any],
    actor: str,
    created_at: str,
) -> None:
    full_payload = {"runtime_instance_id": runtime_instance_id, **payload}
    append_event(
        connection,
        event_type=event_type,
        payload=full_payload,
        actor=actor,
        source=_RUNTIME_EVENT_SOURCE,
        created_at=created_at,
    )


def _normalize_required_text(value: str | None, *, field_name: str) -> str:
    if value is None:
        raise ValidationError(f"{field_name} is required")
    normalized = value.strip()
    if not normalized:
        raise ValidationError(f"{field_name} must not be empty or whitespace-only")
    return normalized


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        raise ValidationError("optional supervisor runtime text must not be empty or whitespace-only")
    return normalized


def _normalize_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if metadata is None:
        return {}
    if not isinstance(metadata, dict):
        raise ValidationError("metadata must be a mapping")
    return metadata


def _parse_metadata_json(raw: str | None) -> dict[str, Any]:
    if raw is None:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if isinstance(parsed, dict):
        return parsed
    return {}


def _runtime_process_is_missing(row: Any) -> bool:
    metadata = _parse_metadata_json(row["metadata_json"])
    pid = metadata.get("process_pid")
    if pid is None:
        return False
    try:
        normalized_pid = int(pid)
    except (TypeError, ValueError):
        return False
    if normalized_pid <= 0:
        return False
    try:
        os.kill(normalized_pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    except OSError:
        return False
    return False


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _normalize_stale_after_seconds(value: int) -> int:
    if value <= 0:
        raise ValidationError("stale_after_seconds must be greater than zero")
    return int(value)


def _normalize_nonnegative_int(value: int, *, field_name: str) -> int:
    if value < 0:
        raise ValidationError(f"{field_name} must be zero or greater")
    return int(value)


def _normalize_nonnegative_float(value: float, *, field_name: str) -> float:
    if value < 0:
        raise ValidationError(f"{field_name} must be zero or greater")
    return float(value)


def _parse_timestamp(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _is_stale(last_seen_at: str, now: str, stale_after_seconds: int) -> bool:
    return (_parse_timestamp(now) - _parse_timestamp(last_seen_at)).total_seconds() > stale_after_seconds


def _normalize_failure_phase(value: str) -> str:
    normalized = _normalize_required_text(value, field_name="failure_phase").lower()
    if normalized not in {FAILURE_PHASE_STARTUP, FAILURE_PHASE_RUNTIME, FAILURE_PHASE_SHUTDOWN}:
        raise ValidationError("failure_phase must be one of: startup, runtime, shutdown")
    return normalized


def _failure_code_for_exception(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return "supervisor_validation_error"
    return f"supervisor_{exc.__class__.__name__.lower()}"
