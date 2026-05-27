from __future__ import annotations

import io
import os
import sqlite3
import subprocess
import stat
import sys
import tempfile
import unittest
from contextlib import closing, redirect_stderr
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ace.false_closure_advisory import (
    commit_message_has_completion_verbs,
    evaluate_false_closure_advisory,
    format_false_closure_warning,
    run_commit_msg_advisory,
)
from ace.hooks_install import install_operational_hooks, status_operational_hooks
from ace.storage import bootstrap_db


class FalseClosureAdvisoryTests(unittest.TestCase):
    def _insert_item(
        self,
        connection: sqlite3.Connection,
        item_id: str,
        state: str,
        updated_at: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO items (
                id, item_type, title, state, source, created_at, updated_at, last_event_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item_id,
                "task",
                f"title for {item_id}",
                state,
                "telegram/direct",
                updated_at,
                updated_at,
                f"evt_{item_id}",
            ),
        )

    def _insert_event(
        self,
        connection: sqlite3.Connection,
        event_id: str,
        item_id: str,
        event_type: str,
        created_at: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO events (event_id, item_id, event_type, payload_json, created_at, event_hash)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (event_id, item_id, event_type, "{}", created_at, "0" * 64),
        )

    def test_completion_verbs_detected_as_whole_words(self) -> None:
        self.assertTrue(commit_message_has_completion_verbs("fix stale digest path"))
        self.assertTrue(commit_message_has_completion_verbs("ship seam 3 advisory hook"))
        self.assertFalse(commit_message_has_completion_verbs("prefix handling only"))
        self.assertFalse(commit_message_has_completion_verbs("documentation update"))

    def test_warning_when_verbs_and_loose_ends_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "ace.db"
            bootstrap_db(db_path)
            old_at = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat().replace("+00:00", "Z")
            with closing(sqlite3.connect(db_path)) as connection:
                self._insert_item(connection, "item_false_close", "APPROVED", old_at)
                self._insert_event(
                    connection,
                    "evt_item_false_close",
                    "item_false_close",
                    "item.state_changed",
                    old_at,
                )
                connection.commit()

            warning = evaluate_false_closure_advisory(
                "fix digest resume formatting",
                db_path=db_path,
            )
            self.assertIsNotNone(warning)
            self.assertIn("ACE false-closure advisory:", warning)
            self.assertIn("item_false_close", warning)

    def test_no_warning_without_completion_verbs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "ace.db"
            bootstrap_db(db_path)
            old_at = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat().replace("+00:00", "Z")
            with closing(sqlite3.connect(db_path)) as connection:
                self._insert_item(connection, "item_doc_only", "APPROVED", old_at)
                self._insert_event(
                    connection,
                    "evt_item_doc_only",
                    "item_doc_only",
                    "item.state_changed",
                    old_at,
                )
                connection.commit()

            warning = evaluate_false_closure_advisory(
                "docs: refresh STATUS wording",
                db_path=db_path,
            )
            self.assertIsNone(warning)

    def test_commit_msg_hook_always_exits_zero_and_warns_on_stderr(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "ace.db"
            bootstrap_db(db_path)
            old_at = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat().replace("+00:00", "Z")
            with closing(sqlite3.connect(db_path)) as connection:
                self._insert_item(connection, "item_hook_warn", "APPROVED", old_at)
                self._insert_event(
                    connection,
                    "evt_item_hook_warn",
                    "item_hook_warn",
                    "item.state_changed",
                    old_at,
                )
                connection.commit()

            message_path = Path(tmpdir) / "COMMIT_EDITMSG"
            message_path.write_text("complete seam 3 hook wiring\n", encoding="utf-8")
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                code = run_commit_msg_advisory(message_path, db_path=db_path)
            self.assertEqual(code, 0)
            self.assertIn("ACE false-closure advisory:", stderr.getvalue())
            self.assertIn("item_hook_warn", stderr.getvalue())

    def test_format_warning_truncates_item_list(self) -> None:
        rows = [{"item_id": f"item_{index}", "pattern_name": "x", "detected_at": "t", "evidence_gap": "g"} for index in range(7)]
        warning = format_false_closure_warning(loose_rows=rows, matched_verbs=["done"], max_items=3)
        self.assertIn("(+4 more)", warning)

    def test_hooks_install_sets_operational_hooks_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            ace_hooks = repo / "ace" / "hooks" / "operational"
            ace_hooks.mkdir(parents=True)
            source_commit_msg = Path(__file__).resolve().parents[1] / "hooks" / "operational" / "commit-msg"
            source_advisory = Path(__file__).resolve().parents[1] / "hooks" / "operational" / "advisory_commit_msg.py"
            (ace_hooks / "commit-msg").write_text(source_commit_msg.read_text(encoding="utf-8"), encoding="utf-8")
            (ace_hooks / "advisory_commit_msg.py").write_text(
                source_advisory.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            commit_hook = ace_hooks / "commit-msg"
            commit_hook.chmod(commit_hook.stat().st_mode | stat.S_IXUSR)

            code = install_operational_hooks(repo_root=repo)
            self.assertEqual(code, 0)
            configured = subprocess.run(
                ["git", "config", "--get", "core.hooksPath"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            self.assertEqual(configured, "ace/hooks/operational")

            status_code = status_operational_hooks(repo_root=repo)
            self.assertEqual(status_code, 0)


if __name__ == "__main__":
    unittest.main()
