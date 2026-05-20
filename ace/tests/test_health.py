from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ace.action_runtime import enqueue_operator_notification
from ace.action_runtime import NOTIFICATION_ACTION_CREATED_BY, NOTIFICATION_ACTION_EVIDENCE_URI
from ace.governed_run_runtime import (
    create_governed_cycle_run,
    fail_governed_run,
    mark_governed_run_running,
    start_governed_run,
)
from ace.health import generate_health_summary, render_health_summary_lines
from ace.repository import ItemRepository
from ace.storage import bootstrap_db, connect, new_id
from ace.supervisor_runtime import RUNTIME_FAMILY_SINGLE_TENANT, start_supervisor_runtime


class HealthSummaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "ace.db"
        bootstrap_db(self.db_path)
        self.repo = ItemRepository(self.db_path)
        self.item = self.repo.create_item(item_type="task", title="Health target")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_generate_health_summary_is_green_for_empty_ledgers(self) -> None:
        summary = generate_health_summary(self.db_path, now="2026-05-20T10:00:00Z")

        self.assertTrue(summary["ok"])
        self.assertEqual(summary["issue_count"], 0)
        self.assertEqual(summary["active_action_count"], 0)
        self.assertEqual(summary["failed_action_count"], 0)
        self.assertEqual(summary["active_run_count"], 0)
        self.assertEqual(summary["failed_run_count"], 0)
        self.assertEqual(summary["skipped_run_count"], 0)
        self.assertEqual(summary["stale_runtime_count"], 0)
        self.assertEqual(summary["failed_alert_count"], 0)
        self.assertEqual(summary["alert_gap_count"], 0)

    def test_generate_health_summary_surfaces_core_operator_health_issues(self) -> None:
        enqueue_operator_notification(
            self.db_path,
            self.item.id,
            channel="jace",
            target="7529788084",
            reason="stale_triage",
            age_context="48h stale",
        )
        active_run = create_governed_cycle_run(self.db_path, trigger_kind="launchd")
        start_governed_run(self.db_path, active_run["run_id"])
        failed_run = create_governed_cycle_run(self.db_path, trigger_kind="launchd")
        start_governed_run(self.db_path, failed_run["run_id"])
        mark_governed_run_running(self.db_path, failed_run["run_id"])
        fail_governed_run(
            self.db_path,
            failed_run["run_id"],
            failure_code="test_failure",
            failure_summary="test failure",
        )
        runtime = start_supervisor_runtime(
            self.db_path,
            runtime_family=RUNTIME_FAMILY_SINGLE_TENANT,
            stale_after_seconds=60,
        )
        with connect(self.db_path) as connection:
            connection.execute(
                "UPDATE runtime_instances SET status = 'live', last_seen_at = ?, updated_at = ? WHERE runtime_instance_id = ?",
                ("2026-05-20T09:00:00Z", "2026-05-20T09:00:00Z", runtime["runtime_instance_id"]),
            )
            connection.execute(
                """
                INSERT INTO alert_log(
                    id, alert_type, transport, bot_username, chat_id, message_id,
                    delivery_state, sent_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id("alert"),
                    "operator_notification",
                    "telegram_bot_api",
                    "JACE",
                    "7529788084",
                    "123",
                    "failed",
                    "2026-05-20T09:01:00Z",
                    "{}",
                ),
            )
            connection.commit()

        summary = generate_health_summary(
            self.db_path,
            now="2026-05-20T10:00:00Z",
            stale_runtime_seconds=60,
        )

        self.assertFalse(summary["ok"])
        self.assertGreaterEqual(summary["issue_count"], 4)
        self.assertEqual(summary["active_action_count"], 1)
        self.assertEqual(summary["active_run_count"], 1)
        self.assertEqual(summary["failed_run_count"], 1)
        self.assertEqual(summary["stale_runtime_count"], 1)
        self.assertEqual(summary["failed_alert_count"], 1)

    def test_notification_alert_gap_uses_durable_delivery_evidence(self) -> None:
        enqueue_operator_notification(
            self.db_path,
            self.item.id,
            channel="telegram",
            target="7529788084",
            reason="legacy_gateway_transport",
            age_context="legacy proof",
        )
        with connect(self.db_path) as connection:
            action = connection.execute(
                "SELECT id FROM action_queue WHERE action_type = 'send_operator_notification'"
            ).fetchone()
            self.assertIsNotNone(action)
            action_id = action["id"]
            connection.execute(
                "UPDATE action_queue SET status = 'completed', completed_at = ?, updated_at = ? WHERE id = ?",
                ("2026-05-20T09:00:00Z", "2026-05-20T09:00:00Z", action_id),
            )
            connection.execute(
                """
                INSERT INTO evidence(id, item_id, evidence_text, evidence_uri, created_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id("evidence"),
                    self.item.id,
                    "legacy OpenClaw delivery evidence",
                    NOTIFICATION_ACTION_EVIDENCE_URI,
                    NOTIFICATION_ACTION_CREATED_BY,
                    "2026-05-20T09:00:00Z",
                ),
            )
            connection.commit()

        summary = generate_health_summary(self.db_path, now="2026-05-20T10:00:00Z")

        self.assertEqual(summary["completed_notification_action_count"], 1)
        self.assertEqual(summary["notification_delivery_evidence_count"], 1)
        self.assertEqual(summary["alert_delivery_count"], 0)
        self.assertEqual(summary["alert_gap_count"], 0)

    def test_notification_alert_gap_flags_completed_action_without_delivery_evidence(self) -> None:
        enqueue_operator_notification(
            self.db_path,
            self.item.id,
            channel="telegram",
            target="7529788084",
            reason="legacy_gateway_transport",
            age_context="legacy proof",
        )
        with connect(self.db_path) as connection:
            action = connection.execute(
                "SELECT id FROM action_queue WHERE action_type = 'send_operator_notification'"
            ).fetchone()
            self.assertIsNotNone(action)
            connection.execute(
                "UPDATE action_queue SET status = 'completed', completed_at = ?, updated_at = ? WHERE id = ?",
                ("2026-05-20T09:00:00Z", "2026-05-20T09:00:00Z", action["id"]),
            )
            connection.commit()

        summary = generate_health_summary(self.db_path, now="2026-05-20T10:00:00Z")

        self.assertEqual(summary["completed_notification_action_count"], 1)
        self.assertEqual(summary["notification_delivery_evidence_count"], 0)
        self.assertEqual(summary["alert_gap_count"], 1)

    def test_render_health_summary_lines_is_deterministic(self) -> None:
        summary = generate_health_summary(self.db_path, now="2026-05-20T10:00:00Z")

        rendered = render_health_summary_lines(summary)

        self.assertEqual(rendered[0], "health.generated_at=2026-05-20T10:00:00Z")
        self.assertIn("health.ok=true", rendered)
        self.assertIn("health.issue_count=0", rendered)


if __name__ == "__main__":
    unittest.main()
