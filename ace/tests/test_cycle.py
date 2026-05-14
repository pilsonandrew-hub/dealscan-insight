from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from ace.cycle import run_cycle
from ace.autonomy_lane import AUTONOMY_ITEM_TYPE
from ace.governed_run_runtime import get_governed_cycle_run_status
from ace.governed_run_runtime import correct_governed_run_trigger_kind
from ace.repository import ItemRepository, ValidationError
from ace.storage import bootstrap_db, connect


def _hours_after(timestamp: str, hours: int) -> str:
    normalized = timestamp[:-1] + "+00:00" if timestamp.endswith("Z") else timestamp
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (parsed + timedelta(hours=hours)).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class AceCycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "ace.db"
        self.briefing_path = Path(self.tempdir.name) / "ace_briefing.md"
        bootstrap_db(self.db_path)
        self.repo = ItemRepository(self.db_path)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_cycle_writes_briefing_file_without_notifications_when_no_actionable_findings(self) -> None:
        self.repo.create_item(item_type="note", title="Fresh triage item")

        result = run_cycle(self.db_path, now="2026-05-05T00:00:00Z", briefing_path=self.briefing_path)

        self.assertEqual(result["actionable_finding_count"], 0)
        self.assertEqual(result["notification_count"], 0)
        self.assertEqual(result["governed_run"]["status"], "completed")
        self.assertTrue(self.briefing_path.exists())
        rendered = self.briefing_path.read_text(encoding="utf-8")
        self.assertIn("generated_at=2026-05-05T00:00:00Z", rendered)

        status = get_governed_cycle_run_status(self.db_path)
        self.assertIsNone(status["current_run"])
        self.assertIsNotNone(status["last_terminal_run"])
        self.assertEqual(status["last_terminal_run"]["status"], "completed")
        self.assertEqual(status["last_terminal_run"]["briefing_path"], str(self.briefing_path))

    def test_cycle_requires_notification_routing_when_actionable_findings_exist(self) -> None:
        item = self.repo.create_item(item_type="note", title="Old triage item")
        stale_now = _hours_after(item.created_at, 25)

        with self.assertRaises(ValidationError):
            run_cycle(self.db_path, now=stale_now, briefing_path=self.briefing_path)

        status = get_governed_cycle_run_status(self.db_path)
        self.assertIsNone(status["current_run"])
        self.assertIsNotNone(status["last_terminal_run"])
        self.assertEqual(status["last_terminal_run"]["status"], "failed")
        self.assertEqual(status["last_terminal_run"]["failure_code"], "cycle_validation_error")

    def test_cycle_sends_notifications_for_actionable_findings_and_writes_briefing_file(self) -> None:
        item = self.repo.create_item(item_type="note", title="Old triage item")
        stale_now = _hours_after(item.created_at, 25)
        sender_calls: list[dict[str, object]] = []

        def fake_sender(**kwargs: object) -> dict[str, object]:
            sender_calls.append(kwargs)
            return {"ok": True, "provider": "test"}

        result = run_cycle(
            self.db_path,
            now=stale_now,
            briefing_path=self.briefing_path,
            notification_channel="telegram",
            notification_target="telegram:7529788084",
            sender=fake_sender,
        )

        self.assertEqual(result["actionable_finding_count"], 1)
        self.assertEqual(result["notification_count"], 1)
        self.assertEqual(len(sender_calls), 1)
        self.assertEqual(sender_calls[0]["channel"], "telegram")
        self.assertEqual(sender_calls[0]["target"], "telegram:7529788084")
        self.assertIn(item.id, sender_calls[0]["message"])
        self.assertTrue(self.briefing_path.exists())

        with connect(self.db_path) as connection:
            evidence_count = connection.execute(
                "SELECT COUNT(*) FROM evidence WHERE item_id = ? AND evidence_uri = ?",
                (item.id, "ace://notification/delivery"),
            ).fetchone()[0]
        self.assertEqual(evidence_count, 1)

        status = get_governed_cycle_run_status(self.db_path)
        self.assertIsNone(status["current_run"])
        self.assertIsNotNone(status["last_terminal_run"])
        self.assertEqual(status["last_terminal_run"]["status"], "completed")
        self.assertEqual(status["last_terminal_run"]["notification_action_id"], result["notifications"][0]["action_id"])
        self.assertEqual(status["last_terminal_run"]["delivery_evidence_id"], result["notifications"][0]["evidence_id"])

    def test_cycle_records_interrupted_terminal_state(self) -> None:
        self.repo.create_item(item_type="note", title="Interrupt target")

        with patch("ace.cycle.generate_briefing", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                run_cycle(self.db_path, now="2026-05-05T00:00:00Z", briefing_path=self.briefing_path)

        status = get_governed_cycle_run_status(self.db_path)
        self.assertIsNone(status["current_run"])
        self.assertIsNotNone(status["last_terminal_run"])
        self.assertEqual(status["last_terminal_run"]["status"], "interrupted")
        self.assertEqual(status["last_terminal_run"]["failure_code"], "cycle_interrupted")

    def test_cycle_can_disable_notifications_for_controlled_proof(self) -> None:
        item = self.repo.create_item(item_type="note", title="Old triage item")
        stale_now = _hours_after(item.created_at, 25)

        result = run_cycle(
            self.db_path,
            now=stale_now,
            briefing_path=self.briefing_path,
            notification_channel="telegram",
            notification_target="telegram:7529788084",
            disable_notifications=True,
        )

        self.assertEqual(result["actionable_finding_count"], 1)
        self.assertEqual(result["notification_count"], 0)
        self.assertTrue(result["notifications_suppressed"])
        self.assertEqual(result["notifications"], [])
        self.assertEqual(result["governed_run"]["status"], "completed")

        with connect(self.db_path) as connection:
            notification_actions = connection.execute(
                "SELECT COUNT(*) FROM action_queue WHERE action_type = 'send_operator_notification'"
            ).fetchone()[0]
            notification_evidence = connection.execute(
                "SELECT COUNT(*) FROM evidence WHERE evidence_uri = 'ace://notification/delivery'"
            ).fetchone()[0]
        self.assertEqual(notification_actions, 0)
        self.assertEqual(notification_evidence, 0)

    def test_cycle_autonomously_closes_machine_verifiable_work(self) -> None:
        item = self.repo.create_item(
            item_type=AUTONOMY_ITEM_TYPE,
            title="Autonomy closure target",
            description="ACE should close this via the bounded machine-verifiable autonomy lane.",
            actor="test",
        )

        result = run_cycle(self.db_path, now="2026-05-05T00:00:00Z", briefing_path=self.briefing_path)

        final_item = self.repo.get_item(item.id)
        assert final_item is not None
        self.assertEqual(final_item.state, "VERIFIED_DONE")
        self.assertEqual(result["autonomy"]["verified_done_ids"], [item.id])
        self.assertEqual(result["actionable_finding_count"], 0)

    def test_cycle_uses_launchd_trigger_kind_when_actor_is_launchd(self) -> None:
        self.repo.create_item(item_type="note", title="Launchd trigger target")

        result = run_cycle(
            self.db_path,
            now="2026-05-05T00:00:00Z",
            briefing_path=self.briefing_path,
            actor="launchd",
        )

        self.assertEqual(result["governed_run"]["trigger_kind"], "launchd")

        status = get_governed_cycle_run_status(self.db_path)
        self.assertIsNotNone(status["last_terminal_run"])
        self.assertEqual(status["last_terminal_run"]["trigger_kind"], "launchd")

    def test_cycle_ingests_actionable_telegram_message_before_autonomy(self) -> None:
        message = {
            "chat_id": "7529788084",
            "message_id": "msg-200",
            "text": "Can you check whether ACE closes parser-created Telegram work end to end?",
            "received_at": "2026-05-08T16:50:00Z",
            "sender_id": "7529788084",
            "sender_name": "Andrew Pilson",
        }

        with patch("ace.cycle.fetch_unprocessed_telegram_messages", return_value=[message]), patch("ace.cycle.mark_telegram_message_processed") as mark_processed:
            result = run_cycle(self.db_path, actor="launchd", briefing_path=self.briefing_path)

        mark_processed.assert_called_once_with(
            chat_id="7529788084",
            message_id="msg-200",
            processed_at="2026-05-08T16:50:00Z",
        )

        self.assertTrue(result["governed_run"]["status"], "completed")
        self.assertEqual(len(result["ingested_messages"]), 1)
        self.assertTrue(result["ingested_messages"][0]["actionable"])

        source_session = "telegram:7529788084:msg-200"
        item = self.repo.get_item_by_source_and_session("telegram/direct", source_session)
        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item.source, "telegram/direct")
        self.assertEqual(item.source_session, source_session)
        self.assertEqual(item.state, "VERIFIED_DONE")

        created_event = self.repo.list_item_events(item.id, event_type="item.created", limit=1)[0]
        payload = json.loads(created_event.payload_json or "{}")
        self.assertEqual(payload["source_message_text"], message["text"])
        self.assertEqual(payload["source_message_id"], "msg-200")
        self.assertEqual(payload["source_chat_id"], "7529788084")
        self.assertEqual(payload["source_received_at"], "2026-05-08T16:50:00Z")
        self.assertEqual(payload["parser_rule"], "bounded_direct_work_rule")

        event_types = [event.event_type for event in self.repo.list_item_events(item.id)]
        self.assertIn("item.created", event_types)
        self.assertIn("item.evidence_added", event_types)
        self.assertIn("item.closeout_attempted", event_types)
        self.assertIn("item.state_changed", event_types)

    def test_cycle_skips_when_another_cycle_is_active(self) -> None:
        fresh_active_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        with connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO governed_runs (
                    run_id, run_kind, trigger_kind, status, briefing_path,
                    notification_action_id, delivery_evidence_id,
                    created_at, started_at, ended_at, interrupted_at,
                    failure_code, failure_summary
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "run_existing_active",
                    "ace_cycle",
                    "launchd",
                    "running",
                    None,
                    None,
                    None,
                    fresh_active_at,
                    fresh_active_at,
                    None,
                    None,
                    None,
                    None,
                ),
            )
            connection.commit()

        result = run_cycle(self.db_path, actor="operator", briefing_path=self.briefing_path)

        self.assertEqual(result["governed_run"]["status"], "skipped")
        self.assertEqual(result["governed_run"]["failure_code"], "cycle_already_active")
        self.assertEqual(result["notification_count"], 0)
        self.assertFalse(result["notifications_suppressed"])
        self.assertEqual(result["ingested_messages"], [])
        self.assertFalse(self.briefing_path.exists())

        with connect(self.db_path) as connection:
            active_count = connection.execute(
                "SELECT COUNT(*) FROM governed_runs WHERE status = 'running'"
            ).fetchone()[0]
            skipped_count = connection.execute(
                "SELECT COUNT(*) FROM governed_runs WHERE status = 'skipped'"
            ).fetchone()[0]
        self.assertEqual(active_count, 1)
        self.assertEqual(skipped_count, 1)

    def test_cycle_reconciles_stale_active_run_before_starting_new_cycle(self) -> None:
        with connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO governed_runs (
                    run_id, run_kind, trigger_kind, status, briefing_path,
                    notification_action_id, delivery_evidence_id,
                    created_at, started_at, ended_at, interrupted_at,
                    failure_code, failure_summary
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "run_stale_active",
                    "ace_cycle",
                    "launchd",
                    "running",
                    None,
                    None,
                    None,
                    "2026-05-01T00:00:00Z",
                    "2026-05-01T00:00:00Z",
                    None,
                    None,
                    None,
                    None,
                ),
            )
            connection.commit()

        result = run_cycle(self.db_path, actor="operator", briefing_path=self.briefing_path)

        self.assertEqual(result["governed_run"]["status"], "completed")
        with connect(self.db_path) as connection:
            stale_row = connection.execute(
                "SELECT status, failure_code, failure_summary FROM governed_runs WHERE run_id = ?",
                ("run_stale_active",),
            ).fetchone()
            active_count = connection.execute(
                "SELECT COUNT(*) FROM governed_runs WHERE status IN ('pending', 'starting', 'running')"
            ).fetchone()[0]
        self.assertEqual(stale_row["status"], "interrupted")
        self.assertEqual(stale_row["failure_code"], "cycle_stale_active_reconciled")
        self.assertIn("stale governed ace cycle", stale_row["failure_summary"])
        self.assertEqual(active_count, 0)

    def test_governed_run_trigger_correction_is_audited(self) -> None:
        result = run_cycle(
            self.db_path,
            now="2026-05-05T00:00:00Z",
            briefing_path=self.briefing_path,
        )
        run_id = result["governed_run"]["run_id"]

        corrected = correct_governed_run_trigger_kind(
            self.db_path,
            run_id,
            trigger_kind="launchd",
            actor="test-auditor",
            source="reports/test.md",
            source_session="test-correction-session",
            reason="historical reconciliation",
        )

        self.assertEqual(corrected["trigger_kind"], "launchd")

        with connect(self.db_path) as connection:
            event = connection.execute(
                """
                SELECT event_type, actor, source, session_id, payload_json
                FROM events
                WHERE event_type = 'ace.governed_run.trigger_kind_corrected'
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()

        self.assertIsNotNone(event)
        self.assertEqual(event["actor"], "test-auditor")
        self.assertEqual(event["source"], "reports/test.md")
        self.assertEqual(event["session_id"], "test-correction-session")
        self.assertIn(run_id, event["payload_json"])


if __name__ == "__main__":
    unittest.main()
