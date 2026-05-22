from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .repository import ValidationError
from .storage import DB_PATH, append_event, bootstrap_db, connect, new_id, utc_now

CONSTRAINT_SET_EVENT = "operator_constraint.set"
CONSTRAINT_CLEARED_EVENT = "operator_constraint.cleared"
CONSTRAINT_VIOLATION_EVENT = "operator_constraint.violation_attempted"

VALID_MODES = frozenset(
    {
        "approval_required",
        "investigation_only",
        "no_code_changes",
        "no_state_writes",
        "no_notifications",
    }
)
VALID_SCOPES = frozenset({"session", "ace", "dealerscope", "repo", "global"})
READ_ONLY_COMMANDS = frozenset(
    {
        "init",
        "bootstrap",
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
NOTIFICATION_COMMANDS = frozenset({"jace-status-send"})


@dataclass(frozen=True)
class OperatorConstraint:
    id: str
    mode: str
    scope: str
    reason: str
    status: str
    actor: str | None
    created_at: str
    cleared_at: str | None
    cleared_by: str | None
    clear_reason: str | None

    @classmethod
    def from_row(cls, row: Any) -> "OperatorConstraint":
        return cls(
            id=row["id"],
            mode=row["mode"],
            scope=row["scope"],
            reason=row["reason"],
            status=row["status"],
            actor=row["actor"],
            created_at=row["created_at"],
            cleared_at=row["cleared_at"],
            cleared_by=row["cleared_by"],
            clear_reason=row["clear_reason"],
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "mode": self.mode,
            "scope": self.scope,
            "reason": self.reason,
            "status": self.status,
            "actor": self.actor,
            "created_at": self.created_at,
            "cleared_at": self.cleared_at,
            "cleared_by": self.cleared_by,
            "clear_reason": self.clear_reason,
        }


class OperatorConstraintBlocked(RuntimeError):
    def __init__(self, *, constraint: OperatorConstraint, attempted_action: str):
        self.constraint = constraint
        self.attempted_action = attempted_action
        super().__init__(
            "OPERATOR_CONSTRAINT_BLOCKED: "
            f"active_constraint={constraint.mode} attempted_action={attempted_action} "
            "required_operator_action=explicit approval"
        )


def _normalize_required_text(value: str | None, *, field_name: str) -> str:
    if value is None:
        raise ValidationError(f"{field_name} is required")
    normalized = value.strip()
    if not normalized:
        raise ValidationError(f"{field_name} must not be empty or whitespace-only")
    return normalized


def _normalize_mode(mode: str) -> str:
    normalized = _normalize_required_text(mode, field_name="mode")
    if normalized not in VALID_MODES:
        raise ValidationError(f"invalid operator constraint mode: {normalized}")
    return normalized


def _normalize_scope(scope: str) -> str:
    normalized = _normalize_required_text(scope, field_name="scope")
    if normalized not in VALID_SCOPES:
        raise ValidationError(f"invalid operator constraint scope: {normalized}")
    return normalized


def _action_class(command: str, subcommand: str | None = None) -> str:
    if command == "audit":
        return "audit"
    if command == "cost" and subcommand == "status":
        return "cost:status"
    if command == "constraints" and subcommand == "status":
        return "constraints:status"
    if command == "constraints" and subcommand is not None:
        return f"constraints:{subcommand}"
    return command


def set_operator_constraint(
    db_path: Path | str = DB_PATH,
    *,
    mode: str,
    scope: str,
    reason: str,
    actor: str | None = None,
) -> OperatorConstraint:
    bootstrap_db(db_path)
    normalized_mode = _normalize_mode(mode)
    normalized_scope = _normalize_scope(scope)
    normalized_reason = _normalize_required_text(reason, field_name="reason")
    normalized_actor = actor.strip() if actor is not None and actor.strip() else actor
    constraint_id = new_id("constraint")
    created_at = utc_now()
    with connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO operator_constraints (
                id, mode, scope, reason, status, actor, created_at, cleared_at, cleared_by, clear_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL)
            """,
            (
                constraint_id,
                normalized_mode,
                normalized_scope,
                normalized_reason,
                "active",
                normalized_actor,
                created_at,
            ),
        )
        append_event(
            connection,
            event_type=CONSTRAINT_SET_EVENT,
            payload={
                "constraint_id": constraint_id,
                "mode": normalized_mode,
                "scope": normalized_scope,
                "reason": normalized_reason,
                "status": "active",
            },
            actor=normalized_actor,
            source="ace/operator_constraints",
            created_at=created_at,
        )
        connection.commit()
        row = connection.execute("SELECT * FROM operator_constraints WHERE id = ?", (constraint_id,)).fetchone()
        assert row is not None
        return OperatorConstraint.from_row(row)


def clear_operator_constraint(
    db_path: Path | str = DB_PATH,
    constraint_id: str | None = None,
    *,
    reason: str,
    actor: str | None = None,
) -> OperatorConstraint:
    bootstrap_db(db_path)
    normalized_constraint_id = _normalize_required_text(constraint_id, field_name="constraint_id")
    normalized_reason = _normalize_required_text(reason, field_name="reason")
    normalized_actor = _normalize_required_text(actor, field_name="actor") if actor is not None else None
    cleared_at = utc_now()
    with connect(db_path) as connection:
        row = connection.execute(
            "SELECT * FROM operator_constraints WHERE id = ?",
            (normalized_constraint_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown constraint_id: {normalized_constraint_id}")
        if row["status"] != "cleared":
            connection.execute(
                """
                UPDATE operator_constraints
                SET status = ?, cleared_at = ?, cleared_by = ?, clear_reason = ?
                WHERE id = ?
                """,
                ("cleared", cleared_at, normalized_actor, normalized_reason, normalized_constraint_id),
            )
            append_event(
                connection,
                event_type=CONSTRAINT_CLEARED_EVENT,
                payload={
                    "constraint_id": normalized_constraint_id,
                    "mode": row["mode"],
                    "scope": row["scope"],
                    "reason": normalized_reason,
                    "status": "cleared",
                    "cleared_by": normalized_actor,
                },
                actor=normalized_actor,
                source="ace/operator_constraints",
                created_at=cleared_at,
            )
            connection.commit()
        final = connection.execute(
            "SELECT * FROM operator_constraints WHERE id = ?",
            (normalized_constraint_id,),
        ).fetchone()
        assert final is not None
        return OperatorConstraint.from_row(final)


def list_operator_constraints(
    db_path: Path | str = DB_PATH,
    *,
    active_only: bool = False,
) -> list[OperatorConstraint]:
    bootstrap_db(db_path)
    sql = "SELECT * FROM operator_constraints"
    params: tuple[Any, ...] = ()
    if active_only:
        sql += " WHERE status = ?"
        params = ("active",)
    sql += " ORDER BY created_at ASC, id ASC"
    with connect(db_path) as connection:
        rows = connection.execute(sql, params).fetchall()
    return [OperatorConstraint.from_row(row) for row in rows]


def _constraint_blocks_action(constraint: OperatorConstraint, action: str) -> bool:
    if constraint.status != "active":
        return False
    if action in {"constraints:set", "constraints:clear", "constraints:status"}:
        return False
    if constraint.mode in {"approval_required", "investigation_only", "no_state_writes"}:
        return action not in READ_ONLY_COMMANDS
    if constraint.mode == "no_notifications":
        return action in NOTIFICATION_COMMANDS or action == "cycle"
    if constraint.mode == "no_code_changes":
        # ACE CLI cannot enforce OpenClaw edit/write/apply_patch tools directly;
        # keep the mode visible and auditable, while blocking broadly mutating ACE commands.
        return action not in READ_ONLY_COMMANDS
    return False


def record_constraint_violation_attempt(
    db_path: Path | str,
    *,
    constraint: OperatorConstraint,
    attempted_action: str,
    actor: str | None = None,
) -> str:
    bootstrap_db(db_path)
    event_id: str | None = None
    created_at = utc_now()
    with connect(db_path) as connection:
        event_id = append_event(
            connection,
            event_type=CONSTRAINT_VIOLATION_EVENT,
            payload={
                "constraint_id": constraint.id,
                "constraint_mode": constraint.mode,
                "scope": constraint.scope,
                "attempted_action": attempted_action,
                "blocked": True,
                "reason": constraint.reason,
            },
            actor=actor,
            source="ace/operator_constraints",
            created_at=created_at,
        )
        connection.commit()
    return event_id


def enforce_operator_constraints(
    db_path: Path | str,
    *,
    command: str,
    subcommand: str | None = None,
    actor: str | None = None,
) -> None:
    action = _action_class(command, subcommand)
    for constraint in list_operator_constraints(db_path, active_only=True):
        if _constraint_blocks_action(constraint, action):
            record_constraint_violation_attempt(
                db_path,
                constraint=constraint,
                attempted_action=action,
                actor=actor,
            )
            raise OperatorConstraintBlocked(constraint=constraint, attempted_action=action)


def render_constraint_lines(constraints: list[OperatorConstraint]) -> list[str]:
    if not constraints:
        return ["operator_constraint_count=0"]
    lines = [f"operator_constraint_count={len(constraints)}"]
    for constraint in constraints:
        payload = constraint.as_dict()
        lines.append("operator_constraint=" + json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return lines
