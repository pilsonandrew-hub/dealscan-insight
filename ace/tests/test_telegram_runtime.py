from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ace import telegram_runtime


class TelegramRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.state_dir = Path(self.tempdir.name) / "state"
        self.runtime_db = self.state_dir / "telegram_runtime.db"
        self.inbox_path = Path(self.tempdir.name) / "telegram_inbox.json"

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_fetch_returns_empty_when_inbox_path_not_configured(self) -> None:
        with patch.dict(os.environ, {}, clear=False), \
             patch.object(telegram_runtime, "STATE_DIR", self.state_dir), \
             patch.object(telegram_runtime, "TELEGRAM_RUNTIME_DB", self.runtime_db):
            os.environ.pop("ACE_TELEGRAM_INBOX_PATH", None)
            self.assertEqual(telegram_runtime.fetch_unprocessed_telegram_messages(), [])

    def test_invalid_messages_are_filtered(self) -> None:
        self.inbox_path.write_text(json.dumps([
            {"chat_id": "", "message_id": "bad-1", "text": "hello", "received_at": "2026-05-08T17:00:00Z"},
            {"chat_id": "7529788084", "message_id": "good-1", "text": "Can you check this", "received_at": "2026-05-08T17:01:00Z"},
            {"not": "a message"},
        ]), encoding="utf-8")

        with patch.dict(os.environ, {"ACE_TELEGRAM_INBOX_PATH": str(self.inbox_path)}, clear=False), \
             patch.object(telegram_runtime, "STATE_DIR", self.state_dir), \
             patch.object(telegram_runtime, "TELEGRAM_RUNTIME_DB", self.runtime_db):
            messages = telegram_runtime.fetch_unprocessed_telegram_messages()

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["message_id"], "good-1")

    def test_configured_chat_id_filters_messages(self) -> None:
        self.inbox_path.write_text(json.dumps([
            {"chat_id": "7529788084", "message_id": "good-1", "text": "Can you check this", "received_at": "2026-05-08T17:01:00Z"},
            {"chat_id": "999", "message_id": "other-1", "text": "Can you check that", "received_at": "2026-05-08T17:02:00Z"},
        ]), encoding="utf-8")

        with patch.dict(os.environ, {
            "ACE_TELEGRAM_INBOX_PATH": str(self.inbox_path),
            "ACE_TELEGRAM_CHAT_ID": "7529788084",
        }, clear=False), \
             patch.object(telegram_runtime, "STATE_DIR", self.state_dir), \
             patch.object(telegram_runtime, "TELEGRAM_RUNTIME_DB", self.runtime_db):
            messages = telegram_runtime.fetch_unprocessed_telegram_messages()

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["chat_id"], "7529788084")

    def test_processed_messages_are_deduped(self) -> None:
        self.inbox_path.write_text(json.dumps([
            {"chat_id": "7529788084", "message_id": "good-1", "text": "Can you check this", "received_at": "2026-05-08T17:01:00Z"},
        ]), encoding="utf-8")

        with patch.dict(os.environ, {"ACE_TELEGRAM_INBOX_PATH": str(self.inbox_path)}, clear=False), \
             patch.object(telegram_runtime, "STATE_DIR", self.state_dir), \
             patch.object(telegram_runtime, "TELEGRAM_RUNTIME_DB", self.runtime_db):
            first = telegram_runtime.fetch_unprocessed_telegram_messages()
            self.assertEqual(len(first), 1)
            telegram_runtime.mark_telegram_message_processed(
                chat_id="7529788084",
                message_id="good-1",
                processed_at="2026-05-08T17:01:00Z",
            )
            second = telegram_runtime.fetch_unprocessed_telegram_messages()

        self.assertEqual(second, [])


if __name__ == "__main__":
    unittest.main()
