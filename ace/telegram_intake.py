from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .autonomy_lane import mark_item_autonomy_eligible
from .repository import ItemRepository
from .storage import DB_PATH
from .telegram_parser import parse_telegram_message


TELEGRAM_DIRECT_SOURCE = "telegram/direct"
TELEGRAM_INTAKE_ACTOR = "ace.telegram_intake"
TELEGRAM_PARSER_ACTOR = "ace.telegram_parser"
TELEGRAM_SOURCE_EVIDENCE_URI = "ace://telegram/intake-source"
TELEGRAM_PARSER_EVIDENCE_URI = "ace://telegram/parser-decision"
TELEGRAM_DUPLICATE_EVIDENCE_URI = "ace://telegram/duplicate-direct-work"

_COALESCE_STATES = {"TRIAGE", "APPROVED", "CLAIMED_DONE", "VERIFIED_DONE"}


def _semantic_direct_work_key(text: str) -> str:
    normalized = " ".join(text.lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _normalize_required_text(value: str | None, *, field_name: str) -> str:
    if value is None:
        raise ValueError(f"{field_name} is required")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} is required")
    return normalized


def _canonical_source_session(chat_id: str, message_id: str) -> str:
    return f"telegram:{chat_id}:{message_id}"


def _find_existing_semantic_direct_work(repo: ItemRepository, *, text: str) -> Any | None:
    semantic_key = _semantic_direct_work_key(text)
    candidates = [
        item for item in repo.list_items()
        if item.source == TELEGRAM_DIRECT_SOURCE and item.state in _COALESCE_STATES
    ]
    for item in reversed(candidates):
        for event in repo.list_item_events(item.id, event_type="item.created", limit=1):
            if event.payload_json is None:
                continue
            try:
                payload = json.loads(event.payload_json)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            if payload.get("semantic_direct_work_key") == semantic_key:
                return item
    return None


def intake_inbound_telegram_work(
    db_path: Path | str = DB_PATH,
    *,
    chat_id: str,
    message_id: str,
    text: str,
    received_at: str,
    sender_id: str | None = None,
    sender_name: str | None = None,
    actor: str = TELEGRAM_INTAKE_ACTOR,
) -> dict[str, Any]:
    normalized_chat_id = _normalize_required_text(chat_id, field_name="chat_id")
    normalized_message_id = _normalize_required_text(message_id, field_name="message_id")
    normalized_received_at = _normalize_required_text(received_at, field_name="received_at")
    normalized_text = "" if text is None else text.strip()

    parse_result = parse_telegram_message(
        normalized_text,
        chat_id=normalized_chat_id,
        message_id=normalized_message_id,
        received_at=normalized_received_at,
    )
    source_session = _canonical_source_session(normalized_chat_id, normalized_message_id)

    if not parse_result.actionable:
        return {
            "actionable": False,
            "created": False,
            "classification": parse_result.classification,
            "parser_rule": parse_result.parser_rule,
            "parser_reason": parse_result.parser_reason,
            "source_session": source_session,
        }

    repo = ItemRepository(db_path)
    existing = repo.get_item_by_source_and_session(TELEGRAM_DIRECT_SOURCE, source_session)
    semantic_existing = None if existing is not None else _find_existing_semantic_direct_work(
        repo,
        text=parse_result.source_text,
    )
    created = False

    if existing is None:
        if semantic_existing is not None:
            item = semantic_existing
        else:
            item = repo.create_item(
                item_type="work",
                title=parse_result.title or "Telegram direct work",
                description=parse_result.description,
                state="TRIAGE",
                source=TELEGRAM_DIRECT_SOURCE,
                source_session=source_session,
                actor=actor,
                created_payload_extra={
                    "source_message_text": parse_result.source_text,
                    "source_message_id": parse_result.source_message_id,
                    "source_chat_id": parse_result.source_chat_id,
                    "source_received_at": parse_result.source_received_at,
                    "semantic_direct_work_key": _semantic_direct_work_key(parse_result.source_text),
                    "parser_rule": parse_result.parser_rule,
                    "parser_reason": parse_result.parser_reason,
                    "autonomy_eligible": parse_result.autonomy_eligible,
                    "autonomy_policy_reason": parse_result.autonomy_policy_reason,
                    "intake_actor": actor,
                    "sender_id": sender_id.strip() if isinstance(sender_id, str) and sender_id.strip() else None,
                    "sender_name": sender_name.strip() if isinstance(sender_name, str) and sender_name.strip() else None,
                },
            )
            created = True
    else:
        item = existing

    duplicate_of_existing = semantic_existing is not None

    source_evidence_id = repo.add_evidence(
        item.id,
        evidence_text=(
            "Inbound telegram source captured for direct-work intake. "
            f"chat_id={parse_result.source_chat_id} message_id={parse_result.source_message_id} "
            f"received_at={parse_result.source_received_at} text={parse_result.source_text}"
        ),
        evidence_uri=TELEGRAM_SOURCE_EVIDENCE_URI,
        created_by=TELEGRAM_INTAKE_ACTOR,
        actor=actor,
    )
    parser_evidence_id = repo.add_evidence(
        item.id,
        evidence_text=(
            "Telegram parser decision recorded for direct-work intake. "
            f"classification={parse_result.classification} rule={parse_result.parser_rule} "
            f"reason={parse_result.parser_reason}"
        ),
        evidence_uri=TELEGRAM_PARSER_EVIDENCE_URI,
        created_by=TELEGRAM_PARSER_ACTOR,
        actor=TELEGRAM_PARSER_ACTOR,
    )
    eligibility_evidence_id = None
    if parse_result.autonomy_eligible:
        eligibility_evidence_id = mark_item_autonomy_eligible(
            db_path,
            item.id,
            reason=parse_result.autonomy_policy_reason or parse_result.parser_reason,
            actor=TELEGRAM_PARSER_ACTOR,
        )
    duplicate_evidence_id = None
    if duplicate_of_existing:
        duplicate_evidence_id = repo.add_evidence(
            item.id,
            evidence_text=(
                "Duplicate semantic Telegram direct-work message coalesced into existing governed item. "
                f"duplicate_source_session={source_session} chat_id={parse_result.source_chat_id} "
                f"message_id={parse_result.source_message_id} received_at={parse_result.source_received_at}"
            ),
            evidence_uri=TELEGRAM_DUPLICATE_EVIDENCE_URI,
            created_by=TELEGRAM_INTAKE_ACTOR,
            actor=actor,
        )

    return {
        "actionable": True,
        "created": created,
        "coalesced": duplicate_of_existing,
        "item_id": item.id,
        "source_session": source_session,
        "source_evidence_id": source_evidence_id,
        "parser_evidence_id": parser_evidence_id,
        "eligibility_evidence_id": eligibility_evidence_id,
        "autonomy_eligible": parse_result.autonomy_eligible,
        "autonomy_policy_reason": parse_result.autonomy_policy_reason,
        "duplicate_evidence_id": duplicate_evidence_id,
    }
