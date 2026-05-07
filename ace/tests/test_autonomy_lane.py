from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ace.autonomy_lane import (
    AUTONOMY_EVIDENCE_URI,
    AUTONOMY_ITEM_TYPE,
    run_autonomy_lane,
)
from ace.repository import ItemRepository
from ace.storage import bootstrap_db, connect


class AutonomyLaneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "ace.db"
        bootstrap_db(self.db_path)
        self.repo = ItemRepository(self.db_path)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_machine_verifiable_item_closes_without_user_touch(self) -> None:
        item = self.repo.create_item(
            item_type=AUTONOMY_ITEM_TYPE,
            title="Autonomy proof item",
            description="Bounded proof item that ACE can close under the machine-verifiable lane.",
            actor="test",
        )

        result = run_autonomy_lane(self.db_path, actor="ace-runtime", source_session="test-session")

        final_item = self.repo.get_item(item.id)
        assert final_item is not None
        self.assertEqual(final_item.state, "VERIFIED_DONE")
        self.assertEqual(result["approved_ids"], [item.id])
        self.assertEqual(result["claimed_done_ids"], [item.id])
        self.assertEqual(result["verified_done_ids"], [item.id])
        self.assertEqual(len(result["evidence_ids"]), 1)

        with connect(self.db_path) as connection:
            evidence_count = connection.execute(
                "SELECT COUNT(*) FROM evidence WHERE item_id = ? AND evidence_uri = ?",
                (item.id, AUTONOMY_EVIDENCE_URI),
            ).fetchone()[0]
        self.assertEqual(evidence_count, 1)

    def test_non_autonomy_items_are_untouched(self) -> None:
        item = self.repo.create_item(item_type="work", title="Human work item", actor="test")

        result = run_autonomy_lane(self.db_path, actor="ace-runtime", source_session="test-session")

        final_item = self.repo.get_item(item.id)
        assert final_item is not None
        self.assertEqual(final_item.state, "TRIAGE")
        self.assertEqual(result["approved_ids"], [])
        self.assertEqual(result["claimed_done_ids"], [])
        self.assertEqual(result["verified_done_ids"], [])
        self.assertEqual(result["evidence_ids"], [])

    def test_eligible_real_work_item_closes_without_user_touch(self) -> None:
        item = self.repo.create_item(
            item_type="work",
            title="Real user work autonomy proof",
            description="Machine-verifiable autonomy proof from direct session work without user touch.",
            source="telegram/direct",
            source_session="2026-05-07-real-user-work-autonomy",
            actor="test",
        )

        result = run_autonomy_lane(self.db_path, actor="ace-runtime", source_session="test-session")

        final_item = self.repo.get_item(item.id)
        assert final_item is not None
        self.assertEqual(final_item.state, "VERIFIED_DONE")
        self.assertEqual(result["approved_ids"], [item.id])
        self.assertEqual(result["claimed_done_ids"], [item.id])
        self.assertEqual(result["verified_done_ids"], [item.id])
        self.assertEqual(len(result["evidence_ids"]), 1)

    def test_real_work_item_without_eligibility_markers_is_untouched(self) -> None:
        item = self.repo.create_item(
            item_type="work",
            title="Dealer strategy follow-up",
            description="Real work, but not bounded machine-verifiable work.",
            source="telegram/direct",
            source_session="2026-05-07-real-work",
            actor="test",
        )

        result = run_autonomy_lane(self.db_path, actor="ace-runtime", source_session="test-session")

        final_item = self.repo.get_item(item.id)
        assert final_item is not None
        self.assertEqual(final_item.state, "TRIAGE")
        self.assertEqual(result["approved_ids"], [])
        self.assertEqual(result["claimed_done_ids"], [])
        self.assertEqual(result["verified_done_ids"], [])
        self.assertEqual(result["evidence_ids"], [])
