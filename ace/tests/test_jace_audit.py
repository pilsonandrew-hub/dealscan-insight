from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import ace.action_runtime as action_runtime
from ace.action_runtime import (
    claim_operator_notification,
    enqueue_operator_notification,
    execute_operator_notification,
    send_jace_status_message,
)
from ace.jace_audit import audit_jace_delivery_history, classify_event_timestamp_inversions
from ace.repository import ItemRepository
from ace.storage import bootstrap_db, connect


class JaceAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "ace.db"
        bootstrap_db(self.db_path)
        self.repo = ItemRepository(self.db_path)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _fake_telegram_request(self, token: str, method: str, params: dict[str, object]) -> dict[str, object]:
        if method == "getMe":
            return {"ok": True, "result": {"username": "JACEthaACE_Bot"}}
        if method == "sendMessage":
            self.message_counter += 1
            return {"ok": True, "result": {"message_id": self.message_counter}}
        raise AssertionError(method)

    def test_jace_audit_separates_actual_sends_support_rows_and_classifies_triggers(self) -> None:
        self.message_counter = 7
        operator_item = self.repo.create_item(
            item_type="work",
            title="Closed operator status item",
            source="telegram/direct",
            source_session="telegram:7529788084:operator",
        )
        proof_item = self.repo.create_item(
            item_type="work",
            title="Classify ACE Gate 2.1 network-loss proof harness",
            source="workspace-residual",
            source_session="gate21-harness-classification-2026-05-19",
            actor="verification.closeout",
        )
        natural_caution_item = self.repo.create_item(
            item_type="work",
            title="Live DealerScope truth audit is back",
            description="Audit-content direct work from Telegram",
            source="telegram/direct",
            source_session="telegram:7529788084:36980",
            actor="ace.telegram_intake",
        )
        clean_natural_item = self.repo.create_item(
            item_type="work",
            title="Do not curse!",
            source="telegram/direct",
            source_session="telegram:7529788084:clean",
            actor="ace.telegram_intake",
        )

        with patch.dict(
            action_runtime.os.environ,
            {"ACE_TELEGRAM_BOT_TOKEN": "jace-token", "ACE_TELEGRAM_CHAT_ID": "7529788084"},
            clear=False,
        ), patch.object(action_runtime, "_telegram_bot_api_request", side_effect=self._fake_telegram_request):
            send_jace_status_message(self.db_path, operator_item.id, message="JACE status proof: independent path")
            send_jace_status_message(self.db_path, proof_item.id, message="ACE alert: network-loss proof harness")
            send_jace_status_message(self.db_path, natural_caution_item.id, message="ACE alert: Live DealerScope truth audit is back")
            send_jace_status_message(self.db_path, clean_natural_item.id, message="ACE alert: Do not curse!")

        audit = audit_jace_delivery_history(self.db_path)
        self.assertEqual(audit["actual_send_count"], 4)
        self.assertGreaterEqual(audit["support_record_count"], 4)
        self.assertEqual(audit["source_counts"]["alert_log"], 4)
        self.assertIn("evidence", audit["source_counts"])

        send_rows = {row["message_id"]: row for row in audit["records"] if row["source_table"] == "alert_log"}
        self.assertEqual(send_rows["8"]["classification"], "operator_triggered")
        self.assertEqual(send_rows["9"]["classification"], "proof_or_synthetic")
        self.assertEqual(send_rows["10"]["classification"], "natural_launchd_driven_with_content_caution")
        self.assertEqual(send_rows["11"]["classification"], "natural_launchd_driven")

    def test_jace_audit_cross_references_action_queue_notification_path(self) -> None:
        self.message_counter = 17
        item = self.repo.create_item(
            item_type="work",
            title="Do not curse!",
            source="telegram/direct",
            source_session="telegram:7529788084:clean",
            actor="ace.telegram_intake",
        )
        action = enqueue_operator_notification(
            self.db_path,
            item.id,
            channel="jace",
            target="7529788084",
            reason="stale_triage",
            age_context="last_activity=now; stale_threshold=0h",
        )
        claim_operator_notification(self.db_path, action["action_id"])

        with patch.dict(
            action_runtime.os.environ,
            {"ACE_TELEGRAM_BOT_TOKEN": "jace-token", "ACE_TELEGRAM_CHAT_ID": "7529788084"},
            clear=False,
        ), patch.object(action_runtime, "_telegram_bot_api_request", side_effect=self._fake_telegram_request):
            execute_operator_notification(self.db_path, action["action_id"])

        audit = audit_jace_delivery_history(self.db_path)
        self.assertEqual(audit["actual_send_count"], 1)
        self.assertGreaterEqual(audit["source_counts"].get("action_queue", 0), 1)
        self.assertGreaterEqual(audit["source_counts"].get("evidence", 0), 2)
        classifications = {row["source_table"]: row["classification"] for row in audit["records"]}
        self.assertEqual(classifications["alert_log"], "natural_launchd_driven")
        self.assertEqual(classifications["action_queue"], "natural_launchd_driven")

    def test_timestamp_inversion_classifier_marks_send_wrapper_without_hash_break(self) -> None:
        events = [
            {
                "id": 1,
                "event_id": "evt_notification_wrapper",
                "item_id": "item_1",
                "created_at": "2026-05-19T03:06:42Z",
                "event_hash": "hash1",
                "previous_event_hash": "hash0",
                "payload_json": '{"evidence_uri":"ace://notification/delivery"}',
            },
            {
                "id": 2,
                "event_id": "evt_jace_receipt",
                "item_id": "item_1",
                "created_at": "2026-05-19T03:06:32Z",
                "event_hash": "hash2",
                "previous_event_hash": "hash1",
                "payload_json": '{"evidence_uri":"ace://jace/outbound-status-delivery"}',
            },
        ]
        findings = classify_event_timestamp_inversions(events)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["classification"], "send_wrapper_timestamp_inversion")
        self.assertTrue(findings[0]["hash_chain_link_consistent"])


if __name__ == "__main__":
    unittest.main()
