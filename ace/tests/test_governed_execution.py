from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ace.governed_execution import (
    GOVERNED_EXECUTION_ACTOR,
    GOVERNED_EXECUTION_PLAN_EVIDENCE_URI,
    run_governed_execution_planner,
)
from ace.repository import ItemRepository
from ace.storage import bootstrap_db, connect
from ace.telegram_intake import TELEGRAM_GOVERNED_EXECUTION_OBLIGATION


class GovernedExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "ace.db"
        bootstrap_db(self.db_path)
        self.repo = ItemRepository(self.db_path)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_planner_attaches_contract_evidence_without_resolving_obligation(self) -> None:
        item = self.repo.create_item(
            item_type="work",
            title="Investigate production issue",
            source="telegram/direct",
            source_session="telegram:7529788084:governed-exec-1",
            actor="test",
        )
        obligation_id = self.repo.add_obligation(
            item.id,
            obligation_type=TELEGRAM_GOVERNED_EXECUTION_OBLIGATION,
            target_surface="ace/autonomy_contract",
            actor="test",
        )

        result = run_governed_execution_planner(self.db_path, actor="launchd", source_session="run_test")

        self.assertEqual(result["planned_ids"], [item.id])
        self.assertEqual(result["obligation_ids"], [obligation_id])
        self.assertEqual(len(result["evidence_ids"]), 1)

        with connect(self.db_path) as connection:
            evidence_row = connection.execute(
                "SELECT evidence_text, evidence_uri, created_by FROM evidence WHERE id = ?",
                (result["evidence_ids"][0],),
            ).fetchone()
            obligation_row = connection.execute(
                "SELECT status, satisfied_at FROM obligations WHERE id = ?",
                (obligation_id,),
            ).fetchone()

        self.assertIsNotNone(evidence_row)
        assert evidence_row is not None
        self.assertEqual(evidence_row["evidence_uri"], GOVERNED_EXECUTION_PLAN_EVIDENCE_URI)
        self.assertEqual(evidence_row["created_by"], GOVERNED_EXECUTION_ACTOR)
        payload = json.loads(evidence_row["evidence_text"])
        self.assertEqual(payload["obligation_id"], obligation_id)
        self.assertFalse(payload["contract"]["may_autonomously_close"])
        self.assertTrue(payload["contract"]["requires_concrete_execution_evidence"])
        self.assertIsNotNone(obligation_row)
        assert obligation_row is not None
        self.assertEqual(obligation_row["status"], "open")
        self.assertIsNone(obligation_row["satisfied_at"])

    def test_planner_is_idempotent_per_obligation(self) -> None:
        item = self.repo.create_item(
            item_type="work",
            title="Investigate production issue",
            source="telegram/direct",
            source_session="telegram:7529788084:governed-exec-2",
            actor="test",
        )
        self.repo.add_obligation(
            item.id,
            obligation_type=TELEGRAM_GOVERNED_EXECUTION_OBLIGATION,
            target_surface="ace/autonomy_contract",
            actor="test",
        )

        first = run_governed_execution_planner(self.db_path, actor="launchd", source_session="run_one")
        second = run_governed_execution_planner(self.db_path, actor="launchd", source_session="run_two")

        self.assertEqual(first["planned_ids"], [item.id])
        self.assertEqual(second["planned_ids"], [])
        with connect(self.db_path) as connection:
            evidence_count = connection.execute(
                "SELECT COUNT(*) FROM evidence WHERE item_id = ? AND evidence_uri = ?",
                (item.id, GOVERNED_EXECUTION_PLAN_EVIDENCE_URI),
            ).fetchone()[0]

        self.assertEqual(evidence_count, 1)

    def test_planner_ignores_other_obligations(self) -> None:
        item = self.repo.create_item(item_type="work", title="Other obligation", actor="test")
        self.repo.add_obligation(item.id, obligation_type="follow_up", actor="test")

        result = run_governed_execution_planner(self.db_path, actor="launchd", source_session="run_test")

        self.assertEqual(result["planned_ids"], [])
        self.assertEqual(result["evidence_ids"], [])
