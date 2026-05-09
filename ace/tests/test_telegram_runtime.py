from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import ssl
from urllib import error
import json as jsonlib

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

    def test_fetch_reads_real_telegram_updates_when_bot_token_configured(self) -> None:
        payload = {
            "ok": True,
            "result": [
                {
                    "update_id": 1,
                    "message": {
                        "message_id": 42,
                        "date": 1746720000,
                        "text": "Can you check this now?",
                        "chat": {"id": 7529788084},
                        "from": {"id": 7529788084, "first_name": "Andrew", "last_name": "Pilson"},
                    },
                }
            ],
        }

        fake_response = MagicMock()
        fake_response.read.return_value = json.dumps(payload).encode("utf-8")
        fake_context = MagicMock()
        fake_context.__enter__.return_value = fake_response
        fake_context.__exit__.return_value = False

        with (
            patch.dict(os.environ, {
                "ACE_TELEGRAM_BOT_TOKEN": "bot-token",
                "ACE_TELEGRAM_CHAT_ID": "7529788084",
            }, clear=False),
            patch.object(telegram_runtime, "STATE_DIR", self.state_dir),
            patch.object(telegram_runtime, "TELEGRAM_RUNTIME_DB", self.runtime_db),
            patch("ace.telegram_runtime.request.urlopen", return_value=fake_context) as mocked_urlopen,
            patch("ace.telegram_runtime._telegram_ssl_context", return_value=ssl.create_default_context()),
        ):
            messages = telegram_runtime.fetch_unprocessed_telegram_messages()

        mocked_urlopen.assert_called_once()
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["chat_id"], "7529788084")
        self.assertEqual(messages[0]["message_id"], "42")
        self.assertEqual(messages[0]["text"], "Can you check this now?")
        self.assertEqual(messages[0]["sender_id"], "7529788084")
        self.assertEqual(messages[0]["sender_name"], "Andrew Pilson")
        self.assertTrue(messages[0]["received_at"].endswith("Z"))

    def test_fetch_real_telegram_updates_filters_non_text_and_non_message_updates(self) -> None:
        payload = {
            "ok": True,
            "result": [
                {"update_id": 1, "edited_message": {"message_id": 7}},
                {
                    "update_id": 2,
                    "message": {
                        "message_id": 8,
                        "date": 1746720000,
                        "text": "   ",
                        "chat": {"id": 7529788084},
                    },
                },
                {
                    "update_id": 3,
                    "message": {
                        "message_id": 9,
                        "date": 1746720001,
                        "text": "Please review this",
                        "chat": {"id": 7529788084},
                    },
                },
            ],
        }

        fake_response = MagicMock()
        fake_response.read.return_value = json.dumps(payload).encode("utf-8")
        fake_context = MagicMock()
        fake_context.__enter__.return_value = fake_response
        fake_context.__exit__.return_value = False

        with (
            patch.dict(os.environ, {"ACE_TELEGRAM_BOT_TOKEN": "bot-token"}, clear=False),
            patch.object(telegram_runtime, "STATE_DIR", self.state_dir),
            patch.object(telegram_runtime, "TELEGRAM_RUNTIME_DB", self.runtime_db),
            patch("ace.telegram_runtime.request.urlopen", return_value=fake_context),
            patch("ace.telegram_runtime._telegram_ssl_context", return_value=ssl.create_default_context()),
        ):
            messages = telegram_runtime.fetch_unprocessed_telegram_messages()

        self.assertEqual([message["message_id"] for message in messages], ["9"])

    def test_fetch_real_telegram_updates_returns_empty_on_ssl_failure(self) -> None:
        with (
            patch.dict(os.environ, {"ACE_TELEGRAM_BOT_TOKEN": "bot-token"}, clear=False),
            patch.object(telegram_runtime, "STATE_DIR", self.state_dir),
            patch.object(telegram_runtime, "TELEGRAM_RUNTIME_DB", self.runtime_db),
            patch("ace.telegram_runtime.request.urlopen", side_effect=error.URLError("ssl failed")),
            patch("ace.telegram_runtime._telegram_ssl_context", side_effect=ssl.SSLError("bad cert")),
        ):
            messages = telegram_runtime.fetch_unprocessed_telegram_messages()

        self.assertEqual(messages, [])

    def test_fetch_reads_openclaw_session_stream_for_exact_chat(self) -> None:
        sessions_dir = Path(self.tempdir.name) / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        session_file = sessions_dir / "main.jsonl"
        sessions_index = sessions_dir / "sessions.json"

        user_message_id = "user-msg-1"
        lines = [
            {
                "type": "message",
                "id": user_message_id,
                "message": {"role": "user", "content": [{"type": "text", "text": "Can you check this session path?"}]},
            },
            {
                "type": "custom_message",
                "customType": "openclaw.runtime-context",
                "parentId": user_message_id,
                "content": (
                    "Conversation info (untrusted metadata):\n```json\n"
                    + jsonlib.dumps(
                        {
                            "chat_id": "telegram:7529788084",
                            "message_id": "33548",
                            "sender_id": "7529788084",
                            "sender": "Andrew Pilson",
                            "timestamp": "Fri 2026-05-08 17:21 PDT",
                        }
                    )
                    + "\n```"
                ),
            },
            {
                "type": "message",
                "id": "internal-msg-1",
                "message": {
                    "role": "user",
                    "content": [{"type": "text", "text": "[Inter-session message] sourceSession=agent:main:subagent:abc"}],
                },
            },
            {
                "type": "custom_message",
                "customType": "openclaw.runtime-context",
                "parentId": "internal-msg-1",
                "content": (
                    "Conversation info (untrusted metadata):\n```json\n"
                    + jsonlib.dumps(
                        {
                            "chat_id": "telegram:7529788084",
                            "message_id": "33549",
                            "sender_id": "7529788084",
                            "sender": "Andrew Pilson",
                            "timestamp": "Fri 2026-05-08 17:22 PDT",
                        }
                    )
                    + "\n```"
                ),
            },
            {
                "type": "message",
                "id": "other-chat-msg",
                "message": {"role": "user", "content": [{"type": "text", "text": "Can you check the wrong chat?"}]},
            },
            {
                "type": "custom_message",
                "customType": "openclaw.runtime-context",
                "parentId": "other-chat-msg",
                "content": (
                    "Conversation info (untrusted metadata):\n```json\n"
                    + jsonlib.dumps(
                        {
                            "chat_id": "telegram:999",
                            "message_id": "99901",
                            "sender_id": "999",
                            "sender": "Other User",
                            "timestamp": "Fri 2026-05-08 17:23 PDT",
                        }
                    )
                    + "\n```"
                ),
            },
        ]
        session_file.write_text("\n".join(jsonlib.dumps(line) for line in lines) + "\n", encoding="utf-8")
        sessions_index.write_text(
            jsonlib.dumps(
                {
                    "agent:main:main": {
                        "updatedAt": 1,
                        "deliveryContext": {"to": "telegram:7529788084", "channel": "telegram"},
                        "sessionFile": str(session_file),
                    }
                }
            ),
            encoding="utf-8",
        )

        with (
            patch.dict(os.environ, {"ACE_OPENCLAW_CHAT_ID": "telegram:7529788084"}, clear=False),
            patch.object(telegram_runtime, "STATE_DIR", self.state_dir),
            patch.object(telegram_runtime, "TELEGRAM_RUNTIME_DB", self.runtime_db),
            patch.object(telegram_runtime, "OPENCLAW_MAIN_SESSIONS_INDEX", sessions_index),
            patch.object(telegram_runtime, "OPENCLAW_MAIN_SESSIONS_DIR", sessions_dir),
        ):
            messages = telegram_runtime.fetch_unprocessed_telegram_messages()

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["chat_id"], "7529788084")
        self.assertEqual(messages[0]["message_id"], "33548")
        self.assertEqual(messages[0]["sender_id"], "7529788084")
        self.assertEqual(messages[0]["sender_name"], "Andrew Pilson")
        self.assertEqual(messages[0]["text"], "Can you check this session path?")
        self.assertEqual(messages[0]["received_at"], "Fri 2026-05-08 17:21 PDT")

    def test_fetch_prefers_explicit_openclaw_session_file(self) -> None:
        session_file = Path(self.tempdir.name) / "explicit.jsonl"
        line_id = "user-msg-explicit"
        lines = [
            {
                "type": "message",
                "id": line_id,
                "message": {"role": "user", "content": [{"type": "text", "text": "Please use explicit file"}]},
            },
            {
                "type": "custom_message",
                "customType": "openclaw.runtime-context",
                "parentId": line_id,
                "content": (
                    "Conversation info (untrusted metadata):\n```json\n"
                    + jsonlib.dumps(
                        {
                            "chat_id": "telegram:7529788084",
                            "message_id": "33550",
                            "sender_id": "7529788084",
                            "sender": "Andrew Pilson",
                            "timestamp": "Fri 2026-05-08 17:24 PDT",
                        }
                    )
                    + "\n```"
                ),
            },
        ]
        session_file.write_text("\n".join(jsonlib.dumps(line) for line in lines) + "\n", encoding="utf-8")

        with (
            patch.dict(
                os.environ,
                {
                    "ACE_OPENCLAW_SESSION_FILE": str(session_file),
                    "ACE_OPENCLAW_CHAT_ID": "telegram:7529788084",
                },
                clear=False,
            ),
            patch.object(telegram_runtime, "STATE_DIR", self.state_dir),
            patch.object(telegram_runtime, "TELEGRAM_RUNTIME_DB", self.runtime_db),
        ):
            messages = telegram_runtime.fetch_unprocessed_telegram_messages()

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["message_id"], "33550")


if __name__ == "__main__":
    unittest.main()
