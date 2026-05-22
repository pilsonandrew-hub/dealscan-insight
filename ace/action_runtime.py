from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

from .repository import ItemRepository, ValidationError
from .scope_guard import ScopeAction, ScopeGuard
from .storage import DB_PATH, append_event, bootstrap_db, connect, new_id, utc_now
from .telegram_runtime import load_ace_telegram_env_file, _telegram_ssl_context


ACTION_KIND = "record_operator_followup"
ACTION_CREATED_BY = "ace.phase2.action_runtime"
ACTION_EVIDENCE_URI = "ace://phase2/action-outcome"
REJECTION_ACTION_KIND = "record_operator_rejection"
REJECTION_ACTION_EVIDENCE_URI = "ace://phase2/action-rejection"
NOTIFICATION_ACTION_KIND = "send_operator_notification"
NOTIFICATION_ACTION_CREATED_BY = "ace.notification_runtime"
NOTIFICATION_ACTION_EVIDENCE_URI = "ace://notification/delivery"
NOTIFICATION_FAILURE_CODE = "action_failed_notification"
NOTIFICATION_RUNTIME_FAILURE_CODE = "action_failed_runtime_error"
JACE_STATUS_EVIDENCE_URI = "ace://jace/outbound-status-delivery"
JACE_STATUS_CREATED_BY = "ace.jace_status_runtime"
OPENCLAW_GATEWAY_URL = "http://127.0.0.1:18789/tools/invoke"
OPENCLAW_CONFIG_PATH = Path.home() / ".openclaw" / "openclaw.json"

_ACTION_STATUS_QUEUED = "queued"
_ACTION_STATUS_CLAIMED = "claimed"
_ACTION_STATUS_COMPLETED = "completed"
_ACTION_STATUS_FAILED = "failed"


class NotificationDeliveryError(RuntimeError):
    """Raised when the notification transport fails visibly."""


class JaceStatusDeliveryError(RuntimeError):
    """Raised when JACE-owned outbound status delivery fails visibly."""


NotificationSender = Callable[..., dict[str, Any]]


DISPATCHABLE_LOCAL_ACTION_KINDS = frozenset({ACTION_KIND, REJECTION_ACTION_KIND})


def run_action_queue_dispatcher(
    db_path: Path | str = DB_PATH,
    *,
    actor: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Drain a bounded set of safe local queued actions.

    This dispatcher intentionally excludes external-delivery actions such as
    operator notifications. It only executes local, durable evidence-recording
    actions whose side effect is confined to the ACE database.
    """
    bootstrap_db(db_path)
    if limit < 1:
        raise ValidationError("limit must be >= 1")

    candidates = _queued_dispatchable_actions(db_path, limit=limit)
    executed: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for candidate in candidates:
        action_id = str(candidate["id"])
        action_type = str(candidate["action_type"])
        try:
            if action_type == ACTION_KIND:
                claim_record_operator_followup(db_path, action_id, actor=actor)
                result = execute_record_operator_followup(db_path, action_id, actor=actor)
            elif action_type == REJECTION_ACTION_KIND:
                claim_record_operator_rejection(db_path, action_id, actor=actor)
                result = execute_record_operator_rejection(db_path, action_id, actor=actor)
            else:  # pragma: no cover - guarded by query and kept as a hard boundary
                skipped.append({
                    "action_id": action_id,
                    "action_type": action_type,
                    "reason": "unsupported_action_type",
                })
                continue
        except Exception as exc:  # pragma: no cover - defensive dispatcher boundary
            failed.append({
                "action_id": action_id,
                "action_type": action_type,
                "error": str(exc) or exc.__class__.__name__,
            })
            continue

        if result["status"] == _ACTION_STATUS_FAILED:
            failed.append(result)
        else:
            executed.append(result)

    return {
        "candidate_count": len(candidates),
        "executed_count": len(executed),
        "failed_count": len(failed),
        "skipped_count": len(skipped),
        "executed": executed,
        "failed": failed,
        "skipped": skipped,
    }


def _queued_dispatchable_actions(db_path: Path | str, *, limit: int) -> list[sqlite3.Row]:
    allowed_kinds = sorted(DISPATCHABLE_LOCAL_ACTION_KINDS)
    placeholders = ", ".join("?" for _ in allowed_kinds)
    with connect(db_path) as connection:
        rows = connection.execute(
            f"""
            SELECT id, action_type
            FROM action_queue
            WHERE status = ? AND action_type IN ({placeholders})
            ORDER BY priority DESC, created_at ASC, id ASC
            LIMIT ?
            """,
            (_ACTION_STATUS_QUEUED, *allowed_kinds, limit),
        ).fetchall()
    return list(rows)


def send_jace_status_message(
    db_path: Path | str = DB_PATH,
    item_id: str | None = None,
    *,
    message: str,
    chat_id: str | None = None,
    actor: str | None = None,
    scope_guard: ScopeGuard | None = None,
) -> dict[str, Any]:
    """Send an independently attributable JACE status message via ACE's bot.

    This deliberately does not use OpenClaw's shared message tool. It uses the
    ACE/JACE-owned Bot API token from ``ace/state/ace-telegram.env`` and records
    both local transport proof (``alert_log``) and item evidence.
    """
    bootstrap_db(db_path)
    normalized_item_id = _normalize_required_text(item_id, field_name="item_id")
    normalized_message = _normalize_required_text(message, field_name="message")
    load_ace_telegram_env_file()
    token = _normalize_optional_text(os.environ.get("ACE_TELEGRAM_BOT_TOKEN"))
    if token is None:
        raise JaceStatusDeliveryError("ACE_TELEGRAM_BOT_TOKEN is not configured")
    normalized_chat_id = _normalize_optional_text(chat_id) or _normalize_optional_text(
        os.environ.get("ACE_TELEGRAM_CHAT_ID")
    )
    if normalized_chat_id is None:
        raise JaceStatusDeliveryError("ACE_TELEGRAM_CHAT_ID is not configured")

    if scope_guard is not None:
        decision = scope_guard.authorize(
            ScopeAction(
                "external_send",
                paths=(str(Path(db_path)),),
                destination=f"telegram:{normalized_chat_id}",
                description="action_runtime.send_jace_status_message",
            )
        )
        if not decision.allowed:
            return {
                "item_id": normalized_item_id,
                "status": "scope_blocked",
                "decision": decision.decision.value,
                "reason": decision.reason,
                "scope_hash": decision.scope_hash,
            }

    repo = ItemRepository(db_path)
    if repo.get_item(normalized_item_id) is None:
        raise KeyError(f"unknown item_id: {normalized_item_id}")

    bot = _telegram_bot_api_get_me(token)
    delivery = _telegram_bot_api_send_message(
        token=token,
        chat_id=normalized_chat_id,
        text=normalized_message,
    )
    result = delivery.get("result") if isinstance(delivery.get("result"), dict) else {}
    message_id = _normalize_required_text(result.get("message_id"), field_name="message_id")
    bot_username = _normalize_optional_text(bot.get("username"))
    sent_at = utc_now()
    alert_id = new_id("alert")
    evidence_payload = {
        "alert_id": alert_id,
        "bot_username": bot_username,
        "chat_id": normalized_chat_id,
        "created_by": JACE_STATUS_CREATED_BY,
        "delivery_state": "sent",
        "item_id": normalized_item_id,
        "message": normalized_message,
        "message_id": message_id,
        "outcome": "jace_status_message_sent",
        "transport": "telegram_bot_api",
    }
    evidence_text = _canonical_json(evidence_payload)

    with connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO alert_log(
                id, alert_type, transport, bot_username, chat_id, message_id,
                delivery_state, sent_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                alert_id,
                "jace_status",
                "telegram_bot_api",
                bot_username,
                normalized_chat_id,
                message_id,
                "sent",
                sent_at,
                _canonical_json({"item_id": normalized_item_id, "message": normalized_message}),
            ),
        )
        evidence_id = new_id("evidence")
        connection.execute(
            """
            INSERT INTO evidence(id, item_id, evidence_text, evidence_uri, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (evidence_id, normalized_item_id, evidence_text, JACE_STATUS_EVIDENCE_URI, JACE_STATUS_CREATED_BY, sent_at),
        )
        append_event(
            connection,
            event_type="item.evidence_added",
            payload={
                "item_id": normalized_item_id,
                "evidence_id": evidence_id,
                "evidence_text": evidence_text,
                "evidence_uri": JACE_STATUS_EVIDENCE_URI,
                "created_by": JACE_STATUS_CREATED_BY,
                "delivery_result": delivery,
            },
            item_id=normalized_item_id,
            actor=actor or JACE_STATUS_CREATED_BY,
            created_at=sent_at,
        )
        connection.commit()

    return {
        "item_id": normalized_item_id,
        "alert_id": alert_id,
        "evidence_id": evidence_id,
        "message_id": message_id,
        "bot_username": bot_username,
        "chat_id": normalized_chat_id,
        "delivery_state": "sent",
        "evidence_written": True,
    }


def enqueue_record_operator_followup(
    db_path: Path | str = DB_PATH,
    item_id: str | None = None,
    *,
    note: str,
    actor: str | None = None,
    scope_guard: ScopeGuard | None = None,
) -> dict[str, Any]:
    return _enqueue_record_operator_action(
        db_path,
        item_id,
        action_kind=ACTION_KIND,
        payload_field_name="note",
        payload_field_value=note,
        actor=actor,
        scope_guard=scope_guard,
    )


def enqueue_record_operator_rejection(
    db_path: Path | str = DB_PATH,
    item_id: str | None = None,
    *,
    reason: str,
    actor: str | None = None,
    scope_guard: ScopeGuard | None = None,
) -> dict[str, Any]:
    return _enqueue_record_operator_action(
        db_path,
        item_id,
        action_kind=REJECTION_ACTION_KIND,
        payload_field_name="reason",
        payload_field_value=reason,
        actor=actor,
        scope_guard=scope_guard,
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


def enqueue_operator_notification(
    db_path: Path | str = DB_PATH,
    item_id: str | None = None,
    *,
    channel: str,
    target: str,
    reason: str,
    age_context: str | None = None,
    deadline_context: str | None = None,
    thread_id: str | None = None,
    actor: str | None = None,
) -> dict[str, Any]:
    bootstrap_db(db_path)
    normalized_item_id = _normalize_required_text(item_id, field_name="item_id")
    normalized_channel = _normalize_required_text(channel, field_name="channel")
    normalized_target = _normalize_required_text(target, field_name="target")
    normalized_reason = _normalize_required_text(reason, field_name="reason")
    normalized_age_context = _normalize_optional_text(age_context)
    normalized_deadline_context = _normalize_optional_text(deadline_context)
    normalized_thread_id = _normalize_optional_text(thread_id)
    if normalized_age_context is None and normalized_deadline_context is None:
        raise ValidationError("notification requires age_context and/or deadline_context")

    repo = ItemRepository(db_path)
    item = repo.get_item(normalized_item_id)
    if item is None:
        raise KeyError(f"unknown item_id: {normalized_item_id}")

    payload = {
        "action_kind": NOTIFICATION_ACTION_KIND,
        "target_item_id": normalized_item_id,
        "channel": normalized_channel,
        "target": normalized_target,
        "reason": normalized_reason,
        "age_context": normalized_age_context,
        "deadline_context": normalized_deadline_context,
        "thread_id": normalized_thread_id,
        "item_title": item.title,
        "item_state": item.state,
        "message": _build_notification_message(
            item_id=normalized_item_id,
            title=item.title,
            state=item.state,
            reason=normalized_reason,
            age_context=normalized_age_context,
            deadline_context=normalized_deadline_context,
        ),
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
                    normalized_item_id,
                    NOTIFICATION_ACTION_KIND,
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
            assert row is not None, "notification enqueue failed unexpectedly"

    return _row_to_action_result(row, evidence_id=None, evidence_written=False)


def claim_operator_notification(
    db_path: Path | str = DB_PATH,
    action_id: str | None = None,
    *,
    actor: str | None = None,
) -> dict[str, Any]:
    return _claim_record_operator_action(db_path, action_id, action_kind=NOTIFICATION_ACTION_KIND)


def execute_operator_notification(
    db_path: Path | str = DB_PATH,
    action_id: str | None = None,
    *,
    sender: NotificationSender | None = None,
    actor: str | None = None,
) -> dict[str, Any]:
    bootstrap_db(db_path)
    normalized_action_id = _normalize_required_text(action_id, field_name="action_id")
    updated_at = utc_now()
    repo = ItemRepository(db_path)
    sender = sender or _openclaw_message_sender

    with connect(db_path) as connection:
        row = _fetch_action_row(connection, normalized_action_id)
        if row is None:
            raise KeyError(f"unknown action_id: {normalized_action_id}")

        if row["action_type"] != NOTIFICATION_ACTION_KIND:
            raise ValidationError(
                f"wrong action kind: expected {NOTIFICATION_ACTION_KIND}, got {row['action_type']}"
            )

        if row["status"] in {_ACTION_STATUS_COMPLETED, _ACTION_STATUS_FAILED}:
            evidence_id = _existing_notification_evidence_id(connection, row)
            return _row_to_action_result(row, evidence_id=evidence_id, evidence_written=False)

        if row["status"] != _ACTION_STATUS_CLAIMED:
            raise ValidationError(f"{NOTIFICATION_ACTION_KIND} actions must be claimed before execution")

        try:
            payload = _decode_action_payload(row["payload_json"])
            target_item_id = _normalize_required_text(payload.get("target_item_id"), field_name="target_item_id")
            channel = _normalize_required_text(payload.get("channel"), field_name="channel")
            target = _normalize_required_text(payload.get("target"), field_name="target")
            reason = _normalize_required_text(payload.get("reason"), field_name="reason")
            item_title = _normalize_required_text(payload.get("item_title"), field_name="item_title")
            item_state = _normalize_required_text(payload.get("item_state"), field_name="item_state")
            message = _normalize_required_text(payload.get("message"), field_name="message")
            age_context = _normalize_optional_text(payload.get("age_context"))
            deadline_context = _normalize_optional_text(payload.get("deadline_context"))
            thread_id = _normalize_optional_text(payload.get("thread_id"))
            if age_context is None and deadline_context is None:
                raise ValidationError("notification requires age_context and/or deadline_context")
        except json.JSONDecodeError as exc:
            return _fail_action(
                connection,
                normalized_action_id,
                updated_at=updated_at,
                error_message=f"invalid action payload: malformed JSON: {exc}",
            )
        except ValidationError as exc:
            return _fail_action(
                connection,
                normalized_action_id,
                updated_at=updated_at,
                error_message=f"invalid action payload: {exc}",
            )

        item = repo.get_item(target_item_id)
        if item is None:
            return _fail_action(
                connection,
                normalized_action_id,
                updated_at=updated_at,
                error_message=f"{NOTIFICATION_FAILURE_CODE}: unknown target_item_id: {target_item_id}",
            )

        try:
            if channel == "jace":
                sender_result = send_jace_status_message(
                    db_path,
                    target_item_id,
                    message=message,
                    chat_id=target,
                    actor=actor or NOTIFICATION_ACTION_CREATED_BY,
                )
            else:
                sender_result = sender(
                    channel=channel,
                    target=target,
                    message=message,
                    thread_id=thread_id,
                )
        except (NotificationDeliveryError, JaceStatusDeliveryError) as exc:
            return _fail_action(
                connection,
                normalized_action_id,
                updated_at=updated_at,
                error_message=f"{NOTIFICATION_FAILURE_CODE}: {exc}",
            )
        except Exception as exc:  # pragma: no cover - defensive runtime boundary
            return _fail_action(
                connection,
                normalized_action_id,
                updated_at=updated_at,
                error_message=f"{NOTIFICATION_RUNTIME_FAILURE_CODE}: {exc}",
            )

        evidence_text = _canonical_json(
            {
                "action_id": normalized_action_id,
                "action_kind": NOTIFICATION_ACTION_KIND,
                "channel": channel,
                "target": target,
                "thread_id": thread_id,
                "message": message,
                "reason": reason,
                "age_context": age_context,
                "deadline_context": deadline_context,
                "item_title": item_title,
                "item_state": item_state,
                "outcome": "operator_notification_sent",
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
            (
                target_item_id,
                NOTIFICATION_ACTION_EVIDENCE_URI,
                NOTIFICATION_ACTION_CREATED_BY,
                evidence_text,
            ),
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
                    NOTIFICATION_ACTION_EVIDENCE_URI,
                    NOTIFICATION_ACTION_CREATED_BY,
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
                    "evidence_uri": NOTIFICATION_ACTION_EVIDENCE_URI,
                    "created_by": NOTIFICATION_ACTION_CREATED_BY,
                    "delivery_result": sender_result,
                },
                item_id=target_item_id,
                actor=actor or NOTIFICATION_ACTION_CREATED_BY,
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
        assert row is not None, "completed notification update unexpectedly missing"

    return _row_to_action_result(row, evidence_id=evidence_id, evidence_written=evidence_written)


def send_operator_notification(
    db_path: Path | str = DB_PATH,
    item_id: str | None = None,
    *,
    channel: str,
    target: str,
    reason: str,
    age_context: str | None = None,
    deadline_context: str | None = None,
    thread_id: str | None = None,
    actor: str | None = None,
    sender: NotificationSender | None = None,
) -> dict[str, Any]:
    enqueued = enqueue_operator_notification(
        db_path,
        item_id,
        channel=channel,
        target=target,
        reason=reason,
        age_context=age_context,
        deadline_context=deadline_context,
        thread_id=thread_id,
        actor=actor,
    )
    claim_operator_notification(db_path, enqueued["action_id"], actor=actor)
    return execute_operator_notification(db_path, enqueued["action_id"], sender=sender, actor=actor)


def _enqueue_record_operator_action(
    db_path: Path | str,
    item_id: str | None,
    *,
    action_kind: str,
    payload_field_name: str,
    payload_field_value: str,
    actor: str | None = None,
    scope_guard: ScopeGuard | None = None,
) -> dict[str, Any]:
    bootstrap_db(db_path)
    normalized_item_id = _normalize_required_text(item_id, field_name="item_id")
    normalized_value = _normalize_required_text(payload_field_value, field_name=payload_field_name)
    if scope_guard is not None:
        decision = scope_guard.authorize(
            ScopeAction(
                "db_mutation",
                paths=(str(Path(db_path)),),
                description=f"action_runtime.enqueue.{action_kind}",
            )
        )
        if not decision.allowed:
            return {
                "action_id": None,
                "item_id": normalized_item_id,
                "action_type": action_kind,
                "status": "scope_blocked",
                "decision": decision.decision.value,
                "reason": decision.reason,
                "scope_hash": decision.scope_hash,
                "evidence_written": False,
            }
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


def _existing_notification_evidence_id(
    connection: sqlite3.Connection,
    row: sqlite3.Row,
) -> str | None:
    try:
        payload = _decode_action_payload(row["payload_json"])
        evidence_text = _canonical_json(
            {
                "action_id": row["id"],
                "action_kind": NOTIFICATION_ACTION_KIND,
                "channel": _normalize_required_text(payload.get("channel"), field_name="channel"),
                "target": _normalize_required_text(payload.get("target"), field_name="target"),
                "thread_id": _normalize_optional_text(payload.get("thread_id")),
                "message": _normalize_required_text(payload.get("message"), field_name="message"),
                "reason": _normalize_required_text(payload.get("reason"), field_name="reason"),
                "age_context": _normalize_optional_text(payload.get("age_context")),
                "deadline_context": _normalize_optional_text(payload.get("deadline_context")),
                "item_title": _normalize_required_text(payload.get("item_title"), field_name="item_title"),
                "item_state": _normalize_required_text(payload.get("item_state"), field_name="item_state"),
                "outcome": "operator_notification_sent",
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
        (row["item_id"], NOTIFICATION_ACTION_EVIDENCE_URI, NOTIFICATION_ACTION_CREATED_BY, evidence_text),
    ).fetchone()
    return evidence_row["id"] if evidence_row is not None else None


def _fail_action(
    connection: sqlite3.Connection,
    action_id: str,
    *,
    updated_at: str,
    error_message: str,
) -> dict[str, Any]:
    connection.execute(
        """
        UPDATE action_queue
        SET status = ?, completed_at = ?, error_message = ?, updated_at = ?
        WHERE id = ?
        """,
        (_ACTION_STATUS_FAILED, updated_at, error_message, updated_at, action_id),
    )
    connection.commit()
    row = _fetch_action_row(connection, action_id)
    assert row is not None, "failed action update unexpectedly missing"
    return _row_to_action_result(
        row,
        evidence_id=None,
        evidence_written=False,
        error_message=error_message,
    )


def _build_notification_message(
    *,
    item_id: str,
    title: str,
    state: str,
    reason: str,
    age_context: str | None,
    deadline_context: str | None,
) -> str:
    parts = [
        f"ACE alert: {title}",
        f"item_id={item_id}",
        f"state={state}",
        f"reason={reason}",
    ]
    if age_context is not None:
        parts.append(f"age={age_context}")
    if deadline_context is not None:
        parts.append(f"deadline={deadline_context}")
    return "\n".join(parts)


def _openclaw_message_sender(
    *,
    channel: str,
    target: str,
    message: str,
    thread_id: str | None = None,
) -> dict[str, Any]:
    token = _load_openclaw_gateway_token()
    args: dict[str, Any] = {
        "action": "send",
        "channel": channel,
        "target": target,
        "message": message,
    }
    if thread_id is not None:
        args["threadId"] = thread_id

    request_body = json.dumps(
        {
            "tool": "message",
            "args": args,
            "sessionKey": "main",
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        OPENCLAW_GATEWAY_URL,
        data=request_body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip() or f"http {exc.code}"
        raise NotificationDeliveryError(f"gateway message invoke failed: {detail}") from exc
    except urllib.error.URLError as exc:
        raise NotificationDeliveryError(f"gateway message invoke failed: {exc}") from exc
    except TimeoutError as exc:
        raise NotificationDeliveryError("transport timeout: gateway message invoke timed out") from exc

    try:
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        return {
            "ok": True,
            "stdout": raw,
            "note": f"non-json delivery result: {exc}",
        }

    if isinstance(payload, dict) and payload.get("ok") is False:
        error = payload.get("error")
        raise NotificationDeliveryError(f"gateway message invoke failed: {error}")
    if isinstance(payload, dict):
        return payload
    return {"ok": True, "payload": payload}


def _telegram_bot_api_get_me(token: str) -> dict[str, Any]:
    payload = _telegram_bot_api_request(token, "getMe", {})
    result = payload.get("result")
    if not isinstance(result, dict):
        raise JaceStatusDeliveryError("Telegram getMe returned no bot result")
    return result


def _telegram_bot_api_send_message(*, token: str, chat_id: str, text: str) -> dict[str, Any]:
    return _telegram_bot_api_request(
        token,
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": text,
        },
    )


def _telegram_bot_api_request(token: str, method: str, params: dict[str, Any]) -> dict[str, Any]:
    body = urllib.parse.urlencode(params).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20, context=_telegram_ssl_context()) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip() or f"http {exc.code}"
        raise JaceStatusDeliveryError(f"Telegram {method} failed: {detail}") from exc
    except urllib.error.URLError as exc:
        raise JaceStatusDeliveryError(f"Telegram {method} failed: {exc}") from exc
    except TimeoutError as exc:
        raise JaceStatusDeliveryError(f"Telegram {method} timed out") from exc

    try:
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise JaceStatusDeliveryError(f"Telegram {method} returned non-json response") from exc
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        raise JaceStatusDeliveryError(f"Telegram {method} failed: {payload}")
    return payload


def _load_openclaw_gateway_token(config_path: Path | None = None) -> str:
    config_path = config_path or OPENCLAW_CONFIG_PATH
    try:
        config = json.loads(config_path.read_text())
    except FileNotFoundError as exc:
        raise NotificationDeliveryError(f"missing OpenClaw config: {config_path}") from exc
    except json.JSONDecodeError as exc:
        raise NotificationDeliveryError(f"invalid OpenClaw config JSON: {exc}") from exc

    token = (
        config.get("gateway", {})
        .get("auth", {})
        .get("token")
    )
    if not isinstance(token, str) or not token.strip():
        raise NotificationDeliveryError("missing gateway auth token in OpenClaw config")
    return token.strip()


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


def _normalize_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _normalize_required_text(value: Any, *, field_name: str) -> str:
    if value is None:
        raise ValidationError(f"{field_name} is required")
    normalized = str(value).strip()
    if not normalized:
        raise ValidationError(f"{field_name} must not be empty or whitespace-only")
    return normalized
