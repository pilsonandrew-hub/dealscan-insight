from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

from ace.commitment_parser import parse_commitment_message
from ace.repository import ItemRepository, ValidationError
from ace.storage import DB_PATH, STATE_DIR
from ace.telegram_runtime import load_openclaw_session_messages

PROPOSAL_SOURCE = "telegram/commitment-proposal"
PROPOSAL_ACTOR = "ace.propose"
DECISION_LOG_PATH = STATE_DIR / "propose_filter_decisions.jsonl"
EVIDENCE_URI = "ace://telegram/commitment-proposal"


@dataclass(frozen=True)
class ProposalScanRow:
    item_id: str
    title: str
    matched_phrase: str
    parser_rule: str
    source_session: str
    created: bool


def _canonical_source_session(chat_id: str, message_id: str) -> str:
    return f"telegram:{chat_id}:{message_id}"


def _utc_now_label() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def append_proposal_decision(
    *,
    decision: str,
    item_id: str,
    parser_rule: str,
    matched_phrase: str,
    source_session: str,
    actor: str,
    log_path: Path = DECISION_LOG_PATH,
) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "decided_at": _utc_now_label(),
        "decision": decision,
        "item_id": item_id,
        "parser_rule": parser_rule,
        "matched_phrase": matched_phrase,
        "source_session": source_session,
        "actor": actor,
    }
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def _pending_proposal_item(repo: ItemRepository, *, source_session: str) -> Any | None:
    item = repo.get_item_by_source_and_session(PROPOSAL_SOURCE, source_session)
    if item is None:
        return None
    if str(item.state).upper() != "TRIAGE":
        return None
    return item


def scan_commitment_proposals(
    db_path: Path | str = DB_PATH,
    *,
    session_file: Path | str | None = None,
    message_loader: Callable[[], list[dict[str, Any]]] | None = None,
    actor: str = PROPOSAL_ACTOR,
) -> list[ProposalScanRow]:
    loader = message_loader
    if loader is None:
        resolved_session = Path(session_file) if session_file is not None else None

        def loader() -> list[dict[str, Any]]:
            return load_openclaw_session_messages(session_file=resolved_session)

    repo = ItemRepository(db_path)
    rows: list[ProposalScanRow] = []
    for message in loader():
        text = str(message.get("text") or "")
        parse_result = parse_commitment_message(text)
        if not parse_result.actionable:
            continue
        chat_id = str(message.get("chat_id") or "").strip()
        message_id = str(message.get("message_id") or "").strip()
        if not chat_id or not message_id:
            continue
        source_session = _canonical_source_session(chat_id, message_id)
        existing = _pending_proposal_item(repo, source_session=source_session)
        created = False
        if existing is None:
            item = repo.create_item(
                item_type="commitment",
                title=parse_result.title or "Telegram commitment",
                description=parse_result.description,
                state="TRIAGE",
                source=PROPOSAL_SOURCE,
                source_session=source_session,
                actor=actor,
                created_payload_extra={
                    "proposal_kind": "commitment",
                    "parser_rule": parse_result.parser_rule,
                    "matched_phrase": parse_result.matched_phrase,
                    "source_message_text": parse_result.source_text,
                    "source_chat_id": chat_id,
                    "source_message_id": message_id,
                    "source_received_at": str(message.get("received_at") or ""),
                },
            )
            repo.add_evidence(
                item.id,
                evidence_text=(
                    "Commitment proposal captured from OpenClaw Telegram session stream. "
                    f"rule={parse_result.parser_rule} phrase={parse_result.matched_phrase} "
                    f"text={parse_result.source_text}"
                ),
                evidence_uri=EVIDENCE_URI,
                created_by=PROPOSAL_ACTOR,
                actor=actor,
            )
            created = True
            item_id = item.id
        else:
            item_id = existing.id

        rows.append(
            ProposalScanRow(
                item_id=item_id,
                title=parse_result.title,
                matched_phrase=parse_result.matched_phrase,
                parser_rule=parse_result.parser_rule,
                source_session=source_session,
                created=created,
            )
        )
    return rows


def _proposal_metadata(repo: ItemRepository, item_id: str) -> dict[str, str]:
    item = repo.get_item(item_id)
    if item is None:
        raise ValidationError(f"unknown item_id: {item_id}")
    if item.source != PROPOSAL_SOURCE:
        raise ValidationError(f"item {item_id} is not a commitment proposal")
    if str(item.state).upper() != "TRIAGE":
        raise ValidationError(f"item {item_id} is not in TRIAGE (state={item.state})")
    events = repo.list_item_events(item_id, event_type="item.created", limit=1)
    parser_rule = "unknown"
    matched_phrase = ""
    if events:
        event = events[0]
        if event.payload_json:
            try:
                payload = json.loads(event.payload_json)
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict):
                parser_rule = str(payload.get("parser_rule") or parser_rule)
                matched_phrase = str(payload.get("matched_phrase") or matched_phrase)
    source_session = str(item.source_session or "")
    return {
        "parser_rule": parser_rule,
        "matched_phrase": matched_phrase,
        "source_session": source_session,
    }


def accept_commitment_proposal(
    db_path: Path | str,
    item_id: str,
    *,
    actor: str = "operator",
) -> dict[str, str]:
    repo = ItemRepository(db_path)
    metadata = _proposal_metadata(repo, item_id)
    item = repo.apply_action(item_id, "approve", actor=actor, reason="commitment proposal accepted")
    append_proposal_decision(
        decision="accept",
        item_id=item_id,
        parser_rule=metadata["parser_rule"],
        matched_phrase=metadata["matched_phrase"],
        source_session=metadata["source_session"],
        actor=actor,
    )
    return {"item_id": item.id, "state": item.state, "decision": "accept"}


def reject_commitment_proposal(
    db_path: Path | str,
    item_id: str,
    *,
    actor: str = "operator",
) -> dict[str, str]:
    repo = ItemRepository(db_path)
    metadata = _proposal_metadata(repo, item_id)
    item = repo.apply_action(item_id, "drop", actor=actor, reason="commitment proposal rejected")
    append_proposal_decision(
        decision="reject",
        item_id=item_id,
        parser_rule=metadata["parser_rule"],
        matched_phrase=metadata["matched_phrase"],
        source_session=metadata["source_session"],
        actor=actor,
    )
    return {"item_id": item.id, "state": item.state, "decision": "reject"}


def print_proposal_scan_rows(rows: Sequence[ProposalScanRow]) -> None:
    if not rows:
        print("propose.count=0")
        return
    print(f"propose.count={len(rows)}")
    print(f"{'item_id':<36} {'created':<8} {'phrase':<14} {'rule':<24} {'title':<40}")
    for row in rows:
        print(
            f"{row.item_id:<36} "
            f"{'yes' if row.created else 'no':<8} "
            f"{row.matched_phrase:<14} "
            f"{row.parser_rule:<24} "
            f"{row.title[:40]:<40}"
        )


def run_propose_command(
    *,
    db_path: Path | str,
    propose_action: str | None,
    item_id: str | None,
    session_file: Path | str | None = None,
    actor: str | None = None,
    message_loader: Callable[[], list[dict[str, Any]]] | None = None,
) -> int:
    normalized_actor = (actor or "operator").strip() or "operator"
    if propose_action == "accept":
        if not item_id:
            print("error=item_id is required for propose accept", file=sys.stderr)
            return 1
        try:
            result = accept_commitment_proposal(db_path, item_id, actor=normalized_actor)
        except (ValidationError, KeyError) as exc:
            print(f"error={exc}")
            return 1
        print(f"propose.decision={result['decision']}")
        print(f"item_id={result['item_id']}")
        print(f"state={result['state']}")
        return 0
    if propose_action == "reject":
        if not item_id:
            print("error=item_id is required for propose reject", file=sys.stderr)
            return 1
        try:
            result = reject_commitment_proposal(db_path, item_id, actor=normalized_actor)
        except (ValidationError, KeyError) as exc:
            print(f"error={exc}")
            return 1
        print(f"propose.decision={result['decision']}")
        print(f"item_id={result['item_id']}")
        print(f"state={result['state']}")
        return 0

    rows = scan_commitment_proposals(
        db_path,
        session_file=session_file,
        message_loader=message_loader,
        actor=PROPOSAL_ACTOR,
    )
    print_proposal_scan_rows(rows)
    return 0
