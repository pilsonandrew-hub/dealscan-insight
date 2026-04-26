from __future__ import annotations

import builtins
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ace.phase1b_closed_loop import (
    DECISION_CREATED_BY,
    DECISION_EVIDENCE_URI,
    DECISION_RULE_VERSION,
    Phase1BClosedLoopParseError,
    Phase1BClosedLoopSchemaError,
    run_phase1b_closed_loop,
)
from ace.repository import ItemRepository
from ace.storage import bootstrap_db, connect


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "open_loops"
SOURCE_LABEL = "continuity/open-loops.json"


def _load_fixture(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_open_loop_item(raw_item: dict[str, object]) -> dict[str, str]:
    return {
        "id": str(raw_item["id"]),
        "title": str(raw_item["title"]),
        "status": str(raw_item["status"]),
        "severity": str(raw_item["severity"]),
        "next_start": str(raw_item["next_start"]),
        "closure_condition": str(raw_item["closure_condition"]),
        "owner": str(raw_item["owner"]),
    }


def _canonical_open_loop_json(item: dict[str, str]) -> str:
    return json.dumps(
        {
            "id": item["id"],
            "title": item["title"],
            "status": item["status"],
            "severity": item["severity"],
            "next_start": item["next_start"],
            "closure_condition": item["closure_condition"],
            "owner": item["owner"],
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _canonical_open_loop_digest(item: dict[str, str]) -> str:
    return hashlib.sha256(_canonical_open_loop_json(item).encode("utf-8")).hexdigest()


def _decision_text(*, decision_classification: str, source_label: str, source_session: str, source_item_id: str) -> str:
    return json.dumps(
        {
            "decision_classification": decision_classification,
            "decision_rule_version": DECISION_RULE_VERSION,
            "source_label": source_label,
            "source_session": source_session,
            "source_item_id": source_item_id,
        },
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _decision_rows(db_path: Path) -> list[dict[str, object]]:
    with connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT item_id, evidence_text, evidence_uri, created_by
            FROM evidence
            WHERE evidence_uri = ? AND created_by = ?
            ORDER BY created_at ASC, id ASC
            """,
            (DECISION_EVIDENCE_URI, DECISION_CREATED_BY),
        ).fetchall()
    return [dict(row) for row in rows]


class Phase1BClosedLoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "ace.db"
        bootstrap_db(self.db_path)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_valid_high_severity_run_writes_exactly_one_decision_evidence_row(self) -> None:
        fixture = _load_fixture(FIXTURES / "phase1b_high.json")
        source_item = _canonical_open_loop_item(fixture["items"][0])
        expected_source_session = f"{SOURCE_LABEL}|{source_item['id']}|{_canonical_open_loop_digest(source_item)}"

        results = run_phase1b_closed_loop(
            self.db_path,
            source_path=FIXTURES / "phase1b_high.json",
            source_label=SOURCE_LABEL,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["decision_classification"], "escalate_for_operator_attention")
        self.assertTrue(results[0]["evidence_written"])
        self.assertIsInstance(results[0]["evidence_id"], str)
        self.assertEqual(results[0]["source_label"], SOURCE_LABEL)
        self.assertEqual(results[0]["source_item_id"], source_item["id"])
        self.assertEqual(results[0]["source_session"], expected_source_session)

        repo = ItemRepository(self.db_path)
        items = repo.list_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].state, "TRIAGE")
        self.assertEqual(items[0].source, SOURCE_LABEL)
        self.assertEqual(items[0].source_session, expected_source_session)

        decision_rows = _decision_rows(self.db_path)
        self.assertEqual(len(decision_rows), 1)
        self.assertEqual(decision_rows[0]["item_id"], items[0].id)
        self.assertEqual(decision_rows[0]["evidence_uri"], DECISION_EVIDENCE_URI)
        self.assertEqual(decision_rows[0]["created_by"], DECISION_CREATED_BY)
        self.assertEqual(
            decision_rows[0]["evidence_text"],
            _decision_text(
                decision_classification="escalate_for_operator_attention",
                source_label=SOURCE_LABEL,
                source_session=expected_source_session,
                source_item_id=source_item["id"],
            ),
        )

    def test_valid_medium_severity_run_writes_exactly_one_decision_evidence_row(self) -> None:
        fixture = _load_fixture(FIXTURES / "phase1b_medium.json")
        source_item = _canonical_open_loop_item(fixture["items"][0])
        expected_source_session = f"{SOURCE_LABEL}|{source_item['id']}|{_canonical_open_loop_digest(source_item)}"

        results = run_phase1b_closed_loop(
            self.db_path,
            source_path=FIXTURES / "phase1b_medium.json",
            source_label=SOURCE_LABEL,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["decision_classification"], "track_without_escalation")
        self.assertTrue(results[0]["evidence_written"])
        self.assertIsInstance(results[0]["evidence_id"], str)
        self.assertEqual(results[0]["source_label"], SOURCE_LABEL)
        self.assertEqual(results[0]["source_item_id"], source_item["id"])
        self.assertEqual(results[0]["source_session"], expected_source_session)

        decision_rows = _decision_rows(self.db_path)
        self.assertEqual(len(decision_rows), 1)
        self.assertEqual(
            decision_rows[0]["evidence_text"],
            _decision_text(
                decision_classification="track_without_escalation",
                source_label=SOURCE_LABEL,
                source_session=expected_source_session,
                source_item_id=source_item["id"],
            ),
        )

    def test_replay_does_not_duplicate_decision_evidence(self) -> None:
        first = run_phase1b_closed_loop(
            self.db_path,
            source_path=FIXTURES / "phase1b_high.json",
            source_label=SOURCE_LABEL,
        )
        second = run_phase1b_closed_loop(
            self.db_path,
            source_path=FIXTURES / "phase1b_high.json",
            source_label=SOURCE_LABEL,
        )

        self.assertEqual(first[0]["evidence_id"], second[0]["evidence_id"])
        self.assertFalse(second[0]["evidence_written"])
        self.assertEqual(len(_decision_rows(self.db_path)), 1)

    def test_malformed_input_raises_typed_error_and_writes_zero_rows(self) -> None:
        with self.assertRaises(Phase1BClosedLoopParseError):
            run_phase1b_closed_loop(
                self.db_path,
                source_path=FIXTURES / "malformed.json",
                source_label=SOURCE_LABEL,
            )

        self.assertEqual(ItemRepository(self.db_path).list_items(), [])
        self.assertEqual(_decision_rows(self.db_path), [])

    def test_missing_required_field_raises_typed_error_and_writes_zero_rows(self) -> None:
        with self.assertRaises(Phase1BClosedLoopSchemaError):
            run_phase1b_closed_loop(
                self.db_path,
                source_path=FIXTURES / "missing_required.json",
                source_label=SOURCE_LABEL,
            )

        self.assertEqual(ItemRepository(self.db_path).list_items(), [])
        self.assertEqual(_decision_rows(self.db_path), [])

    def test_continuity_source_file_remains_unchanged_during_run(self) -> None:
        source_path = FIXTURES / "phase1b_high.json"
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
            run_phase1b_closed_loop(
                self.db_path,
                source_path=source_path,
                source_label=SOURCE_LABEL,
            )

        self.assertEqual(source_path.read_text(encoding="utf-8"), original_text)


if __name__ == "__main__":
    unittest.main()
