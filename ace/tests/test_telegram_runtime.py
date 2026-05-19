from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
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
        self._saved_ace_env = {
            key: value
            for key, value in os.environ.items()
            if key.startswith("ACE_TELEGRAM_") or key.startswith("ACE_OPENCLAW_") or key == "ACE_USE_OPENCLAW_TELEGRAM_BOT_TOKEN"
        }
        for key in self._saved_ace_env:
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        for key in list(os.environ):
            if key.startswith("ACE_TELEGRAM_") or key.startswith("ACE_OPENCLAW_") or key == "ACE_USE_OPENCLAW_TELEGRAM_BOT_TOKEN":
                os.environ.pop(key, None)
        os.environ.update(self._saved_ace_env)
        self.tempdir.cleanup()


    def test_load_ace_telegram_env_file_fills_missing_ace_values(self) -> None:
        env_file = Path(self.tempdir.name) / "ace-telegram.env"
        env_file.write_text(
            "ACE_TELEGRAM_TRANSPORT=telegram_bot_api\n"
            "ACE_TELEGRAM_BOT_TOKEN=file-token\n"
            "ACE_TELEGRAM_CHAT_ID=7529788084\n"
            "OTHER_TOKEN=must-not-load\n",
            encoding="utf-8",
        )

        with patch.dict(os.environ, {"ACE_TELEGRAM_ENV_FILE": str(env_file)}, clear=True):
            loaded = telegram_runtime.load_ace_telegram_env_file()
            self.assertTrue(loaded)
            self.assertEqual(os.environ["ACE_TELEGRAM_TRANSPORT"], "telegram_bot_api")
            self.assertEqual(os.environ["ACE_TELEGRAM_BOT_TOKEN"], "file-token")
            self.assertEqual(os.environ["ACE_TELEGRAM_CHAT_ID"], "7529788084")
            self.assertNotIn("OTHER_TOKEN", os.environ)

    def test_load_ace_telegram_env_file_does_not_override_process_env(self) -> None:
        env_file = Path(self.tempdir.name) / "ace-telegram.env"
        env_file.write_text("ACE_TELEGRAM_BOT_TOKEN=file-token\n", encoding="utf-8")

        with patch.dict(os.environ, {
            "ACE_TELEGRAM_ENV_FILE": str(env_file),
            "ACE_TELEGRAM_BOT_TOKEN": "process-token",
        }, clear=True):
            loaded = telegram_runtime.load_ace_telegram_env_file()
            self.assertFalse(loaded)
            self.assertEqual(os.environ["ACE_TELEGRAM_BOT_TOKEN"], "process-token")

    def test_fetch_returns_empty_when_inbox_path_not_configured(self) -> None:
        with patch.dict(os.environ, {}, clear=False), \
             patch.object(telegram_runtime, "STATE_DIR", self.state_dir), \
             patch.object(telegram_runtime, "TELEGRAM_RUNTIME_DB", self.runtime_db):
            os.environ.pop("ACE_TELEGRAM_BOT_TOKEN", None)
            os.environ.pop("ACE_OPENCLAW_CHAT_ID", None)
            os.environ.pop("ACE_TELEGRAM_INBOX_PATH", None)
            self.assertEqual(telegram_runtime.fetch_unprocessed_telegram_messages(), [])

            with closing(sqlite3.connect(self.runtime_db)) as connection:
                attempt = connection.execute(
                    "SELECT transport, status, error_type, error_summary FROM telegram_transport_attempts"
                ).fetchone()

        self.assertEqual(attempt[0], "telegram_bot_api")
        self.assertEqual(attempt[1], "disabled")
        self.assertEqual(attempt[2], "missing_bot_token")
        self.assertIn("ACE_TELEGRAM_BOT_TOKEN", attempt[3])

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

    def test_bootstrap_existing_messages_marks_backlog_processed_without_returning_it(self) -> None:
        self.inbox_path.write_text(json.dumps([
            {"chat_id": "7529788084", "message_id": "old-1", "text": "Can you check old backlog?", "received_at": "2026-05-08T17:01:00Z"},
            {"chat_id": "7529788084", "message_id": "old-2", "text": "Please review old backlog", "received_at": "2026-05-08T17:02:00Z"},
        ]), encoding="utf-8")

        with patch.dict(os.environ, {
            "ACE_TELEGRAM_INBOX_PATH": str(self.inbox_path),
            "ACE_TELEGRAM_BOOTSTRAP_EXISTING_AS_PROCESSED": "true",
        }, clear=False), \
             patch.object(telegram_runtime, "STATE_DIR", self.state_dir), \
             patch.object(telegram_runtime, "TELEGRAM_RUNTIME_DB", self.runtime_db):
            messages = telegram_runtime.fetch_unprocessed_telegram_messages()

        self.assertEqual(messages, [])
        with closing(sqlite3.connect(self.runtime_db)) as connection:
            rows = connection.execute(
                "SELECT source_session FROM processed_telegram_messages ORDER BY source_session"
            ).fetchall()
        self.assertEqual([row[0] for row in rows], ["telegram:7529788084:old-1", "telegram:7529788084:old-2"])

    def test_bootstrap_existing_messages_only_runs_when_checkpoint_is_empty(self) -> None:
        self.inbox_path.write_text(json.dumps([
            {"chat_id": "7529788084", "message_id": "seen-1", "text": "Can you check seen?", "received_at": "2026-05-08T17:01:00Z"},
            {"chat_id": "7529788084", "message_id": "new-1", "text": "Can you check new?", "received_at": "2026-05-08T17:02:00Z"},
        ]), encoding="utf-8")

        with patch.dict(os.environ, {"ACE_TELEGRAM_INBOX_PATH": str(self.inbox_path)}, clear=False), \
             patch.object(telegram_runtime, "STATE_DIR", self.state_dir), \
             patch.object(telegram_runtime, "TELEGRAM_RUNTIME_DB", self.runtime_db):
            telegram_runtime.mark_telegram_message_processed(
                chat_id="7529788084",
                message_id="seen-1",
                processed_at="2026-05-08T17:01:00Z",
            )

        with patch.dict(os.environ, {
            "ACE_TELEGRAM_INBOX_PATH": str(self.inbox_path),
            "ACE_TELEGRAM_BOOTSTRAP_EXISTING_AS_PROCESSED": "true",
        }, clear=False), \
             patch.object(telegram_runtime, "STATE_DIR", self.state_dir), \
             patch.object(telegram_runtime, "TELEGRAM_RUNTIME_DB", self.runtime_db):
            messages = telegram_runtime.fetch_unprocessed_telegram_messages()

        self.assertEqual([message["message_id"] for message in messages], ["new-1"])

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
        self.assertIn("timeout=30", mocked_urlopen.call_args.args[0])
        self.assertNotIn("offset=", mocked_urlopen.call_args.args[0])
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["chat_id"], "7529788084")
        self.assertEqual(messages[0]["message_id"], "42")
        self.assertEqual(messages[0]["text"], "Can you check this now?")
        self.assertEqual(messages[0]["sender_id"], "7529788084")
        self.assertEqual(messages[0]["sender_name"], "Andrew Pilson")
        self.assertTrue(messages[0]["received_at"].endswith("Z"))
        with closing(sqlite3.connect(self.runtime_db)) as connection:
            attempt = connection.execute(
                "SELECT transport, status, message_count, error_type FROM telegram_transport_attempts"
            ).fetchone()
        self.assertEqual(tuple(attempt), ("telegram_bot_api", "ok", 1, None))

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
            patch.dict(os.environ, {
                "ACE_TELEGRAM_BOT_TOKEN": "bot-token",
                "ACE_TELEGRAM_UPDATE_OFFSET": "123",
            }, clear=False),
            patch.object(telegram_runtime, "STATE_DIR", self.state_dir),
            patch.object(telegram_runtime, "TELEGRAM_RUNTIME_DB", self.runtime_db),
            patch("ace.telegram_runtime.request.urlopen", return_value=fake_context) as mocked_urlopen,
            patch("ace.telegram_runtime._telegram_ssl_context", return_value=ssl.create_default_context()),
        ):
            messages = telegram_runtime.fetch_unprocessed_telegram_messages()

        self.assertEqual([message["message_id"] for message in messages], ["9"])
        self.assertIn("offset=123", mocked_urlopen.call_args.args[0])

    def test_fetch_real_telegram_updates_persists_next_update_offset(self) -> None:
        payload = {
            "ok": True,
            "result": [
                {
                    "update_id": 100,
                    "message": {
                        "message_id": 10,
                        "date": 1746720000,
                        "text": "Can you check offset persistence?",
                        "chat": {"id": 7529788084},
                    },
                },
                {
                    "update_id": 105,
                    "message": {
                        "message_id": 11,
                        "date": 1746720001,
                        "text": "Please verify next offset",
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

        self.assertEqual([message["message_id"] for message in messages], ["10", "11"])
        with closing(sqlite3.connect(self.runtime_db)) as connection:
            row = connection.execute(
                "SELECT next_offset FROM telegram_transport_offsets WHERE transport = ?",
                ("telegram_bot_api",),
            ).fetchone()
        self.assertEqual(row[0], 106)

    def test_fetch_real_telegram_updates_uses_persisted_offset_when_env_offset_absent(self) -> None:
        first_payload = {"ok": True, "result": [{"update_id": 12, "edited_message": {"message_id": 99}}]}
        second_payload = {"ok": True, "result": []}

        first_response = MagicMock()
        first_response.read.return_value = json.dumps(first_payload).encode("utf-8")
        first_context = MagicMock()
        first_context.__enter__.return_value = first_response
        first_context.__exit__.return_value = False

        second_response = MagicMock()
        second_response.read.return_value = json.dumps(second_payload).encode("utf-8")
        second_context = MagicMock()
        second_context.__enter__.return_value = second_response
        second_context.__exit__.return_value = False

        with (
            patch.dict(os.environ, {"ACE_TELEGRAM_BOT_TOKEN": "bot-token"}, clear=False),
            patch.object(telegram_runtime, "STATE_DIR", self.state_dir),
            patch.object(telegram_runtime, "TELEGRAM_RUNTIME_DB", self.runtime_db),
            patch("ace.telegram_runtime.request.urlopen", side_effect=[first_context, second_context]) as mocked_urlopen,
            patch("ace.telegram_runtime._telegram_ssl_context", return_value=ssl.create_default_context()),
        ):
            self.assertEqual(telegram_runtime.fetch_unprocessed_telegram_messages(), [])
            self.assertEqual(telegram_runtime.fetch_unprocessed_telegram_messages(), [])

        self.assertNotIn("offset=", mocked_urlopen.call_args_list[0].args[0])
        self.assertIn("offset=13", mocked_urlopen.call_args_list[1].args[0])

    def test_fetch_real_telegram_updates_returns_empty_on_ssl_failure(self) -> None:
        with (
            patch.dict(os.environ, {"ACE_TELEGRAM_BOT_TOKEN": "bot-token"}, clear=False),
            patch.object(telegram_runtime, "STATE_DIR", self.state_dir),
            patch.object(telegram_runtime, "TELEGRAM_RUNTIME_DB", self.runtime_db),
            patch("ace.telegram_runtime.request.urlopen", side_effect=error.URLError("ssl failed")),
            patch("ace.telegram_runtime._telegram_ssl_context", return_value=ssl.create_default_context()),
        ):
            messages = telegram_runtime.fetch_unprocessed_telegram_messages()

        self.assertEqual(messages, [])
        with closing(sqlite3.connect(self.runtime_db)) as connection:
            attempt = connection.execute(
                "SELECT transport, status, message_count, error_type, error_summary FROM telegram_transport_attempts"
            ).fetchone()
        self.assertEqual(attempt[0], "telegram_bot_api")
        self.assertEqual(attempt[1], "error")
        self.assertEqual(attempt[2], 0)
        self.assertEqual(attempt[3], "URLError")
        self.assertIn("ssl failed", attempt[4])


    def test_fetch_real_telegram_updates_records_conflict_without_ingesting(self) -> None:
        conflict = error.HTTPError(
            url="https://api.telegram.org/botx/getUpdates",
            code=409,
            msg="Conflict",
            hdrs=None,
            fp=None,
        )
        with (
            patch.dict(os.environ, {"ACE_TELEGRAM_BOT_TOKEN": "bot-token"}, clear=False),
            patch.object(telegram_runtime, "STATE_DIR", self.state_dir),
            patch.object(telegram_runtime, "TELEGRAM_RUNTIME_DB", self.runtime_db),
            patch("ace.telegram_runtime.request.urlopen", side_effect=conflict),
            patch("ace.telegram_runtime._telegram_ssl_context", return_value=ssl.create_default_context()),
        ):
            messages = telegram_runtime.fetch_unprocessed_telegram_messages()

        self.assertEqual(messages, [])
        with closing(sqlite3.connect(self.runtime_db)) as connection:
            attempt = connection.execute(
                "SELECT transport, status, message_count, error_type, error_summary FROM telegram_transport_attempts"
            ).fetchone()
            offset_count = connection.execute("SELECT COUNT(*) FROM telegram_transport_offsets").fetchone()[0]
        self.assertEqual(tuple(attempt[:4]), ("telegram_bot_api", "error", 0, "telegram_conflict"))
        self.assertIn("another consumer", attempt[4])
        self.assertEqual(offset_count, 0)

    def test_fetch_real_telegram_updates_can_disable_long_polling_for_proofs(self) -> None:
        payload = {"ok": True, "result": []}
        fake_response = MagicMock()
        fake_response.read.return_value = json.dumps(payload).encode("utf-8")
        fake_context = MagicMock()
        fake_context.__enter__.return_value = fake_response
        fake_context.__exit__.return_value = False

        with (
            patch.dict(os.environ, {
                "ACE_TELEGRAM_BOT_TOKEN": "bot-token",
                "ACE_TELEGRAM_GET_UPDATES_TIMEOUT": "30",
                "ACE_TELEGRAM_DISABLE_LONG_POLL": "true",
            }, clear=False),
            patch.object(telegram_runtime, "STATE_DIR", self.state_dir),
            patch.object(telegram_runtime, "TELEGRAM_RUNTIME_DB", self.runtime_db),
            patch("ace.telegram_runtime.request.urlopen", return_value=fake_context) as mocked_urlopen,
            patch("ace.telegram_runtime._telegram_ssl_context", return_value=ssl.create_default_context()),
        ):
            self.assertEqual(telegram_runtime.fetch_unprocessed_telegram_messages(), [])

        self.assertIn("timeout=0", mocked_urlopen.call_args.args[0])

    def test_fetch_real_telegram_updates_records_json_failure(self) -> None:
        fake_response = MagicMock()
        fake_response.read.return_value = b"not-json"
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

        self.assertEqual(messages, [])
        with closing(sqlite3.connect(self.runtime_db)) as connection:
            attempt = connection.execute(
                "SELECT status, error_type FROM telegram_transport_attempts"
            ).fetchone()
        self.assertEqual(tuple(attempt), ("error", "JSONDecodeError"))

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
        with closing(sqlite3.connect(self.runtime_db)) as connection:
            attempt = connection.execute(
                "SELECT transport, status, message_count, error_type FROM telegram_transport_attempts"
            ).fetchone()
        self.assertEqual(tuple(attempt), ("openclaw_session", "ok", 2, None))


    def test_openclaw_session_reader_tails_large_session_files(self) -> None:
        session_file = Path(self.tempdir.name) / "large-session.jsonl"
        old_lines = [
            jsonlib.dumps({
                "type": "message",
                "id": f"old-{i}",
                "message": {"role": "user", "content": [{"type": "text", "text": "Please ignore old backlog"}]},
            })
            for i in range(50)
        ]
        line_id = "recent-user-msg"
        recent_lines = [
            jsonlib.dumps({
                "type": "message",
                "id": line_id,
                "message": {"role": "user", "content": [{"type": "text", "text": "Please process recent bounded work"}]},
            }),
            jsonlib.dumps({
                "type": "custom_message",
                "customType": "openclaw.runtime-context",
                "parentId": line_id,
                "content": (
                    "Conversation info (untrusted metadata):\n```json\n"
                    + jsonlib.dumps(
                        {
                            "chat_id": "telegram:7529788084",
                            "message_id": "44550",
                            "sender_id": "7529788084",
                            "sender": "Andrew Pilson",
                            "timestamp": "Tue 2026-05-19 05:40 PDT",
                        }
                    )
                    + "\n```"
                ),
            }),
        ]
        session_file.write_text("\n".join(old_lines + recent_lines) + "\n", encoding="utf-8")

        with (
            patch.dict(
                os.environ,
                {
                    "ACE_OPENCLAW_SESSION_FILE": str(session_file),
                    "ACE_OPENCLAW_CHAT_ID": "telegram:7529788084",
                    "ACE_OPENCLAW_SESSION_TAIL_LINES": "4",
                },
                clear=False,
            ),
            patch.object(telegram_runtime, "STATE_DIR", self.state_dir),
            patch.object(telegram_runtime, "TELEGRAM_RUNTIME_DB", self.runtime_db),
        ):
            messages = telegram_runtime.fetch_unprocessed_telegram_messages()

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["message_id"], "44550")
        self.assertEqual(messages[0]["text"], "Please process recent bounded work")

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

    def test_bot_api_bootstrap_runs_when_no_bot_api_offset_even_if_other_checkpoints_exist(self) -> None:
        payload = {
            "ok": True,
            "result": [
                {
                    "update_id": 200,
                    "message": {
                        "message_id": 20,
                        "date": 1746720000,
                        "text": "Old raw bot backlog",
                        "chat": {"id": 7529788084},
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
            patch.object(telegram_runtime, "STATE_DIR", self.state_dir),
            patch.object(telegram_runtime, "TELEGRAM_RUNTIME_DB", self.runtime_db),
        ):
            telegram_runtime.mark_telegram_message_processed(
                chat_id="7529788084",
                message_id="openclaw-existing",
                processed_at="2026-05-13T00:00:00Z",
            )

        with (
            patch.dict(os.environ, {
                "ACE_TELEGRAM_BOT_TOKEN": "bot-token",
                "ACE_TELEGRAM_BOOTSTRAP_EXISTING_AS_PROCESSED": "true",
            }, clear=False),
            patch.object(telegram_runtime, "STATE_DIR", self.state_dir),
            patch.object(telegram_runtime, "TELEGRAM_RUNTIME_DB", self.runtime_db),
            patch("ace.telegram_runtime.request.urlopen", return_value=fake_context),
            patch("ace.telegram_runtime._telegram_ssl_context", return_value=ssl.create_default_context()),
        ):
            messages = telegram_runtime.fetch_unprocessed_telegram_messages()

        self.assertEqual(messages, [])
        with closing(sqlite3.connect(self.runtime_db)) as connection:
            processed = [row[0] for row in connection.execute(
                "SELECT source_session FROM processed_telegram_messages ORDER BY source_session"
            ).fetchall()]
            offset = connection.execute(
                "SELECT next_offset FROM telegram_transport_offsets WHERE transport = ?",
                ("telegram_bot_api",),
            ).fetchone()[0]
        self.assertIn("telegram:7529788084:20", processed)
        self.assertEqual(offset, 201)

    def test_telegram_ssl_context_prefers_certifi_when_available(self) -> None:
        fake_certifi = MagicMock()
        fake_certifi.where.return_value = "/tmp/fake-cacert.pem"
        with patch.dict("sys.modules", {"certifi": fake_certifi}):
            with patch("ace.telegram_runtime.ssl.create_default_context") as mocked_context:
                telegram_runtime._telegram_ssl_context()
        mocked_context.assert_called_once_with(cafile="/tmp/fake-cacert.pem")

    def test_telegram_ssl_context_explicit_ca_bundle_overrides_certifi(self) -> None:
        fake_certifi = MagicMock()
        fake_certifi.where.return_value = "/tmp/fake-cacert.pem"
        with patch.dict(os.environ, {"ACE_TELEGRAM_CA_BUNDLE": "/tmp/operator-cacert.pem"}, clear=False):
            with patch.dict("sys.modules", {"certifi": fake_certifi}):
                with patch("ace.telegram_runtime.ssl.create_default_context") as mocked_context:
                    telegram_runtime._telegram_ssl_context()
        mocked_context.assert_called_once_with(cafile="/tmp/operator-cacert.pem")

    def test_fetch_can_use_governed_openclaw_token_source_without_committing_secret(self) -> None:
        config_path = Path(self.tempdir.name) / "openclaw.json"
        config_path.write_text(json.dumps({"channels": {"telegram": {"botToken": "bot-token"}}}), encoding="utf-8")
        payload = {"ok": True, "result": []}

        fake_response = MagicMock()
        fake_response.read.return_value = json.dumps(payload).encode("utf-8")
        fake_context = MagicMock()
        fake_context.__enter__.return_value = fake_response
        fake_context.__exit__.return_value = False

        with (
            patch.dict(os.environ, {
                "ACE_USE_OPENCLAW_TELEGRAM_BOT_TOKEN": "true",
                "ACE_OPENCLAW_CONFIG_PATH": str(config_path),
            }, clear=False),
            patch.object(telegram_runtime, "STATE_DIR", self.state_dir),
            patch.object(telegram_runtime, "TELEGRAM_RUNTIME_DB", self.runtime_db),
            patch("ace.telegram_runtime.request.urlopen", return_value=fake_context) as mocked_urlopen,
            patch("ace.telegram_runtime._telegram_ssl_context", return_value=ssl.create_default_context()),
        ):
            messages = telegram_runtime.fetch_unprocessed_telegram_messages()

        self.assertEqual(messages, [])
        mocked_urlopen.assert_called_once()
        self.assertIn("botbot-token", mocked_urlopen.call_args.args[0])
        with closing(sqlite3.connect(self.runtime_db)) as connection:
            attempt = connection.execute(
                "SELECT transport, status, message_count, error_type FROM telegram_transport_attempts"
            ).fetchone()
        self.assertEqual(tuple(attempt), ("telegram_bot_api", "ok", 0, None))

    def test_explicit_bot_api_transport_bypasses_openclaw_session_for_launchd_proof(self) -> None:
        config_path = Path(self.tempdir.name) / "openclaw.json"
        config_path.write_text(json.dumps({"channels": {"telegram": {"botToken": "bot-token"}}}), encoding="utf-8")
        session_file = Path(self.tempdir.name) / "session.jsonl"
        session_file.write_text("", encoding="utf-8")
        payload = {"ok": True, "result": []}

        fake_response = MagicMock()
        fake_response.read.return_value = json.dumps(payload).encode("utf-8")
        fake_context = MagicMock()
        fake_context.__enter__.return_value = fake_response
        fake_context.__exit__.return_value = False

        with (
            patch.dict(os.environ, {
                "ACE_TELEGRAM_TRANSPORT": "telegram_bot_api",
                "ACE_USE_OPENCLAW_TELEGRAM_BOT_TOKEN": "true",
                "ACE_OPENCLAW_CONFIG_PATH": str(config_path),
                "ACE_OPENCLAW_SESSION_FILE": str(session_file),
            }, clear=False),
            patch.object(telegram_runtime, "STATE_DIR", self.state_dir),
            patch.object(telegram_runtime, "TELEGRAM_RUNTIME_DB", self.runtime_db),
            patch("ace.telegram_runtime.request.urlopen", return_value=fake_context) as mocked_urlopen,
            patch("ace.telegram_runtime._telegram_ssl_context", return_value=ssl.create_default_context()),
        ):
            messages = telegram_runtime.fetch_unprocessed_telegram_messages()

        self.assertEqual(messages, [])
        mocked_urlopen.assert_called_once()
        self.assertIn("getUpdates", mocked_urlopen.call_args.args[0])
        with closing(sqlite3.connect(self.runtime_db)) as connection:
            attempt = connection.execute(
                "SELECT transport, status, message_count, error_type FROM telegram_transport_attempts"
            ).fetchone()
        self.assertEqual(tuple(attempt), ("telegram_bot_api", "ok", 0, None))

    def test_explicit_openclaw_session_transport_does_not_fall_back_to_bot_api(self) -> None:
        with (
            patch.dict(os.environ, {
                "ACE_TELEGRAM_TRANSPORT": "openclaw_session",
                "ACE_OPENCLAW_CHAT_ID": "telegram:7529788084",
                "ACE_TELEGRAM_BOT_TOKEN": "bot-token",
            }, clear=False),
            patch.object(telegram_runtime, "STATE_DIR", self.state_dir),
            patch.object(telegram_runtime, "TELEGRAM_RUNTIME_DB", self.runtime_db),
            patch("ace.telegram_runtime.OPENCLAW_MAIN_SESSIONS_INDEX", Path(self.tempdir.name) / "missing-sessions.json"),
            patch("ace.telegram_runtime.request.urlopen") as mocked_urlopen,
        ):
            messages = telegram_runtime.fetch_unprocessed_telegram_messages()

        self.assertEqual(messages, [])
        mocked_urlopen.assert_not_called()
        with closing(sqlite3.connect(self.runtime_db)) as connection:
            attempt = connection.execute(
                "SELECT transport, status, error_type FROM telegram_transport_attempts"
            ).fetchone()
        self.assertEqual(tuple(attempt), ("openclaw_session", "disabled", "missing_openclaw_session"))

    def test_invalid_explicit_telegram_transport_fails_closed(self) -> None:
        with (
            patch.dict(os.environ, {"ACE_TELEGRAM_TRANSPORT": "raw-ish"}, clear=False),
            patch.object(telegram_runtime, "STATE_DIR", self.state_dir),
            patch.object(telegram_runtime, "TELEGRAM_RUNTIME_DB", self.runtime_db),
        ):
            messages = telegram_runtime.fetch_unprocessed_telegram_messages()

        self.assertEqual(messages, [])
        with closing(sqlite3.connect(self.runtime_db)) as connection:
            attempt = connection.execute(
                "SELECT transport, status, error_type FROM telegram_transport_attempts"
            ).fetchone()
        self.assertEqual(tuple(attempt), ("raw-ish", "disabled", "invalid_transport"))

    def test_governed_openclaw_token_source_records_disabled_when_config_missing(self) -> None:
        with (
            patch.dict(os.environ, {
                "ACE_USE_OPENCLAW_TELEGRAM_BOT_TOKEN": "true",
                "ACE_OPENCLAW_CONFIG_PATH": str(Path(self.tempdir.name) / "missing.json"),
            }, clear=False),
            patch.object(telegram_runtime, "STATE_DIR", self.state_dir),
            patch.object(telegram_runtime, "TELEGRAM_RUNTIME_DB", self.runtime_db),
        ):
            messages = telegram_runtime.fetch_unprocessed_telegram_messages()

        self.assertEqual(messages, [])
        with closing(sqlite3.connect(self.runtime_db)) as connection:
            attempts = connection.execute(
                "SELECT status, error_type FROM telegram_transport_attempts ORDER BY attempted_at"
            ).fetchall()
        self.assertIn(("disabled", "FileNotFoundError"), [tuple(row) for row in attempts])


if __name__ == "__main__":
    unittest.main()
