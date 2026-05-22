from __future__ import annotations

import io
import sqlite3
import tempfile
import unittest
from contextlib import closing, redirect_stdout
from pathlib import Path

from ace.ace import main
from ace.operator_constraints import list_operator_constraints
from ace.storage import bootstrap_db


class OperatorConstraintRuntimeTests(unittest.TestCase):
    def run_cli(self, *argv: str) -> tuple[int, str]:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main(list(argv))
        return code, buffer.getvalue()

    def test_investigation_only_blocks_intake_and_records_violation_without_item_creation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "ace.db"
            code, output = self.run_cli(
                "--db",
                str(db_path),
                "constraints",
                "set",
                "--mode",
                "investigation_only",
                "--scope",
                "ace",
                "--reason",
                "operator asked for proposal only",
                "--actor",
                "andrew",
            )
            self.assertEqual(code, 0, output)

            code, output = self.run_cli("--db", str(db_path), "intake", "task", "Must be blocked")

            self.assertEqual(code, 1, output)
            self.assertIn("OPERATOR_CONSTRAINT_BLOCKED", output)
            self.assertIn("active_constraint=investigation_only", output)
            self.assertIn("attempted_action=intake", output)
            with closing(sqlite3.connect(db_path)) as connection:
                connection.row_factory = sqlite3.Row
                item_count = connection.execute("SELECT COUNT(*) AS c FROM items").fetchone()["c"]
                violation_count = connection.execute(
                    "SELECT COUNT(*) AS c FROM events WHERE event_type = 'operator_constraint.violation_attempted'"
                ).fetchone()["c"]
            self.assertEqual(item_count, 0)
            self.assertEqual(violation_count, 1)

    def test_read_only_commands_remain_allowed_under_investigation_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "ace.db"
            self.run_cli(
                "--db",
                str(db_path),
                "constraints",
                "set",
                "--mode",
                "investigation_only",
                "--scope",
                "ace",
                "--reason",
                "read only",
            )

            code, output = self.run_cli("--db", str(db_path), "audit", "verify")

            self.assertEqual(code, 0, output)
            self.assertIn("audit.verify.event_hash_chain=ok", output)

    def test_no_notifications_blocks_jace_status_send_before_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "ace.db"
            bootstrap_db(db_path)
            self.run_cli(
                "--db",
                str(db_path),
                "constraints",
                "set",
                "--mode",
                "no_notifications",
                "--scope",
                "ace",
                "--reason",
                "no outgoing messages",
            )

            code, output = self.run_cli(
                "--db",
                str(db_path),
                "jace-status-send",
                "item_missing",
                "would send if not blocked",
            )

            self.assertEqual(code, 1, output)
            self.assertIn("OPERATOR_CONSTRAINT_BLOCKED", output)
            self.assertIn("attempted_action=jace-status-send", output)
            with closing(sqlite3.connect(db_path)) as connection:
                connection.row_factory = sqlite3.Row
                alert_count = connection.execute("SELECT COUNT(*) AS c FROM alert_log").fetchone()["c"]
                violation_count = connection.execute(
                    "SELECT COUNT(*) AS c FROM events WHERE event_type = 'operator_constraint.violation_attempted'"
                ).fetchone()["c"]
            self.assertEqual(alert_count, 0)
            self.assertEqual(violation_count, 1)

    def test_clear_constraint_unblocks_write_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "ace.db"
            self.run_cli(
                "--db",
                str(db_path),
                "constraints",
                "set",
                "--mode",
                "approval_required",
                "--scope",
                "ace",
                "--reason",
                "wait for approval",
            )
            constraint = list_operator_constraints(db_path, active_only=True)[0]

            code, output = self.run_cli(
                "--db",
                str(db_path),
                "constraints",
                "clear",
                constraint.id,
                "--reason",
                "Andrew explicitly approved implementation",
                "--actor",
                "andrew",
            )
            self.assertEqual(code, 0, output)

            code, output = self.run_cli("--db", str(db_path), "intake", "task", "Allowed now")

            self.assertEqual(code, 0, output)
            self.assertIn("state=TRIAGE", output)
            self.assertEqual(list_operator_constraints(db_path, active_only=True), [])


if __name__ == "__main__":
    unittest.main()
