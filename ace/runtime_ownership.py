from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .repository import ItemRepository, ValidationError
from .storage import DB_PATH, bootstrap_db, connect, utc_now


OWNERSHIP_ACTION_KIND = "register_runtime_ownership"
OWNERSHIP_CREATED_BY = "ace.phase4.runtime_ownership"
OWNERSHIP_EVIDENCE_URI = "ace://phase4/runtime-ownership-outcome"

_OWNERSHIP_STATUS_QUEUED = "queued"
_OWNERSHIP_STATUS_CLAIMED = "claimed"
_OWNERSHIP_STATUS_COMPLETED = "completed"
_OWNERSHIP_STATUS_FAILED = "failed"


def register_runtime_ownership(
    db_path: Path | str = DB_PATH,
    item_id: str | None = None,
    *,
    owner: str,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    bootstrap_db(db_path)
    normalized_item_id = _normalize_required_text(item_id, field_name="item_id")
    normalized_owner = _normalize_required_text(owner, field_name="owner")
    normalized_metadata = _normalize_metadata(metadata)
    ownership_id = _deterministic_ownership_id(normalized_item_id)
    created_at = utc_now()
    payload = {
        "item_id": normalized_item_id,
        "owner": normalized_owner,
        "metadata": normalized_metadata,
    }

    with connect(db_path) as connection:
        row = _fetch_ownership_row(connection, ownership_id)
        if row is not None:
            existing_payload = _decode_ownership_payload(row["payload_json"])
            if _ownership_payload_matches(existing_payload, payload):
                return _row_to_ownership_result(
                    row,
                    evidence_id=_existing_ownership_evidence_id(connection, row),
                    evidence_written=False,
                )
            raise ValidationError(
                f"ownership already registered for item {normalized_item_id} with conflicting owner or metadata"
            )

        repo = ItemRepository(db_path)
        if repo.get_item(normalized_item_id) is None:
            raise KeyError(f"unknown item_id: {normalized_item_id}")

        connection.execute(
            """
            INSERT INTO action_queue (
                id, item_id, action_type, payload_json, status, priority,
                scheduled_at, claimed_at, completed_at, error_message, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ownership_id,
                normalized_item_id,
                OWNERSHIP_ACTION_KIND,
                _canonical_json(payload),
                _OWNERSHIP_STATUS_QUEUED,
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
        row = _fetch_ownership_row(connection, ownership_id)
        assert row is not None, "ownership registration failed unexpectedly"

    return _row_to_ownership_result(row, evidence_id=None, evidence_written=False)


def claim_runtime_ownership(
    db_path: Path | str = DB_PATH,
    ownership_id: str | None = None,
    *,
    owner: str,
) -> dict[str, Any]:
    bootstrap_db(db_path)
    normalized_ownership_id = _normalize_required_text(ownership_id, field_name="ownership_id")
    normalized_owner = _normalize_required_text(owner, field_name="owner")
    claimed_at = utc_now()

    with connect(db_path) as connection:
        row = _fetch_ownership_row(connection, normalized_ownership_id)
        if row is None:
            raise KeyError(f"unknown ownership_id: {normalized_ownership_id}")

        payload = _decode_ownership_payload(row["payload_json"])
        _assert_owner_matches(payload, normalized_owner, ownership_id=normalized_ownership_id)

        if row["status"] == _OWNERSHIP_STATUS_QUEUED:
            connection.execute(
                """
                UPDATE action_queue
                SET status = ?, claimed_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (_OWNERSHIP_STATUS_CLAIMED, claimed_at, claimed_at, normalized_ownership_id),
            )
            connection.commit()
            row = _fetch_ownership_row(connection, normalized_ownership_id)
            assert row is not None, "ownership claim failed unexpectedly"

        return _row_to_ownership_result(row, evidence_id=None, evidence_written=False)


def release_runtime_ownership(
    db_path: Path | str = DB_PATH,
    ownership_id: str | None = None,
    *,
    owner: str,
) -> dict[str, Any]:
    bootstrap_db(db_path)
    normalized_ownership_id = _normalize_required_text(ownership_id, field_name="ownership_id")
    normalized_owner = _normalize_required_text(owner, field_name="owner")
    completed_at = utc_now()
    repo = ItemRepository(db_path)

    with connect(db_path) as connection:
        row = _fetch_ownership_row(connection, normalized_ownership_id)
        if row is None:
            raise KeyError(f"unknown ownership_id: {normalized_ownership_id}")

        payload = _decode_ownership_payload(row["payload_json"])
        _assert_owner_matches(payload, normalized_owner, ownership_id=normalized_ownership_id)

        if row["status"] in {_OWNERSHIP_STATUS_COMPLETED, _OWNERSHIP_STATUS_FAILED}:
            evidence_id = _existing_ownership_evidence_id(connection, row)
            return _row_to_ownership_result(
                row,
                evidence_id=evidence_id,
                evidence_written=False,
                error_message=row["error_message"],
            )

        if row["status"] != _OWNERSHIP_STATUS_CLAIMED:
            raise ValidationError("ownership must be claimed before release")

        item = repo.get_item(row["item_id"])
        if item is None:
            error_message = f"missing target item: {row['item_id']}"
            connection.execute(
                """
                UPDATE action_queue
                SET status = ?, completed_at = ?, error_message = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    _OWNERSHIP_STATUS_FAILED,
                    completed_at,
                    error_message,
                    completed_at,
                    normalized_ownership_id,
                ),
            )
            connection.commit()
            row = _fetch_ownership_row(connection, normalized_ownership_id)
            assert row is not None, "ownership failure update failed unexpectedly"
            return _row_to_ownership_result(
                row,
                evidence_id=None,
                evidence_written=False,
                error_message=error_message,
            )

        evidence_text = _canonical_json(
            {
                "item_id": row["item_id"],
                "metadata": payload["metadata"],
                "outcome": "ownership_released_completed",
                "ownership_id": normalized_ownership_id,
                "owner": normalized_owner,
            }
        )
        evidence_id = _existing_ownership_evidence_id(connection, row)
        evidence_written = evidence_id is None
        if evidence_written:
            repo.add_evidence(
                row["item_id"],
                evidence_text=evidence_text,
                evidence_uri=OWNERSHIP_EVIDENCE_URI,
                created_by=OWNERSHIP_CREATED_BY,
            )
            evidence_id = _existing_ownership_evidence_id(connection, row)
            assert evidence_id is not None, "ownership evidence write failed unexpectedly"

        connection.execute(
            """
            UPDATE action_queue
            SET status = ?, completed_at = ?, error_message = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                _OWNERSHIP_STATUS_COMPLETED,
                completed_at,
                None,
                completed_at,
                normalized_ownership_id,
            ),
        )
        connection.commit()
        row = _fetch_ownership_row(connection, normalized_ownership_id)
        assert row is not None, "ownership completion update failed unexpectedly"

        return _row_to_ownership_result(
            row,
            evidence_id=evidence_id,
            evidence_written=evidence_written,
            error_message=None,
        )


def _fetch_ownership_row(connection: Any, ownership_id: str) -> Any:
    return connection.execute(
        """
        SELECT id, item_id, action_type, payload_json, status, claimed_at, completed_at, error_message
        FROM action_queue
        WHERE id = ?
        """,
        (ownership_id,),
    ).fetchone()


def _row_to_ownership_result(
    row: Any,
    *,
    evidence_id: str | None,
    evidence_written: bool,
    error_message: str | None = None,
) -> dict[str, Any]:
    payload = _decode_ownership_payload(row["payload_json"])
    return {
        "ownership_id": row["id"],
        "item_id": row["item_id"],
        "action_type": row["action_type"],
        "owner": payload["owner"],
        "metadata": payload["metadata"],
        "payload_json": row["payload_json"],
        "status": row["status"],
        "claimed_at": row["claimed_at"],
        "completed_at": row["completed_at"],
        "error_message": error_message if error_message is not None else row["error_message"],
        "evidence_id": evidence_id,
        "evidence_written": evidence_written,
    }


def _existing_ownership_evidence_id(connection: Any, row: Any) -> str | None:
    payload = _decode_ownership_payload(row["payload_json"])
    evidence_text = _canonical_json(
        {
            "item_id": row["item_id"],
            "metadata": payload["metadata"],
            "outcome": "ownership_released_completed",
            "ownership_id": row["id"],
            "owner": payload["owner"],
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
        (row["item_id"], OWNERSHIP_EVIDENCE_URI, OWNERSHIP_CREATED_BY, evidence_text),
    ).fetchone()
    return evidence_row["id"] if evidence_row is not None else None


def _ownership_payload_matches(existing: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    return (
        existing.get("item_id") == expected["item_id"]
        and existing.get("owner") == expected["owner"]
        and existing.get("metadata") == expected["metadata"]
    )


def _assert_owner_matches(payload: Mapping[str, Any], owner: str, *, ownership_id: str) -> None:
    payload_owner = payload.get("owner")
    if payload_owner != owner:
        raise ValidationError(
            f"ownership {ownership_id} is already bound to owner {payload_owner}"
        )


def _decode_ownership_payload(payload_json: str) -> dict[str, Any]:
    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"invalid ownership payload: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValidationError("ownership payload must be a JSON object")
    return payload


def _normalize_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(metadata, Mapping):
        raise ValidationError("metadata must be a JSON object")
    return {str(key): value for key, value in metadata.items()}


def _deterministic_ownership_id(item_id: str) -> str:
    digest = hashlib.sha256(_canonical_json({"item_id": item_id}).encode("utf-8")).hexdigest()
    return f"ownership_{digest}"


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(dict(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _normalize_required_text(value: Any, *, field_name: str) -> str:
    if value is None:
        raise ValidationError(f"{field_name} is required")
    normalized = str(value).strip()
    if not normalized:
        raise ValidationError(f"{field_name} must not be empty or whitespace-only")
    return normalized
