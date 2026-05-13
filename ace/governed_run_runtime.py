from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .repository import ValidationError
from .storage import DB_PATH, bootstrap_db, connect, new_id, utc_now


RUN_KIND_CYCLE = "ace_cycle"
TRIGGER_KIND_OPERATOR = "operator"

STATUS_PENDING = "pending"
STATUS_STARTING = "starting"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_INTERRUPTED = "interrupted"
STATUS_SKIPPED = "skipped"

TRIGGER_CORRECTION_REASON_HISTORICAL_RECONCILIATION = "historical_trigger_reconciliation"

_ACTIVE_STATUSES = {STATUS_PENDING, STATUS_STARTING, STATUS_RUNNING}
_TERMINAL_STATUSES = {STATUS_COMPLETED, STATUS_FAILED, STATUS_INTERRUPTED, STATUS_SKIPPED}


def create_governed_cycle_run(
    db_path: Path | str = DB_PATH,
    *,
    trigger_kind: str = TRIGGER_KIND_OPERATOR,
) -> dict[str, Any]:
    bootstrap_db(db_path)
    normalized_trigger_kind = _normalize_required_text(trigger_kind, field_name="trigger_kind")
    run_id = new_id("run")
    created_at = utc_now()

    with connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO governed_runs (
                run_id, run_kind, trigger_kind, status, briefing_path,
                notification_action_id, delivery_evidence_id,
                created_at, started_at, ended_at, interrupted_at,
                failure_code, failure_summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                RUN_KIND_CYCLE,
                normalized_trigger_kind,
                STATUS_PENDING,
                None,
                None,
                None,
                created_at,
                None,
                None,
                None,
                None,
                None,
            ),
        )
        connection.commit()
        row = _fetch_run_row(connection, run_id)
        assert row is not None, "governed run creation failed unexpectedly"
    return _row_to_governed_run(row)


def create_or_skip_governed_cycle_run(
    db_path: Path | str = DB_PATH,
    *,
    trigger_kind: str = TRIGGER_KIND_OPERATOR,
    active_run_stale_after_seconds: int = 24 * 60 * 60,
) -> dict[str, Any]:
    """Create one governed ACE cycle run, or record a skipped run if one is already active.

    This is the single-flight boundary for bounded ACE cycles. It does not kill,
    steal, or overwrite a live run. If an active row is fresh, it records an
    auditable skipped terminal run. If an active row is stale, it first
    terminalizes that stale row as interrupted and then creates a new pending run.
    """

    bootstrap_db(db_path)
    normalized_trigger_kind = _normalize_required_text(trigger_kind, field_name="trigger_kind")
    normalized_stale_after_seconds = _normalize_active_run_stale_after_seconds(active_run_stale_after_seconds)
    run_id = new_id("run")
    created_at = utc_now()

    with connect(db_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        active_row = connection.execute(
            """
            SELECT run_id, status, created_at, started_at
            FROM governed_runs
            WHERE run_kind = ? AND status IN (?, ?, ?)
            ORDER BY created_at DESC, run_id DESC
            LIMIT 1
            """,
            (RUN_KIND_CYCLE, STATUS_PENDING, STATUS_STARTING, STATUS_RUNNING),
        ).fetchone()
        if active_row is not None and not _active_run_is_stale(
            active_row,
            now=created_at,
            stale_after_seconds=normalized_stale_after_seconds,
        ):
            failure_summary = (
                "governed ace cycle skipped because another cycle is active: "
                f"{active_row['run_id']} ({active_row['status']})"
            )
            connection.execute(
                """
                INSERT INTO governed_runs (
                    run_id, run_kind, trigger_kind, status, briefing_path,
                    notification_action_id, delivery_evidence_id,
                    created_at, started_at, ended_at, interrupted_at,
                    failure_code, failure_summary
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    RUN_KIND_CYCLE,
                    normalized_trigger_kind,
                    STATUS_SKIPPED,
                    None,
                    None,
                    None,
                    created_at,
                    None,
                    created_at,
                    None,
                    "cycle_already_active",
                    failure_summary,
                ),
            )
        else:
            if active_row is not None:
                failure_summary = (
                    "stale governed ace cycle reconciled before creating a new cycle: "
                    f"{active_row['run_id']} ({active_row['status']})"
                )
                connection.execute(
                    """
                    UPDATE governed_runs
                    SET status = ?, ended_at = ?, interrupted_at = ?,
                        failure_code = ?, failure_summary = ?
                    WHERE run_id = ?
                    """,
                    (
                        STATUS_INTERRUPTED,
                        created_at,
                        created_at,
                        "cycle_stale_active_reconciled",
                        failure_summary,
                        active_row["run_id"],
                    ),
                )
            connection.execute(
                """
                INSERT INTO governed_runs (
                    run_id, run_kind, trigger_kind, status, briefing_path,
                    notification_action_id, delivery_evidence_id,
                    created_at, started_at, ended_at, interrupted_at,
                    failure_code, failure_summary
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    RUN_KIND_CYCLE,
                    normalized_trigger_kind,
                    STATUS_PENDING,
                    None,
                    None,
                    None,
                    created_at,
                    None,
                    None,
                    None,
                    None,
                    None,
                ),
            )
        connection.commit()
        row = _fetch_run_row(connection, run_id)
        assert row is not None, "governed run creation failed unexpectedly"
    return _row_to_governed_run(row)


def start_governed_run(
    db_path: Path | str = DB_PATH,
    run_id: str | None = None,
) -> dict[str, Any]:
    return _transition_run(
        db_path,
        run_id,
        expected_status=STATUS_PENDING,
        target_status=STATUS_STARTING,
        started_at=utc_now(),
    )


def mark_governed_run_running(
    db_path: Path | str = DB_PATH,
    run_id: str | None = None,
) -> dict[str, Any]:
    return _transition_run(
        db_path,
        run_id,
        expected_status=STATUS_STARTING,
        target_status=STATUS_RUNNING,
    )


def complete_governed_run(
    db_path: Path | str = DB_PATH,
    run_id: str | None = None,
    *,
    briefing_path: str | None = None,
    notification_action_id: str | None = None,
    delivery_evidence_id: str | None = None,
) -> dict[str, Any]:
    return _terminalize_run(
        db_path,
        run_id,
        target_status=STATUS_COMPLETED,
        briefing_path=briefing_path,
        notification_action_id=notification_action_id,
        delivery_evidence_id=delivery_evidence_id,
        failure_code=None,
        failure_summary=None,
    )


def fail_governed_run(
    db_path: Path | str = DB_PATH,
    run_id: str | None = None,
    *,
    failure_code: str,
    failure_summary: str,
    briefing_path: str | None = None,
    notification_action_id: str | None = None,
    delivery_evidence_id: str | None = None,
) -> dict[str, Any]:
    return _terminalize_run(
        db_path,
        run_id,
        target_status=STATUS_FAILED,
        briefing_path=briefing_path,
        notification_action_id=notification_action_id,
        delivery_evidence_id=delivery_evidence_id,
        failure_code=_normalize_required_text(failure_code, field_name="failure_code"),
        failure_summary=_normalize_required_text(failure_summary, field_name="failure_summary"),
    )


def interrupt_governed_run(
    db_path: Path | str = DB_PATH,
    run_id: str | None = None,
    *,
    failure_code: str,
    failure_summary: str,
    briefing_path: str | None = None,
    notification_action_id: str | None = None,
    delivery_evidence_id: str | None = None,
) -> dict[str, Any]:
    return _terminalize_run(
        db_path,
        run_id,
        target_status=STATUS_INTERRUPTED,
        briefing_path=briefing_path,
        notification_action_id=notification_action_id,
        delivery_evidence_id=delivery_evidence_id,
        failure_code=_normalize_required_text(failure_code, field_name="failure_code"),
        failure_summary=_normalize_required_text(failure_summary, field_name="failure_summary"),
    )


def get_governed_cycle_run_status(db_path: Path | str = DB_PATH) -> dict[str, Any]:
    bootstrap_db(db_path)
    with connect(db_path) as connection:
        current_row = connection.execute(
            """
            SELECT *
            FROM governed_runs
            WHERE status IN (?, ?, ?)
            ORDER BY created_at DESC, run_id DESC
            LIMIT 1
            """,
            (STATUS_PENDING, STATUS_STARTING, STATUS_RUNNING),
        ).fetchone()
        last_terminal_row = connection.execute(
            """
            SELECT *
            FROM governed_runs
            WHERE status IN (?, ?, ?, ?)
            ORDER BY ended_at DESC, created_at DESC, run_id DESC
            LIMIT 1
            """,
            (STATUS_COMPLETED, STATUS_FAILED, STATUS_INTERRUPTED, STATUS_SKIPPED),
        ).fetchone()

    return {
        "current_run": _row_to_governed_run(current_row) if current_row is not None else None,
        "last_terminal_run": _row_to_governed_run(last_terminal_row) if last_terminal_row is not None else None,
    }


def correct_governed_run_trigger_kind(
    db_path: Path | str = DB_PATH,
    run_id: str | None = None,
    *,
    trigger_kind: str,
    actor: str | None,
    source: str | None,
    source_session: str | None,
    reason: str,
) -> dict[str, Any]:
    bootstrap_db(db_path)
    normalized_run_id = _normalize_required_text(run_id, field_name="run_id")
    normalized_trigger_kind = _normalize_required_text(trigger_kind, field_name="trigger_kind")
    normalized_reason = _normalize_required_text(reason, field_name="reason")
    normalized_actor = _normalize_optional_text(actor)
    normalized_source = _normalize_optional_text(source)
    normalized_source_session = _normalize_optional_text(source_session)
    corrected_at = utc_now()

    with connect(db_path) as connection:
        row = _fetch_run_row(connection, normalized_run_id)
        if row is None:
            raise KeyError(f"unknown run_id: {normalized_run_id}")

        previous_trigger_kind = row["trigger_kind"]
        changed = previous_trigger_kind != normalized_trigger_kind
        if changed:
            connection.execute(
                """
                UPDATE governed_runs
                SET trigger_kind = ?
                WHERE run_id = ?
                """,
                (normalized_trigger_kind, normalized_run_id),
            )

        payload = {
            "run_id": normalized_run_id,
            "from_trigger_kind": previous_trigger_kind,
            "to_trigger_kind": normalized_trigger_kind,
            "reason": normalized_reason,
            "corrected_at": corrected_at,
            "changed": changed,
        }
        from .storage import append_event

        append_event(
            connection,
            event_type="ace.governed_run.trigger_kind_corrected",
            payload=payload,
            item_id=None,
            actor=normalized_actor,
            source=normalized_source,
            session_id=normalized_source_session,
            created_at=corrected_at,
        )
        connection.commit()
        updated = _fetch_run_row(connection, normalized_run_id)
        assert updated is not None, "governed run correction failed unexpectedly"
    return _row_to_governed_run(updated)


def _transition_run(
    db_path: Path | str,
    run_id: str | None,
    *,
    expected_status: str,
    target_status: str,
    started_at: str | None = None,
) -> dict[str, Any]:
    bootstrap_db(db_path)
    normalized_run_id = _normalize_required_text(run_id, field_name="run_id")

    with connect(db_path) as connection:
        row = _fetch_run_row(connection, normalized_run_id)
        if row is None:
            raise KeyError(f"unknown run_id: {normalized_run_id}")
        current_status = row["status"]
        if current_status != expected_status:
            raise ValidationError(
                f"illegal governed run transition: expected {expected_status}, found {current_status}"
            )

        next_started_at = row["started_at"]
        if started_at is not None:
            next_started_at = started_at

        connection.execute(
            """
            UPDATE governed_runs
            SET status = ?, started_at = ?
            WHERE run_id = ?
            """,
            (target_status, next_started_at, normalized_run_id),
        )
        connection.commit()
        row = _fetch_run_row(connection, normalized_run_id)
        assert row is not None, "governed run transition failed unexpectedly"
    return _row_to_governed_run(row)


def _terminalize_run(
    db_path: Path | str,
    run_id: str | None,
    *,
    target_status: str,
    briefing_path: str | None,
    notification_action_id: str | None,
    delivery_evidence_id: str | None,
    failure_code: str | None,
    failure_summary: str | None,
) -> dict[str, Any]:
    bootstrap_db(db_path)
    normalized_run_id = _normalize_required_text(run_id, field_name="run_id")
    ended_at = utc_now()
    normalized_briefing_path = _normalize_optional_text(briefing_path)
    normalized_notification_action_id = _normalize_optional_text(notification_action_id)
    normalized_delivery_evidence_id = _normalize_optional_text(delivery_evidence_id)

    with connect(db_path) as connection:
        row = _fetch_run_row(connection, normalized_run_id)
        if row is None:
            raise KeyError(f"unknown run_id: {normalized_run_id}")

        current_status = row["status"]
        if current_status == target_status and target_status in _TERMINAL_STATUSES:
            return _row_to_governed_run(row)
        if current_status in _TERMINAL_STATUSES:
            raise ValidationError(
                f"illegal governed run transition: terminal run cannot move from {current_status} to {target_status}"
            )
        if current_status != STATUS_RUNNING:
            raise ValidationError(
                f"illegal governed run terminalization: expected running, found {current_status}"
            )

        interrupted_at = ended_at if target_status == STATUS_INTERRUPTED else None
        connection.execute(
            """
            UPDATE governed_runs
            SET status = ?,
                briefing_path = COALESCE(?, briefing_path),
                notification_action_id = COALESCE(?, notification_action_id),
                delivery_evidence_id = COALESCE(?, delivery_evidence_id),
                ended_at = ?,
                interrupted_at = ?,
                failure_code = ?,
                failure_summary = ?
            WHERE run_id = ?
            """,
            (
                target_status,
                normalized_briefing_path,
                normalized_notification_action_id,
                normalized_delivery_evidence_id,
                ended_at,
                interrupted_at,
                failure_code,
                failure_summary,
                normalized_run_id,
            ),
        )
        connection.commit()
        row = _fetch_run_row(connection, normalized_run_id)
        assert row is not None, "governed run terminalization failed unexpectedly"
    return _row_to_governed_run(row)


def _fetch_run_row(connection: Any, run_id: str) -> Any:
    return connection.execute(
        """
        SELECT run_id, run_kind, trigger_kind, status, briefing_path,
               notification_action_id, delivery_evidence_id, created_at,
               started_at, ended_at, interrupted_at, failure_code, failure_summary
        FROM governed_runs
        WHERE run_id = ?
        """,
        (run_id,),
    ).fetchone()


def _row_to_governed_run(row: Any) -> dict[str, Any]:
    return {
        "run_id": row["run_id"],
        "run_kind": row["run_kind"],
        "trigger_kind": row["trigger_kind"],
        "status": row["status"],
        "briefing_path": row["briefing_path"],
        "notification_action_id": row["notification_action_id"],
        "delivery_evidence_id": row["delivery_evidence_id"],
        "created_at": row["created_at"],
        "started_at": row["started_at"],
        "ended_at": row["ended_at"],
        "interrupted_at": row["interrupted_at"],
        "failure_code": row["failure_code"],
        "failure_summary": row["failure_summary"],
    }


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
        raise ValidationError("optional governed run text must not be empty or whitespace-only")
    return normalized


def _normalize_active_run_stale_after_seconds(value: int) -> int:
    if value <= 0:
        raise ValidationError("active_run_stale_after_seconds must be greater than zero")
    return value


def _active_run_is_stale(row: Any, *, now: str, stale_after_seconds: int) -> bool:
    reference = row["started_at"] or row["created_at"]
    return (_parse_timestamp(now) - _parse_timestamp(reference)).total_seconds() > stale_after_seconds


def _parse_timestamp(value: str) -> datetime:
    normalized = str(value).strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
