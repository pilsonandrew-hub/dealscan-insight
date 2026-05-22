from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ace.operator_constraints import (
    OperatorConstraintViolation,
    clear_operator_constraint,
    enforce_operator_constraints,
    list_operator_constraints,
    set_operator_constraint,
)
from ace.storage import bootstrap_db, connect


class OperatorConstraintTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "ace.db"
        bootstrap_db(self.db_path)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_approval_required_blocks_write_command_and_records_attempt(self) -> None:
        constraint = set_operator_constraint(
            self.db_path,
            mode="approval_required",
            reason="wait for explicit operator approval",
            actor="test",
        )

        with self.assertRaises(OperatorConstraintViolation) as exc:
            enforce_operator_constraints(
                self.db_path,
                command_key="intake",
                attempted_action="intake",
                actor="test-runner",
            )

        self.assertEqual(exc.exception.constraint.constraint_id, constraint.constraint_id)
        self.assertIn("OPERATOR_CONSTRAINT_BLOCKED", str(exc.exception))
        with connect(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT event_type, payload_json, actor
                FROM events
                WHERE event_type = 'operator_constraint.violation_attempted'
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertIn('"blocked":true', row["payload_json"])
        self.assertIn(constraint.constraint_id, row["payload_json"])

    def test_read_only_commands_remain_allowed_under_investigation_only(self) -> None:
        set_operator_constraint(
            self.db_path,
            mode="investigation_only",
            reason="read-only investigation",
            actor="test",
        )

        enforce_operator_constraints(self.db_path, command_key="audit", attempted_action="audit")
        enforce_operator_constraints(self.db_path, command_key="show", attempted_action="show")

    def test_clear_constraint_unblocks_write_command(self) -> None:
        constraint = set_operator_constraint(
            self.db_path,
            mode="no_state_writes",
            reason="temporary freeze",
            actor="test",
        )
        clear_operator_constraint(
            self.db_path,
            constraint_id=constraint.constraint_id,
            reason="explicit approval",
            actor="operator",
        )

        enforce_operator_constraints(self.db_path, command_key="intake", attempted_action="intake")
        active = list_operator_constraints(self.db_path)
        self.assertEqual(active, [])


if __name__ == "__main__":
    unittest.main()
