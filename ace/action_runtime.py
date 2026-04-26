from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from .repository import ItemRepository, ValidationError
from .storage import DB_PATH, append_event, bootstrap_db, connect, new_id, utc_now


ACTION_KIND = "record_operator_followup"
ACTION_CREATED_BY = "ace.phase2.action_runtime"
ACTION_EVIDENCE_URI = "ace://phase2/action-outcome"
REJECTION_ACTION_KIND = "record_operator_rejection"
REJECTION_ACTION_EVIDENCE_URI = "ace://phase2/action-rejection"

_ACTION_STATUS_QUEUED = "queued"
_ACTION_STATUS_CLAIMED = "claimed"
_ACTION_STATUS_COMPLETED = "completed"
_ACTION_STATUS_FAILED = "failed"


def enqueue_record_operator_followup(
    db_path: Path | str = DB_PATH,
    item_id: str | None = None,
    *,
    note: str,
    actor: str | None = None,
) -> dict[str, Any]:
    return _enqueue_record_operator_action(
        db_path,
        item_id,
        action_kind=ACTION_KIND,
        payload_field_name="note",
        payload_field_value=note,
        actor=actor,
    )


def enqueue_record_operator_rejection(
    db_path: Path | str = DB_PATH,
    item_id: str | None = None,
    *,
    reason: str,
    actor: str | None = None,
) -> dict[str, Any]:
    return _enqueue_record_operator_action(
        db_path,
        item_id,
        action_kind=REJECTION_ACTION_KIND,
        payload_field_name="reason",
        payload_field_value=reason,
        actor=actor,
    )


def claim_record_operator_followup(
    db_path: Path | str = DB_PATH,
    action_id: str | None = None,
    *,
    actor: str | None = None,
) -> dict[str, Any]:
    return _claim_record_operator_action(db_path, action_id, action_kind=ACTION_KIND)


def claim_record_operator_rejection(
    db_path: Path | str = DB_PATH,
    action_id: str | None = None,
    *,
    actor: str | None = None,
) -> dict[str, Any]:
    return _claim_record_operator_action(db_path, action_id, action_kind=REJECTION_ACTION_KIND)


def execute_record_operator_followup(
    db_path: Path | str = DB_PATH,
    action_id: str | None = None,
    *,
    actor: str | None = None,
) -> dict[str, Any]:
    return _execute_record_operator_action(
        db_path,
        action_id,
        action_kind=ACTION_KIND,
        payload_field_name="note",
        outcome="operator_followup_recorded",
        evidence_uri=ACTION_EVIDENCE_URI,
        actor=actor,
    )


def execute_record_operator_rejection(
    db_path: Path | str = DB_PATH,
    action_id: str | None = None,
    *,
    actor: str | None = None,
) -> dict[str, Any]:
    return _execute_record_operator_action(
        db_path,
        action_id,
        action_kind=REJECTION_ACTION_KIND,
        payload_field_name="reason",
        outcome="operator_rejection_recorded",
        evidence_uri=REJECTION_ACTION_EVIDENCE_URI,
        actor=actor,
    )


def _enqueue_record_operator_action(
    db_path: Path | str,
    item_id: str | None,
    *,
    action_kind: str,
    payload_field_name: str,
    payload_field_value: str,
    actor: str | None = None,
) -> dict[str, Any]:
    bootstrap_db(db_path)
    normalized_item_id = _normalize_required_text(item_id, field_name="item_id")
    normalized_value = _normalize_required_text(payload_field_value, field_name=payload_field_name)
    repo = ItemRepository(db_path)
    queued_item_id = normalized_item_id if repo.get_item(normalized_item_id) is not None else None
    payload = {
        "action_kind": action_kind,
        "target_item_id": normalized_item_id,
        payload_field_name: normalized_value,
    }
    action_id = _deterministic_action_id(payload)
    created_at = utc_now()

    with connect(db_path) as connection:
        row = _fetch_action_row(connection, action_id)
        if row is None:
            connection.execute(
                """
                INSERT INTO action_queue (
                    id, item_id, action_type, payload_json, status, priority,
                    scheduled_at, claimed_at, completed_at, error_message, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    action_id,
                    queued_item_id,
                    action_kind,
                    _canonical_json(payload),
                    _ACTION_STATUS_QUEUED,
                    0,
                    None,
                    None,
                    None,
                    None,
                    created_at,
                    created_at,
                ),
            )
            connection.commit()
            row = _fetch_action_row(connection, action_id)
            assert row is not None, "action enqueue failed unexpectedly"

    return _row_to_action_result(row, evidence_id=None, evidence_written=False)


def _claim_record_operator_action(
    db_path: Path | str,
    action_id: str | None,
    *,
    action_kind: str,
) -> dict[str, Any]:
    bootstrap_db(db_path)
    normalized_action_id = _normalize_required_text(action_id, field_name="action_id")
    updated_at = utc_now()

    with connect(db_path) as connection:
        row = _fetch_action_row(connection, normalized_action_id)
        if row is None:
            raise KeyError(f"unknown action_id: {normalized_action_id}")

        if row["action_type"] != action_kind:
            raise ValidationError(f"wrong action kind: expected {action_kind}, got {row['action_type']}")

        if row["status"] == _ACTION_STATUS_QUEUED:
            connection.execute(
                """
                UPDATE action_queue
                SET status = ?, claimed_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (_ACTION_STATUS_CLAIMED, updated_at, updated_at, normalized_action_id),
            )
            connection.commit()
            row = _fetch_action_row(connection, normalized_action_id)
            assert row is not None, "action claim failed unexpectedly"

    return _row_to_action_result(row, evidence_id=None, evidence_written=False)


def _execute_record_operator_action(
    db_path: Path | str,
    action_id: str | None,
    *,
    action_kind: str,
    payload_field_name: str,
    outcome: str,
    evidence_uri: str,
    actor: str | None = None,
) -> dict[str, Any]:
    bootstrap_db(db_path)
    normalized_action_id = _normalize_required_text(action_id, field_name="action_id")
    updated_at = utc_now()
    repo = ItemRepository(db_path)

    with connect(db_path) as connection:
        row = _fetch_action_row(connection, normalized_action_id)
        if row is None:
            raise KeyError(f"unknown action_id: {normalized_action_id}")

        if row["action_type"] != action_kind:
            raise ValidationError(f"wrong action kind: expected {action_kind}, got {row['action_type']}")

        if row["status"] in {_ACTION_STATUS_COMPLETED, _ACTION_STATUS_FAILED}:
            evidence_id = _existing_action_evidence_id(
                connection,
                row,
                action_kind=action_kind,
                payload_field_name=payload_field_name,
                outcome=outcome,
                evidence_uri=evidence_uri,
            )
            return _row_to_action_result(
                row,
                evidence_id=evidence_id,
                evidence_written=False,
            )

        if row["status"] != _ACTION_STATUS_CLAIMED:
            raise ValidationError(f"{action_kind} actions must be claimed before execution")

        try:
            payload = _decode_action_payload(row["payload_json"])
        except json.JSONDecodeError as exc:
            error_message = f"malformed action payload: {exc}"
            connection.execute(
                """
                UPDATE action_queue
                SET status = ?, completed_at = ?, error_message = ?, updated_at = ?
                WHERE id = ?
                """,
                (_ACTION_STATUS_FAILED, updated_at, error_message, updated_at, normalized_action_id),
            )
            connection.commit()
            row = _fetch_action_row(connection, normalized_action_id)
            assert row is not None, "failed action update unexpectedly missing"
            return _row_to_action_result(
                row,
                evidence_id=None,
                evidence_written=False,
                error_message=error_message,
            )
        except ValidationError as exc:
            error_message = f"invalid action payload: {exc}"
            connection.execute(
                """
                UPDATE action_queue
                SET status = ?, completed_at = ?, error_message = ?, updated_at = ?
                WHERE id = ?
                """,
                (_ACTION_STATUS_FAILED, updated_at, error_message, updated_at, normalized_action_id),
            )
            connection.commit()
            row = _fetch_action_row(connection, normalized_action_id)
            assert row is not None, "failed action update unexpectedly missing"
            return _row_to_action_result(
                row,
                evidence_id=None,
                evidence_written=False,
                error_message=error_message,
            )
        try:
            target_item_id = _normalize_required_text(payload.get("target_item_id"), field_name="target_item_id")
            value = _normalize_required_text(payload.get(payload_field_name), field_name=payload_field_name)
        except ValidationError as exc:
            error_message = f"invalid action payload: {exc}"
            connection.execute(
                """
                UPDATE action_queue
                SET status = ?, completed_at = ?, error_message = ?, updated_at = ?
                WHERE id = ?
                """,
                (_ACTION_STATUS_FAILED, updated_at, error_message, updated_at, normalized_action_id),
            )
            connection.commit()
            row = _fetch_action_row(connection, normalized_action_id)
            assert row is not None, "failed action update unexpectedly missing"
            return _row_to_action_result(
                row,
                evidence_id=None,
                evidence_written=False,
                error_message=error_message,
            )
        item = repo.get_item(target_item_id)
        if item is None:
            error_message = f"unknown target_item_id: {target_item_id}"
            connection.execute(
                """
                UPDATE action_queue
                SET status = ?, completed_at = ?, error_message = ?, updated_at = ?
                WHERE id = ?
                """,
                (_ACTION_STATUS_FAILED, updated_at, error_message, updated_at, normalized_action_id),
            )
            connection.commit()
            row = _fetch_action_row(connection, normalized_action_id)
            assert row is not None, "failed action update unexpectedly missing"
            return _row_to_action_result(
                row,
                evidence_id=None,
                evidence_written=False,
                error_message=error_message,
            )

        evidence_text = _canonical_json(
            {
                "action_id": normalized_action_id,
                "action_kind": action_kind,
                payload_field_name: value,
                "outcome": outcome,
                "target_item_id": target_item_id,
            }
        )
        evidence_row = connection.execute(
            """
            SELECT id
            FROM evidence
            WHERE item_id = ? AND evidence_uri = ? AND created_by = ? AND evidence_text = ?
            ORDER BY created_at ASC, id ASC
            LIMIT 1
            """,
            (target_item_id, evidence_uri, ACTION_CREATED_BY, evidence_text),
        ).fetchone()

        evidence_written = False
        if evidence_row is None:
            evidence_id = new_id("evidence")
            created_at = updated_at
            connection.execute(
                """
                INSERT INTO evidence (
                    id, item_id, evidence_text, evidence_uri, created_by, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence_id,
                    target_item_id,
                    evidence_text,
                    evidence_uri,
                    ACTION_CREATED_BY,
                    created_at,
                ),
            )
            append_event(
                connection,
                event_type="item.evidence_added",
                payload={
                    "item_id": target_item_id,
                    "evidence_id": evidence_id,
                    "evidence_text": evidence_text,
                    "evidence_uri": evidence_uri,
                    "created_by": ACTION_CREATED_BY,
                },
                item_id=target_item_id,
                actor=actor or ACTION_CREATED_BY,
                created_at=created_at,
            )
            evidence_written = True
        else:
            evidence_id = evidence_row["id"]

        connection.execute(
            """
            UPDATE action_queue
            SET status = ?, completed_at = ?, error_message = NULL, updated_at = ?
            WHERE id = ?
            """,
            (_ACTION_STATUS_COMPLETED, updated_at, updated_at, normalized_action_id),
        )
        connection.commit()
        row = _fetch_action_row(connection, normalized_action_id)
        assert row is not None, "completed action update unexpectedly missing"

    return _row_to_action_result(
        row,
        evidence_id=evidence_id,
        evidence_written=evidence_written,
    )


def _row_to_action_result(
    row: sqlite3.Row,
    *,
    evidence_id: str | None,
    evidence_written: bool,
    error_message: str | None = None,
) -> dict[str, Any]:
    result = {
        "action_id": row["id"],
        "item_id": row["item_id"],
        "action_type": row["action_type"],
        "payload_json": row["payload_json"],
        "status": row["status"],
        "priority": row["priority"],
        "scheduled_at": row["scheduled_at"],
        "claimed_at": row["claimed_at"],
        "completed_at": row["completed_at"],
        "error_message": error_message if error_message is not None else row["error_message"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "evidence_id": evidence_id,
        "evidence_written": evidence_written,
    }
    return result


def _fetch_action_row(connection: sqlite3.Connection, action_id: str) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT id, item_id, action_type, payload_json, status, priority,
               scheduled_at, claimed_at, completed_at, error_message,
               created_at, updated_at
        FROM action_queue
        WHERE id = ?
        """,
        (action_id,),
    ).fetchone()


def _existing_action_evidence_id(
    connection: sqlite3.Connection,
    row: sqlite3.Row,
    *,
    action_kind: str,
    payload_field_name: str,
    outcome: str,
    evidence_uri: str,
) -> str | None:
    try:
        payload = _decode_action_payload(row["payload_json"])
        evidence_text = _canonical_json(
            {
                "action_id": row["id"],
                "action_kind": action_kind,
                payload_field_name: _normalize_required_text(payload.get(payload_field_name), field_name=payload_field_name),
                "outcome": outcome,
                "target_item_id": _normalize_required_text(payload.get("target_item_id"), field_name="target_item_id"),
            }
        )
    except (json.JSONDecodeError, ValidationError):
        return None
    evidence_row = connection.execute(
        """
        SELECT id
        FROM evidence
        WHERE item_id = ? AND evidence_uri = ? AND created_by = ? AND evidence_text = ?
        ORDER BY created_at ASC, id ASC
        LIMIT 1
        """,
        (row["item_id"], evidence_uri, ACTION_CREATED_BY, evidence_text),
    ).fetchone()
    return evidence_row["id"] if evidence_row is not None else None


def _deterministic_action_id(payload: dict[str, Any]) -> str:
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return f"action_{digest}"


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _decode_action_payload(payload_json: str) -> dict[str, Any]:
    payload = json.loads(payload_json)
    if not isinstance(payload, dict):
        raise ValidationError("action payload must be a JSON object")
    return payload


def _normalize_required_text(value: Any, *, field_name: str) -> str:
    if value is None:
        raise ValidationError(f"{field_name} is required")
    normalized = str(value).strip()
    if not normalized:
        raise ValidationError(f"{field_name} must not be empty or whitespace-only")
    return normalized
