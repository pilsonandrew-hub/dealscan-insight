from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from ace.autonomy_lane import (
    AUTONOMY_DIRECT_WORK_EVIDENCE_URI,
    AUTONOMY_DIRECT_WORK_EXECUTION_EVIDENCE_URI,
    AUTONOMY_EVIDENCE_URI,
    AUTONOMY_ELIGIBILITY_CREATED_BY,
    AUTONOMY_ELIGIBILITY_EVIDENCE_URI,
    AUTONOMY_ITEM_TYPE,
    AUTONOMY_SOURCE,
    intake_autonomy_eligible_direct_work,
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
                (item.id, AUTONOMY_DIRECT_WORK_EXECUTION_EVIDENCE_URI),
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
                "SELECT evidence_text, evidence_uri FROM evidence WHERE item_id = ? AND evidence_uri = ? ORDER BY created_at DESC, id DESC LIMIT 1",
                (item.id, AUTONOMY_DIRECT_WORK_EXECUTION_EVIDENCE_URI),
            ).fetchone()

        serialized = "\n".join(row[0] for row in state_change_rows)
        self.assertIn("explicitly eligible direct work item", serialized)
        self.assertNotIn("machine-verifiable direct work item", serialized)
        assert closeout_row is not None
        self.assertIn("explicit eligibility evidence", closeout_row[0])
        self.assertIn('"verdict":"ship"', closeout_row[0])
        assert evidence_row is not None
        self.assertIn("explicit governed eligibility evidence", evidence_row[0])
        self.assertNotIn("machine-verifiable eligibility rules", evidence_row[0])
        self.assertEqual(evidence_row[1], AUTONOMY_DIRECT_WORK_EXECUTION_EVIDENCE_URI)

    def test_explicit_real_work_uses_distinct_closeout_evidence_uri(self) -> None:
        item = self.repo.create_item(
            item_type="work",
            title="Explicit direct work item uri check",
            source="telegram/direct",
            source_session="2026-05-07-direct-work-uri-check",
            actor="test",
        )
        mark_item_autonomy_eligible(
            self.db_path,
            item.id,
            reason="uri separation proof",
            actor="operator",
        )

        run_autonomy_lane(self.db_path, actor="launchd", source_session="run_test")

        with connect(self.db_path) as connection:
            uris = [
                row[0]
                for row in connection.execute(
                    "SELECT evidence_uri FROM evidence WHERE item_id = ? ORDER BY created_at ASC, id ASC",
                    (item.id,),
                ).fetchall()
            ]

        self.assertIn(AUTONOMY_ELIGIBILITY_EVIDENCE_URI, uris)
        self.assertIn(AUTONOMY_DIRECT_WORK_EXECUTION_EVIDENCE_URI, uris)
        self.assertNotIn(AUTONOMY_DIRECT_WORK_EVIDENCE_URI, uris)
        self.assertNotIn(AUTONOMY_EVIDENCE_URI, uris)

    def test_autonomy_lane_records_computed_ship_verdict_before_closeout(self) -> None:
        item = self.repo.create_item(
            item_type="work",
            title="Explicit direct work item verdict check",
            source="telegram/direct",
            source_session="2026-05-12-direct-work-verdict-check",
            actor="test",
        )
        mark_item_autonomy_eligible(
            self.db_path,
            item.id,
            reason="verdict governance proof",
            actor="operator",
        )

        run_autonomy_lane(self.db_path, actor="launchd", source_session="run_test")

        final_item = self.repo.get_item(item.id)
        assert final_item is not None
        self.assertEqual(final_item.state, "VERIFIED_DONE")
        self.assertEqual(final_item.verdict, "ship")
        events = self.repo.list_item_events(item.id)
        event_types = [event.event_type for event in events]
        self.assertIn("item.verdict_recorded", event_types)
        self.assertLess(event_types.index("item.verdict_recorded"), event_types.index("item.closeout_attempted"))
        verdict_event = next(event for event in events if event.event_type == "item.verdict_recorded")
        self.assertIn('"verdict":"ship"', verdict_event.payload_json or "")
        self.assertIn("computed verdict from drift composite", verdict_event.payload_json or "")
        closeout_event = next(event for event in events if event.event_type == "item.closeout_attempted")
        self.assertIn('"verdict":"ship"', closeout_event.payload_json or "")


    def test_autonomy_lane_uses_verdict_engine_output_for_recorded_verdict(self) -> None:
        item = self.repo.create_item(
            item_type="work",
            title="Explicit direct work item verdict engine check",
            source="telegram/direct",
            source_session="2026-05-14-direct-work-verdict-engine-check",
            actor="test",
        )
        mark_item_autonomy_eligible(
            self.db_path,
            item.id,
            reason="verdict engine governance proof",
            actor="operator",
        )

        with patch("ace.autonomy_lane.compute_verdict", return_value="monitor") as verdict_engine:
            run_autonomy_lane(self.db_path, actor="launchd", source_session="run_test")

        verdict_engine.assert_called_once()
        drift_report = verdict_engine.call_args.args[0]
        self.assertEqual(drift_report.item_id, item.id)
        self.assertEqual(drift_report.composite_score, 0.0)
        final_item = self.repo.get_item(item.id)
        assert final_item is not None
        self.assertEqual(final_item.state, "VERIFIED_DONE")
        self.assertEqual(final_item.verdict, "monitor")
        events = self.repo.list_item_events(item.id)
        verdict_event = next(event for event in events if event.event_type == "item.verdict_recorded")
        self.assertIn('"verdict":"monitor"', verdict_event.payload_json or "")
        self.assertIn("computed verdict from drift composite 0.0", verdict_event.payload_json or "")
        closeout_event = next(event for event in events if event.event_type == "item.closeout_attempted")
        self.assertIn('"verdict":"monitor"', closeout_event.payload_json or "")
        self.assertIn('"result":"passed"', closeout_event.payload_json or "")


    def test_autonomy_lane_retries_claimed_done_item_with_existing_positive_verdict_without_recomputing(self) -> None:
        item = self.repo.create_item(
            item_type="work",
            title="Explicit direct work item retry with existing verdict",
            source="telegram/direct",
            source_session="2026-05-14-direct-work-retry-existing-verdict",
            actor="test",
        )
        mark_item_autonomy_eligible(
            self.db_path,
            item.id,
            reason="verdict retry governance proof",
            actor="operator",
        )
        item = self.repo.apply_action(item.id, "approve", actor="test")
        self.repo.add_evidence(
            item.id,
            evidence_text="supporting proof",
            evidence_uri="ace://proof/retry-existing-verdict",
            created_by="test",
            actor="test",
        )
        item = self.repo.apply_action(item.id, "done", actor="test")
        item = self.repo.record_verdict(
            item.id,
            "ship",
            actor="test",
            source=AUTONOMY_SOURCE,
            source_session="interrupted_run",
            reason="pre-existing verdict from interrupted cycle",
        )
        self.assertEqual(item.state, "CLAIMED_DONE")
        self.assertEqual(item.verdict, "ship")

        with patch("ace.autonomy_lane.compute_verdict", return_value="review") as verdict_engine:
            result = run_autonomy_lane(self.db_path, actor="launchd", source_session="retry_run")

        verdict_engine.assert_not_called()
        self.assertEqual(result["verified_done_ids"], [item.id])
        final_item = self.repo.get_item(item.id)
        assert final_item is not None
        self.assertEqual(final_item.state, "VERIFIED_DONE")
        self.assertEqual(final_item.verdict, "ship")
        events = self.repo.list_item_events(item.id)
        verdict_events = [event for event in events if event.event_type == "item.verdict_recorded"]
        self.assertEqual(len(verdict_events), 1)
        closeout_event = next(event for event in events if event.event_type == "item.closeout_attempted")
        self.assertIn('"verdict":"ship"', closeout_event.payload_json or "")
        self.assertIn('"result":"passed"', closeout_event.payload_json or "")

    def test_autonomy_lane_refuses_to_overwrite_existing_fail_verdict(self) -> None:
        item = self.repo.create_item(
            item_type="work",
            title="Explicit direct work item conflicting verdict",
            verdict="fail",
            source="telegram/direct",
            source_session="2026-05-12-direct-work-conflicting-verdict",
            actor="test",
        )
        mark_item_autonomy_eligible(
            self.db_path,
            item.id,
            reason="verdict conflict proof",
            actor="operator",
        )

        with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
            run_autonomy_lane(self.db_path, actor="launchd", source_session="run_test")

        final_item = self.repo.get_item(item.id)
        assert final_item is not None
        self.assertEqual(final_item.state, "CLAIMED_DONE")
        self.assertEqual(final_item.verdict, "fail")

    def test_intake_autonomy_eligible_direct_work_creates_governed_seed(self) -> None:
        item, evidence_id = intake_autonomy_eligible_direct_work(
            self.db_path,
            title="Governed direct work",
            reason="governed production-path seed",
            source_session="2026-05-08-governed-direct-work",
            description="Created through first-class governed intake.",
            actor="operator",
        )

        self.assertEqual(item.item_type, "work")
        self.assertEqual(item.source, "telegram/direct")
        self.assertEqual(item.source_session, "2026-05-08-governed-direct-work")
        self.assertEqual(item.state, "TRIAGE")

        with connect(self.db_path) as connection:
            evidence_row = connection.execute(
                "SELECT id, evidence_uri, created_by FROM evidence WHERE id = ?",
                (evidence_id,),
            ).fetchone()

        self.assertIsNotNone(evidence_row)
        self.assertEqual(evidence_row[0], evidence_id)
        self.assertEqual(evidence_row[1], AUTONOMY_ELIGIBILITY_EVIDENCE_URI)
        self.assertEqual(evidence_row[2], AUTONOMY_ELIGIBILITY_CREATED_BY)

    def test_intake_autonomy_eligible_direct_work_is_idempotent_by_source_session(self) -> None:
        first_item, first_evidence_id = intake_autonomy_eligible_direct_work(
            self.db_path,
            title="Governed direct work",
            reason="first seed",
            source_session="2026-05-08-governed-direct-work-idempotent",
            actor="operator",
        )
        second_item, second_evidence_id = intake_autonomy_eligible_direct_work(
            self.db_path,
            title="Different title should not duplicate",
            reason="second seed",
            source_session="2026-05-08-governed-direct-work-idempotent",
            actor="operator",
        )

        self.assertEqual(first_item.id, second_item.id)
        self.assertEqual(first_evidence_id, second_evidence_id)

        with connect(self.db_path) as connection:
            item_count = connection.execute(
                "SELECT COUNT(*) FROM items WHERE source = ? AND source_session = ?",
                ("telegram/direct", "2026-05-08-governed-direct-work-idempotent"),
            ).fetchone()[0]
            evidence_count = connection.execute(
                "SELECT COUNT(*) FROM evidence WHERE item_id = ? AND evidence_uri = ? AND created_by = ?",
                (first_item.id, AUTONOMY_ELIGIBILITY_EVIDENCE_URI, AUTONOMY_ELIGIBILITY_CREATED_BY),
            ).fetchone()[0]

        self.assertEqual(item_count, 1)
        self.assertEqual(evidence_count, 1)
