from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ace.repository import ItemRepository, ValidationError
from ace.storage import _disable_event_insert, _enable_event_insert, bootstrap_db, connect
from ace.workflow import CloseoutGateError


class ItemRepositoryContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "ace.db"
        bootstrap_db(self.db_path)
        self.repo = ItemRepository(self.db_path)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_create_item_persists_normalized_confidence_tier(self) -> None:
        item = self.repo.create_item(
            item_type="continuity_open_loop",
            title="Item with confidence tier",
            confidence_tier="Live Confirmed",
            actor="test",
        )

        stored = self.repo.get_item(item.id)

        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertEqual(stored.confidence_tier, "live_confirmed")

    def test_create_item_persists_normalized_verdict(self) -> None:
        item = self.repo.create_item(
            item_type="continuity_open_loop",
            title="Item with verdict",
            verdict=" PASS ",
            actor="test",
        )

        stored = self.repo.get_item(item.id)

        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertEqual(stored.verdict, "pass")

    def test_record_verdict_persists_event_and_refuses_overwrite(self) -> None:
        item = self.repo.create_item(
            item_type="task",
            title="Verdict target",
            actor="test",
        )

        updated = self.repo.record_verdict(
            item.id,
            " PASS ",
            actor="auditor",
            source="test",
            source_session="run_test",
            reason="evidence reviewed",
        )

        self.assertEqual(updated.verdict, "pass")
        events = self.repo.list_item_events(item.id)
        verdict_events = [event for event in events if event.event_type == "item.verdict_recorded"]
        self.assertEqual(len(verdict_events), 1)
        self.assertIn('"verdict":"pass"', verdict_events[0].payload_json or "")
        self.assertIn('"reason":"evidence reviewed"', verdict_events[0].payload_json or "")

        idempotent = self.repo.record_verdict(item.id, "pass", actor="auditor")
        self.assertEqual(idempotent.verdict, "pass")
        events = self.repo.list_item_events(item.id)
        self.assertEqual(len([event for event in events if event.event_type == "item.verdict_recorded"]), 1)

        with self.assertRaises(ValidationError):
            self.repo.record_verdict(item.id, "fail", actor="auditor")

    def test_resolve_enforces_persisted_fail_verdict(self) -> None:
        item = self.repo.create_item(
            item_type="task",
            title="Failed verdict closeout target",
            verdict="fail",
            actor="test",
        )
        self.repo.add_evidence(item.id, evidence_text="evidence exists", actor="test")
        self.repo.apply_action(item.id, "approve", actor="test")
        self.repo.apply_action(item.id, "done", actor="test")

        with self.assertRaises(CloseoutGateError) as raised:
            self.repo.apply_action(item.id, "resolve", actor="test")

        self.assertIn("verdict_fail", str(raised.exception))
        stored = self.repo.get_item(item.id)
        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertEqual(stored.state, "CLAIMED_DONE")

        closeout_event = next(
            event for event in self.repo.list_item_events(item.id) if event.event_type == "item.closeout_attempted"
        )
        self.assertIn('"failure_code":"verdict_fail"', closeout_event.payload_json or "")
        self.assertIn('"verdict":"fail"', closeout_event.payload_json or "")

    def test_resolve_blocks_missing_verdict(self) -> None:
        item = self.repo.create_item(
            item_type="task",
            title="Missing verdict closeout target",
            actor="test",
        )
        self.repo.add_evidence(item.id, evidence_text="evidence exists", actor="test")
        self.repo.apply_action(item.id, "approve", actor="test")
        self.repo.apply_action(item.id, "done", actor="test")

        with self.assertRaises(CloseoutGateError) as raised:
            self.repo.apply_action(item.id, "resolve", actor="test")

        self.assertIn("missing_verdict", str(raised.exception))
        stored = self.repo.get_item(item.id)
        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertEqual(stored.state, "CLAIMED_DONE")

    def test_resolve_allows_persisted_pass_verdict(self) -> None:
        item = self.repo.create_item(
            item_type="task",
            title="Pass verdict closeout target",
            verdict="pass",
            actor="test",
        )
        self.repo.add_evidence(item.id, evidence_text="evidence exists", actor="test")
        self.repo.apply_action(item.id, "approve", actor="test")
        self.repo.apply_action(item.id, "done", actor="test")

        resolved = self.repo.apply_action(item.id, "resolve", actor="test")

        self.assertEqual(resolved.state, "VERIFIED_DONE")
        closeout_event = next(
            event for event in self.repo.list_item_events(item.id) if event.event_type == "item.closeout_attempted"
        )
        self.assertIn('"result":"passed"', closeout_event.payload_json or "")
        self.assertIn('"verdict":"pass"', closeout_event.payload_json or "")

    def test_get_item_by_source_and_session_reuses_single_matching_item(self) -> None:
        item = self.repo.create_item(
            item_type="continuity_open_loop",
            title="Item with provenance",
            source="continuity/open-loops.json",
            source_session="continuity/open-loops.json|open-loop-001|digest",
            actor="test",
        )

        found = self.repo.get_item_by_source_and_session(
            "continuity/open-loops.json",
            "continuity/open-loops.json|open-loop-001|digest",
        )

        self.assertEqual(found, item)

    def test_get_item_by_source_and_session_returns_none_when_absent(self) -> None:
        found = self.repo.get_item_by_source_and_session(
            "continuity/open-loops.json",
            "continuity/open-loops.json|missing|digest",
        )
        self.assertIsNone(found)

    def test_create_item_reuses_existing_item_for_duplicate_provenance(self) -> None:
        source = "continuity/open-loops.json"
        source_session = "continuity/open-loops.json|dup|digest"
        first = self.repo.create_item(
            item_type="continuity_open_loop",
            title="First",
            source=source,
            source_session=source_session,
            actor="test",
        )
        second = self.repo.create_item(
            item_type="continuity_open_loop",
            title="Second",
            source=source,
            source_session=source_session,
            actor="test",
        )

        self.assertEqual(second, first)
        found = self.repo.get_item_by_source_and_session(source, source_session)
        self.assertEqual(found, first)

        with connect(self.db_path) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM items WHERE source = ? AND source_session = ?",
                (source, source_session),
            ).fetchone()[0]
            created_event_count = connection.execute(
                "SELECT COUNT(*) FROM events WHERE item_id = ? AND event_type = ?",
                (first.id, "item.created"),
            ).fetchone()[0]

        self.assertEqual(count, 1)
        self.assertEqual(created_event_count, 1)

    def test_add_evidence_rejects_whitespace_only_text(self) -> None:
        item = self.repo.create_item(item_type="note", title="Evidence target", actor="test")

        with self.assertRaises(ValidationError):
            self.repo.add_evidence(item.id, evidence_text="   ", actor="test")

    def test_add_obligation_and_open_count_track_terminal_transition(self) -> None:
        item = self.repo.create_item(item_type="task", title="Obligation target", actor="test")

        obligation_id = self.repo.add_obligation(
            item.id,
            obligation_type="follow_up",
            target_surface="briefing",
            notes="needs confirmation",
            actor="test",
        )
        self.assertEqual(self.repo.item_open_obligation_count(item.id), 1)

        result = self.repo.resolve_obligation(obligation_id, reason="confirmed", actor="test")
        self.assertEqual(result["status"], "resolved")
        self.assertIsNotNone(result["satisfied_at"])
        self.assertEqual(self.repo.item_open_obligation_count(item.id), 0)

    def test_resolve_obligation_requires_nonempty_reason(self) -> None:
        item = self.repo.create_item(item_type="task", title="Needs reason", actor="test")
        obligation_id = self.repo.add_obligation(item.id, obligation_type="follow_up", actor="test")

        with self.assertRaises(ValidationError):
            self.repo.resolve_obligation(obligation_id, reason="   ", actor="test")

    def test_add_contradiction_and_open_count_track_terminal_transition(self) -> None:
        source_item = self.repo.create_item(item_type="task", title="Source item", actor="test")
        target_item = self.repo.create_item(item_type="task", title="Target item", actor="test")

        contradiction_id = self.repo.add_contradiction(
            target_item.id,
            source_item_id=source_item.id,
            reason="conflicting evidence",
            actor="test",
        )
        self.assertEqual(self.repo.item_open_contradiction_count(target_item.id), 1)

        result = self.repo.resolve_contradiction(contradiction_id, reason="reconciled", actor="test")
        self.assertEqual(result["status"], "resolved")
        self.assertIsNotNone(result["resolved_at"])
        self.assertEqual(self.repo.item_open_contradiction_count(target_item.id), 0)

    def test_resolve_contradiction_requires_nonempty_reason(self) -> None:
        source_item = self.repo.create_item(item_type="task", title="Source item", actor="test")
        target_item = self.repo.create_item(item_type="task", title="Target item", actor="test")
        contradiction_id = self.repo.add_contradiction(target_item.id, source_item_id=source_item.id, actor="test")

        with self.assertRaises(ValidationError):
            self.repo.resolve_contradiction(contradiction_id, reason="   ", actor="test")


    def test_submit_closeout_metadata_correction_updates_item_through_audit_event(self) -> None:
        item = self.repo.create_item(item_type="task", title="Correct metadata", actor="test")
        approved = self.repo.apply_action(item.id, "approve", actor="test")
        claimed = self.repo.apply_action(approved.id, "done", actor="test")
        self.repo.add_evidence(claimed.id, evidence_text="proof", actor="test")
        self.repo.record_verdict(claimed.id, "pass", actor="test", reason="proof reviewed")
        verified = self.repo.apply_action(claimed.id, "resolve", actor="test", reason="verified")

        result = self.repo.submit_closeout_metadata_correction(
            verified.id,
            closed_at="2026-05-15T00:00:00Z",
            closed_by="audit-corrector",
            closed_reason="pass: historical closeout event correction",
            reason="repair denormalized closeout metadata from audit log",
            actor="test",
        )

        corrected = self.repo.get_item(verified.id)
        self.assertEqual(corrected.closed_at, "2026-05-15T00:00:00Z")
        self.assertEqual(corrected.closed_by, "audit-corrector")
        self.assertEqual(corrected.closed_reason, "pass: historical closeout event correction")
        self.assertEqual(corrected.last_event_id, result["event_id"])
        events = self.repo.list_item_events(verified.id, event_type="item.closeout_metadata_corrected")
        self.assertEqual(len(events), 1)
        self.assertIn('"reason":"repair denormalized closeout metadata from audit log"', events[0].payload_json or "")

    def test_record_correction_preserves_original_truth_and_links_corrected_item(self) -> None:
        original = self.repo.create_item(item_type="task", title="Original claim", actor="test")
        corrected = self.repo.create_item(item_type="task", title="Corrected claim", actor="test")

        result = self.repo.record_correction(
            original.id,
            corrected_item_id=corrected.id,
            reason="new evidence supersedes the original claim",
            actor="auditor",
        )

        self.assertEqual(result["item_id"], original.id)
        self.assertEqual(result["corrected_item_id"], corrected.id)
        self.assertIsNotNone(result["contradiction_id"])

        original_current = self.repo.get_item(original.id)
        corrected_current = self.repo.get_item(corrected.id)
        self.assertIsNotNone(original_current)
        self.assertIsNotNone(corrected_current)
        self.assertEqual(original_current.state, "TRIAGE")
        self.assertEqual(corrected_current.state, "TRIAGE")

        original_events = self.repo.list_item_events(original.id)
        corrected_events = self.repo.list_item_events(corrected.id)

        self.assertIn("item.contradiction_added", [event.event_type for event in original_events])
        self.assertIn("item.correction_recorded", [event.event_type for event in original_events])
        self.assertIn("item.correction_linked", [event.event_type for event in corrected_events])

        correction_payload = next(
            event.payload_json for event in original_events if event.event_type == "item.correction_recorded"
        )
        self.assertIn(f'"corrected_item_id":"{corrected.id}"', correction_payload or "")
        self.assertIn('"reason":"new evidence supersedes the original claim"', correction_payload or "")

        linked_payload = next(
            event.payload_json for event in corrected_events if event.event_type == "item.correction_linked"
        )
        self.assertIn(f'"supersedes_item_id":"{original.id}"', linked_payload or "")

    def test_record_correction_rejects_self_correction(self) -> None:
        item = self.repo.create_item(item_type="task", title="Self correction", actor="test")

        with self.assertRaises(ValidationError):
            self.repo.record_correction(
                item.id,
                corrected_item_id=item.id,
                reason="cannot correct itself",
                actor="auditor",
            )

    def test_list_item_events_returns_chronological_order_with_latest_matching_selection(self) -> None:
        item = self.repo.create_item(item_type="task", title="Event target", actor="test")
        self.repo.add_evidence(item.id, evidence_text="first", actor="test")
        self.repo.add_evidence(item.id, evidence_text="second", actor="test")

        events = self.repo.list_item_events(item.id, event_type="item.evidence_added", limit=1)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, "item.evidence_added")
        self.assertIn('"evidence_text":"second"', events[0].payload_json or "")

    def test_list_item_events_preserves_malformed_payload_truth(self) -> None:
        item = self.repo.create_item(item_type="task", title="Malformed payload target", actor="test")
        with connect(self.db_path) as connection:
            _enable_event_insert(connection)
            try:
                connection.execute(
                    """
                    INSERT INTO events (
                        event_id, item_id, event_type, payload_json, actor, source, session_id, created_at, event_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "evt_malformed",
                        item.id,
                        "item.evidence_added",
                        '{"broken":',
                        "test",
                        None,
                        None,
                        "2026-04-26T00:00:00Z",
                        "0" * 64,
                    ),
                )
            finally:
                _disable_event_insert(connection)
            connection.commit()

        events = self.repo.list_item_events(item.id, event_type="item.evidence_added")
        malformed = [event for event in events if event.event_id == "evt_malformed"]
        self.assertEqual(len(malformed), 1)
        self.assertEqual(malformed[0].payload_status, "malformed")
        self.assertEqual(malformed[0].payload_json, None)
        self.assertEqual(malformed[0].payload_raw, '{"broken":')

    def test_finalize_closeout_blocks_without_evidence(self) -> None:
        item = self.repo.create_item(item_type="task", title="Needs evidence", actor="test")
        claimed = self.repo.apply_action(item.id, "approve", actor="test")
        claimed = self.repo.apply_action(claimed.id, "done", actor="test")
        self.assertEqual(claimed.state, "CLAIMED_DONE")

        with self.assertRaises(CloseoutGateError):
            self.repo.apply_action(claimed.id, "resolve", actor="test")

        current = self.repo.get_item(claimed.id)
        self.assertIsNotNone(current)
        self.assertEqual(current.state, "CLAIMED_DONE")

    def test_finalize_closeout_blocks_with_only_process_evidence(self) -> None:
        item = self.repo.create_item(item_type="task", title="Needs substantive evidence", actor="test")
        approved = self.repo.apply_action(item.id, "approve", actor="test")
        claimed = self.repo.apply_action(approved.id, "done", actor="test")
        self.repo.add_evidence(
            claimed.id,
            evidence_text="parser provenance is not claim support",
            evidence_uri="ace://telegram/parser-decision",
            actor="test",
        )
        self.repo.record_verdict(claimed.id, "pass", actor="test", reason="process metadata only")

        with self.assertRaises(CloseoutGateError) as raised:
            self.repo.apply_action(claimed.id, "resolve", actor="test")

        self.assertIn("missing_supporting_evidence", str(raised.exception))
        closeout_event = next(
            event for event in self.repo.list_item_events(claimed.id) if event.event_type == "item.closeout_attempted"
        )
        self.assertIn('"evidence_count":1', closeout_event.payload_json or "")
        self.assertIn('"supporting_evidence_count":0', closeout_event.payload_json or "")

    def test_finalize_closeout_blocks_failed_governed_execution_result_as_claim_support(self) -> None:
        item = self.repo.create_item(item_type="task", title="Failed governed result is not support", actor="test")
        approved = self.repo.apply_action(item.id, "approve", actor="test")
        claimed = self.repo.apply_action(approved.id, "done", actor="test")
        self.repo.add_evidence(
            claimed.id,
            evidence_text='{"result":"fail","durable_checks":{"event_hash_chain":{"ok":false}}}',
            evidence_uri="ace://governed-execution/result",
            actor="test",
        )
        self.repo.record_verdict(claimed.id, "pass", actor="test", reason="failed inspection should not close")

        with self.assertRaises(CloseoutGateError) as raised:
            self.repo.apply_action(claimed.id, "resolve", actor="test")

        self.assertIn("missing_supporting_evidence", str(raised.exception))
        closeout_event = next(
            event for event in self.repo.list_item_events(claimed.id) if event.event_type == "item.closeout_attempted"
        )
        self.assertIn('"evidence_count":1', closeout_event.payload_json or "")
        self.assertIn('"supporting_evidence_count":0', closeout_event.payload_json or "")

    def test_finalize_closeout_passes_and_records_closeout_linkage(self) -> None:
        item = self.repo.create_item(item_type="task", title="Ready for closeout", actor="test")
        approved = self.repo.apply_action(item.id, "approve", actor="test")
        claimed = self.repo.apply_action(approved.id, "done", actor="test")
        self.repo.add_evidence(claimed.id, evidence_text="proof", actor="test")
        self.repo.record_verdict(claimed.id, "pass", actor="test", reason="proof reviewed")

        verified = self.repo.apply_action(claimed.id, "resolve", actor="test", reason="verified")
        self.assertEqual(verified.state, "VERIFIED_DONE")
        self.assertEqual(verified.closed_at, verified.updated_at)
        self.assertEqual(verified.closed_by, "test")
        self.assertEqual(verified.closed_reason, "verified")

        events = self.repo.list_item_events(verified.id, event_type="item.state_changed")
        self.assertGreaterEqual(len(events), 2)
        final_payload = events[-1].payload_json or ""
        self.assertIn('"closeout_run_id":', final_payload)
        self.assertIn('"closeout_event_id":', final_payload)

    def test_finalize_closeout_defaults_metadata_when_actor_or_reason_missing(self) -> None:
        item = self.repo.create_item(item_type="task", title="Default closeout metadata", actor="test")
        approved = self.repo.apply_action(item.id, "approve", actor="test")
        claimed = self.repo.apply_action(approved.id, "done", actor="test")
        self.repo.add_evidence(claimed.id, evidence_text="proof", actor="test")
        self.repo.record_verdict(claimed.id, "pass", actor="test", reason="proof reviewed")

        verified = self.repo.apply_action(claimed.id, "resolve")

        self.assertEqual(verified.state, "VERIFIED_DONE")
        self.assertEqual(verified.closed_at, verified.updated_at)
        self.assertEqual(verified.closed_by, "ace.closeout")
        self.assertEqual(verified.closed_reason, "closeout verified")


if __name__ == "__main__":
    unittest.main()
