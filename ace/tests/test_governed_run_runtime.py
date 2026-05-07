from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ace.governed_run_runtime import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_INTERRUPTED,
    STATUS_RUNNING,
    complete_governed_run,
    create_governed_cycle_run,
    fail_governed_run,
    get_governed_cycle_run_status,
    interrupt_governed_run,
    mark_governed_run_running,
    start_governed_run,
)
from ace.repository import ValidationError
from ace.storage import bootstrap_db, connect


class GovernedRunRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "ace.db"
        bootstrap_db(self.db_path)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_duplicate_completion_is_replay_safe(self) -> None:
        run = create_governed_cycle_run(self.db_path)
        start_governed_run(self.db_path, run["run_id"])
        mark_governed_run_running(self.db_path, run["run_id"])

        first = complete_governed_run(
            self.db_path,
            run["run_id"],
            briefing_path="/tmp/briefing.md",
            notification_action_id="action_1",
            delivery_evidence_id="evidence_1",
        )
        second = complete_governed_run(
            self.db_path,
            run["run_id"],
            briefing_path="/tmp/briefing.md",
            notification_action_id="action_1",
            delivery_evidence_id="evidence_1",
        )

        self.assertEqual(first["status"], STATUS_COMPLETED)
        self.assertEqual(second["status"], STATUS_COMPLETED)
        self.assertEqual(first["ended_at"], second["ended_at"])

    def test_illegal_terminal_transition_fails_loudly(self) -> None:
        run = create_governed_cycle_run(self.db_path)
        with self.assertRaises(ValidationError):
            complete_governed_run(self.db_path, run["run_id"])

    def test_status_surface_returns_current_and_last_terminal_truth(self) -> None:
        first = create_governed_cycle_run(self.db_path)
        start_governed_run(self.db_path, first["run_id"])
        mark_governed_run_running(self.db_path, first["run_id"])
        fail_governed_run(self.db_path, first["run_id"], failure_code="x", failure_summary="failed")

        second = create_governed_cycle_run(self.db_path)
        start_governed_run(self.db_path, second["run_id"])

        status = get_governed_cycle_run_status(self.db_path)
        self.assertIsNotNone(status["current_run"])
        self.assertEqual(status["current_run"]["run_id"], second["run_id"])
        self.assertEqual(status["current_run"]["status"], "starting")
        self.assertIsNotNone(status["last_terminal_run"])
        self.assertEqual(status["last_terminal_run"]["run_id"], first["run_id"])
        self.assertEqual(status["last_terminal_run"]["status"], STATUS_FAILED)

    def test_interrupt_persists_interrupted_terminal_state(self) -> None:
        run = create_governed_cycle_run(self.db_path)
        start_governed_run(self.db_path, run["run_id"])
        mark_governed_run_running(self.db_path, run["run_id"])

        interrupted = interrupt_governed_run(
            self.db_path,
            run["run_id"],
            failure_code="cycle_interrupted",
            failure_summary="manual interrupt",
        )

        self.assertEqual(interrupted["status"], STATUS_INTERRUPTED)
        self.assertIsNotNone(interrupted["interrupted_at"])

        with connect(self.db_path) as connection:
            row = connection.execute(
                "SELECT status, interrupted_at FROM governed_runs WHERE run_id = ?",
                (run["run_id"],),
            ).fetchone()
        self.assertEqual(row["status"], STATUS_INTERRUPTED)
        self.assertIsNotNone(row["interrupted_at"])
