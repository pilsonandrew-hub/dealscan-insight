from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ace.repository import ItemRepository, ValidationError
from ace.storage import bootstrap_db, connect
from ace.workflow import CloseoutGateError


class ItemRepositoryContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "ace.db"
        bootstrap_db(self.db_path)
        self.repo = ItemRepository(self.db_path)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

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

    def test_get_item_by_source_and_session_rejects_duplicate_provenance_rows(self) -> None:
        source = "continuity/open-loops.json"
        source_session = "continuity/open-loops.json|dup|digest"
        self.repo.create_item(
            item_type="continuity_open_loop",
            title="First",
            source=source,
            source_session=source_session,
            actor="test",
        )
        self.repo.create_item(
            item_type="continuity_open_loop",
            title="Second",
            source=source,
            source_session=source_session,
            actor="test",
        )

        with self.assertRaises(ValidationError):
            self.repo.get_item_by_source_and_session(source, source_session)

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
            connection.execute(
                """
                INSERT INTO events (
                    event_id, item_id, event_type, payload_json, actor, source, session_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
                ),
            )
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

    def test_finalize_closeout_passes_and_records_closeout_linkage(self) -> None:
        item = self.repo.create_item(item_type="task", title="Ready for closeout", actor="test")
        approved = self.repo.apply_action(item.id, "approve", actor="test")
        claimed = self.repo.apply_action(approved.id, "done", actor="test")
        self.repo.add_evidence(claimed.id, evidence_text="proof", actor="test")

        verified = self.repo.apply_action(claimed.id, "resolve", actor="test", reason="verified")
        self.assertEqual(verified.state, "VERIFIED_DONE")

        events = self.repo.list_item_events(verified.id, event_type="item.state_changed")
        self.assertGreaterEqual(len(events), 2)
        final_payload = events[-1].payload_json or ""
        self.assertIn('"closeout_run_id":', final_payload)
        self.assertIn('"closeout_event_id":', final_payload)


if __name__ == "__main__":
    unittest.main()
