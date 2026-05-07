from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ace.governed_run_runtime import correct_governed_run_trigger_kind, create_governed_cycle_run
from ace.storage import bootstrap_db, connect


class GovernedRunRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "ace.db"
        bootstrap_db(self.db_path)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_correct_governed_run_trigger_kind_updates_row_and_emits_audit_event(self) -> None:
        run = create_governed_cycle_run(self.db_path, trigger_kind="operator")

        corrected = correct_governed_run_trigger_kind(
            self.db_path,
            run["run_id"],
            trigger_kind="launchd",
            actor="test-auditor",
            source="reports/test.md",
            source_session="test-governed-run-correction",
            reason="historical trigger reconciliation",
        )

        self.assertEqual(corrected["trigger_kind"], "launchd")

        with connect(self.db_path) as connection:
            row = connection.execute(
                "SELECT trigger_kind FROM governed_runs WHERE run_id = ?",
                (run["run_id"],),
            ).fetchone()
            event = connection.execute(
                """
                SELECT event_type, actor, source, session_id, payload_json
                FROM events
                WHERE event_type = 'ace.governed_run.trigger_kind_corrected'
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()

        self.assertEqual(row["trigger_kind"], "launchd")
        self.assertIsNotNone(event)
        self.assertEqual(event["actor"], "test-auditor")
        self.assertEqual(event["source"], "reports/test.md")
        self.assertEqual(event["session_id"], "test-governed-run-correction")
        self.assertIn(run["run_id"], event["payload_json"])

    def test_correct_governed_run_trigger_kind_emits_audit_event_even_when_value_already_matches(self) -> None:
        run = create_governed_cycle_run(self.db_path, trigger_kind="launchd")

        corrected = correct_governed_run_trigger_kind(
            self.db_path,
            run["run_id"],
            trigger_kind="launchd",
            actor="test-auditor",
            source="reports/test.md",
            source_session="test-governed-run-noop-correction",
            reason="re-assert launchd trigger truth",
        )

        self.assertEqual(corrected["trigger_kind"], "launchd")

        with connect(self.db_path) as connection:
            event = connection.execute(
                """
                SELECT payload_json
                FROM events
                WHERE event_type = 'ace.governed_run.trigger_kind_corrected'
                  AND session_id = 'test-governed-run-noop-correction'
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()

        self.assertIsNotNone(event)
        self.assertIn('"changed":false', event["payload_json"])


if __name__ == "__main__":
    unittest.main()
