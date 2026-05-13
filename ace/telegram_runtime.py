from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any
import ssl
from urllib import error, parse, request

STATE_DIR = Path(__file__).resolve().parent / "state"
TELEGRAM_RUNTIME_DB = STATE_DIR / "telegram_runtime.db"
OPENCLAW_MAIN_SESSIONS_DIR = Path.home() / ".openclaw" / "agents" / "main" / "sessions"
OPENCLAW_MAIN_SESSIONS_INDEX = OPENCLAW_MAIN_SESSIONS_DIR / "sessions.json"


def _runtime_db_path() -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return TELEGRAM_RUNTIME_DB


def _connect_runtime_db() -> sqlite3.Connection:
    path = _runtime_db_path()
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS processed_telegram_messages (
            source_session TEXT PRIMARY KEY,
            processed_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS telegram_transport_attempts (
            attempt_id TEXT PRIMARY KEY,
            attempted_at TEXT NOT NULL,
            transport TEXT NOT NULL,
            status TEXT NOT NULL,
            message_count INTEGER NOT NULL DEFAULT 0,
            error_type TEXT,
            error_summary TEXT
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS telegram_transport_offsets (
            transport TEXT PRIMARY KEY,
            next_offset INTEGER NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.commit()
    return connection


def _source_session_for(message: dict[str, Any]) -> str:
    return f"telegram:{message['chat_id']}:{message['message_id']}"


def _env_flag(name: str) -> bool:
    return str(os.environ.get(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _record_transport_attempt(
    *,
    transport: str,
    status: str,
    message_count: int = 0,
    error_type: str | None = None,
    error_summary: str | None = None,
) -> None:
    connection = _connect_runtime_db()
    try:
        attempted_at = _utc_now()
        attempt_id = f"{transport}:{attempted_at}"
        connection.execute(
            """
            INSERT INTO telegram_transport_attempts(
                attempt_id,
                attempted_at,
                transport,
                status,
                message_count,
                error_type,
                error_summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                attempt_id,
                attempted_at,
                transport,
                status,
                int(message_count),
                error_type,
                error_summary,
            ),
        )
        connection.commit()
    finally:
        connection.close()


def _stored_transport_offset(transport: str) -> int | None:
    connection = _connect_runtime_db()
    try:
        row = connection.execute(
            "SELECT next_offset FROM telegram_transport_offsets WHERE transport = ?",
            (transport,),
        ).fetchone()
        if row is None:
            return None
        return int(row["next_offset"])
    finally:
        connection.close()


def _store_transport_offset(*, transport: str, next_offset: int) -> None:
    connection = _connect_runtime_db()
    try:
        connection.execute(
            """
            INSERT INTO telegram_transport_offsets(transport, next_offset, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(transport) DO UPDATE SET
                next_offset = excluded.next_offset,
                updated_at = excluded.updated_at
            """,
            (transport, int(next_offset), _utc_now()),
        )
        connection.commit()
    finally:
        connection.close()


def _normalize_chat_id(raw: Any) -> str:
    value = str(raw or "").strip()
    if value.startswith("telegram:"):
        return value.split(":", 1)[1].strip()
    return value


def _telegram_received_at(raw_date: Any) -> str:
    if isinstance(raw_date, (int, float)):
        return datetime.fromtimestamp(raw_date, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    return str(raw_date or "").strip()


def _target_chat_variants(raw: str) -> set[str]:
    raw = str(raw or "").strip()
    if not raw:
        return set()
    normalized = _normalize_chat_id(raw)
    return {raw, normalized, f"telegram:{normalized}"}


def _normalize_message(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None

    chat_id = str(raw.get("chat_id", "")).strip()
    message_id = str(raw.get("message_id", "")).strip()
    received_at = str(raw.get("received_at", "")).strip()
    text = str(raw.get("text", ""))

    if not chat_id or not message_id or not received_at or not text.strip():
        return None

    normalized = {
        "chat_id": chat_id,
        "message_id": message_id,
        "received_at": received_at,
        "text": text,
    }
    if raw.get("sender_id") is not None:
        normalized["sender_id"] = str(raw.get("sender_id"))
    if raw.get("sender_name") is not None:
        normalized["sender_name"] = str(raw.get("sender_name"))
    return normalized


def _normalize_telegram_update(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None

    message = raw.get("message")
    if not isinstance(message, dict):
        return None

    chat = message.get("chat")
    if not isinstance(chat, dict):
        return None

    sender = message.get("from") if isinstance(message.get("from"), dict) else {}
    sender_name_parts = [
        str(sender.get("first_name", "")).strip(),
        str(sender.get("last_name", "")).strip(),
    ]
    sender_name = " ".join(part for part in sender_name_parts if part).strip() or None
    if not sender_name and sender.get("username") is not None:
        sender_name = str(sender.get("username")).strip() or None

    return _normalize_message(
        {
            "chat_id": chat.get("id"),
            "message_id": message.get("message_id"),
            "received_at": _telegram_received_at(message.get("date")),
            "text": message.get("text", ""),
            "sender_id": sender.get("id"),
            "sender_name": sender_name,
        }
    )


def _load_inbound_messages_from_file(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        return []
    messages: list[dict[str, Any]] = []
    for raw in payload:
        normalized = _normalize_message(raw)
        if normalized is not None:
            messages.append(normalized)
    return messages


def _extract_runtime_context_metadata(content: str) -> dict[str, Any] | None:
    if not content:
        return None
    match = re.search(r"```json\s*(\{.*?\})\s*```", content, re.DOTALL)
    if not match:
        return None
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _resolve_openclaw_session_file() -> Path | None:
    explicit = os.environ.get("ACE_OPENCLAW_SESSION_FILE", "").strip()
    if explicit:
        path = Path(explicit)
        return path if path.exists() else None

    target_chat = os.environ.get("ACE_OPENCLAW_CHAT_ID", "").strip()
    if not target_chat or not OPENCLAW_MAIN_SESSIONS_INDEX.exists():
        return None

    variants = _target_chat_variants(target_chat)
    try:
        sessions = json.loads(OPENCLAW_MAIN_SESSIONS_INDEX.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(sessions, dict):
        return None

    candidates: list[tuple[int, Path]] = []
    for entry in sessions.values():
        if not isinstance(entry, dict):
            continue
        delivery_to = str((entry.get("deliveryContext") or {}).get("to") or entry.get("lastTo") or "").strip()
        if delivery_to not in variants:
            continue
        session_file = entry.get("sessionFile")
        if not session_file:
            continue
        path = Path(str(session_file))
        if not path.exists():
            continue
        candidates.append((int(entry.get("updatedAt") or 0), path))

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _load_inbound_messages_from_openclaw_session(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    runtime_context_by_parent: dict[str, dict[str, Any]] = {}
    entries: list[dict[str, Any]] = []
    for line in lines:
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        entries.append(obj)
        if obj.get("type") != "custom_message":
            continue
        if obj.get("customType") != "openclaw.runtime-context":
            continue
        parent_id = str(obj.get("parentId") or "").strip()
        metadata = _extract_runtime_context_metadata(str(obj.get("content") or ""))
        if parent_id and metadata:
            runtime_context_by_parent[parent_id] = metadata

    messages: list[dict[str, Any]] = []
    for obj in entries:
        if obj.get("type") != "message":
            continue
        message = obj.get("message")
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        content = message.get("content")
        if not isinstance(content, list) or not content or not isinstance(content[0], dict):
            continue
        text = str(content[0].get("text") or "")
        stripped_text = text.strip()
        if not stripped_text:
            continue
        if stripped_text.startswith("[Inter-session message]") or "<<<BEGIN_OPENCLAW_INTERNAL_CONTEXT>>>" in stripped_text:
            continue

        metadata = runtime_context_by_parent.get(str(obj.get("id") or "").strip())
        if not metadata:
            continue

        normalized = _normalize_message(
            {
                "chat_id": _normalize_chat_id(metadata.get("chat_id")),
                "message_id": metadata.get("message_id"),
                "received_at": metadata.get("timestamp"),
                "text": text,
                "sender_id": metadata.get("sender_id"),
                "sender_name": metadata.get("sender"),
            }
        )
        if normalized is not None:
            messages.append(normalized)
    return messages


def _telegram_ssl_context() -> ssl.SSLContext:
    cafile = os.environ.get("ACE_TELEGRAM_CA_BUNDLE", "").strip()
    if cafile:
        return ssl.create_default_context(cafile=cafile)

    try:
        import certifi  # type: ignore[import-not-found]
    except Exception:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


def _load_openclaw_telegram_bot_token() -> str:
    if not _env_flag("ACE_USE_OPENCLAW_TELEGRAM_BOT_TOKEN"):
        return ""

    config_path = Path(os.environ.get("ACE_OPENCLAW_CONFIG_PATH", "~/.openclaw/openclaw.json")).expanduser()
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _record_transport_attempt(
            transport="telegram_bot_api",
            status="disabled",
            error_type=exc.__class__.__name__,
            error_summary=f"OpenClaw Telegram token source unavailable: {config_path}",
        )
        return ""

    token = str(((payload.get("channels") or {}).get("telegram") or {}).get("botToken") or "").strip()
    if not token:
        _record_transport_attempt(
            transport="telegram_bot_api",
            status="disabled",
            error_type="missing_openclaw_bot_token",
            error_summary="ACE_USE_OPENCLAW_TELEGRAM_BOT_TOKEN is enabled but channels.telegram.botToken is not configured.",
        )
        return ""
    return token


def _load_inbound_messages_from_telegram(token: str) -> list[dict[str, Any]]:
    timeout_seconds = str(os.environ.get("ACE_TELEGRAM_GET_UPDATES_TIMEOUT", "30")).strip() or "30"
    query: dict[str, str] = {"timeout": timeout_seconds}
    checkpoint_offset = os.environ.get("ACE_TELEGRAM_UPDATE_OFFSET", "").strip()
    if not checkpoint_offset:
        stored_offset = _stored_transport_offset("telegram_bot_api")
        if stored_offset is not None:
            checkpoint_offset = str(stored_offset)
    if checkpoint_offset:
        query["offset"] = checkpoint_offset
    encoded = parse.urlencode(query)
    url = f"https://api.telegram.org/bot{token}/getUpdates?{encoded}"
    try:
        with request.urlopen(url, timeout=45, context=_telegram_ssl_context()) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (error.URLError, ssl.SSLError) as exc:
        _record_transport_attempt(
            transport="telegram_bot_api",
            status="error",
            error_type=exc.__class__.__name__,
            error_summary=str(exc),
        )
        return []
    except json.JSONDecodeError as exc:
        _record_transport_attempt(
            transport="telegram_bot_api",
            status="error",
            error_type=exc.__class__.__name__,
            error_summary=str(exc),
        )
        return []

    if not isinstance(payload, dict) or payload.get("ok") is not True:
        _record_transport_attempt(
            transport="telegram_bot_api",
            status="error",
            error_type="telegram_api_not_ok",
            error_summary=str(payload)[:500],
        )
        return []

    results = payload.get("result")
    if not isinstance(results, list):
        _record_transport_attempt(
            transport="telegram_bot_api",
            status="error",
            error_type="telegram_api_result_not_list",
            error_summary=str(type(results).__name__),
        )
        return []

    update_ids = [raw.get("update_id") for raw in results if isinstance(raw, dict) and isinstance(raw.get("update_id"), int)]
    if update_ids:
        _store_transport_offset(transport="telegram_bot_api", next_offset=max(update_ids) + 1)

    messages: list[dict[str, Any]] = []
    for raw in results:
        normalized = _normalize_telegram_update(raw)
        if normalized is not None:
            messages.append(normalized)
    _record_transport_attempt(
        transport="telegram_bot_api",
        status="ok",
        message_count=len(messages),
    )
    return messages


def fetch_unprocessed_telegram_messages() -> list[dict[str, Any]]:
    session_file = _resolve_openclaw_session_file()
    bootstrap_existing = _env_flag("ACE_TELEGRAM_BOOTSTRAP_EXISTING_AS_PROCESSED")
    bootstrap_transport = ""
    if session_file is not None:
        messages = _load_inbound_messages_from_openclaw_session(session_file)
        bootstrap_transport = "openclaw_session"
    else:
        token = os.environ.get("ACE_TELEGRAM_BOT_TOKEN", "").strip() or _load_openclaw_telegram_bot_token()
        if token:
            has_explicit_or_stored_offset = bool(os.environ.get("ACE_TELEGRAM_UPDATE_OFFSET", "").strip()) or _stored_transport_offset("telegram_bot_api") is not None
            bootstrap_transport = "telegram_bot_api" if not has_explicit_or_stored_offset else ""
            messages = _load_inbound_messages_from_telegram(token)
        else:
            inbox_path = os.environ.get("ACE_TELEGRAM_INBOX_PATH", "").strip()
            if not inbox_path:
                _record_transport_attempt(
                    transport="telegram_bot_api",
                    status="disabled",
                    error_type="missing_bot_token",
                    error_summary="ACE_TELEGRAM_BOT_TOKEN is not configured and no local Telegram inbox source is configured.",
                )
                return []
            messages = _load_inbound_messages_from_file(Path(inbox_path))
            bootstrap_transport = "inbox_file"

    configured_chat_id = os.environ.get("ACE_TELEGRAM_CHAT_ID", "").strip() or os.environ.get("ACE_OPENCLAW_CHAT_ID", "").strip()
    if configured_chat_id:
        normalized_chat_id = _normalize_chat_id(configured_chat_id)
        messages = [m for m in messages if _normalize_chat_id(m["chat_id"]) == normalized_chat_id]

    connection = _connect_runtime_db()
    try:
        seen = {row[0] for row in connection.execute("SELECT source_session FROM processed_telegram_messages").fetchall()}
        should_bootstrap = bootstrap_existing and (not seen or bootstrap_transport == "telegram_bot_api")
        if should_bootstrap:
            processed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            for message in messages:
                connection.execute(
                    "INSERT OR IGNORE INTO processed_telegram_messages(source_session, processed_at) VALUES (?, ?)",
                    (_source_session_for(message), processed_at),
                )
            connection.commit()
            return []
    finally:
        connection.close()

    return [message for message in messages if _source_session_for(message) not in seen]


def mark_telegram_message_processed(*, chat_id: str, message_id: str, processed_at: str) -> None:
    message = {
        "chat_id": str(chat_id).strip(),
        "message_id": str(message_id).strip(),
    }
    source_session = _source_session_for(message)
    connection = _connect_runtime_db()
    try:
        connection.execute(
            "INSERT OR REPLACE INTO processed_telegram_messages(source_session, processed_at) VALUES (?, ?)",
            (source_session, str(processed_at).strip()),
        )
        connection.commit()
    finally:
        connection.close()
