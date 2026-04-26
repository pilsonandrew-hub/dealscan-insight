from __future__ import annotations

import builtins
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ace.open_loops_ingest import ingest_continuity_open_loops
from ace.pending_promotions_ingest import ingest_continuity_pending_promotions
from ace.storage import bootstrap_db


OPEN_LOOPS_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "open_loops" / "valid.json"
PENDING_PROMOTIONS_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "pending_promotions" / "valid.json"


class ReadOnlyContinuityBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "ace.db"
        bootstrap_db(self.db_path)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_open_loops_ingest_does_not_write_to_source_surface(self) -> None:
        self._assert_read_only_ingest(OPEN_LOOPS_FIXTURE, lambda: ingest_continuity_open_loops(self.db_path, source_path=OPEN_LOOPS_FIXTURE))

    def test_pending_promotions_ingest_does_not_write_to_source_surface(self) -> None:
        self._assert_read_only_ingest(
            PENDING_PROMOTIONS_FIXTURE,
            lambda: ingest_continuity_pending_promotions(self.db_path, source_path=PENDING_PROMOTIONS_FIXTURE),
        )

    def _assert_read_only_ingest(self, protected_path: Path, run_ingest) -> None:
        protected_path = protected_path.resolve()
        original_text = protected_path.read_text(encoding="utf-8")

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
            path_resolved = Path(path_obj).resolve()
            target_resolved = Path(target).resolve()
            if path_resolved == protected_path or target_resolved == protected_path:
                raise AssertionError(f"rename attempt against continuity source: {protected_path}")
            return real_rename(path_obj, target, *args, **kwargs)

        def guarded_replace(path_obj, target, *args, **kwargs):
            path_resolved = Path(path_obj).resolve()
            target_resolved = Path(target).resolve()
            if path_resolved == protected_path or target_resolved == protected_path:
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
            run_ingest()

        self.assertEqual(protected_path.read_text(encoding="utf-8"), original_text)


if __name__ == "__main__":
    unittest.main()
