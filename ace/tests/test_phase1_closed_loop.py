from __future__ import annotations

import builtins
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ace.pending_promotions_ingest import PendingPromotionParseError, PendingPromotionSchemaError
from ace.phase1_closed_loop import run_phase1_closed_loop
from ace.repository import ItemRepository
from ace.storage import bootstrap_db, connect


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "pending_promotions"
DECISION_URI = "ace://phase1/decision"
DECISION_CREATED_BY = "ace.phase1_closed_loop"


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _decision_rows(db_path: Path) -> list[dict[str, object]]:
    with connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT item_id, evidence_text, evidence_uri, created_by
            FROM evidence
            WHERE evidence_uri = ? AND created_by = ?
            ORDER BY created_at ASC, id ASC
            """,
            (DECISION_URI, DECISION_CREATED_BY),
        ).fetchall()
    return [dict(row) for row in rows]


class Phase1ClosedLoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "ace.db"
        bootstrap_db(self.db_path)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_valid_closed_loop_run_writes_exactly_one_decision_evidence_row(self) -> None:
        results = run_phase1_closed_loop(
            self.db_path,
            source_path=FIXTURES / "phase1_manual_test.json",
            source_label="continuity/pending-promotions.json",
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["decision_classification"], "accepted_for_local_followup")
        self.assertTrue(results[0]["evidence_written"])
        self.assertIsInstance(results[0]["evidence_id"], str)

        decision_rows = _decision_rows(self.db_path)
        self.assertEqual(len(decision_rows), 1)
        self.assertEqual(decision_rows[0]["evidence_uri"], DECISION_URI)
        self.assertEqual(decision_rows[0]["created_by"], DECISION_CREATED_BY)
        self.assertEqual(
            decision_rows[0]["evidence_text"],
            json.dumps(
                {
                    "decision_classification": "accepted_for_local_followup",
                    "decision_rule_version": "phase1.manual-test.v1",
                    "source_label": results[0]["source_label"],
                    "source_session": results[0]["source_session"],
                    "source_item_id": results[0]["source_item_id"],
                },
                separators=(",", ":"),
                ensure_ascii=False,
            ),
        )

    def test_replay_does_not_duplicate_decision_evidence(self) -> None:
        first = run_phase1_closed_loop(
            self.db_path,
            source_path=FIXTURES / "phase1_manual_test.json",
            source_label="continuity/pending-promotions.json",
        )
        second = run_phase1_closed_loop(
            self.db_path,
            source_path=FIXTURES / "phase1_manual_test.json",
            source_label="continuity/pending-promotions.json",
        )

        self.assertEqual(first[0]["evidence_id"], second[0]["evidence_id"])
        self.assertFalse(second[0]["evidence_written"])
        self.assertEqual(len(_decision_rows(self.db_path)), 1)

    def test_non_pending_rows_produce_no_action_artifact(self) -> None:
        results = run_phase1_closed_loop(
            self.db_path,
            source_path=FIXTURES / "phase1_manual_test.json",
            source_label="continuity/pending-promotions.json",
        )

        repo = ItemRepository(self.db_path)
        self.assertEqual(len(results), 1)
        self.assertEqual(len(repo.list_items()), 1)
        self.assertEqual(len(_decision_rows(self.db_path)), 1)

    def test_non_manual_test_source_maps_to_insufficient_context(self) -> None:
        results = run_phase1_closed_loop(
            self.db_path,
            source_path=FIXTURES / "phase1_non_manual_test.json",
            source_label="continuity/pending-promotions.json",
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["decision_classification"], "insufficient_context")
        self.assertTrue(results[0]["evidence_written"])
        self.assertEqual(len(_decision_rows(self.db_path)), 1)

    def test_malformed_input_zero_write_fails(self) -> None:
        with self.assertRaises(PendingPromotionParseError):
            run_phase1_closed_loop(
                self.db_path,
                source_path=FIXTURES / "malformed.json",
                source_label="continuity/pending-promotions.json",
            )

        self.assertEqual(ItemRepository(self.db_path).list_items(), [])
        self.assertEqual(_decision_rows(self.db_path), [])

    def test_missing_required_input_zero_write_fails(self) -> None:
        with self.assertRaises(PendingPromotionSchemaError):
            run_phase1_closed_loop(
                self.db_path,
                source_path=FIXTURES / "invalid_missing_required.json",
                source_label="continuity/pending-promotions.json",
            )

        self.assertEqual(ItemRepository(self.db_path).list_items(), [])
        self.assertEqual(_decision_rows(self.db_path), [])

    def test_continuity_source_file_remains_unchanged_during_run(self) -> None:
        source_path = FIXTURES / "phase1_manual_test.json"
        original_text = source_path.read_text(encoding="utf-8")
        protected_path = source_path.resolve()

        real_open = builtins.open
        real_write_text = Path.write_text
        real_write_bytes = Path.write_bytes
        real_unlink = Path.unlink
        real_rename = Path.rename
        real_replace = Path.replace

        def guarded_open(file, mode="r", *args, **kwargs):
            candidate = Path(file).resolve()
            if candidate == protected_path and any(flag in mode for flag in ("w", "a", "+", "x")):
                raise AssertionError(f"write attempt against continuity source: {candidate} mode={mode}")
            return real_open(file, mode, *args, **kwargs)

        def guarded_write_text(path_obj, *args, **kwargs):
            if Path(path_obj).resolve() == protected_path:
                raise AssertionError(f"write_text attempt against continuity source: {protected_path}")
            return real_write_text(path_obj, *args, **kwargs)

        def guarded_write_bytes(path_obj, *args, **kwargs):
            if Path(path_obj).resolve() == protected_path:
                raise AssertionError(f"write_bytes attempt against continuity source: {protected_path}")
            return real_write_bytes(path_obj, *args, **kwargs)

        def guarded_unlink(path_obj, *args, **kwargs):
            if Path(path_obj).resolve() == protected_path:
                raise AssertionError(f"unlink attempt against continuity source: {protected_path}")
            return real_unlink(path_obj, *args, **kwargs)

        def guarded_rename(path_obj, target, *args, **kwargs):
            if Path(path_obj).resolve() == protected_path or Path(target).resolve() == protected_path:
                raise AssertionError(f"rename attempt against continuity source: {protected_path}")
            return real_rename(path_obj, target, *args, **kwargs)

        def guarded_replace(path_obj, target, *args, **kwargs):
            if Path(path_obj).resolve() == protected_path or Path(target).resolve() == protected_path:
                raise AssertionError(f"replace attempt against continuity source: {protected_path}")
            return real_replace(path_obj, target, *args, **kwargs)

        with (
            mock.patch("builtins.open", side_effect=guarded_open),
            mock.patch.object(Path, "write_text", autospec=True, side_effect=guarded_write_text),
            mock.patch.object(Path, "write_bytes", autospec=True, side_effect=guarded_write_bytes),
            mock.patch.object(Path, "unlink", autospec=True, side_effect=guarded_unlink),
            mock.patch.object(Path, "rename", autospec=True, side_effect=guarded_rename),
            mock.patch.object(Path, "replace", autospec=True, side_effect=guarded_replace),
        ):
            run_phase1_closed_loop(self.db_path, source_path=source_path, source_label="manual-test")

        self.assertEqual(source_path.read_text(encoding="utf-8"), original_text)


if __name__ == "__main__":
    unittest.main()
