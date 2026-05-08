from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

STATE_DIR = Path(__file__).resolve().parent / "state"
TELEGRAM_RUNTIME_DB = STATE_DIR / "telegram_runtime.db"


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
    connection.commit()
    return connection


def _source_session_for(message: dict[str, Any]) -> str:
    return f"telegram:{message['chat_id']}:{message['message_id']}"


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


def fetch_unprocessed_telegram_messages() -> list[dict[str, Any]]:
    inbox_path = os.environ.get("ACE_TELEGRAM_INBOX_PATH", "").strip()
    if not inbox_path:
        return []

    messages = _load_inbound_messages_from_file(Path(inbox_path))
    configured_chat_id = os.environ.get("ACE_TELEGRAM_CHAT_ID", "").strip()
    if configured_chat_id:
        messages = [m for m in messages if m["chat_id"] == configured_chat_id]

    with _connect_runtime_db() as connection:
        seen = {row[0] for row in connection.execute("SELECT source_session FROM processed_telegram_messages").fetchall()}

    return [message for message in messages if _source_session_for(message) not in seen]


def mark_telegram_message_processed(*, chat_id: str, message_id: str, processed_at: str) -> None:
    message = {
        "chat_id": str(chat_id).strip(),
        "message_id": str(message_id).strip(),
    }
    source_session = _source_session_for(message)
    with _connect_runtime_db() as connection:
        connection.execute(
            "INSERT OR REPLACE INTO processed_telegram_messages(source_session, processed_at) VALUES (?, ?)",
            (source_session, str(processed_at).strip()),
        )
        connection.commit()
