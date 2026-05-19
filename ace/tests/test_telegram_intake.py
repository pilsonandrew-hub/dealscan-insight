from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ace.repository import ItemRepository
from ace.storage import bootstrap_db, connect
from ace.telegram_intake import intake_inbound_telegram_work


class TelegramIntakeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "ace.db"
        bootstrap_db(self.db_path)
        self.repo = ItemRepository(self.db_path)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_actionable_message_creates_parser_backed_direct_work_item(self) -> None:
        result = intake_inbound_telegram_work(
            self.db_path,
            chat_id="7529788084",
            message_id="msg-100",
            text="Can you check whether the parser-created intake closes cleanly?",
            received_at="2026-05-08T16:50:00Z",
            sender_id="7529788084",
            sender_name="Andrew Pilson",
        )

        self.assertTrue(result["actionable"])
        self.assertTrue(result["created"])
        self.assertEqual(result["source_session"], "telegram:7529788084:msg-100")

        item = self.repo.get_item(result["item_id"])
        assert item is not None
        self.assertEqual(item.source, "telegram/direct")
        self.assertEqual(item.source_session, "telegram:7529788084:msg-100")
        self.assertEqual(item.state, "TRIAGE")

        events = self.repo.list_item_events(item.id, event_type="item.created")
        self.assertEqual(len(events), 1)
        payload = json.loads(events[0].payload_json or "{}")
        self.assertEqual(payload["source_message_text"], "Can you check whether the parser-created intake closes cleanly?")
        self.assertEqual(payload["source_message_id"], "msg-100")
        self.assertEqual(payload["source_chat_id"], "7529788084")
        self.assertEqual(payload["source_received_at"], "2026-05-08T16:50:00Z")
        self.assertIsInstance(payload["semantic_direct_work_key"], str)
        self.assertEqual(len(payload["semantic_direct_work_key"]), 64)
        self.assertEqual(payload["parser_rule"], "bounded_direct_work_rule")
        self.assertIn("can you", payload["parser_reason"])
        self.assertEqual(payload["intake_actor"], "ace.telegram_intake")

        with connect(self.db_path) as connection:
            evidence_rows = connection.execute(
                "SELECT evidence_uri, created_by FROM evidence WHERE item_id = ? ORDER BY created_at ASC, id ASC",
                (item.id,),
            ).fetchall()

        self.assertFalse(result["autonomy_eligible"])
        self.assertIsNone(result["eligibility_evidence_id"])
        self.assertIn("requires governed execution evidence", result["autonomy_policy_reason"])
        self.assertIn(("ace://telegram/intake-source", "ace.telegram_intake"), [tuple(row) for row in evidence_rows])
        self.assertIn(("ace://telegram/parser-decision", "ace.telegram_parser"), [tuple(row) for row in evidence_rows])
        self.assertNotIn(("ace://autonomy/eligible-direct-work", "ace.autonomy_lane"), [tuple(row) for row in evidence_rows])

    def test_idempotency_uses_same_message_once(self) -> None:
        first = intake_inbound_telegram_work(
            self.db_path,
            chat_id="7529788084",
            message_id="msg-101",
            text="Please follow up on the parser proof.",
            received_at="2026-05-08T16:51:00Z",
        )
        second = intake_inbound_telegram_work(
            self.db_path,
            chat_id="7529788084",
            message_id="msg-101",
            text="Please follow up on the parser proof.",
            received_at="2026-05-08T16:51:00Z",
        )

        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertEqual(first["item_id"], second["item_id"])

        with connect(self.db_path) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM items WHERE source = ? AND source_session = ?",
                ("telegram/direct", "telegram:7529788084:msg-101"),
            ).fetchone()[0]

        self.assertEqual(count, 1)

    def test_semantically_duplicate_direct_work_coalesces_without_new_item(self) -> None:
        first = intake_inbound_telegram_work(
            self.db_path,
            chat_id="7529788084",
            message_id="msg-201",
            text="Proceed + continue on that path.",
            received_at="2026-05-08T17:01:00Z",
        )
        second = intake_inbound_telegram_work(
            self.db_path,
            chat_id="7529788084",
            message_id="msg-202",
            text="  Proceed   + continue on that path.  ",
            received_at="2026-05-08T17:02:00Z",
        )

        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertTrue(second["coalesced"])
        self.assertEqual(first["item_id"], second["item_id"])
        self.assertTrue(second["autonomy_eligible"])
        self.assertIsNotNone(second["eligibility_evidence_id"])
        self.assertIn("operator-continuation", second["autonomy_policy_reason"])
        self.assertIsNotNone(second["duplicate_evidence_id"])

        with connect(self.db_path) as connection:
            item_count = connection.execute(
                "SELECT COUNT(*) FROM items WHERE source = ?",
                ("telegram/direct",),
            ).fetchone()[0]
            duplicate_count = connection.execute(
                "SELECT COUNT(*) FROM evidence WHERE item_id = ? AND evidence_uri = ?",
                (first["item_id"], "ace://telegram/duplicate-direct-work"),
            ).fetchone()[0]

        self.assertEqual(item_count, 1)
        self.assertEqual(duplicate_count, 1)

    def test_direct_work_without_bounded_continuation_is_not_autonomy_eligible(self) -> None:
        result = intake_inbound_telegram_work(
            self.db_path,
            chat_id="7529788084",
            message_id="msg-203",
            text="Please investigate whether this production issue is safe to fix.",
            received_at="2026-05-08T17:03:00Z",
        )

        self.assertTrue(result["actionable"])
        self.assertTrue(result["created"])
        self.assertFalse(result["autonomy_eligible"])
        self.assertIsNone(result["eligibility_evidence_id"])

        with connect(self.db_path) as connection:
            eligible_count = connection.execute(
                "SELECT COUNT(*) FROM evidence WHERE item_id = ? AND evidence_uri = ?",
                (result["item_id"], "ace://autonomy/eligible-direct-work"),
            ).fetchone()[0]

        self.assertEqual(eligible_count, 0)

    def test_non_actionable_message_creates_no_item(self) -> None:
        result = intake_inbound_telegram_work(
            self.db_path,
            chat_id="7529788084",
            message_id="msg-102",
            text="The weather is great today.",
            received_at="2026-05-08T16:52:00Z",
        )

        self.assertFalse(result["actionable"])
        self.assertFalse(result["created"])
        self.assertEqual(result["classification"], "ignore")

        with connect(self.db_path) as connection:
            count = connection.execute("SELECT COUNT(*) FROM items").fetchone()[0]

        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
