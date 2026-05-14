from __future__ import annotations

# DEPRECATED: 2026-05-14, no active CLI callers found in audit. Slated for review in 1.x.

import json
from pathlib import Path
from typing import Any, Mapping

from .pending_promotions_ingest import (
    DEFAULT_SOURCE_LABEL,
    DEFAULT_SOURCE_PATH,
    PendingPromotionParseError,
    PendingPromotionSchemaError,
    _canonical_json,
    _load_payload,
    _normalize_required_text,
    _normalize_source_item,
    ingest_continuity_pending_promotions,
)
from .repository import Item, ItemRepository, ValidationError
from .storage import DB_PATH, connect


DECISION_CREATED_BY = "ace.phase1_closed_loop"
DECISION_EVIDENCE_URI = "ace://phase1/decision"
DECISION_RULE_VERSION = "phase1.manual-test.v1"


def run_phase1_closed_loop(
    db_path: Path | str = DB_PATH,
    source_path: Path | str = DEFAULT_SOURCE_PATH,
    *,
    source_label: str = DEFAULT_SOURCE_LABEL,
) -> list[dict[str, Any]]:
    """Run the smallest local-only Phase 1 closed loop on pending promotions.

    The loop reuses the existing pending-promotions ingest proof, then writes one
    ACE-owned decision evidence row per newly ingested pending item. Replay is
    idempotent because the existing decision evidence row is detected and reused.
    """
    repo = ItemRepository(db_path)
    pending_items = ingest_continuity_pending_promotions(
        db_path,
        source_path=source_path,
        source_label=source_label,
    )

    results: list[dict[str, Any]] = []
    source_rows = _load_pending_source_rows(source_path)

    for item in pending_items:
        source_label_value = _normalized_source_label(item)
        source_item_id, source_session = _parse_source_session(item)
        source_row = _source_row_by_id(source_rows, source_item_id)
        decision_classification = _decision_classification(_normalized_queue_source(source_row))
        decision_text = _decision_evidence_text(
            decision_classification=decision_classification,
            source_label=source_label_value,
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
                "source_label": source_label_value,
                "source_item_id": source_item_id,
                "source_session": source_session,
                "decision_classification": decision_classification,
                "evidence_id": evidence_id,
                "evidence_written": evidence_written,
            }
        )

    return results


process_phase1_closed_loop = run_phase1_closed_loop


def _load_pending_source_rows(source_path: Path | str) -> dict[str, dict[str, str]]:
    source_path = Path(source_path)
    try:
        payload = _load_payload(source_path)
    except (PendingPromotionParseError, PendingPromotionSchemaError):
        raise

    rows: dict[str, dict[str, str]] = {}
    for raw_item in payload["items"]:
        if not isinstance(raw_item, Mapping):
            raise PendingPromotionSchemaError("each pending-promotion item must be a JSON object")

        status = _normalize_required_text(raw_item.get("status"), field_name="status").lower()
        if status != "pending":
            continue

        normalized_item = _normalize_source_item(raw_item)
        rows[normalized_item["id"]] = normalized_item
    return rows


def _source_row_by_id(rows: dict[str, dict[str, str]], source_item_id: str) -> dict[str, str]:
    row = rows.get(source_item_id)
    if row is None:
        raise ValidationError(f"missing pending-promotions source row for phase1 item: {source_item_id}")
    return row


def _normalized_queue_source(source_row: dict[str, str]) -> str:
    return _normalize_required_text(source_row.get("source"), field_name="source")


def _decision_classification(queue_source: str) -> str:
    if queue_source.strip() == "manual-test":
        return "accepted_for_local_followup"
    return "insufficient_context"


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


def _normalized_source_label(item: Item) -> str:
    source_label = item.source
    if source_label is None:
        raise ValidationError("source is required for phase1 closed loop")
    normalized_source_label = source_label.strip()
    if not normalized_source_label:
        raise ValidationError("source must not be empty or whitespace-only")
    return normalized_source_label


def _parse_source_session(item: Item) -> tuple[str, str]:
    source_session = item.source_session
    if source_session is None:
        raise ValidationError("source_session is required for phase1 closed loop")
    normalized_source_session = source_session.strip()
    if not normalized_source_session:
        raise ValidationError("source_session must not be empty or whitespace-only")

    parts = normalized_source_session.split("|", 2)
    if len(parts) != 3 or not all(part.strip() for part in parts):
        raise ValidationError(f"invalid source_session format for phase1 closed loop: {source_session}")
    return parts[1], parts[2]


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
