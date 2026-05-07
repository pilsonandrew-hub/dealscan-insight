from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from ace.ace import GATE4_OPERATOR_ARTIFACTS, main
from ace.cycle import run_cycle
from ace.storage import bootstrap_db
from ace.repository import ItemRepository


class GovernedRunCliTests(unittest.TestCase):
    def run_cli(self, *argv: str) -> tuple[int, str]:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main(list(argv))
        return code, buffer.getvalue()

    def test_gate4_inspection_reports_bounded_operator_artifacts(self) -> None:
        code, output = self.run_cli("gate4-inspection")

        self.assertEqual(code, 0, output)
        self.assertIn("gate4_scope=bounded_operator_inspection_only", output)
        self.assertIn("gate4_claim=inspection_centralization_not_v1_promotion", output)
        self.assertIn("artifact_missing_count=0", output)
        self.assertIn("operator_status_family[0]=explicit_bounded_failure", output)
        self.assertIn("remaining_partial_count=0", output)
        self.assertNotIn("remaining_partial[0]=", output)
        self.assertNotIn("phase1_ambiguity_centralization", output)
        self.assertNotIn("composition_seam_contradiction_centralization", output)
        self.assertNotIn("recovery_family_centralization", output)
        self.assertNotIn("one_step_operator_inspection", output)
        self.assertIn("composition_truth[0]=decision_top_level_rejection_and_replay_are_bounded", output)
        self.assertIn("composition_truth[3]=phase1_pending_rows_now_use_governed_normalization", output)
        self.assertIn("phase1_truth[0]=non_pending_rows_are_acceptable_bounded_filtering", output)
        self.assertIn("phase1_truth[1]=non_object_rows_fail_loudly_as_schema_error", output)
        self.assertIn("phase1_truth[2]=invalid_or_missing_status_rows_fail_loudly_as_schema_error", output)
        self.assertIn("phase1_truth[3]=pending_rows_failing_required_field_normalization_fail_loudly_as_schema_error", output)
        self.assertIn("phase1_truth[4]=later_missing_source_row_is_explicit_bounded_failure", output)
        self.assertIn("recovery_truth[0]=stale_or_deleted_target_is_explicit_bounded_failure", output)
        self.assertIn("recovery_truth[4]=interrupted_split_success_replay_heals_without_duplicate_evidence", output)
        for label, relative_path in GATE4_OPERATOR_ARTIFACTS:
            self.assertIn(f"artifact.{label}.path={relative_path}", output)
            self.assertIn(f"artifact.{label}.present=true", output)

    def test_gate4_inspection_fails_loudly_when_artifact_missing(self) -> None:
        missing_relative_path = GATE4_OPERATOR_ARTIFACTS[0][1]
        workspace_root = Path(__file__).resolve().parent.parent.parent
        target_path = workspace_root / missing_relative_path
        original_exists = Path.exists

        def fake_exists(path_obj: Path) -> bool:
            if path_obj == target_path:
                return False
            return original_exists(path_obj)

        with mock.patch.object(Path, "exists", fake_exists):
            code, output = self.run_cli("gate4-inspection")

        self.assertEqual(code, 1, output)
        self.assertIn("artifact_missing_count=1", output)
        self.assertIn(f"artifact_missing[0]={missing_relative_path}", output)
        self.assertIn("artifact.inspection_surface.present=false", output)

    def test_cycle_status_reports_last_terminal_run_after_cycle_completion(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "ace.db"
            briefing_path = Path(tmpdir) / "briefing.md"
            bootstrap_db(db_path)
            repo = ItemRepository(db_path)
            repo.create_item(item_type="note", title="CLI status target")

            run_cycle(db_path, now="2026-05-05T00:00:00Z", briefing_path=briefing_path)

            code, output = self.run_cli("--db", str(db_path), "cycle-status")

            self.assertEqual(code, 0, output)
            self.assertIn("current_run_present=false", output)
            self.assertIn("last_terminal_run_present=true", output)
            self.assertIn("last_terminal_run.run_kind=ace_cycle", output)
            self.assertIn("last_terminal_run.status=completed", output)
