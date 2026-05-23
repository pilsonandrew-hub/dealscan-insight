from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from ace.scripts.b_cutover_execute import (
    EXIT_POST_COMMIT_FAILURE,
    EXIT_PRE_COMMIT_FAILURE,
    EXIT_SUCCESS,
    RECOVERY_INSTRUCTIONS,
    execute_cutover,
)
from ace.storage import (
    CUTOVER_EVENT_TYPE,
    CUTOVER_EXECUTE_AUTHORIZATION_TOKEN,
    append_event,
    bootstrap_db,
    connect,
    post_cutover_event_hash_chain,
)


class BCutoverExecuteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.db_path = self.root / "ace.db"
        self.log_path = self.root / "cutover.jsonl"
        bootstrap_db(self.db_path)
        with connect(self.db_path) as connection:
            self.legacy_event_id = append_event(
                connection,
                event_type="item.legacy",
                payload={"legacy": True},
                actor="test",
                source="ace/tests/test_b_cutover_execute.py",
                session_id="legacy:test",
            )
            connection.commit()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _execute(self, **overrides: object) -> tuple[int, str | None]:
        kwargs = {
            "db_path": self.db_path,
            "log_path": self.log_path,
            "authorization_token": CUTOVER_EXECUTE_AUTHORIZATION_TOKEN,
            "governing_decision_reference": "test operator approval",
            "actor": "test",
            "source": "ace/tests/test_b_cutover_execute.py",
            "session_id": "v1.1-cutover:test",
        }
        kwargs.update(overrides)
        return execute_cutover(**kwargs)  # type: ignore[arg-type]

    def _log_records(self) -> list[dict[str, object]]:
        return [json.loads(line) for line in self.log_path.read_text(encoding="utf-8").splitlines()]

    def _cutover_count(self) -> int:
        with closing(sqlite3.connect(self.db_path)) as connection:
            return connection.execute(
                "SELECT COUNT(*) FROM events WHERE event_type = ?",
                (CUTOVER_EVENT_TYPE,),
            ).fetchone()[0]

    def test_script_refuses_without_authorization_token(self) -> None:
        exit_code, cutover_id = self._execute(authorization_token="wrong")

        self.assertEqual(EXIT_PRE_COMMIT_FAILURE, exit_code)
        self.assertIsNone(cutover_id)
        self.assertEqual(0, self._cutover_count())
        records = self._log_records()
        self.assertEqual("run.failed.pre_commit", records[-1]["step"])
        self.assertIn("authorization", records[-1]["detail"])

    def test_script_refuses_if_cutover_already_exists(self) -> None:
        first_exit, first_cutover_id = self._execute()
        self.assertEqual(EXIT_SUCCESS, first_exit)
        self.assertIsNotNone(first_cutover_id)

        second_log = self.root / "second.jsonl"
        second_exit, second_cutover_id = execute_cutover(
            db_path=self.db_path,
            log_path=second_log,
            authorization_token=CUTOVER_EXECUTE_AUTHORIZATION_TOKEN,
            governing_decision_reference="test operator approval",
            actor="test",
            source="ace/tests/test_b_cutover_execute.py",
            session_id="v1.1-cutover:test-second",
        )

        self.assertEqual(EXIT_PRE_COMMIT_FAILURE, second_exit)
        self.assertIsNone(second_cutover_id)
        self.assertEqual(1, self._cutover_count())
        records = [json.loads(line) for line in second_log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual("run.failed.pre_commit", records[-1]["step"])
        self.assertIn("already exists", records[-1]["detail"])

    def test_pre_commit_failure_writes_no_cutover_and_is_safe_to_retry(self) -> None:
        exit_code, cutover_id = self._execute(failpoint="pre_commit")

        self.assertEqual(EXIT_PRE_COMMIT_FAILURE, exit_code)
        self.assertIsNone(cutover_id)
        self.assertEqual(0, self._cutover_count())
        records = self._log_records()
        self.assertEqual("run.failed.pre_commit", records[-1]["step"])
        self.assertFalse(records[-1]["commit_completed"])

    def test_post_commit_failure_logs_manual_recovery_required(self) -> None:
        exit_code, cutover_id = self._execute(failpoint="post_commit")

        self.assertEqual(EXIT_POST_COMMIT_FAILURE, exit_code)
        self.assertIsNotNone(cutover_id)
        self.assertEqual(1, self._cutover_count())
        records = self._log_records()
        self.assertEqual("run.failed.post_commit", records[-1]["step"])
        self.assertTrue(records[-1]["commit_completed"])
        self.assertEqual(cutover_id, records[-1]["cutover_event_id"])
        self.assertEqual(RECOVERY_INSTRUCTIONS, records[-1]["recovery_instructions"])
        self.assertEqual(post_cutover_event_hash_chain(self.db_path), (True, None))

    def test_recovery_procedure_is_testable_after_post_commit_crash(self) -> None:
        exit_code, cutover_id = self._execute(failpoint="post_commit")
        self.assertEqual(EXIT_POST_COMMIT_FAILURE, exit_code)
        self.assertIsNotNone(cutover_id)

        with closing(sqlite3.connect(self.db_path)) as connection:
            event_ids = [
                row[0]
                for row in connection.execute(
                    "SELECT event_id FROM events WHERE event_type = ?",
                    (CUTOVER_EVENT_TYPE,),
                ).fetchall()
            ]
        self.assertEqual([cutover_id], event_ids)
        self.assertEqual(post_cutover_event_hash_chain(self.db_path), (True, None))
        self.assertIn("audit verify", RECOVERY_INSTRUCTIONS)

    def test_success_logs_commit_and_followup(self) -> None:
        exit_code, cutover_id = self._execute()

        self.assertEqual(EXIT_SUCCESS, exit_code)
        self.assertIsNotNone(cutover_id)
        records = self._log_records()
        steps = [record["step"] for record in records]
        self.assertIn("cutover.commit.after", steps)
        self.assertIn("post_commit.followup.after", steps)
        self.assertEqual("run.completed", records[-1]["step"])
        self.assertEqual(post_cutover_event_hash_chain(self.db_path), (True, None))


if __name__ == "__main__":
    unittest.main()
