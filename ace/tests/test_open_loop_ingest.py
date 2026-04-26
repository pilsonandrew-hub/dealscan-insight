from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ace.repository import ItemRepository
from ace.storage import bootstrap_db
from ace.open_loops_ingest import (
    OpenLoopIngestError,
    UnsupportedOpenLoopStateError,
    ingest_continuity_open_loops,
)


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "open_loops"


class ContinuityOpenLoopIngestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "ace.db"
        bootstrap_db(self.db_path)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_valid_open_loop_ingest_maps_active_like_items_to_triage_and_preserves_provenance(self) -> None:
        results = ingest_continuity_open_loops(
            self.db_path,
            source_path=FIXTURES / "valid.json",
        )

        self.assertEqual(len(results), 2)
        repo = ItemRepository(self.db_path)
        items = repo.list_items()
        self.assertEqual([item.state for item in items], ["TRIAGE", "TRIAGE"])
        self.assertEqual([item.title for item in items], ["Fix telemetry gap", "Refresh continuity note"])
        self.assertEqual([item.source for item in items], ["continuity/open-loops.json", "continuity/open-loops.json"])
        for item in items:
            self.assertRegex(
                item.source_session or "",
                r"^continuity/open-loops\.json\|open-loop-00[12]\|[0-9a-f]{64}$",
            )

    def test_malformed_json_is_rejected_without_writing_rows(self) -> None:
        with self.assertRaises(OpenLoopIngestError):
            ingest_continuity_open_loops(
                self.db_path,
                source_path=FIXTURES / "malformed.json",
            )

        repo = ItemRepository(self.db_path)
        self.assertEqual(repo.list_items(), [])

    def test_closed_open_loop_is_rejected_as_unsupported(self) -> None:
        with self.assertRaises(UnsupportedOpenLoopStateError):
            ingest_continuity_open_loops(
                self.db_path,
                source_path=FIXTURES / "closed.json",
            )

        repo = ItemRepository(self.db_path)
        self.assertEqual(repo.list_items(), [])

    def test_replay_reuses_existing_rows_for_same_source_id_and_digest(self) -> None:
        first = ingest_continuity_open_loops(
            self.db_path,
            source_path=FIXTURES / "valid.json",
        )
        second = ingest_continuity_open_loops(
            self.db_path,
            source_path=FIXTURES / "valid.json",
        )

        self.assertEqual([item.id for item in first], [item.id for item in second])
        repo = ItemRepository(self.db_path)
        self.assertEqual(len(repo.list_items()), 2)

    def test_invalid_severity_is_rejected_without_writing_rows(self) -> None:
        with self.assertRaises(OpenLoopIngestError):
            ingest_continuity_open_loops(
                self.db_path,
                source_path=FIXTURES / "invalid_severity.json",
            )

        repo = ItemRepository(self.db_path)
        self.assertEqual(repo.list_items(), [])

    def test_missing_required_field_is_rejected_without_writing_rows(self) -> None:
        with self.assertRaises(OpenLoopIngestError):
            ingest_continuity_open_loops(
                self.db_path,
                source_path=FIXTURES / "missing_required.json",
            )

        repo = ItemRepository(self.db_path)
        self.assertEqual(repo.list_items(), [])

    def test_non_object_item_is_rejected_without_writing_rows(self) -> None:
        with self.assertRaises(OpenLoopIngestError):
            ingest_continuity_open_loops(
                self.db_path,
                source_path=FIXTURES / "non_object_item.json",
            )

        repo = ItemRepository(self.db_path)
        self.assertEqual(repo.list_items(), [])

    def test_non_object_payload_is_rejected_without_writing_rows(self) -> None:
        with self.assertRaises(OpenLoopIngestError):
            ingest_continuity_open_loops(
                self.db_path,
                source_path=FIXTURES / "non_object_payload.json",
            )

        repo = ItemRepository(self.db_path)
        self.assertEqual(repo.list_items(), [])

    def test_missing_items_array_is_rejected_without_writing_rows(self) -> None:
        with self.assertRaises(OpenLoopIngestError):
            ingest_continuity_open_loops(
                self.db_path,
                source_path=FIXTURES / "missing_items_array.json",
            )

        repo = ItemRepository(self.db_path)
        self.assertEqual(repo.list_items(), [])


if __name__ == "__main__":
    unittest.main()
