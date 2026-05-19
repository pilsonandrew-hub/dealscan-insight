from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ace.repository import ItemRepository
from ace.storage import bootstrap_db
from ace.sweep import ITEM_SWEEP_FLAGGED_EVENT_TYPE, SWEEP_EVENT_TYPE, SweepThresholds, run_sweep


class SweepRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "ace.db"
        bootstrap_db(self.db_path)
        self.repo = ItemRepository(self.db_path)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_run_sweep_flags_stale_triage_item_and_writes_events(self) -> None:
        item = self.repo.create_item(
            item_type="task",
            title="Needs triage",
            actor="test",
        )
        result = run_sweep(
            self.db_path,
            thresholds=SweepThresholds(triage_after_seconds=0),
            actor="test",
            now="2026-05-05T12:00:00Z",
        )

        self.assertEqual(result["finding_count"], 1)
        self.assertEqual(result["emitted_count"], 1)
        finding = result["findings"][0]
        self.assertEqual(finding["item_id"], item.id)
        self.assertEqual(finding["classification"], "stale_triage")
        self.assertFalse(finding["suppressed"])

        events = self.repo.list_item_events(item.id, event_type=ITEM_SWEEP_FLAGGED_EVENT_TYPE)
        self.assertEqual(len(events), 1)
        payload = json.loads(events[0].payload_json or "{}")
        self.assertEqual(payload["classification"], "stale_triage")
        self.assertEqual(payload["item_id"], item.id)

    def test_run_sweep_suppresses_duplicate_flag_event_when_fingerprint_unchanged(self) -> None:
        item = self.repo.create_item(item_type="task", title="Duplicate suppression", actor="test")
        thresholds = SweepThresholds(triage_after_seconds=0)

        first = run_sweep(
            self.db_path,
            thresholds=thresholds,
            actor="test",
            now="2026-05-05T12:00:00Z",
        )
        second = run_sweep(
            self.db_path,
            thresholds=thresholds,
            actor="test",
            now="2026-05-05T12:00:00Z",
        )

        self.assertEqual(first["emitted_count"], 1)
        self.assertEqual(second["finding_count"], 1)
        self.assertEqual(second["emitted_count"], 0)
        self.assertEqual(second["suppressed_count"], 1)
        self.assertTrue(second["findings"][0]["suppressed"])

        events = self.repo.list_item_events(item.id, event_type=ITEM_SWEEP_FLAGGED_EVENT_TYPE)
        self.assertEqual(len(events), 1)

    def test_run_sweep_suppresses_evidence_only_activity_changes(self) -> None:
        item = self.repo.create_item(item_type="task", title="Activity change", actor="test")
        thresholds = SweepThresholds(triage_after_seconds=0)

        first = run_sweep(
            self.db_path,
            thresholds=thresholds,
            actor="test",
            now="2026-05-05T12:00:00Z",
        )
        self.assertEqual(first["emitted_count"], 1)

        self.repo.add_evidence(item.id, evidence_text="new proof", actor="test")

        second = run_sweep(
            self.db_path,
            thresholds=thresholds,
            actor="test",
            now="2026-05-05T12:05:00Z",
        )
        self.assertEqual(second["emitted_count"], 0)
        self.assertTrue(second["findings"][0]["suppressed"])
        self.assertEqual(second["findings"][0]["evidence_count"], 1)

        events = self.repo.list_item_events(item.id, event_type=ITEM_SWEEP_FLAGGED_EVENT_TYPE)
        self.assertEqual(len(events), 1)

    def test_run_sweep_classifies_claimed_done_and_counts_open_dependencies(self) -> None:
        item = self.repo.create_item(item_type="task", title="Closeout stalled", actor="test")
        approved = self.repo.apply_action(item.id, "approve", actor="test")
        claimed = self.repo.apply_action(approved.id, "done", actor="test")
        blocker = self.repo.create_item(item_type="task", title="Contradictor", actor="test")
        self.repo.add_obligation(claimed.id, obligation_type="follow_up", actor="test")
        self.repo.add_contradiction(claimed.id, source_item_id=blocker.id, actor="test")

        result = run_sweep(
            self.db_path,
            thresholds=SweepThresholds(claimed_done_after_seconds=0),
            actor="test",
            now="2026-05-05T12:00:00Z",
        )

        self.assertEqual(result["finding_count"], 1)
        finding = result["findings"][0]
        self.assertEqual(finding["classification"], "stale_claimed_done")
        self.assertEqual(finding["open_obligation_count"], 1)
        self.assertEqual(finding["open_contradiction_count"], 1)

    def test_run_sweep_writes_summary_event_even_with_no_findings(self) -> None:
        self.repo.create_item(item_type="task", title="Fresh triage", actor="test")
        result = run_sweep(
            self.db_path,
            thresholds=SweepThresholds(triage_after_seconds=999999),
            actor="test",
            now="2026-05-05T12:00:00Z",
        )

        self.assertEqual(result["finding_count"], 0)
        self.assertEqual(result["emitted_count"], 0)

        bootstrap = ItemRepository(self.db_path)
        items = bootstrap.list_items()
        self.assertEqual(len(items), 1)
        events = bootstrap.list_item_events(items[0].id)
        self.assertEqual(len(events), 1)

        from ace.storage import connect
        with connect(self.db_path) as connection:
            row = connection.execute(
                "SELECT payload_json FROM events WHERE event_type = ? ORDER BY id DESC LIMIT 1",
                (SWEEP_EVENT_TYPE,),
            ).fetchone()
        self.assertIsNotNone(row)
        payload = json.loads(row[0])
        self.assertEqual(payload["finding_count"], 0)
        self.assertEqual(payload["emitted_count"], 0)


if __name__ == "__main__":
    unittest.main()
