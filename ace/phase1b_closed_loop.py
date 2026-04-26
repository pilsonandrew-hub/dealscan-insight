from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .open_loops_ingest import (
    DEFAULT_SOURCE_LABEL,
    DEFAULT_SOURCE_PATH,
    OpenLoopParseError,
    OpenLoopSchemaError,
    UnsupportedOpenLoopStateError,
    _build_source_session,
    _canonical_digest,
    _load_payload,
    _normalize_source_item,
    ingest_continuity_open_loops,
)
from .repository import Item, ItemRepository, ValidationError
from .storage import DB_PATH, connect


DECISION_CREATED_BY = "ace.phase1b_closed_loop"
DECISION_EVIDENCE_URI = "ace://phase1b/decision"
DECISION_RULE_VERSION = "phase1b.open-loop.v1"


class Phase1BClosedLoopIngestError(ValueError):
    """Raised when the phase1b closed loop cannot proceed."""


class Phase1BClosedLoopParseError(Phase1BClosedLoopIngestError):
    """Raised when the source file cannot be parsed as JSON."""


class Phase1BClosedLoopSchemaError(Phase1BClosedLoopIngestError):
    """Raised when the source shape does not match the narrow contract."""


def run_phase1b_closed_loop(
    db_path: Path | str = DB_PATH,
    source_path: Path | str = DEFAULT_SOURCE_PATH,
    *,
    source_label: str = DEFAULT_SOURCE_LABEL,
) -> list[dict[str, Any]]:
    """Run the smallest local-only Phase 1B closed loop on open-loop TRIAGE items."""
    repo = ItemRepository(db_path)

    try:
        ingested_items = ingest_continuity_open_loops(
            db_path,
            source_path=source_path,
            source_label=source_label,
        )
    except OpenLoopParseError as exc:
        raise Phase1BClosedLoopParseError(str(exc)) from exc
    except (OpenLoopSchemaError, UnsupportedOpenLoopStateError) as exc:
        raise Phase1BClosedLoopSchemaError(str(exc)) from exc

    source_rows = _load_open_loop_source_rows(source_path=source_path, source_label=source_label)

    results: list[dict[str, Any]] = []
    for item in ingested_items:
        if item.state != "TRIAGE":
            continue

        source_session = _normalized_source_session(item)
        source_row = _source_row_by_session(source_rows, source_session)
        source_item_id = source_row["id"]
        decision_classification = _decision_classification(source_row["severity"])
        decision_text = _decision_evidence_text(
            decision_classification=decision_classification,
            source_label=source_label,
            source_session=source_session,
            source_item_id=source_item_id,
        )

        evidence_id = _existing_decision_evidence_id(repo, item.id)
        evidence_written = False
        if evidence_id is None:
            evidence_id = repo.add_evidence(
                item.id,
                evidence_text=decision_text,
                evidence_uri=DECISION_EVIDENCE_URI,
                created_by=DECISION_CREATED_BY,
                actor=DECISION_CREATED_BY,
            )
            evidence_written = True

        results.append(
            {
                "item_id": item.id,
                "source_label": source_label,
                "source_item_id": source_item_id,
                "source_session": source_session,
                "decision_classification": decision_classification,
                "evidence_id": evidence_id,
                "evidence_written": evidence_written,
            }
        )

    return results


process_phase1b_closed_loop = run_phase1b_closed_loop


def _load_open_loop_source_rows(
    *,
    source_path: Path | str,
    source_label: str,
) -> dict[str, dict[str, str]]:
    payload = _load_payload(Path(source_path))

    rows: dict[str, dict[str, str]] = {}
    for raw_item in payload["items"]:
        normalized_item = _normalize_source_item(raw_item)
        source_session = _build_source_session(
            source_label=source_label,
            source_item_id=normalized_item["id"],
            canonical_digest=_canonical_digest(normalized_item),
        )
        rows[source_session] = normalized_item
    return rows


def _source_row_by_session(
    rows: Mapping[str, dict[str, str]],
    source_session: str,
) -> dict[str, str]:
    row = rows.get(source_session)
    if row is None:
        raise Phase1BClosedLoopSchemaError(
            f"missing open-loop source row for phase1b item: {source_session}"
        )
    return row


def _normalized_source_session(item: Item) -> str:
    source_session = item.source_session
    if source_session is None:
        raise ValidationError("source_session is required for phase1b closed loop")
    normalized_source_session = source_session.strip()
    if not normalized_source_session:
        raise ValidationError("source_session must not be empty or whitespace-only")
    return normalized_source_session


def _decision_classification(source_severity: str) -> str:
    normalized_severity = source_severity.strip().lower()
    if normalized_severity in {"high", "critical"}:
        return "escalate_for_operator_attention"
    return "track_without_escalation"


def _decision_evidence_text(
    *,
    decision_classification: str,
    source_label: str,
    source_session: str,
    source_item_id: str,
) -> str:
    return json.dumps(
        {
            "decision_classification": decision_classification,
            "decision_rule_version": DECISION_RULE_VERSION,
            "source_label": source_label,
            "source_session": source_session,
            "source_item_id": source_item_id,
        },
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _existing_decision_evidence_id(repo: ItemRepository, item_id: str) -> str | None:
    with connect(repo.db_path) as connection:
        row = connection.execute(
            """
            SELECT id
            FROM evidence
            WHERE item_id = ? AND evidence_uri = ? AND created_by = ?
            ORDER BY created_at ASC, id ASC
            LIMIT 1
            """,
            (item_id, DECISION_EVIDENCE_URI, DECISION_CREATED_BY),
        ).fetchone()
    return row["id"] if row is not None else None
