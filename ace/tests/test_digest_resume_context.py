from __future__ import annotations

import io
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import ace.ace as ace_cli_module
from ace.ace import _format_digest_message, main
from ace.digest_resume_context import load_stale_resume_contexts, render_stale_resume_context
from ace.storage import bootstrap_db


class DigestResumeContextTests(unittest.TestCase):
    def _insert_item(
        self,
        connection: sqlite3.Connection,
        item_id: str,
        state: str,
        updated_at: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO items (
                id, item_type, title, state, source, created_at, updated_at, last_event_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item_id,
                "task",
                f"title for {item_id}",
                state,
                "telegram/direct",
                updated_at,
                updated_at,
                f"evt_{item_id}_latest",
            ),
        )

    def _insert_event(
        self,
        connection: sqlite3.Connection,
        event_id: str,
        item_id: str,
        event_type: str,
        created_at: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO events (event_id, item_id, event_type, payload_json, created_at, event_hash)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (event_id, item_id, event_type, "{}", created_at, "0" * 64),
        )

    def _insert_obligation(
        self,
        connection: sqlite3.Connection,
        obligation_id: str,
        item_id: str,
        *,
        obligation_type: str = "follow_up",
        status: str = "open",
        notes: str | None = "confirm receipt",
        created_at: str = "2026-05-20T00:00:00Z",
    ) -> None:
        connection.execute(
            """
            INSERT INTO obligations (
                id, item_id, obligation_type, status, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                obligation_id,
                item_id,
                obligation_type,
                status,
                notes,
                created_at,
                created_at,
            ),
        )

    def test_loads_last_three_events_newest_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "ace.db"
            bootstrap_db(db_path)
            item_id = "item_resume_events"
            stale_rows = [
                {
                    "item_id": item_id,
                    "state": "APPROVED",
                    "days_idle": 10,
                    "last_event_type": "item.touched",
                }
            ]
            timestamps = [
                "2026-05-10T00:00:00Z",
                "2026-05-12T00:00:00Z",
                "2026-05-14T00:00:00Z",
                "2026-05-16T00:00:00Z",
            ]
            with closing(sqlite3.connect(db_path)) as connection:
                self._insert_item(connection, item_id, "APPROVED", timestamps[-1])
                for index, created_at in enumerate(timestamps):
                    self._insert_event(
                        connection,
                        f"evt_{index}",
                        item_id,
                        f"event_{index}",
                        created_at,
                    )
                connection.execute(
                    "UPDATE items SET last_event_id = ? WHERE id = ?",
                    ("evt_3", item_id),
                )
                connection.commit()

            contexts = load_stale_resume_contexts(db_path, stale_rows)
            events = contexts[item_id]["events"]
            self.assertEqual(len(events), 3)
            self.assertEqual(events[0]["event_type"], "event_3")
            self.assertEqual(events[1]["event_type"], "event_2")
            self.assertEqual(events[2]["event_type"], "event_1")

    def test_open_obligations_exclude_terminal_statuses(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "ace.db"
            bootstrap_db(db_path)
            item_id = "item_resume_obligations"
            stale_rows = [
                {
                    "item_id": item_id,
                    "state": "TRIAGE",
                    "days_idle": 8,
                    "last_event_type": "item.created",
                }
            ]
            with closing(sqlite3.connect(db_path)) as connection:
                self._insert_item(connection, item_id, "TRIAGE", "2026-05-18T00:00:00Z")
                self._insert_event(
                    connection,
                    "evt_created",
                    item_id,
                    "item.created",
                    "2026-05-18T00:00:00Z",
                )
                self._insert_obligation(connection, "obl_open", item_id, status="open")
                self._insert_obligation(
                    connection,
                    "obl_done",
                    item_id,
                    status="done",
                    notes="finished",
                )
                connection.commit()

            contexts = load_stale_resume_contexts(db_path, stale_rows)
            obligations = contexts[item_id]["obligations"]
            self.assertEqual(len(obligations), 1)
            self.assertEqual(obligations[0]["obligation_type"], "follow_up")
            self.assertEqual(obligations[0]["status"], "open")

    def test_render_includes_state_events_and_obligations(self) -> None:
        stale_rows = [
            {
                "item_id": "item_render_ctx",
                "state": "CLAIMED_DONE",
                "days_idle": 12,
                "last_event_type": "item.touched",
            }
        ]
        contexts = {
            "item_render_ctx": {
                "item_id": "item_render_ctx",
                "current_state": "CLAIMED_DONE",
                "days_idle": 12,
                "events": [{"event_type": "item.touched", "created_at": "2026-05-14T10:00:00Z"}],
                "obligations": [{"obligation_type": "review", "status": "open", "notes": None}],
            }
        }
        rendered = render_stale_resume_context(stale_rows, contexts)
        self.assertIn("Stale item resume context:", rendered)
        self.assertIn("state CLAIMED_DONE", rendered)
        self.assertIn("12d idle", rendered)
        self.assertIn("events (latest 3):", rendered)
        self.assertIn("item.touched", rendered)
        self.assertIn("obligations (open):", rendered)
        self.assertIn("review [open]", rendered)

    def test_format_digest_appends_resume_context_after_stale_table(self) -> None:
        stale_rows = [
            {
                "item_id": "item_digest_ctx",
                "state": "APPROVED",
                "days_idle": 9,
                "last_event_type": "item.touched",
            }
        ]
        resume = render_stale_resume_context(
            stale_rows,
            {
                "item_digest_ctx": {
                    "item_id": "item_digest_ctx",
                    "current_state": "APPROVED",
                    "days_idle": 9,
                    "events": [],
                    "obligations": [],
                }
            },
        )
        message = _format_digest_message(
            stale_rows=stale_rows,
            loose_rows=[],
            stale_resume_context=resume,
            generated_at=datetime(2026, 5, 26, tzinfo=timezone.utc),
        )
        stale_index = message.index("Stale items (1)")
        resume_index = message.index("Stale item resume context:")
        loose_index = message.index("Loose ends (0)")
        self.assertLess(stale_index, resume_index)
        self.assertLess(resume_index, loose_index)
        self.assertIn("item_id", message)

    def test_digest_cli_includes_resume_context_for_stale_item(self) -> None:
        sent: list[dict[str, str]] = []

        def fake_send(*, token: str, chat_id: str, text: str) -> dict[str, object]:
            sent.append({"token": token, "chat_id": chat_id, "text": text})
            return {"ok": True, "result": {"message_id": 404}}

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "ace.db"
            bootstrap_db(db_path)
            item_id = "item_digest_resume"
            old_at = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat().replace("+00:00", "Z")
            with closing(sqlite3.connect(db_path)) as connection:
                self._insert_item(connection, item_id, "APPROVED", old_at)
                self._insert_event(connection, "evt_old", item_id, "item.created", old_at)
                self._insert_event(connection, "evt_mid", item_id, "item.touched", old_at)
                self._insert_obligation(connection, "obl_ctx", item_id)
                connection.execute(
                    "UPDATE items SET last_event_id = ? WHERE id = ?",
                    ("evt_mid", item_id),
                )
                connection.commit()

            with (
                mock.patch.dict(
                    os.environ,
                    {"ACE_TELEGRAM_BOT_TOKEN": "token", "ACE_TELEGRAM_CHAT_ID": "chat"},
                    clear=False,
                ),
                mock.patch.object(
                    ace_cli_module.action_runtime,
                    "_telegram_bot_api_send_message",
                    fake_send,
                ),
                mock.patch.object(ace_cli_module, "load_ace_telegram_env_file", lambda: None),
                redirect_stdout(io.StringIO()),
            ):
                code = main(["--db", str(db_path), "digest", "--days", "7"])

            self.assertEqual(code, 0)
            self.assertEqual(len(sent), 1)
            text = sent[0]["text"]
            self.assertIn("Stale item resume context:", text)
            self.assertIn("state APPROVED", text)
            self.assertIn("events (latest 3):", text)
            self.assertIn("item.touched", text)
            self.assertIn("obligations (open):", text)
            self.assertIn("follow_up [open]", text)
            self.assertIn("Stale items (1)", text)
            self.assertIn("Loose ends (", text)

    def test_empty_stale_items_omit_resume_context_block(self) -> None:
        message = _format_digest_message(
            stale_rows=[],
            loose_rows=[],
            stale_resume_context="",
            generated_at=datetime(2026, 5, 26, tzinfo=timezone.utc),
        )
        self.assertNotIn("Stale item resume context:", message)


if __name__ == "__main__":
    unittest.main()
