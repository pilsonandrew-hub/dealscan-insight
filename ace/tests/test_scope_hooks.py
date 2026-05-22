from __future__ import annotations

import json
import shutil
import stat
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ace.scope_guard import compute_scope_hash, render_authorization


REPO_ROOT = Path(__file__).resolve().parents[2]
HOOKS_DIR = REPO_ROOT / "ace" / "hooks"


class ScopeHookTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original_hooks_path = subprocess.run(
            ("git", "config", "--get", "core.hooksPath"),
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        ).stdout.strip()

    def tearDown(self) -> None:
        if self._original_hooks_path:
            subprocess.run(("git", "config", "core.hooksPath", self._original_hooks_path), cwd=REPO_ROOT, check=False)
        else:
            subprocess.run(("git", "config", "--unset", "core.hooksPath"), cwd=REPO_ROOT, check=False)

    def test_pre_commit_refuses_commit_outside_allowed_paths_before_commit_completes(self) -> None:
        with self._fixture_repo() as repo:
            self._write_authorization(repo, allowed_actions=["git_commit"], allowed_paths=["ace/hooks/**"])
            before = self._head(repo)
            (repo / "unauthorized.txt").write_text("nope\n", encoding="utf-8")
            self._git(repo, "add", "unauthorized.txt", check=True)

            result = self._git(repo, "commit", "-m", "bad commit\n\nOperator-Scope: test", check=False)

            self.assertNotEqual(0, result.returncode, result.stderr)
            self.assertEqual(before, self._head(repo))
            self.assertIn("operator-scope hook refused", result.stderr)
            self.assert_block_log(repo, "git_commit")

    def test_commit_msg_refuses_missing_operator_scope_trailer_before_commit_completes(self) -> None:
        with self._fixture_repo() as repo:
            self._write_authorization(repo, allowed_actions=["git_commit"], allowed_paths=["ace/hooks/**"])
            before = self._head(repo)
            target = repo / "ace" / "hooks" / "tracked.txt"
            target.write_text("ok\n", encoding="utf-8")
            self._git(repo, "add", "ace/hooks/tracked.txt", check=True)

            result = self._git(repo, "commit", "-m", "missing trailer", check=False)

            self.assertNotEqual(0, result.returncode, result.stderr)
            self.assertEqual(before, self._head(repo))
            self.assertIn("missing Operator-Scope trailer", result.stderr)
            self.assert_block_log(repo, "git_commit")

    def test_pre_push_refuses_protected_paths_before_remote_ref_updates(self) -> None:
        with self._fixture_repo() as repo:
            self._write_authorization(repo, allowed_actions=["git_commit"], allowed_paths=["ace/hooks/**"])
            remote = Path(tempfile.mkdtemp(prefix="ace-hook-remote-"))
            try:
                self._git(remote, "init", "--bare", check=True)
                self._git(repo, "remote", "add", "origin", str(remote), check=True)
                target = repo / "ace" / "tests" / "protected_test.py"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("protected change\n", encoding="utf-8")
                self._git(repo, "add", "ace/tests/protected_test.py", check=True)
                self._git(repo, "commit", "--no-verify", "-m", "protected\n\nOperator-Scope: test", check=True)

                result = self._git(repo, "push", "origin", "HEAD:refs/heads/main", check=False)

                self.assertNotEqual(0, result.returncode, result.stderr)
                remote_heads = subprocess.run(
                    ("git", "--git-dir", str(remote), "show-ref", "--heads"),
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                self.assertEqual("", remote_heads.stdout.strip())
                self.assertIn("operator-scope hook refused", result.stderr)
                self.assert_block_log(repo, "git_push")
            finally:
                shutil.rmtree(remote, ignore_errors=True)

    def test_hooks_path_is_restored_after_fixture_activation(self) -> None:
        with self._fixture_repo() as repo:
            configured = self._git(repo, "config", "--get", "core.hooksPath", check=True).stdout.strip()
            self.assertEqual("ace/hooks", configured)

        current = subprocess.run(
            ("git", "config", "--get", "core.hooksPath"),
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        ).stdout.strip()
        self.assertEqual(self._original_hooks_path, current)

    def assert_block_log(self, repo: Path, action_class: str) -> None:
        log_path = repo / "ace" / "state" / "v1_1_required_items" / "operator-scope-block-log.jsonl"
        self.assertTrue(log_path.exists())
        records = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line]
        self.assertTrue(any(record.get("action_class") == action_class for record in records), records)

    def _fixture_repo(self):
        test_case = self

        class Fixture:
            def __enter__(self) -> Path:
                self.path = Path(tempfile.mkdtemp(prefix="ace-hook-repo-"))
                test_case._git(self.path, "init", check=True)
                test_case._git(self.path, "config", "user.email", "test@example.invalid", check=True)
                test_case._git(self.path, "config", "user.name", "ACE Hook Test", check=True)
                (self.path / "ace" / "hooks").mkdir(parents=True)
                (self.path / "ace" / "state" / "v1_1_required_items").mkdir(parents=True)
                (self.path / "ace" / "tests").mkdir(parents=True)
                shutil.copytree(HOOKS_DIR, self.path / "ace" / "hooks", dirs_exist_ok=True)
                (self.path / "ace" / "__init__.py").write_text("", encoding="utf-8")
                shutil.copy2(REPO_ROOT / "ace" / "scope_guard.py", self.path / "ace" / "scope_guard.py")
                for hook in (self.path / "ace" / "hooks").iterdir():
                    if hook.is_file() and hook.name != "README.md":
                        hook.chmod(hook.stat().st_mode | stat.S_IXUSR)
                test_case._git(self.path, "config", "core.hooksPath", "ace/hooks", check=True)
                (self.path / "README.md").write_text("fixture\n", encoding="utf-8")
                test_case._git(self.path, "add", "README.md", check=True)
                test_case._git(self.path, "commit", "--no-verify", "-m", "initial", check=True)
                return self.path

            def __exit__(self, exc_type, exc, tb) -> None:
                shutil.rmtree(self.path, ignore_errors=True)

        return Fixture()

    def _write_authorization(self, repo: Path, *, allowed_actions: list[str], allowed_paths: list[str]) -> None:
        data = render_authorization(
            mode="implementation_approved",
            approval_ref="test",
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
        path = repo / "ace" / "state" / "v1_1_required_items" / "authorization.json"
        path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _head(self, repo: Path) -> str:
        return self._git(repo, "rev-parse", "HEAD", check=True).stdout.strip()

    def _git(self, repo: Path, *args: str, check: bool) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ("git", *args),
            cwd=repo,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if check and result.returncode != 0:
            self.fail(f"git {' '.join(args)} failed\nstdout={result.stdout}\nstderr={result.stderr}")
        return result


if __name__ == "__main__":
    unittest.main()
