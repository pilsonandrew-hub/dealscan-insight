from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator

from .action_runtime import (
    JACE_STATUS_CREATED_BY,
    JACE_STATUS_EVIDENCE_URI,
    NOTIFICATION_ACTION_EVIDENCE_URI,
)
from .storage import DB_PATH, bootstrap_db, connect


ACTUAL_SEND_SOURCE_TABLE = "alert_log"
SUPPORT_SOURCE_TABLES = frozenset({"evidence", "action_queue", "governed_runs"})
DELIVERY_RELATED_EVIDENCE_URIS = frozenset(
    {
        JACE_STATUS_EVIDENCE_URI,
        NOTIFICATION_ACTION_EVIDENCE_URI,
    }
)
PROOF_CONTEXT_MARKERS = (
    "proof",
    "synthetic",
    "test",
    "e2e",
    "smoke",
    "harness",
    "suppression",
    "launchagent",
    "gateway transport",
    "verification/manual",
    "ace-launchd-jace-proof",
)
_WORD_PROOF_CONTEXT_MARKERS = frozenset({"proof", "synthetic", "test", "e2e", "smoke", "harness", "suppression", "launchagent"})
CONTENT_CAUTION_MARKERS = (
    "audit",
    "truth",
    "report",
    "verification",
)


@dataclass(frozen=True)
class JaceAuditRecord:
    source_table: str
    row_id: str
    item_id: str | None
    sent_at: str | None
    message_id: str | None
    message: str
    delivery_state: str | None
    transport: str | None
    trigger_kind: str | None = None
    notification_action_id: str | None = None
    delivery_evidence_id: str | None = None
    classification: str = "unclassified"
    is_actual_send: bool = False
    support_role: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "classification": self.classification,
            "delivery_evidence_id": self.delivery_evidence_id,
            "delivery_state": self.delivery_state,
            "is_actual_send": self.is_actual_send,
            "item_id": self.item_id,
            "message": self.message,
            "message_id": self.message_id,
            "notification_action_id": self.notification_action_id,
            "row_id": self.row_id,
            "sent_at": self.sent_at,
            "source_table": self.source_table,
            "support_role": self.support_role,
            "transport": self.transport,
            "trigger_kind": self.trigger_kind,
        }


def audit_jace_delivery_history(db_path: Path | str = DB_PATH) -> dict[str, Any]:
    """Return a read-only cross-table JACE delivery audit.

    This intentionally distinguishes actual Telegram sends (`alert_log`) from
    supporting state records (`evidence`, `action_queue`, `governed_runs`).
    """
    bootstrap_db(db_path)
    records = collect_jace_audit_records(db_path)
    source_counts = Counter(record.source_table for record in records)
    classification_counts = Counter(record.classification for record in records)
    actual_sends = [record for record in records if record.is_actual_send]
    support_records = [record for record in records if not record.is_actual_send]
    missing_message_ids = _missing_numeric_message_ids(
        record.message_id for record in actual_sends if record.message_id is not None
    )
    return {
        "actual_send_count": len(actual_sends),
        "support_record_count": len(support_records),
        "normalized_record_count": len(records),
        "source_counts": dict(sorted(source_counts.items())),
        "classification_counts": dict(sorted(classification_counts.items())),
        "missing_message_ids": missing_message_ids,
        "records": [record.as_dict() for record in records],
    }


def collect_jace_audit_records(db_path: Path | str = DB_PATH) -> list[JaceAuditRecord]:
    with _readonly_connection(db_path) as connection:
        item_context = _load_item_context(connection)
        action_context = _load_action_context(connection)
        evidence_context = _load_evidence_context(connection)
        records: list[JaceAuditRecord] = []
        records.extend(_alert_log_records(connection, item_context))
        records.extend(_evidence_records(connection, item_context))
        records.extend(_action_records(connection, item_context))
        records.extend(_governed_run_records(connection, action_context, evidence_context, item_context))
    records.sort(key=lambda record: ((record.sent_at or ""), record.source_table, record.row_id))
    return records


def classify_jace_trigger(
    *,
    item: dict[str, Any] | None,
    message: str,
    trigger_kind: str | None = None,
) -> str:
    text_parts = [message or "", trigger_kind or ""]
    if item:
        text_parts.extend(
            str(item.get(key) or "")
            for key in ("title", "description", "source", "source_session", "first_actor", "first_source", "first_session_id")
        )
    haystack = "\n".join(text_parts).lower()

    if trigger_kind == "operator":
        return "operator_triggered"
    if _contains_proof_context_marker(haystack):
        first_state = (item or {}).get("first_payload_state")
        if first_state == "ACTIVE":
            return "legacy_proof"
        return "proof_or_synthetic"
    if item and item.get("first_actor") == "ace.telegram_intake" and item.get("first_source") == "telegram/direct":
        if any(marker in haystack for marker in CONTENT_CAUTION_MARKERS):
            return "natural_launchd_driven_with_content_caution"
        return "natural_launchd_driven"
    return "unclassified"


def classify_event_timestamp_inversions(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Classify created_at inversions without treating them as hash tamper by default."""
    ordered = sorted(events, key=lambda event: int(event["id"]))
    findings: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None
    for event in ordered:
        if previous is not None and str(event.get("created_at")) < str(previous.get("created_at")):
            findings.append(
                {
                    "previous_event_id": previous.get("event_id"),
                    "event_id": event.get("event_id"),
                    "classification": _classify_inversion_pair(previous, event),
                    "hash_chain_link_consistent": event.get("previous_event_hash") == previous.get("event_hash"),
                    "previous_created_at": previous.get("created_at"),
                    "created_at": event.get("created_at"),
                }
            )
        previous = event
    return findings


def _classify_inversion_pair(previous: dict[str, Any], current: dict[str, Any]) -> str:
    previous_uri = _payload_value(previous, "evidence_uri")
    current_uri = _payload_value(current, "evidence_uri")
    if {previous_uri, current_uri} == {JACE_STATUS_EVIDENCE_URI, NOTIFICATION_ACTION_EVIDENCE_URI}:
        return "send_wrapper_timestamp_inversion"
    if previous.get("item_id") == current.get("item_id"):
        return "same_item_lifecycle_timestamp_inversion"
    return "event_id_order_timestamp_inversion"


def _is_direct_jace_status_record(alert_type: str | None, message: str) -> bool:
    return alert_type == "jace_status" and not message.lstrip().startswith("ACE alert:")


def _is_direct_jace_status_evidence(evidence_uri: str | None, message: str) -> bool:
    return evidence_uri == JACE_STATUS_EVIDENCE_URI and not message.lstrip().startswith("ACE alert:")


def _contains_proof_context_marker(haystack: str) -> bool:
    for marker in PROOF_CONTEXT_MARKERS:
        if marker in _WORD_PROOF_CONTEXT_MARKERS:
            if re.search(rf"(?<![a-z0-9]){re.escape(marker)}(?![a-z0-9])", haystack):
                return True
        elif marker in haystack:
            return True
    return False


def _alert_log_records(connection: sqlite3.Connection, item_context: dict[str, dict[str, Any]]) -> list[JaceAuditRecord]:
    rows = connection.execute(
        """
        SELECT id, alert_type, transport, bot_username, chat_id, message_id,
               delivery_state, sent_at, metadata_json
        FROM alert_log
        WHERE bot_username = ? OR transport = ? OR alert_type IN (?, ?)
        ORDER BY sent_at ASC, id ASC
        """,
        ("JACEthaACE_Bot", "telegram_bot_api", "jace_status", "operator_notification"),
    ).fetchall()
    records = []
    for row in rows:
        metadata = _json_object(row["metadata_json"])
        item_id = _optional_text(metadata.get("item_id"))
        message = _optional_text(metadata.get("message")) or ""
        records.append(
            JaceAuditRecord(
                source_table="alert_log",
                row_id=row["id"],
                item_id=item_id,
                sent_at=row["sent_at"],
                message_id=str(row["message_id"]),
                message=message,
                delivery_state=row["delivery_state"],
                transport=row["transport"],
                classification=classify_jace_trigger(
                    item=item_context.get(item_id or ""),
                    message=message,
                    trigger_kind="operator" if _is_direct_jace_status_record(row["alert_type"], message) else None,
                ),
                is_actual_send=True,
            )
        )
    return records


def _evidence_records(connection: sqlite3.Connection, item_context: dict[str, dict[str, Any]]) -> list[JaceAuditRecord]:
    rows = connection.execute(
        """
        SELECT id, item_id, evidence_text, evidence_uri, created_by, created_at
        FROM evidence
        WHERE evidence_uri IN (?, ?) OR created_by IN (?, ?)
        ORDER BY created_at ASC, id ASC
        """,
        (
            JACE_STATUS_EVIDENCE_URI,
            NOTIFICATION_ACTION_EVIDENCE_URI,
            JACE_STATUS_CREATED_BY,
            "ace.notification_runtime",
        ),
    ).fetchall()
    records = []
    for row in rows:
        payload = _json_object(row["evidence_text"])
        delivery = payload.get("delivery_result") if isinstance(payload.get("delivery_result"), dict) else {}
        result = delivery.get("result") if isinstance(delivery.get("result"), dict) else {}
        message = _optional_text(payload.get("message")) or _optional_text(result.get("text")) or ""
        message_id = _optional_text(payload.get("message_id")) or _optional_text(delivery.get("message_id")) or _optional_text(result.get("message_id"))
        records.append(
            JaceAuditRecord(
                source_table="evidence",
                row_id=row["id"],
                item_id=row["item_id"],
                sent_at=row["created_at"],
                message_id=message_id,
                message=message,
                delivery_state=_optional_text(payload.get("delivery_state")) or _optional_text(payload.get("outcome")),
                transport=_optional_text(payload.get("transport")),
                classification=classify_jace_trigger(
                    item=item_context.get(row["item_id"]),
                    message=message,
                    trigger_kind="operator" if _is_direct_jace_status_evidence(row["evidence_uri"], message) else None,
                ),
                support_role=row["evidence_uri"],
            )
        )
    return records


def _action_records(connection: sqlite3.Connection, item_context: dict[str, dict[str, Any]]) -> list[JaceAuditRecord]:
    rows = connection.execute(
        """
        SELECT id, item_id, action_type, payload_json, status, created_at,
               claimed_at, completed_at, error_message
        FROM action_queue
        WHERE action_type = ?
        ORDER BY COALESCE(completed_at, claimed_at, created_at) ASC, id ASC
        """,
        ("send_operator_notification",),
    ).fetchall()
    records = []
    for row in rows:
        payload = _json_object(row["payload_json"])
        if _optional_text(payload.get("channel")) != "jace":
            continue
        item_id = _optional_text(row["item_id"]) or _optional_text(payload.get("target_item_id"))
        message = _optional_text(payload.get("message")) or ""
        records.append(
            JaceAuditRecord(
                source_table="action_queue",
                row_id=row["id"],
                item_id=item_id,
                sent_at=row["completed_at"] or row["claimed_at"] or row["created_at"],
                message_id=None,
                message=message,
                delivery_state=row["status"],
                transport="jace",
                classification=classify_jace_trigger(item=item_context.get(item_id or ""), message=message),
                support_role="queued_operator_notification",
            )
        )
    return records


def _governed_run_records(
    connection: sqlite3.Connection,
    action_context: dict[str, dict[str, Any]],
    evidence_context: dict[str, dict[str, Any]],
    item_context: dict[str, dict[str, Any]],
) -> list[JaceAuditRecord]:
    rows = connection.execute(
        """
        SELECT run_id, trigger_kind, status, notification_action_id,
               delivery_evidence_id, created_at, ended_at
        FROM governed_runs
        WHERE notification_action_id IS NOT NULL OR delivery_evidence_id IS NOT NULL
        ORDER BY COALESCE(ended_at, created_at) ASC, run_id ASC
        """
    ).fetchall()
    records = []
    for row in rows:
        action = action_context.get(row["notification_action_id"] or "")
        evidence = evidence_context.get(row["delivery_evidence_id"] or "")
        item_id = _optional_text((action or {}).get("item_id")) or _optional_text((evidence or {}).get("item_id"))
        message = _optional_text((action or {}).get("message")) or _optional_text((evidence or {}).get("message")) or ""
        records.append(
            JaceAuditRecord(
                source_table="governed_runs",
                row_id=row["run_id"],
                item_id=item_id,
                sent_at=row["ended_at"] or row["created_at"],
                message_id=_optional_text((evidence or {}).get("message_id")),
                message=message,
                delivery_state=row["status"],
                transport="jace" if action or evidence else None,
                trigger_kind=row["trigger_kind"],
                notification_action_id=row["notification_action_id"],
                delivery_evidence_id=row["delivery_evidence_id"],
                classification=classify_jace_trigger(
                    item=item_context.get(item_id or ""),
                    message=message,
                    trigger_kind=row["trigger_kind"],
                ),
                support_role="governed_run_reference",
            )
        )
    return records


def _load_item_context(connection: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    items = {
        row["id"]: dict(row)
        for row in connection.execute(
            "SELECT id, title, description, state, source, source_session, created_at FROM items"
        ).fetchall()
    }
    for row in connection.execute(
        """
        SELECT e.item_id, e.event_type, e.actor, e.source, e.session_id, e.payload_json, e.created_at
        FROM events e
        JOIN (
            SELECT item_id, MIN(id) AS first_id
            FROM events
            WHERE item_id IS NOT NULL
            GROUP BY item_id
        ) first ON first.item_id = e.item_id AND first.first_id = e.id
        """
    ).fetchall():
        item = items.get(row["item_id"])
        if item is None:
            continue
        payload = _json_object(row["payload_json"])
        item.update(
            {
                "first_event_type": row["event_type"],
                "first_actor": row["actor"],
                "first_source": row["source"],
                "first_session_id": row["session_id"],
                "first_created_at": row["created_at"],
                "first_payload_state": payload.get("state"),
            }
        )
    return items


def _load_action_context(connection: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    rows = connection.execute("SELECT id, item_id, payload_json FROM action_queue").fetchall()
    context = {}
    for row in rows:
        payload = _json_object(row["payload_json"])
        context[row["id"]] = {
            "item_id": row["item_id"] or payload.get("target_item_id"),
            "message": payload.get("message"),
        }
    return context


def _load_evidence_context(connection: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    rows = connection.execute("SELECT id, item_id, evidence_text FROM evidence").fetchall()
    context = {}
    for row in rows:
        payload = _json_object(row["evidence_text"])
        delivery = payload.get("delivery_result") if isinstance(payload.get("delivery_result"), dict) else {}
        result = delivery.get("result") if isinstance(delivery.get("result"), dict) else {}
        context[row["id"]] = {
            "item_id": row["item_id"],
            "message": payload.get("message"),
            "message_id": payload.get("message_id") or delivery.get("message_id") or result.get("message_id"),
        }
    return context


@contextmanager
def _readonly_connection(db_path: Path | str) -> Iterator[sqlite3.Connection]:
    path = str(db_path)
    if not path.startswith("file:"):
        path = f"file:{Path(path)}?mode=ro"
    connection = sqlite3.connect(path, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()


def _json_object(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, str) or not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _payload_value(event: dict[str, Any], key: str) -> Any:
    return _json_object(event.get("payload_json")).get(key)


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _missing_numeric_message_ids(message_ids: Iterable[str]) -> list[str]:
    numeric = sorted({int(value) for value in message_ids if str(value).isdigit()})
    if len(numeric) < 2:
        return []
    present = set(numeric)
    return [str(value) for value in range(numeric[0], numeric[-1] + 1) if value not in present]
