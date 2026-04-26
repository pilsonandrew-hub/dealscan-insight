from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ace.repository import ItemRepository, ValidationError
from ace.storage import DB_PATH, connect, new_id, utc_now

RECOVERY_CREATED_BY = "ace.phase3b.resume_recovery_runtime"
RECOVERY_EVIDENCE_URI = "ace://phase3b/recovery-outcome"


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _require_nonblank(value: str | None, field: str) -> str:
    if value is None:
        raise ValidationError(f"{field} is required")
    normalized = str(value).strip()
    if not normalized:
        raise ValidationError(f"{field} is required")
    return normalized


def _normalize_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if metadata is None:
        return {}
    if not isinstance(metadata, dict):
        raise ValidationError("metadata must be a mapping")
    return metadata


def _normalize_reason(reason: dict[str, Any] | None) -> dict[str, Any]:
    if reason is None:
        raise ValidationError("reason is required")
    if not isinstance(reason, dict):
        raise ValidationError("reason must be a mapping")
    return reason


def register_resume_session(db_path: str | Path = DB_PATH, *, session_key: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    normalized_session_key = _require_nonblank(session_key, "session_key")
    normalized_metadata = _normalize_metadata(metadata)
    metadata_json = _canonical_json(normalized_metadata)
    with connect(db_path) as connection:
        existing = connection.execute(
            "SELECT id, session_key, status, metadata_json, started_at, last_seen_at, ended_at FROM sessions WHERE session_key = ?",
            (normalized_session_key,),
        ).fetchone()
        if existing is not None:
            return {
                "session_id": existing["id"],
                "session_key": existing["session_key"],
                "status": existing["status"],
                "metadata_json": existing["metadata_json"],
                "started_at": existing["started_at"],
                "last_seen_at": existing["last_seen_at"],
                "ended_at": existing["ended_at"],
                "created": False,
            }
        session_id = new_id("session")
        now = utc_now()
        connection.execute(
            "INSERT INTO sessions (id, session_key, status, metadata_json, started_at, last_seen_at, ended_at) VALUES (?, ?, ?, ?, ?, ?, NULL)",
            (session_id, normalized_session_key, "registered", metadata_json, now, now),
        )
        connection.commit()
        return {
            "session_id": session_id,
            "session_key": normalized_session_key,
            "status": "registered",
            "metadata_json": metadata_json,
            "started_at": now,
            "last_seen_at": now,
            "ended_at": None,
            "created": True,
        }


def register_resume_candidate(
    db_path: str | Path = DB_PATH,
    *,
    item_id: str,
    score: float,
    reason: dict[str, Any] | None,
) -> dict[str, Any]:
    normalized_item_id = _require_nonblank(item_id, "item_id")
    normalized_reason = _normalize_reason(reason)
    reason_json = _canonical_json(normalized_reason)
    with connect(db_path) as connection:
        existing = connection.execute(
            "SELECT id, item_id, score, reason_json, generated_at, sweep_run_id FROM resume_candidates WHERE item_id = ? AND score = ? AND reason_json = ?",
            (normalized_item_id, score, reason_json),
        ).fetchone()
        if existing is not None:
            return {
                "candidate_id": existing["id"],
                "item_id": existing["item_id"],
                "score": existing["score"],
                "reason_json": existing["reason_json"],
                "generated_at": existing["generated_at"],
                "sweep_run_id": existing["sweep_run_id"],
                "created": False,
            }
        candidate_id = new_id("resume")
        now = utc_now()
        connection.execute(
            "INSERT INTO resume_candidates (id, item_id, score, reason_json, generated_at, sweep_run_id) VALUES (?, ?, ?, ?, ?, NULL)",
            (candidate_id, normalized_item_id, score, reason_json, now),
        )
        connection.commit()
        return {
            "candidate_id": candidate_id,
            "item_id": normalized_item_id,
            "score": score,
            "reason_json": reason_json,
            "generated_at": now,
            "sweep_run_id": None,
            "created": True,
        }


def select_resume_candidate(db_path: str | Path, candidate_id: str, *, session_id: str) -> dict[str, Any]:
    normalized_candidate_id = _require_nonblank(candidate_id, "candidate_id")
    normalized_session_id = _require_nonblank(session_id, "session_id")
    with connect(db_path) as connection:
        session_row = connection.execute(
            "SELECT id, session_key, status, metadata_json, started_at, last_seen_at, ended_at FROM sessions WHERE id = ?",
            (normalized_session_id,),
        ).fetchone()
        if session_row is None:
            raise KeyError(f"unknown session_id: {normalized_session_id}")
        candidate_row = connection.execute(
            "SELECT id, item_id, score, reason_json, generated_at, sweep_run_id FROM resume_candidates WHERE id = ?",
            (normalized_candidate_id,),
        ).fetchone()
        if candidate_row is None:
            raise KeyError(f"unknown candidate_id: {normalized_candidate_id}")
        metadata = json.loads(session_row["metadata_json"] or "{}")
        selected_candidate_id = metadata.get("selected_candidate_id")
        if selected_candidate_id is not None and selected_candidate_id != normalized_candidate_id:
            raise ValidationError("session already selected a different candidate")
        metadata["selected_candidate_id"] = normalized_candidate_id
        metadata_json = _canonical_json(metadata)
        now = utc_now()
        connection.execute(
            "UPDATE sessions SET status = ?, metadata_json = ?, last_seen_at = ? WHERE id = ?",
            ("selected", metadata_json, now, normalized_session_id),
        )
        connection.commit()
        return {
            "candidate_id": candidate_row["id"],
            "item_id": candidate_row["item_id"],
            "score": candidate_row["score"],
            "reason_json": candidate_row["reason_json"],
            "generated_at": candidate_row["generated_at"],
            "session_id": normalized_session_id,
            "status": "selected",
            "created": False,
        }


def _existing_recovery_evidence_id(repo: ItemRepository, *, item_id: str, evidence_text: str) -> str | None:
    with connect(repo.db_path) as connection:
        row = connection.execute(
            "SELECT id FROM evidence WHERE item_id = ? AND evidence_uri = ? AND created_by = ? AND evidence_text = ? ORDER BY created_at ASC, id ASC LIMIT 1",
            (item_id, RECOVERY_EVIDENCE_URI, RECOVERY_CREATED_BY, evidence_text),
        ).fetchone()
    return None if row is None else row["id"]


def complete_resume_candidate(
    db_path: str | Path,
    candidate_id: str,
    *,
    session_id: str,
    terminal_status: str,
) -> dict[str, Any]:
    normalized_candidate_id = _require_nonblank(candidate_id, "candidate_id")
    normalized_session_id = _require_nonblank(session_id, "session_id")
    normalized_terminal_status = _require_nonblank(terminal_status, "terminal_status")
    if normalized_terminal_status != "dismissed":
        raise ValidationError("terminal_status must be dismissed")

    repo = ItemRepository(db_path)
    with connect(db_path) as connection:
        session_row = connection.execute(
            "SELECT id, session_key, status, metadata_json, started_at, last_seen_at, ended_at FROM sessions WHERE id = ?",
            (normalized_session_id,),
        ).fetchone()
        if session_row is None:
            raise KeyError(f"unknown session_id: {normalized_session_id}")
        candidate_row = connection.execute(
            "SELECT id, item_id, score, reason_json, generated_at, sweep_run_id FROM resume_candidates WHERE id = ?",
            (normalized_candidate_id,),
        ).fetchone()
        if candidate_row is None:
            raise KeyError(f"unknown candidate_id: {normalized_candidate_id}")

        metadata = json.loads(session_row["metadata_json"] or "{}")
        selected_candidate_id = metadata.get("selected_candidate_id")
        if selected_candidate_id != normalized_candidate_id:
            raise ValidationError("session has not selected this candidate")

        item_id = candidate_row["item_id"]
        now = utc_now()
        evidence_text = _canonical_json(
            {
                "candidate_id": normalized_candidate_id,
                "item_id": item_id,
                "outcome": "resume_recovery_dismissed",
                "session_id": normalized_session_id,
                "session_key": session_row["session_key"],
                "terminal_status": normalized_terminal_status,
            }
        )

        if session_row["status"] == normalized_terminal_status:
            evidence_id = _existing_recovery_evidence_id(repo, item_id=item_id, evidence_text=evidence_text)
            return {
                "candidate_id": normalized_candidate_id,
                "session_id": normalized_session_id,
                "status": normalized_terminal_status,
                "evidence_id": evidence_id,
                "evidence_written": False,
                "error_message": None,
            }
        if session_row["status"] == "failed":
            return {
                "candidate_id": normalized_candidate_id,
                "session_id": normalized_session_id,
                "status": "failed",
                "evidence_id": None,
                "evidence_written": False,
                "error_message": metadata.get("error_message"),
            }

        item = repo.get_item(item_id)
        if item is None:
            error_message = f"stale resume target missing item_id: {item_id}"
            metadata["error_message"] = error_message
            connection.execute(
                "UPDATE sessions SET status = ?, metadata_json = ?, last_seen_at = ?, ended_at = ? WHERE id = ?",
                ("failed", _canonical_json(metadata), now, now, normalized_session_id),
            )
            connection.commit()
            return {
                "candidate_id": normalized_candidate_id,
                "session_id": normalized_session_id,
                "status": "failed",
                "evidence_id": None,
                "evidence_written": False,
                "error_message": error_message,
            }

        existing_evidence_id = _existing_recovery_evidence_id(repo, item_id=item_id, evidence_text=evidence_text)
        evidence_written = False
        if existing_evidence_id is None:
            repo.add_evidence(
                item_id,
                evidence_text=evidence_text,
                evidence_uri=RECOVERY_EVIDENCE_URI,
                created_by=RECOVERY_CREATED_BY,
            )
            existing_evidence_id = _existing_recovery_evidence_id(repo, item_id=item_id, evidence_text=evidence_text)
            evidence_written = True

        connection.execute(
            "UPDATE sessions SET status = ?, metadata_json = ?, last_seen_at = ?, ended_at = ? WHERE id = ?",
            (normalized_terminal_status, _canonical_json(metadata), now, now, normalized_session_id),
        )
        connection.commit()
        return {
            "candidate_id": normalized_candidate_id,
            "session_id": normalized_session_id,
            "status": normalized_terminal_status,
            "evidence_id": existing_evidence_id,
            "evidence_written": evidence_written,
            "error_message": None,
        }
