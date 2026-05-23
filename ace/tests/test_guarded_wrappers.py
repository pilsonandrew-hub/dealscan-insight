from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ace.scope_guard import compute_scope_hash, render_authorization


REPO_ROOT = Path(__file__).resolve().parents[2]
WRAPPER_DIR = REPO_ROOT / "ace" / "bin" / "guarded"


class GuardedWrapperTests(unittest.TestCase):
    def test_git_wrapper_refuses_unauthorized_add_before_index_side_effect(self) -> None:
        with self._fixture_workspace() as workspace:
            self._write_authorization(workspace, allowed_actions=[], allowed_paths=[])
            before = self._git_index_entries(workspace)
            target = workspace / "unauthorized.txt"
            target.write_text("nope\n", encoding="utf-8")

            result = self._run_wrapper(workspace, "git", "add", "unauthorized.txt")

            self.assertNotEqual(0, result.returncode, result.stderr)
            self.assertEqual(before, self._git_index_entries(workspace))
            self.assertIn("ACE guarded wrapper refused git", result.stderr)
            self.assert_block_log(workspace, "git_stage")

    def test_git_wrapper_allows_authorized_read_only_status(self) -> None:
        with self._fixture_workspace() as workspace:
            self._write_authorization(workspace, allowed_actions=[], allowed_paths=[])

            result = self._run_wrapper(workspace, "git", "status", "--short")

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("??", result.stdout)
            self.assertFalse(self._block_log_path(workspace).exists())

    def test_sqlite_wrapper_refuses_mutation_before_database_side_effect(self) -> None:
        with self._fixture_workspace() as workspace:
            self._write_authorization(workspace, allowed_actions=[], allowed_paths=[])
            db_path = workspace / "ace" / "state" / "ace.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)

            result = self._run_wrapper(workspace, "sqlite3", "ace/state/ace.db", "CREATE TABLE forbidden(id INTEGER)")

            self.assertNotEqual(0, result.returncode, result.stderr)
            inspect = subprocess.run(
                ("/usr/bin/sqlite3", str(db_path), "SELECT name FROM sqlite_master WHERE type='table' AND name='forbidden'"),
                cwd=workspace,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual("", inspect.stdout.strip())
            self.assert_block_log(workspace, "db_mutation")

    def test_sqlite_wrapper_allows_authorized_read_only_query(self) -> None:
        with self._fixture_workspace() as workspace:
            self._write_authorization(workspace, allowed_actions=[], allowed_paths=[])
            db_path = workspace / "ace" / "state" / "ace.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)

            result = self._run_wrapper(workspace, "sqlite3", "ace/state/ace.db", "SELECT 1")

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("1", result.stdout.strip())
            self.assertFalse(self._block_log_path(workspace).exists())

    def test_curl_wrapper_refuses_external_send_before_execing_real_binary(self) -> None:
        with self._fixture_workspace() as workspace:
            self._write_authorization(workspace, allowed_actions=[], allowed_paths=[])

            result = self._run_wrapper(
                workspace,
                "curl",
                "-sS",
                "https://api.telegram.org/botTOKEN/sendMessage",
                "-d",
                "chat_id=1",
            )

            self.assertNotEqual(0, result.returncode, result.stderr)
            self.assertEqual("", result.stdout)
            self.assert_block_log(workspace, "external_send")

    def test_python3_wrapper_refuses_inline_eval_before_side_effect(self) -> None:
        with self._fixture_workspace() as workspace:
            self._write_authorization(workspace, allowed_actions=[], allowed_paths=[])
            side_effect = workspace / "inline-side-effect.txt"

            result = self._run_wrapper(
                workspace,
                "python3",
                "-c",
                "from pathlib import Path; Path('inline-side-effect.txt').write_text('bad')",
            )

            self.assertNotEqual(0, result.returncode, result.stderr)
            self.assertFalse(side_effect.exists())
            self.assert_block_log(workspace, "test_side_effecting")

    def test_python3_wrapper_allows_authorized_test_command(self) -> None:
        with self._fixture_workspace() as workspace:
            self._write_authorization(workspace, allowed_actions=["test_side_effecting"], allowed_paths=[])

            result = self._run_wrapper(workspace, "python3", "-m", "unittest", "--help")

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("usage:", result.stdout.lower())

    def assert_block_log(self, workspace: Path, action_class: str) -> None:
        path = self._block_log_path(workspace)
        self.assertTrue(path.exists())
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
        self.assertTrue(any(record.get("action_class") == action_class for record in records), records)

    def _fixture_workspace(self):
        test_case = self

        class Fixture:
            def __enter__(self) -> Path:
                self.path = Path(tempfile.mkdtemp(prefix="ace-wrapper-workspace-"))
                test_case._copy_wrapper_tree(self.path)
                (self.path / "ace" / "state" / "v1_1_required_items").mkdir(parents=True, exist_ok=True)
                subprocess.run(("/usr/bin/git", "init"), cwd=self.path, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
                subprocess.run(("/usr/bin/git", "config", "user.email", "test@example.invalid"), cwd=self.path, check=True)
                subprocess.run(("/usr/bin/git", "config", "user.name", "ACE Wrapper Test"), cwd=self.path, check=True)
                (self.path / "README.md").write_text("fixture\n", encoding="utf-8")
                subprocess.run(("/usr/bin/git", "add", "README.md"), cwd=self.path, check=True)
                subprocess.run(("/usr/bin/git", "commit", "-m", "initial"), cwd=self.path, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
                return self.path

            def __exit__(self, exc_type, exc, tb) -> None:
                import shutil

                shutil.rmtree(self.path, ignore_errors=True)

        return Fixture()

    def _copy_wrapper_tree(self, workspace: Path) -> None:
        import shutil

        target = workspace / "ace" / "bin" / "guarded"
        target.mkdir(parents=True, exist_ok=True)
        shutil.copytree(WRAPPER_DIR, target, dirs_exist_ok=True)
        (workspace / "ace" / "__init__.py").write_text("", encoding="utf-8")
        shutil.copy2(REPO_ROOT / "ace" / "scope_guard.py", workspace / "ace" / "scope_guard.py")
        for path in target.iterdir():
            if path.is_file():
                path.chmod(path.stat().st_mode | stat.S_IXUSR)

    def _write_authorization(self, workspace: Path, *, allowed_actions: list[str], allowed_paths: list[str]) -> None:
        data = render_authorization(
            mode="implementation_approved",
            approval_ref="test-slice4",
            issued_by="Andrew Pilson",
            issued_at="2026-05-22T20:30:00Z",
            expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
            allowed_actions=allowed_actions,
            allowed_paths=allowed_paths,
            denied_actions=[],
            denied_paths=["ace/state/*.db"],
            allowed_commands=[],
            allowed_external_destinations=[],
        )
        data["scope_hash"] = compute_scope_hash(data)
        path = workspace / "ace" / "state" / "v1_1_required_items" / "authorization.json"
        path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _run_wrapper(self, workspace: Path, wrapper: str, *args: str) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ)
        env["PYTHONPATH"] = str(workspace)
        return subprocess.run(
            (str(workspace / "ace" / "bin" / "guarded" / wrapper), *args),
            cwd=workspace,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def _git_index_entries(self, workspace: Path) -> str:
        return subprocess.run(
            ("/usr/bin/git", "ls-files", "--stage"),
            cwd=workspace,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        ).stdout

    def _block_log_path(self, workspace: Path) -> Path:
        return workspace / "ace" / "state" / "v1_1_required_items" / "operator-scope-block-log.jsonl"


if __name__ == "__main__":
    unittest.main()
