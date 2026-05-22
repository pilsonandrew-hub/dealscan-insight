from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .storage import DB_PATH, append_event, bootstrap_db, connect, new_id, utc_now


ACTIVE_STATUS = "active"
CLEARED_STATUS = "cleared"

CONSTRAINT_MODES = frozenset(
    {
        "approval_required",
        "investigation_only",
        "no_code_changes",
        "no_state_writes",
        "no_notifications",
    }
)

READ_ONLY_COMMANDS = frozenset(
    {
        "list",
        "show",
        "inspect",
        "briefing",
        "cycle-status",
        "supervisor-status",
        "gate4-inspection",
        "audit",
        "cost:status",
        "constraints:status",
    }
)

CONSTRAINT_ADMIN_COMMANDS = frozenset(
    {
        "constraints:set",
        "constraints:clear",
    }
)

NOTIFICATION_COMMANDS = frozenset({"jace-status-send", "cycle"})


@dataclass(frozen=True)
class OperatorConstraint:
    constraint_id: str
    mode: str
    scope: str
    reason: str
    status: str
    created_at: str
    actor: str | None = None
    cleared_at: str | None = None
    cleared_by: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "constraint_id": self.constraint_id,
            "mode": self.mode,
            "scope": self.scope,
            "reason": self.reason,
            "status": self.status,
            "created_at": self.created_at,
            "actor": self.actor,
            "cleared_at": self.cleared_at,
            "cleared_by": self.cleared_by,
        }


class OperatorConstraintViolation(RuntimeError):
    def __init__(self, *, constraint: OperatorConstraint, attempted_action: str, command: str):
        self.constraint = constraint
        self.attempted_action = attempted_action
        self.command = command
        super().__init__(
            "OPERATOR_CONSTRAINT_BLOCKED: "
            f"active_constraint={constraint.mode} "
            f"constraint_id={constraint.constraint_id} "
            f"attempted_action={attempted_action} "
            "required_operator_action=explicit approval"
        )


def _normalize_required(value: str | None, *, field_name: str) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _row_to_constraint(row) -> OperatorConstraint:
    return OperatorConstraint(
        constraint_id=row["id"],
        mode=row["mode"],
        scope=row["scope"],
        reason=row["reason"],
        status=row["status"],
        created_at=row["created_at"],
        actor=row["actor"],
        cleared_at=row["cleared_at"],
        cleared_by=row["cleared_by"],
    )


def set_operator_constraint(
    db_path: Path | str = DB_PATH,
    *,
    mode: str,
    reason: str,
    scope: str = "session",
    actor: str | None = None,
) -> OperatorConstraint:
    normalized_mode = _normalize_required(mode, field_name="mode")
    if normalized_mode not in CONSTRAINT_MODES:
        raise ValueError(f"unsupported constraint mode: {normalized_mode}")
    normalized_scope = _normalize_required(scope, field_name="scope")
    normalized_reason = _normalize_required(reason, field_name="reason")
    bootstrap_db(db_path)
    constraint_id = new_id("constraint")
    created_at = utc_now()
    with connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO operator_constraints (
                id, mode, scope, reason, status, created_at, actor, cleared_at, cleared_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL)
            """,
            (
                constraint_id,
                normalized_mode,
                normalized_scope,
                normalized_reason,
                ACTIVE_STATUS,
                created_at,
                actor,
            ),
        )
        append_event(
            connection,
            event_type="operator_constraint.set",
            payload={
                "constraint_id": constraint_id,
                "mode": normalized_mode,
                "scope": normalized_scope,
                "reason": normalized_reason,
                "status": ACTIVE_STATUS,
            },
            actor=actor or "operator_constraints",
            source="ace/operator_constraints.py",
            created_at=created_at,
        )
        connection.commit()
    return OperatorConstraint(
        constraint_id=constraint_id,
        mode=normalized_mode,
        scope=normalized_scope,
        reason=normalized_reason,
        status=ACTIVE_STATUS,
        created_at=created_at,
        actor=actor,
    )


def clear_operator_constraint(
    db_path: Path | str = DB_PATH,
    *,
    constraint_id: str,
    actor: str | None = None,
    reason: str | None = None,
) -> OperatorConstraint:
    normalized_id = _normalize_required(constraint_id, field_name="constraint_id")
    bootstrap_db(db_path)
    cleared_at = utc_now()
    with connect(db_path) as connection:
        row = connection.execute(
            "SELECT * FROM operator_constraints WHERE id = ?",
            (normalized_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown constraint_id: {normalized_id}")
        if row["status"] != CLEARED_STATUS:
            connection.execute(
                """
                UPDATE operator_constraints
                SET status = ?, cleared_at = ?, cleared_by = ?
                WHERE id = ?
                """,
                (CLEARED_STATUS, cleared_at, actor, normalized_id),
            )
            append_event(
                connection,
                event_type="operator_constraint.cleared",
                payload={
                    "constraint_id": normalized_id,
                    "mode": row["mode"],
                    "scope": row["scope"],
                    "reason": reason,
                    "status": CLEARED_STATUS,
                },
                actor=actor or "operator_constraints",
                source="ace/operator_constraints.py",
                created_at=cleared_at,
            )
            connection.commit()
        updated = connection.execute(
            "SELECT * FROM operator_constraints WHERE id = ?",
            (normalized_id,),
        ).fetchone()
    return _row_to_constraint(updated)


def list_operator_constraints(
    db_path: Path | str = DB_PATH,
    *,
    include_cleared: bool = False,
) -> list[OperatorConstraint]:
    bootstrap_db(db_path)
    with connect(db_path) as connection:
        if include_cleared:
            rows = connection.execute(
                "SELECT * FROM operator_constraints ORDER BY created_at ASC, id ASC"
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT * FROM operator_constraints
                WHERE status = ?
                ORDER BY created_at ASC, id ASC
                """,
                (ACTIVE_STATUS,),
            ).fetchall()
    return [_row_to_constraint(row) for row in rows]


def _is_read_only_action(command_key: str) -> bool:
    return command_key in READ_ONLY_COMMANDS


def _is_constraint_admin(command_key: str) -> bool:
    return command_key in CONSTRAINT_ADMIN_COMMANDS


def _constraint_blocks_command(constraint: OperatorConstraint, command_key: str) -> bool:
    if _is_constraint_admin(command_key) or _is_read_only_action(command_key):
        return False
    if constraint.mode in {"approval_required", "investigation_only", "no_state_writes"}:
        return True
    if constraint.mode == "no_notifications" and command_key in NOTIFICATION_COMMANDS:
        return True
    # `no_code_changes` cannot intercept arbitrary editor/git tools from inside ACE,
    # but it blocks ACE write-capable commands so the constraint is durable and auditable.
    if constraint.mode == "no_code_changes":
        return True
    return False


def enforce_operator_constraints(
    db_path: Path | str = DB_PATH,
    *,
    command_key: str,
    attempted_action: str | None = None,
    actor: str | None = None,
) -> None:
    constraints = list_operator_constraints(db_path)
    attempted = attempted_action or command_key
    for constraint in constraints:
        if _constraint_blocks_command(constraint, command_key):
            record_constraint_violation_attempt(
                db_path,
                constraint=constraint,
                command_key=command_key,
                attempted_action=attempted,
                actor=actor,
            )
            raise OperatorConstraintViolation(
                constraint=constraint,
                command=command_key,
                attempted_action=attempted,
            )


def record_constraint_violation_attempt(
    db_path: Path | str,
    *,
    constraint: OperatorConstraint,
    command_key: str,
    attempted_action: str,
    actor: str | None = None,
) -> str:
    bootstrap_db(db_path)
    created_at = utc_now()
    with connect(db_path) as connection:
        event_id = append_event(
            connection,
            event_type="operator_constraint.violation_attempted",
            payload={
                "constraint_id": constraint.constraint_id,
                "constraint_mode": constraint.mode,
                "constraint_scope": constraint.scope,
                "attempted_action": attempted_action,
                "command": command_key,
                "blocked": True,
                "required_operator_action": "explicit approval",
            },
            actor=actor or "operator_constraints",
            source="ace/operator_constraints.py",
            created_at=created_at,
        )
        connection.commit()
    return event_id


def constraints_as_json(constraints: Iterable[OperatorConstraint]) -> str:
    return json.dumps([constraint.as_dict() for constraint in constraints], sort_keys=True)
