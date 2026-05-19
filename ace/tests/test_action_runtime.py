from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import ace.action_runtime as action_runtime
from ace.action_runtime import (
    ACTION_CREATED_BY,
    ACTION_EVIDENCE_URI,
    ACTION_KIND,
    JACE_STATUS_CREATED_BY,
    JACE_STATUS_EVIDENCE_URI,
    NOTIFICATION_ACTION_EVIDENCE_URI,
    NOTIFICATION_ACTION_KIND,
    claim_record_operator_followup,
    claim_operator_notification,
    enqueue_record_operator_followup,
    enqueue_operator_notification,
    execute_record_operator_followup,
    execute_operator_notification,
    send_jace_status_message,
    send_operator_notification,
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

    def test_notification_enqueue_claim_execute_writes_one_evidence_row_and_completes(self) -> None:
        action = enqueue_operator_notification(
            self.db_path,
            self.item.id,
            channel="telegram",
            target="telegram:7529788084",
            reason="stale_triage",
            age_context="48h stale",
        )
        self.assertEqual(action["action_type"], NOTIFICATION_ACTION_KIND)
        self.assertEqual(action["status"], "queued")

        claim = claim_operator_notification(self.db_path, action["action_id"])
        self.assertEqual(claim["status"], "claimed")

        sender_calls: list[dict[str, object]] = []

        def fake_sender(**kwargs: object) -> dict[str, object]:
            sender_calls.append(kwargs)
            return {"ok": True, "provider": "test"}

        result = execute_operator_notification(
            self.db_path,
            action["action_id"],
            sender=fake_sender,
        )
        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["evidence_written"])
        self.assertEqual(len(sender_calls), 1)
        self.assertEqual(sender_calls[0]["channel"], "telegram")
        self.assertEqual(sender_calls[0]["target"], "telegram:7529788084")

        with connect(self.db_path) as connection:
            row = connection.execute(
                "SELECT evidence_text, evidence_uri, created_by FROM evidence WHERE item_id = ? ORDER BY created_at ASC, id ASC LIMIT 1",
                (self.item.id,),
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["evidence_uri"], NOTIFICATION_ACTION_EVIDENCE_URI)
        self.assertEqual(row["created_by"], action_runtime.NOTIFICATION_ACTION_CREATED_BY)
        payload = json.loads(row["evidence_text"])
        self.assertEqual(payload["action_kind"], NOTIFICATION_ACTION_KIND)
        self.assertEqual(payload["outcome"], "operator_notification_sent")
        self.assertEqual(payload["target_item_id"], self.item.id)

    def test_notification_duplicate_enqueue_reuses_same_deterministic_row(self) -> None:
        first = enqueue_operator_notification(
            self.db_path,
            self.item.id,
            channel="telegram",
            target="telegram:7529788084",
            reason="stale_triage",
            age_context="48h stale",
        )
        second = enqueue_operator_notification(
            self.db_path,
            self.item.id,
            channel="telegram",
            target="telegram:7529788084",
            reason="stale_triage",
            age_context="48h stale",
        )
        self.assertEqual(first["action_id"], second["action_id"])

    def test_notification_duplicate_execute_does_not_duplicate_evidence(self) -> None:
        action = enqueue_operator_notification(
            self.db_path,
            self.item.id,
            channel="telegram",
            target="telegram:7529788084",
            reason="stale_triage",
            age_context="48h stale",
        )
        claim_operator_notification(self.db_path, action["action_id"])

        def fake_sender(**kwargs: object) -> dict[str, object]:
            return {"ok": True, "provider": "test"}

        first = execute_operator_notification(self.db_path, action["action_id"], sender=fake_sender)
        second = execute_operator_notification(self.db_path, action["action_id"], sender=fake_sender)
        self.assertEqual(first["evidence_id"], second["evidence_id"])
        self.assertTrue(first["evidence_written"])
        self.assertFalse(second["evidence_written"])

        with connect(self.db_path) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM evidence WHERE item_id = ? AND evidence_uri = ? AND created_by = ?",
                (self.item.id, NOTIFICATION_ACTION_EVIDENCE_URI, action_runtime.NOTIFICATION_ACTION_CREATED_BY),
            ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_notification_execute_marks_failed_on_delivery_error(self) -> None:
        action = enqueue_operator_notification(
            self.db_path,
            self.item.id,
            channel="telegram",
            target="telegram:7529788084",
            reason="stale_triage",
            age_context="48h stale",
        )
        claim_operator_notification(self.db_path, action["action_id"])

        def failing_sender(**kwargs: object) -> dict[str, object]:
            raise action_runtime.NotificationDeliveryError("telegram send failed")

        result = execute_operator_notification(self.db_path, action["action_id"], sender=failing_sender)
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["evidence_written"])
        self.assertIn(action_runtime.NOTIFICATION_FAILURE_CODE, result["error_message"])

    def test_notification_execute_marks_failed_on_missing_target_item(self) -> None:
        action = enqueue_operator_notification(
            self.db_path,
            self.item.id,
            channel="telegram",
            target="telegram:7529788084",
            reason="stale_triage",
            age_context="48h stale",
        )
        claim_operator_notification(self.db_path, action["action_id"])

        with connect(self.db_path) as connection:
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute("DELETE FROM items WHERE id = ?", (self.item.id,))
            connection.commit()

        result = execute_operator_notification(self.db_path, action["action_id"], sender=lambda **kwargs: {"ok": True})
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["evidence_written"])
        self.assertIn(action_runtime.NOTIFICATION_FAILURE_CODE, result["error_message"])

    def test_notification_enqueue_requires_age_or_deadline_context(self) -> None:
        with self.assertRaises(ValidationError):
            enqueue_operator_notification(
                self.db_path,
                self.item.id,
                channel="telegram",
                target="telegram:7529788084",
                reason="stale_triage",
            )

    def test_jace_status_send_uses_dedicated_bot_and_records_delivery_evidence(self) -> None:
        telegram_calls: list[tuple[str, dict[str, object]]] = []

        def fake_telegram_request(token: str, method: str, params: dict[str, object]) -> dict[str, object]:
            telegram_calls.append((method, params))
            self.assertEqual(token, "jace-token")
            if method == "getMe":
                return {"ok": True, "result": {"username": "JACEthaACE_Bot"}}
            if method == "sendMessage":
                self.assertEqual(params["chat_id"], "7529788084")
                self.assertEqual(params["text"], "JACE proof message")
                return {"ok": True, "result": {"message_id": 4242}}
            raise AssertionError(method)

        with patch.dict(
            action_runtime.os.environ,
            {
                "ACE_TELEGRAM_BOT_TOKEN": "jace-token",
                "ACE_TELEGRAM_CHAT_ID": "7529788084",
            },
            clear=False,
        ), patch.object(action_runtime, "_telegram_bot_api_request", side_effect=fake_telegram_request):
            result = send_jace_status_message(
                self.db_path,
                self.item.id,
                message="JACE proof message",
            )

        self.assertEqual([call[0] for call in telegram_calls], ["getMe", "sendMessage"])
        self.assertEqual(result["delivery_state"], "sent")
        self.assertEqual(result["message_id"], "4242")
        self.assertEqual(result["bot_username"], "JACEthaACE_Bot")
        self.assertTrue(result["evidence_written"])

        with connect(self.db_path) as connection:
            alert = connection.execute(
                "SELECT alert_type, transport, bot_username, chat_id, message_id, delivery_state FROM alert_log WHERE id = ?",
                (result["alert_id"],),
            ).fetchone()
            evidence = connection.execute(
                "SELECT evidence_text, evidence_uri, created_by FROM evidence WHERE id = ?",
                (result["evidence_id"],),
            ).fetchone()
        self.assertIsNotNone(alert)
        self.assertEqual(alert["alert_type"], "jace_status")
        self.assertEqual(alert["transport"], "telegram_bot_api")
        self.assertEqual(alert["bot_username"], "JACEthaACE_Bot")
        self.assertEqual(alert["chat_id"], "7529788084")
        self.assertEqual(alert["message_id"], "4242")
        self.assertEqual(alert["delivery_state"], "sent")
        self.assertIsNotNone(evidence)
        self.assertEqual(evidence["evidence_uri"], JACE_STATUS_EVIDENCE_URI)
        self.assertEqual(evidence["created_by"], JACE_STATUS_CREATED_BY)
        payload = json.loads(evidence["evidence_text"])
        self.assertEqual(payload["outcome"], "jace_status_message_sent")
        self.assertEqual(payload["transport"], "telegram_bot_api")
        self.assertEqual(payload["message_id"], "4242")

    def test_jace_status_send_records_each_successful_delivery_attempt(self) -> None:
        message_counter = {"value": 4241}

        def fake_telegram_request(token: str, method: str, params: dict[str, object]) -> dict[str, object]:
            self.assertEqual(token, "jace-token")
            if method == "getMe":
                return {"ok": True, "result": {"username": "JACEthaACE_Bot"}}
            if method == "sendMessage":
                message_counter["value"] += 1
                return {"ok": True, "result": {"message_id": message_counter["value"]}}
            raise AssertionError(method)

        with patch.dict(
            action_runtime.os.environ,
            {
                "ACE_TELEGRAM_BOT_TOKEN": "jace-token",
                "ACE_TELEGRAM_CHAT_ID": "7529788084",
            },
            clear=False,
        ), patch.object(action_runtime, "_telegram_bot_api_request", side_effect=fake_telegram_request):
            first = send_jace_status_message(self.db_path, self.item.id, message="JACE proof message")
            second = send_jace_status_message(self.db_path, self.item.id, message="JACE proof message")

        self.assertTrue(first["evidence_written"])
        self.assertTrue(second["evidence_written"])
        self.assertNotEqual(first["alert_id"], second["alert_id"])
        self.assertNotEqual(first["evidence_id"], second["evidence_id"])
        self.assertEqual(first["message_id"], "4242")
        self.assertEqual(second["message_id"], "4243")
        with connect(self.db_path) as connection:
            evidence_count = connection.execute(
                "SELECT COUNT(*) FROM evidence WHERE evidence_uri = ? AND created_by = ?",
                (JACE_STATUS_EVIDENCE_URI, JACE_STATUS_CREATED_BY),
            ).fetchone()[0]
            alert_count = connection.execute(
                "SELECT COUNT(*) FROM alert_log WHERE alert_type = 'jace_status'",
            ).fetchone()[0]
        self.assertEqual(evidence_count, 2)
        self.assertEqual(alert_count, 2)

    def test_jace_status_send_fails_without_dedicated_token(self) -> None:
        with patch.dict(action_runtime.os.environ, {}, clear=True), patch.object(
            action_runtime,
            "load_ace_telegram_env_file",
            return_value=False,
        ):
            with self.assertRaises(action_runtime.JaceStatusDeliveryError):
                send_jace_status_message(self.db_path, self.item.id, message="No token")

    def test_operator_notification_can_route_through_jace_owned_bot(self) -> None:
        telegram_calls: list[tuple[str, dict[str, object]]] = []

        def fake_telegram_request(token: str, method: str, params: dict[str, object]) -> dict[str, object]:
            telegram_calls.append((method, params))
            self.assertEqual(token, "jace-token")
            if method == "getMe":
                return {"ok": True, "result": {"username": "JACEthaACE_Bot"}}
            if method == "sendMessage":
                self.assertEqual(params["chat_id"], "7529788084")
                self.assertIn(str(self.item.id), str(params["text"]))
                return {"ok": True, "result": {"message_id": 5252}}
            raise AssertionError(method)

        with patch.dict(
            action_runtime.os.environ,
            {
                "ACE_TELEGRAM_BOT_TOKEN": "jace-token",
                "ACE_TELEGRAM_CHAT_ID": "7529788084",
            },
            clear=False,
        ), patch.object(action_runtime, "_telegram_bot_api_request", side_effect=fake_telegram_request):
            result = send_operator_notification(
                self.db_path,
                self.item.id,
                channel="jace",
                target="7529788084",
                reason="stale_triage",
                age_context="48h stale",
            )

        self.assertEqual([call[0] for call in telegram_calls], ["getMe", "sendMessage"])
        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["evidence_written"])

        with connect(self.db_path) as connection:
            notification_evidence = connection.execute(
                "SELECT COUNT(*) FROM evidence WHERE evidence_uri = ?",
                (NOTIFICATION_ACTION_EVIDENCE_URI,),
            ).fetchone()[0]
            jace_evidence = connection.execute(
                "SELECT COUNT(*) FROM evidence WHERE evidence_uri = ? AND created_by = ?",
                (JACE_STATUS_EVIDENCE_URI, JACE_STATUS_CREATED_BY),
            ).fetchone()[0]
            alert = connection.execute(
                "SELECT transport, bot_username, message_id, delivery_state FROM alert_log WHERE alert_type = 'jace_status'",
            ).fetchone()
        self.assertEqual(notification_evidence, 1)
        self.assertEqual(jace_evidence, 1)
        self.assertIsNotNone(alert)
        self.assertEqual(alert["transport"], "telegram_bot_api")
        self.assertEqual(alert["bot_username"], "JACEthaACE_Bot")
        self.assertEqual(alert["message_id"], "5252")
        self.assertEqual(alert["delivery_state"], "sent")

    def test_openclaw_message_sender_uses_gateway_tool_invoke(self) -> None:
        config_path = Path(self.tempdir.name) / "openclaw.json"
        config_path.write_text(json.dumps({"gateway": {"auth": {"token": "test-token"}}}))

        class FakeResponse:
            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps({"ok": True, "result": {"messageId": "123"}}).encode("utf-8")

        captured: dict[str, object] = {}

        def fake_urlopen(request, timeout: int = 0):
            captured["timeout"] = timeout
            captured["url"] = request.full_url
            captured["auth"] = request.get_header("Authorization")
            captured["content_type"] = request.get_header("Content-type")
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse()

        with patch.object(action_runtime, "OPENCLAW_CONFIG_PATH", config_path), patch.object(
            action_runtime.urllib.request,
            "urlopen",
            fake_urlopen,
        ):
            result = action_runtime._openclaw_message_sender(
                channel="telegram",
                target="7529788084",
                message="ACE alert",
            )

        self.assertEqual(captured["url"], action_runtime.OPENCLAW_GATEWAY_URL)
        self.assertEqual(captured["auth"], "Bearer test-token")
        self.assertEqual(captured["content_type"], "application/json")
        self.assertEqual(captured["timeout"], 20)
        self.assertEqual(
            captured["body"],
            {
                "tool": "message",
                "args": {
                    "action": "send",
                    "channel": "telegram",
                    "target": "7529788084",
                    "message": "ACE alert",
                },
                "sessionKey": "main",
            },
        )
        self.assertEqual(result, {"ok": True, "result": {"messageId": "123"}})


if __name__ == "__main__":
    unittest.main()
