from __future__ import annotations

# DEPRECATED: 2026-05-14, no active CLI callers found in audit. Slated for review in 1.x.

import json
from pathlib import Path
from typing import Any, Mapping

from .repository import ValidationError
from .resume_recovery_runtime import (
    complete_resume_candidate,
    register_resume_candidate,
    register_resume_session,
    select_resume_candidate,
)
from .runtime_ownership import (
    claim_runtime_ownership,
    register_runtime_ownership,
    release_runtime_ownership,
)
from .storage import DB_PATH, connect


def start_owned_recovery_lifecycle(
    db_path: Path | str = DB_PATH,
    *,
    item_id: str,
    owner: str,
    ownership_metadata: Mapping[str, Any],
    session_key: str,
    session_metadata: Mapping[str, Any] | None,
    candidate_score: float,
    candidate_reason: Mapping[str, Any],
) -> dict[str, Any]:
    registration = register_runtime_ownership(
        db_path,
        item_id,
        owner=owner,
        metadata=dict(ownership_metadata),
    )
    claimed = claim_runtime_ownership(db_path, registration["ownership_id"], owner=owner)

    normalized_session_metadata = _normalize_mapping(session_metadata, field_name="session_metadata")
    session_metadata_payload = {
        **normalized_session_metadata,
        "phase7a_item_id": item_id,
        "phase7a_ownership_id": registration["ownership_id"],
        "phase7a_owner": owner,
    }
    session = register_resume_session(
        db_path,
        session_key=session_key,
        metadata=session_metadata_payload,
    )
    candidate = register_resume_candidate(
        db_path,
        item_id=item_id,
        score=candidate_score,
        reason=dict(candidate_reason),
    )
    selected = select_resume_candidate(
        db_path,
        candidate["candidate_id"],
        session_id=session["session_id"],
    )

    _assert_connected_same_item(
        db_path,
        ownership_id=registration["ownership_id"],
        session_id=session["session_id"],
        candidate_id=candidate["candidate_id"],
    )

    return {
        "ownership_id": registration["ownership_id"],
        "ownership_status": claimed["status"],
        "session_id": session["session_id"],
        "candidate_id": candidate["candidate_id"],
        "recovery_status": selected["status"],
    }


def finalize_owned_recovery_lifecycle(
    db_path: Path | str = DB_PATH,
    *,
    ownership_id: str,
    session_id: str,
    candidate_id: str,
    owner: str,
) -> dict[str, Any]:
    _assert_connected_same_item(
        db_path,
        ownership_id=ownership_id,
        session_id=session_id,
        candidate_id=candidate_id,
    )

    recovery = complete_resume_candidate(
        db_path,
        candidate_id,
        session_id=session_id,
        terminal_status="dismissed",
    )

    if recovery["status"] != "dismissed":
        ownership = claim_runtime_ownership(db_path, ownership_id, owner=owner)
        return {
            "ownership_id": ownership_id,
            "ownership_status": ownership["status"],
            "ownership_evidence_id": None,
            "ownership_evidence_written": False,
            "session_id": session_id,
            "candidate_id": candidate_id,
            "recovery_status": recovery["status"],
            "recovery_evidence_id": recovery["evidence_id"],
            "recovery_evidence_written": recovery["evidence_written"],
            "error_message": recovery["error_message"],
        }

    ownership = release_runtime_ownership(db_path, ownership_id, owner=owner)
    return {
        "ownership_id": ownership_id,
        "ownership_status": ownership["status"],
        "ownership_evidence_id": ownership["evidence_id"],
        "ownership_evidence_written": ownership["evidence_written"],
        "session_id": session_id,
        "candidate_id": candidate_id,
        "recovery_status": recovery["status"],
        "recovery_evidence_id": recovery["evidence_id"],
        "recovery_evidence_written": recovery["evidence_written"],
        "error_message": ownership["error_message"],
    }


def _assert_connected_same_item(
    db_path: Path | str,
    *,
    ownership_id: str,
    session_id: str,
    candidate_id: str,
) -> None:
    with connect(db_path) as connection:
        ownership_row = connection.execute(
            "SELECT id, item_id FROM action_queue WHERE id = ?",
            (ownership_id,),
        ).fetchone()
        if ownership_row is None:
            raise KeyError(f"unknown ownership_id: {ownership_id}")

        session_row = connection.execute(
            "SELECT id, metadata_json FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if session_row is None:
            raise KeyError(f"unknown session_id: {session_id}")

        candidate_row = connection.execute(
            "SELECT id, item_id FROM resume_candidates WHERE id = ?",
            (candidate_id,),
        ).fetchone()
        if candidate_row is None:
            raise KeyError(f"unknown candidate_id: {candidate_id}")

    session_metadata = _decode_session_metadata(session_row["metadata_json"])
    session_item_id = session_metadata.get("phase7a_item_id")
    session_ownership_id = session_metadata.get("phase7a_ownership_id")
    selected_candidate_id = session_metadata.get("selected_candidate_id")
    if session_item_id != ownership_row["item_id"]:
        raise ValidationError("connected lifecycle requires same item across ownership and recovery session")
    if session_ownership_id != ownership_id:
        raise ValidationError("recovery session is not bound to the supplied ownership")
    if candidate_row["item_id"] != ownership_row["item_id"]:
        raise ValidationError("connected lifecycle requires candidate item to match ownership item")
    if selected_candidate_id != candidate_id:
        raise ValidationError("recovery session has not selected the supplied candidate")


def _normalize_mapping(metadata: Mapping[str, Any] | None, *, field_name: str) -> dict[str, Any]:
    if metadata is None:
        return {}
    if not isinstance(metadata, Mapping):
        raise ValidationError(f"{field_name} must be a mapping")
    return {str(key): value for key, value in metadata.items()}


def _decode_session_metadata(metadata_json: str | None) -> dict[str, Any]:
    if not metadata_json:
        return {}
    try:
        payload = json.loads(metadata_json)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"invalid session metadata: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValidationError("session metadata must be a JSON object")
    return payload
