from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import ace.action_runtime as action_runtime
from ace.action_runtime import (
    ACTION_CREATED_BY,
    ACTION_EVIDENCE_URI,
    ACTION_KIND,
    claim_record_operator_followup,
    enqueue_record_operator_followup,
    execute_record_operator_followup,
)
from ace.repository import ItemRepository
from ace.repository import ValidationError
from ace.storage import bootstrap_db, connect, utc_now


class ActionRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "ace.db"
        bootstrap_db(self.db_path)
        self.repo = ItemRepository(self.db_path)
        self.item = self.repo.create_item(item_type="note", title="Action runtime target")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _action_row(self, action_id: str) -> dict[str, object]:
        with connect(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT id, item_id, action_type, payload_json, status, priority,
                       scheduled_at, claimed_at, completed_at, error_message
                FROM action_queue
                WHERE id = ?
                """,
                (action_id,),
            ).fetchone()
        self.assertIsNotNone(row)
        return dict(row)

    def _evidence_rows(self) -> list[dict[str, object]]:
        with connect(self.db_path) as connection:
            rows = connection.execute(
                """
                SELECT item_id, evidence_text, evidence_uri, created_by
                FROM evidence
                WHERE item_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (self.item.id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _insert_action_row(
        self,
        *,
        action_id: str,
        payload_json: str,
        action_type: str = ACTION_KIND,
        status: str = "claimed",
        item_id: str | None = None,
        claimed_at: str | None = None,
    ) -> None:
        now = utc_now()
        with connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO action_queue (
                    id, item_id, action_type, payload_json, status, priority,
                    scheduled_at, claimed_at, completed_at, error_message, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    action_id,
                    item_id if item_id is not None else self.item.id,
                    action_type,
                    payload_json,
                    status,
                    0,
                    None,
                    claimed_at if claimed_at is not None else now,
                    None,
                    None,
                    now,
                    now,
                ),
            )
            connection.commit()

    def test_enqueue_claim_execute_writes_one_evidence_row_and_completes(self) -> None:
        enqueue_result = enqueue_record_operator_followup(
            self.db_path,
            self.item.id,
            note="Call the operator and confirm follow-up",
        )
        self.assertEqual(enqueue_result["action_type"], ACTION_KIND)
        self.assertEqual(enqueue_result["item_id"], self.item.id)
        self.assertEqual(enqueue_result["status"], "queued")

        claim_result = claim_record_operator_followup(self.db_path, enqueue_result["action_id"])
        self.assertEqual(claim_result["status"], "claimed")
        self.assertIsNotNone(claim_result["claimed_at"])

        execute_result = execute_record_operator_followup(self.db_path, enqueue_result["action_id"])
        self.assertEqual(execute_result["status"], "completed")
        self.assertTrue(execute_result["evidence_written"])
        self.assertIsInstance(execute_result["evidence_id"], str)

        action_row = self._action_row(enqueue_result["action_id"])
        self.assertEqual(action_row["status"], "completed")
        self.assertIsNotNone(action_row["claimed_at"])
        self.assertIsNotNone(action_row["completed_at"])
        self.assertIsNone(action_row["error_message"])

        evidence_rows = self._evidence_rows()
        self.assertEqual(len(evidence_rows), 1)
        self.assertEqual(evidence_rows[0]["item_id"], self.item.id)
        self.assertEqual(evidence_rows[0]["evidence_uri"], ACTION_EVIDENCE_URI)
        self.assertEqual(evidence_rows[0]["created_by"], ACTION_CREATED_BY)
        self.assertEqual(
            json.loads(evidence_rows[0]["evidence_text"]),
            {
                "action_id": enqueue_result["action_id"],
                "action_kind": ACTION_KIND,
                "note": "Call the operator and confirm follow-up",
                "outcome": "operator_followup_recorded",
                "target_item_id": self.item.id,
            },
        )

    def test_duplicate_enqueue_reuses_same_deterministic_action_row(self) -> None:
        first = enqueue_record_operator_followup(
            self.db_path,
            self.item.id,
            note="Call the operator and confirm follow-up",
        )
        second = enqueue_record_operator_followup(
            self.db_path,
            self.item.id,
            note="Call the operator and confirm follow-up",
        )

        self.assertEqual(first["action_id"], second["action_id"])

        with connect(self.db_path) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM action_queue WHERE id = ?",
                (first["action_id"],),
            ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_duplicate_execute_does_not_duplicate_evidence(self) -> None:
        action = enqueue_record_operator_followup(
            self.db_path,
            self.item.id,
            note="Call the operator and confirm follow-up",
        )
        claim_record_operator_followup(self.db_path, action["action_id"])

        first = execute_record_operator_followup(self.db_path, action["action_id"])
        second = execute_record_operator_followup(self.db_path, action["action_id"])

        self.assertEqual(first["evidence_id"], second["evidence_id"])
        self.assertTrue(first["evidence_written"])
        self.assertFalse(second["evidence_written"])

        with connect(self.db_path) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM evidence WHERE item_id = ? AND evidence_uri = ? AND created_by = ?",
                (self.item.id, ACTION_EVIDENCE_URI, ACTION_CREATED_BY),
            ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_claim_is_replay_safe_and_does_not_double_claim(self) -> None:
        action = enqueue_record_operator_followup(
            self.db_path,
            self.item.id,
            note="Call the operator and confirm follow-up",
        )

        first_claim = claim_record_operator_followup(self.db_path, action["action_id"])
        second_claim = claim_record_operator_followup(self.db_path, action["action_id"])

        self.assertEqual(first_claim["status"], "claimed")
        self.assertEqual(second_claim["status"], "claimed")
        self.assertEqual(first_claim["claimed_at"], second_claim["claimed_at"])
        self.assertEqual(first_claim["action_id"], second_claim["action_id"])

        action_row = self._action_row(action["action_id"])
        self.assertEqual(action_row["status"], "claimed")
        self.assertEqual(action_row["claimed_at"], first_claim["claimed_at"])

    def test_execute_rejects_unclaimed_actions_without_writing_evidence(self) -> None:
        action = enqueue_record_operator_followup(
            self.db_path,
            self.item.id,
            note="Call the operator and confirm follow-up",
        )

        with self.assertRaises(ValidationError):
            execute_record_operator_followup(self.db_path, action["action_id"])

        action_row = self._action_row(action["action_id"])
        self.assertEqual(action_row["status"], "queued")
        self.assertIsNone(action_row["completed_at"])
        self.assertIsNone(action_row["error_message"])
        self.assertEqual(self._evidence_rows(), [])

    def test_execute_rejects_malformed_payload_without_writing_success_artifact(self) -> None:
        action_id = "action_malformed_payload"
        self._insert_action_row(
            action_id=action_id,
            payload_json='{"broken":',
        )

        result = execute_record_operator_followup(self.db_path, action_id)

        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["evidence_written"])
        self.assertIsNone(result["evidence_id"])
        self.assertIn("malformed", result["error_message"])

        action_row = self._action_row(action_id)
        self.assertEqual(action_row["status"], "failed")
        self.assertIsNotNone(action_row["completed_at"])
        self.assertIsNotNone(action_row["error_message"])
        self.assertEqual(self._evidence_rows(), [])

    def test_execute_rejects_non_object_payload_without_writing_success_artifact(self) -> None:
        action_id = "action_non_object_payload"
        self._insert_action_row(
            action_id=action_id,
            payload_json="[]",
        )

        result = execute_record_operator_followup(self.db_path, action_id)

        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["evidence_written"])
        self.assertIsNone(result["evidence_id"])
        self.assertIn("JSON object", result["error_message"])

        action_row = self._action_row(action_id)
        self.assertEqual(action_row["status"], "failed")
        self.assertIsNotNone(action_row["completed_at"])
        self.assertIsNotNone(action_row["error_message"])
        self.assertEqual(self._evidence_rows(), [])

    def test_failed_execute_marks_failed_and_writes_no_success_artifact(self) -> None:
        missing_item_id = "item_missing"
        action = enqueue_record_operator_followup(
            self.db_path,
            missing_item_id,
            note="Call the operator and confirm follow-up",
        )
        claim_record_operator_followup(self.db_path, action["action_id"])

        result = execute_record_operator_followup(self.db_path, action["action_id"])

        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["evidence_written"])
        self.assertIsNone(result["evidence_id"])
        self.assertIn(missing_item_id, result["error_message"])

        action_row = self._action_row(action["action_id"])
        self.assertEqual(action_row["status"], "failed")
        self.assertIsNotNone(action_row["completed_at"])
        self.assertIsNotNone(action_row["error_message"])

        with connect(self.db_path) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM evidence WHERE item_id = ?",
                (missing_item_id,),
            ).fetchone()[0]
        self.assertEqual(count, 0)

    def test_rejection_enqueue_claim_execute_writes_one_evidence_row_and_completes(self) -> None:
        enqueue_result = action_runtime.enqueue_record_operator_rejection(
            self.db_path,
            self.item.id,
            reason="Operator rejected the proposed change",
        )
        self.assertEqual(enqueue_result["action_type"], action_runtime.REJECTION_ACTION_KIND)
        self.assertEqual(enqueue_result["item_id"], self.item.id)
        self.assertEqual(enqueue_result["status"], "queued")

        claim_result = action_runtime.claim_record_operator_rejection(self.db_path, enqueue_result["action_id"])
        self.assertEqual(claim_result["status"], "claimed")
        self.assertIsNotNone(claim_result["claimed_at"])

        execute_result = action_runtime.execute_record_operator_rejection(self.db_path, enqueue_result["action_id"])
        self.assertEqual(execute_result["status"], "completed")
        self.assertTrue(execute_result["evidence_written"])
        self.assertIsInstance(execute_result["evidence_id"], str)

        action_row = self._action_row(enqueue_result["action_id"])
        self.assertEqual(action_row["status"], "completed")
        self.assertIsNotNone(action_row["claimed_at"])
        self.assertIsNotNone(action_row["completed_at"])
        self.assertIsNone(action_row["error_message"])

        evidence_rows = self._evidence_rows()
        self.assertEqual(len(evidence_rows), 1)
        self.assertEqual(evidence_rows[0]["item_id"], self.item.id)
        self.assertEqual(evidence_rows[0]["evidence_uri"], action_runtime.REJECTION_ACTION_EVIDENCE_URI)
        self.assertEqual(evidence_rows[0]["created_by"], action_runtime.ACTION_CREATED_BY)
        self.assertEqual(
            json.loads(evidence_rows[0]["evidence_text"]),
            {
                "action_id": enqueue_result["action_id"],
                "action_kind": action_runtime.REJECTION_ACTION_KIND,
                "outcome": "operator_rejection_recorded",
                "reason": "Operator rejected the proposed change",
                "target_item_id": self.item.id,
            },
        )

    def test_duplicate_enqueue_reuses_same_deterministic_rejection_action_row(self) -> None:
        first = action_runtime.enqueue_record_operator_rejection(
            self.db_path,
            self.item.id,
            reason="Operator rejected the proposed change",
        )
        second = action_runtime.enqueue_record_operator_rejection(
            self.db_path,
            self.item.id,
            reason="Operator rejected the proposed change",
        )

        self.assertEqual(first["action_id"], second["action_id"])

        with connect(self.db_path) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM action_queue WHERE id = ?",
                (first["action_id"],),
            ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_duplicate_execute_does_not_duplicate_rejection_evidence(self) -> None:
        action = action_runtime.enqueue_record_operator_rejection(
            self.db_path,
            self.item.id,
            reason="Operator rejected the proposed change",
        )
        action_runtime.claim_record_operator_rejection(self.db_path, action["action_id"])

        first = action_runtime.execute_record_operator_rejection(self.db_path, action["action_id"])
        second = action_runtime.execute_record_operator_rejection(self.db_path, action["action_id"])

        self.assertEqual(first["evidence_id"], second["evidence_id"])
        self.assertTrue(first["evidence_written"])
        self.assertFalse(second["evidence_written"])

        with connect(self.db_path) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM evidence WHERE item_id = ? AND evidence_uri = ? AND created_by = ?",
                (self.item.id, action_runtime.REJECTION_ACTION_EVIDENCE_URI, action_runtime.ACTION_CREATED_BY),
            ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_rejection_claim_is_replay_safe_and_does_not_double_claim(self) -> None:
        action = action_runtime.enqueue_record_operator_rejection(
            self.db_path,
            self.item.id,
            reason="Operator rejected the proposed change",
        )

        first_claim = action_runtime.claim_record_operator_rejection(self.db_path, action["action_id"])
        second_claim = action_runtime.claim_record_operator_rejection(self.db_path, action["action_id"])

        self.assertEqual(first_claim["status"], "claimed")
        self.assertEqual(second_claim["status"], "claimed")
        self.assertEqual(first_claim["claimed_at"], second_claim["claimed_at"])
        self.assertEqual(first_claim["action_id"], second_claim["action_id"])

        action_row = self._action_row(action["action_id"])
        self.assertEqual(action_row["status"], "claimed")
        self.assertEqual(action_row["claimed_at"], first_claim["claimed_at"])

    def test_rejection_execute_rejects_malformed_payload_without_writing_success_artifact(self) -> None:
        action_id = "action_rejection_malformed_payload"
        self._insert_action_row(
            action_id=action_id,
            payload_json='{"broken":',
            action_type=action_runtime.REJECTION_ACTION_KIND,
        )

        result = action_runtime.execute_record_operator_rejection(self.db_path, action_id)

        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["evidence_written"])
        self.assertIsNone(result["evidence_id"])
        self.assertIn("malformed", result["error_message"])

        action_row = self._action_row(action_id)
        self.assertEqual(action_row["status"], "failed")
        self.assertIsNotNone(action_row["completed_at"])
        self.assertIsNotNone(action_row["error_message"])
        self.assertEqual(self._evidence_rows(), [])

    def test_rejection_execute_rejects_missing_target_without_writing_success_artifact(self) -> None:
        missing_item_id = "item_missing_rejection"
        action = action_runtime.enqueue_record_operator_rejection(
            self.db_path,
            missing_item_id,
            reason="Operator rejected the proposed change",
        )
        action_runtime.claim_record_operator_rejection(self.db_path, action["action_id"])

        result = action_runtime.execute_record_operator_rejection(self.db_path, action["action_id"])

        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["evidence_written"])
        self.assertIsNone(result["evidence_id"])
        self.assertIn(missing_item_id, result["error_message"])

        action_row = self._action_row(action["action_id"])
        self.assertEqual(action_row["status"], "failed")
        self.assertIsNotNone(action_row["completed_at"])
        self.assertIsNotNone(action_row["error_message"])

        with connect(self.db_path) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM evidence WHERE item_id = ?",
                (missing_item_id,),
            ).fetchone()[0]
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
