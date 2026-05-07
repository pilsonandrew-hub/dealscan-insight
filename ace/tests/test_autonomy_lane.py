from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ace.autonomy_lane import (
    AUTONOMY_EVIDENCE_URI,
    AUTONOMY_ELIGIBILITY_CREATED_BY,
    AUTONOMY_ELIGIBILITY_EVIDENCE_URI,
    AUTONOMY_ITEM_TYPE,
    mark_item_autonomy_eligible,
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

    def test_keyword_only_real_work_item_is_untouched(self) -> None:
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
        self.assertEqual(final_item.state, "TRIAGE")
        self.assertEqual(result["approved_ids"], [])
        self.assertEqual(result["claimed_done_ids"], [])
        self.assertEqual(result["verified_done_ids"], [])
        self.assertEqual(result["evidence_ids"], [])

    def test_explicitly_marked_real_work_item_closes_without_user_touch(self) -> None:
        item = self.repo.create_item(
            item_type="work",
            title="Dealer strategy follow-up",
            description="Real direct work that should only run when explicitly marked eligible.",
            source="telegram/direct",
            source_session="2026-05-07-real-user-work-autonomy",
            actor="test",
        )

        evidence_id = mark_item_autonomy_eligible(
            self.db_path,
            item.id,
            reason="bounded machine-verifiable direct-work proof",
            actor="operator",
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
            eligibility_count = connection.execute(
                "SELECT COUNT(*) FROM evidence WHERE item_id = ? AND evidence_uri = ? AND created_by = ?",
                (item.id, AUTONOMY_ELIGIBILITY_EVIDENCE_URI, AUTONOMY_ELIGIBILITY_CREATED_BY),
            ).fetchone()[0]
            eligibility_row = connection.execute(
                "SELECT id FROM evidence WHERE item_id = ? AND evidence_uri = ? AND created_by = ?",
                (item.id, AUTONOMY_ELIGIBILITY_EVIDENCE_URI, AUTONOMY_ELIGIBILITY_CREATED_BY),
            ).fetchone()
            autonomy_row = connection.execute(
                "SELECT evidence_text FROM evidence WHERE item_id = ? AND evidence_uri = ?",
                (item.id, AUTONOMY_EVIDENCE_URI),
            ).fetchone()
        self.assertEqual(eligibility_count, 1)
        self.assertIsNotNone(eligibility_row)
        self.assertEqual(eligibility_row[0], evidence_id)
        self.assertIsNotNone(autonomy_row)
        self.assertIn("explicit governed eligibility evidence", autonomy_row[0])

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

    def test_mark_item_autonomy_eligible_is_idempotent(self) -> None:
        item = self.repo.create_item(
            item_type="work",
            title="Direct work item",
            source="telegram/direct",
            source_session="2026-05-07-direct-work",
            actor="test",
        )

        first = mark_item_autonomy_eligible(
            self.db_path,
            item.id,
            reason="first eligibility marker",
            actor="operator",
        )
        second = mark_item_autonomy_eligible(
            self.db_path,
            item.id,
            reason="duplicate eligibility marker",
            actor="operator",
        )

        self.assertEqual(first, second)
        with connect(self.db_path) as connection:
            eligibility_count = connection.execute(
                "SELECT COUNT(*) FROM evidence WHERE item_id = ? AND evidence_uri = ? AND created_by = ?",
                (item.id, AUTONOMY_ELIGIBILITY_EVIDENCE_URI, AUTONOMY_ELIGIBILITY_CREATED_BY),
            ).fetchone()[0]
        self.assertEqual(eligibility_count, 1)

    def test_explicit_real_work_reasons_no_longer_claim_machine_verifiable_path(self) -> None:
        item = self.repo.create_item(
            item_type="work",
            title="Explicit direct work item",
            source="telegram/direct",
            source_session="2026-05-07-direct-work-reason-check",
            actor="test",
        )
        mark_item_autonomy_eligible(
            self.db_path,
            item.id,
            reason="reason wording proof",
            actor="operator",
        )

        run_autonomy_lane(self.db_path, actor="launchd", source_session="run_test")

        with connect(self.db_path) as connection:
            state_change_rows = connection.execute(
                "SELECT payload_json FROM events WHERE item_id = ? AND event_type = 'item.state_changed' ORDER BY created_at ASC, id ASC",
                (item.id,),
            ).fetchall()
            closeout_row = connection.execute(
                "SELECT payload_json FROM events WHERE item_id = ? AND event_type = 'item.closeout_attempted' ORDER BY created_at DESC, id DESC LIMIT 1",
                (item.id,),
            ).fetchone()
            evidence_row = connection.execute(
                "SELECT evidence_text FROM evidence WHERE item_id = ? AND evidence_uri = ? ORDER BY created_at DESC, id DESC LIMIT 1",
                (item.id, AUTONOMY_EVIDENCE_URI),
            ).fetchone()

        serialized = "\n".join(row[0] for row in state_change_rows)
        self.assertIn("explicitly eligible direct work item", serialized)
        self.assertNotIn("machine-verifiable direct work item", serialized)
        assert closeout_row is not None
        self.assertIn("explicit eligibility evidence", closeout_row[0])
        assert evidence_row is not None
        self.assertIn("explicit governed eligibility evidence", evidence_row[0])
        self.assertNotIn("machine-verifiable eligibility rules", evidence_row[0])
