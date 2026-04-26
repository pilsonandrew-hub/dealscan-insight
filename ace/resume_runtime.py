from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .repository import ItemRepository, ValidationError
from .storage import DB_PATH, bootstrap_db, connect, utc_now

RECOVERY_CREATED_BY = "ace.phase3.resume_runtime"
RECOVERY_EVIDENCE_URI = "ace://phase3/recovery-outcome"

_SESSION_STATUS_REGISTERED = "registered"
_SESSION_STATUS_CLAIMED = "claimed"
_SESSION_STATUS_COMPLETED = "completed"
_SESSION_STATUS_FAILED = "failed"


def register_resume_session(
    db_path: Path | str = DB_PATH,
    *,
    session_key: str,
) -> dict[str, Any]:
    bootstrap_db(db_path)
    normalized_session_key = _normalize_required_text(session_key, field_name="session_key")
    session_id = _deterministic_id("session", {"session_key": normalized_session_key})
    now = utc_now()
    metadata_json = _canonical_json({"session_key": normalized_session_key})

    with connect(db_path) as connection:
        row = connection.execute(
            "SELECT id, session_key, status, metadata_json, started_at, last_seen_at, ended_at FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            connection.execute(
                """
                INSERT INTO sessions (id, session_key, status, metadata_json, started_at, last_seen_at, ended_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    normalized_session_key,
                    _SESSION_STATUS_REGISTERED,
                    metadata_json,
                    now,
                    now,
                    None,
                ),
            )
            connection.commit()
            row = connection.execute(
                "SELECT id, session_key, status, metadata_json, started_at, last_seen_at, ended_at FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            assert row is not None, "session registration failed unexpectedly"

    return _row_to_session_result(row)


def register_resume_candidate(
    db_path: Path | str = DB_PATH,
    *,
    item_id: str,
    score: float,
    reason: Mapping[str, Any],
) -> dict[str, Any]:
    bootstrap_db(db_path)
    normalized_item_id = _normalize_required_text(item_id, field_name="item_id")
    normalized_reason = _normalize_reason(reason)
    reason_json = _canonical_json(normalized_reason)
    candidate_id = _deterministic_id(
        "resume",
        {
            "item_id": normalized_item_id,
            "reason": normalized_reason,
            "score": score,
        },
    )
    now = utc_now()

    with connect(db_path) as connection:
        row = connection.execute(
            "SELECT id, item_id, score, reason_json, generated_at, sweep_run_id FROM resume_candidates WHERE id = ?",
            (candidate_id,),
        ).fetchone()
        if row is None:
            connection.execute(
                """
                INSERT INTO resume_candidates (id, item_id, score, reason_json, generated_at, sweep_run_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (candidate_id, normalized_item_id, score, reason_json, now, None),
            )
            connection.commit()
            row = connection.execute(
                "SELECT id, item_id, score, reason_json, generated_at, sweep_run_id FROM resume_candidates WHERE id = ?",
                (candidate_id,),
            ).fetchone()
            assert row is not None, "resume candidate registration failed unexpectedly"

    return _row_to_candidate_result(row, session_id=None, status=None, evidence_id=None, evidence_written=False, error_message=None)


def claim_resume_candidate(
    db_path: Path | str = DB_PATH,
    candidate_id: str | None = None,
    *,
    session_id: str,
) -> dict[str, Any]:
    bootstrap_db(db_path)
    normalized_candidate_id = _normalize_required_text(candidate_id, field_name="candidate_id")
    normalized_session_id = _normalize_required_text(session_id, field_name="session_id")
    now = utc_now()

    with connect(db_path) as connection:
        candidate_row = connection.execute(
            "SELECT id, item_id, score, reason_json, generated_at, sweep_run_id FROM resume_candidates WHERE id = ?",
            (normalized_candidate_id,),
        ).fetchone()
        if candidate_row is None:
            raise KeyError(f"unknown candidate_id: {normalized_candidate_id}")

        session_row = connection.execute(
            "SELECT id, session_key, status, metadata_json, started_at, last_seen_at, ended_at FROM sessions WHERE id = ?",
            (normalized_session_id,),
        ).fetchone()
        if session_row is None:
            raise KeyError(f"unknown session_id: {normalized_session_id}")

        metadata = _decode_session_metadata(session_row["metadata_json"])
        claimed_candidate_id = metadata.get("claimed_candidate_id")
        if claimed_candidate_id is None:
            metadata["claimed_candidate_id"] = normalized_candidate_id
            connection.execute(
                """
                UPDATE sessions
                SET status = ?, metadata_json = ?, last_seen_at = ?, ended_at = ?
                WHERE id = ?
                """,
                (_SESSION_STATUS_CLAIMED, _canonical_json(metadata), now, None, normalized_session_id),
            )
            connection.commit()
            session_row = connection.execute(
                "SELECT id, session_key, status, metadata_json, started_at, last_seen_at, ended_at FROM sessions WHERE id = ?",
                (normalized_session_id,),
            ).fetchone()
            assert session_row is not None, "resume claim update failed unexpectedly"
            metadata = _decode_session_metadata(session_row["metadata_json"])
        elif claimed_candidate_id != normalized_candidate_id:
            raise ValidationError(
                f"session {normalized_session_id} already claimed candidate {claimed_candidate_id}"
            )

    return _row_to_candidate_result(
        candidate_row,
        session_id=normalized_session_id,
        status=_SESSION_STATUS_CLAIMED,
        evidence_id=None,
        evidence_written=False,
        error_message=None,
    )


def complete_resume_candidate(
    db_path: Path | str = DB_PATH,
    candidate_id: str | None = None,
    *,
    session_id: str,
) -> dict[str, Any]:
    bootstrap_db(db_path)
    normalized_candidate_id = _normalize_required_text(candidate_id, field_name="candidate_id")
    normalized_session_id = _normalize_required_text(session_id, field_name="session_id")
    now = utc_now()
    repo = ItemRepository(db_path)

    with connect(db_path) as connection:
        candidate_row = connection.execute(
            "SELECT id, item_id, score, reason_json, generated_at, sweep_run_id FROM resume_candidates WHERE id = ?",
            (normalized_candidate_id,),
        ).fetchone()
        if candidate_row is None:
            raise KeyError(f"unknown candidate_id: {normalized_candidate_id}")

        session_row = connection.execute(
            "SELECT id, session_key, status, metadata_json, started_at, last_seen_at, ended_at FROM sessions WHERE id = ?",
            (normalized_session_id,),
        ).fetchone()
        if session_row is None:
            raise KeyError(f"unknown session_id: {normalized_session_id}")

        metadata = _decode_session_metadata(session_row["metadata_json"])
        claimed_candidate_id = metadata.get("claimed_candidate_id")
        if claimed_candidate_id != normalized_candidate_id:
            raise ValidationError(
                f"session {normalized_session_id} has not claimed candidate {normalized_candidate_id}"
            )

        if session_row["status"] in {_SESSION_STATUS_COMPLETED, _SESSION_STATUS_FAILED}:
            evidence_id = _existing_recovery_evidence_id(connection, candidate_row, session_row)
            return _row_to_candidate_result(
                candidate_row,
                session_id=normalized_session_id,
                status=session_row["status"],
                evidence_id=evidence_id,
                evidence_written=False,
                error_message=metadata.get("error_message"),
            )

        item = repo.get_item(candidate_row["item_id"])
        if item is None:
            error_message = f"missing target item: {candidate_row['item_id']}"
            metadata["error_message"] = error_message
            connection.execute(
                """
                UPDATE sessions
                SET status = ?, metadata_json = ?, last_seen_at = ?, ended_at = ?
                WHERE id = ?
                """,
                (_SESSION_STATUS_FAILED, _canonical_json(metadata), now, now, normalized_session_id),
            )
            connection.commit()
            session_row = connection.execute(
                "SELECT id, session_key, status, metadata_json, started_at, last_seen_at, ended_at FROM sessions WHERE id = ?",
                (normalized_session_id,),
            ).fetchone()
            assert session_row is not None, "resume failure update failed unexpectedly"
            return _row_to_candidate_result(
                candidate_row,
                session_id=normalized_session_id,
                status=_SESSION_STATUS_FAILED,
                evidence_id=None,
                evidence_written=False,
                error_message=error_message,
            )

        evidence_text = _canonical_json(
            {
                "candidate_id": normalized_candidate_id,
                "item_id": candidate_row["item_id"],
                "outcome": "resume_recovery_completed",
                "session_id": normalized_session_id,
                "session_key": session_row["session_key"],
            }
        )
        evidence_id = _existing_recovery_evidence_id(connection, candidate_row, session_row)
        evidence_written = evidence_id is None
        if evidence_written:
            repo.add_evidence(
                candidate_row["item_id"],
                evidence_text=evidence_text,
                evidence_uri=RECOVERY_EVIDENCE_URI,
                created_by=RECOVERY_CREATED_BY,
            )
            evidence_id = _existing_recovery_evidence_id(connection, candidate_row, session_row)
            assert evidence_id is not None, "recovery evidence write failed unexpectedly"

        connection.execute(
            """
            UPDATE sessions
            SET status = ?, metadata_json = ?, last_seen_at = ?, ended_at = ?
            WHERE id = ?
            """,
            (_SESSION_STATUS_COMPLETED, _canonical_json(metadata), now, now, normalized_session_id),
        )
        connection.commit()

        return _row_to_candidate_result(
            candidate_row,
            session_id=normalized_session_id,
            status=_SESSION_STATUS_COMPLETED,
            evidence_id=evidence_id,
            evidence_written=evidence_written,
            error_message=None,
        )


def _row_to_session_result(row: Any) -> dict[str, Any]:
    return {
        "session_id": row["id"],
        "session_key": row["session_key"],
        "status": row["status"],
        "metadata_json": row["metadata_json"],
        "started_at": row["started_at"],
        "last_seen_at": row["last_seen_at"],
        "ended_at": row["ended_at"],
    }


def _row_to_candidate_result(
    row: Any,
    *,
    session_id: str | None,
    status: str | None,
    evidence_id: str | None,
    evidence_written: bool,
    error_message: str | None,
) -> dict[str, Any]:
    return {
        "candidate_id": row["id"],
        "item_id": row["item_id"],
        "score": row["score"],
        "reason_json": row["reason_json"],
        "generated_at": row["generated_at"],
        "sweep_run_id": row["sweep_run_id"],
        "session_id": session_id,
        "status": status,
        "evidence_id": evidence_id,
        "evidence_written": evidence_written,
        "error_message": error_message,
    }


def _existing_recovery_evidence_id(connection: Any, candidate_row: Any, session_row: Any) -> str | None:
    evidence_text = _canonical_json(
        {
            "candidate_id": candidate_row["id"],
            "item_id": candidate_row["item_id"],
            "outcome": "resume_recovery_completed",
            "session_id": session_row["id"],
            "session_key": session_row["session_key"],
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
        (candidate_row["item_id"], RECOVERY_EVIDENCE_URI, RECOVERY_CREATED_BY, evidence_text),
    ).fetchone()
    return evidence_row["id"] if evidence_row is not None else None


def _normalize_reason(reason: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(reason, Mapping):
        raise ValidationError("reason must be a JSON object")
    normalized = {str(key): value for key, value in reason.items()}
    if not normalized:
        raise ValidationError("reason must not be empty")
    return normalized


def _decode_session_metadata(metadata_json: str) -> dict[str, Any]:
    try:
        payload = json.loads(metadata_json)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"invalid session metadata: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValidationError("session metadata must be a JSON object")
    return payload


def _deterministic_id(prefix: str, payload: Mapping[str, Any]) -> str:
    digest = hashlib.sha256(_canonical_json(dict(payload)).encode("utf-8")).hexdigest()
    return f"{prefix}_{digest}"


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(dict(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _normalize_required_text(value: Any, *, field_name: str) -> str:
    if value is None:
        raise ValidationError(f"{field_name} is required")
    normalized = str(value).strip()
    if not normalized:
        raise ValidationError(f"{field_name} must not be empty or whitespace-only")
    return normalized
