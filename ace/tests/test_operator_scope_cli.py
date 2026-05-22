from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from ace.ace import main
from ace.operator_scope import compute_scope_hash


class OperatorScopeCliTests(unittest.TestCase):
    def run_cli(self, *argv: str) -> tuple[int, str]:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main(list(argv))
        return code, buffer.getvalue()

    def write_authorization(self, tmpdir: str, **overrides) -> Path:
        data = {
            "mode": "implementation_approved",
            "approval_ref": "telegram:7529788084:2026-05-22",
            "issued_by": "Andrew Pilson",
            "issued_at": "2026-05-22T19:00:00Z",
            "expires_at": "2099-01-01T00:00:00Z",
            "allowed_actions": ["file_write", "git_commit"],
            "allowed_paths": ["ace/**"],
            "denied_actions": ["external_send", "db_mutation"],
            "denied_paths": ["ace/state/*.db", "ace/state/*.sqlite"],
            "allowed_commands": [],
            "allowed_external_destinations": [],
        }
        data.update(overrides)
        data["scope_hash"] = compute_scope_hash(data)
        path = Path(tmpdir) / "authorization.json"
        path.write_text(json.dumps(data, sort_keys=True, indent=2), encoding="utf-8")
        return path

    def test_scope_template_emits_hash_bound_json(self) -> None:
        code, output = self.run_cli(
            "scope",
            "template",
            "--mode",
            "consultation_only",
            "--approval-ref",
            "telegram:1",
            "--issued-by",
            "Andrew",
            "--issued-at",
            "2026-05-22T19:00:00Z",
            "--expires-at",
            "2099-01-01T00:00:00Z",
            "--allowed-action",
            "file_write",
            "--allowed-path",
            "ace/state/v1_1_required_items/*.md",
        )

        self.assertEqual(code, 0, output)
        payload = json.loads(output)
        self.assertEqual(payload["mode"], "consultation_only")
        self.assertEqual(payload["scope_hash"], compute_scope_hash(payload))

    def test_scope_show_prints_active_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self.write_authorization(tmpdir)

            code, output = self.run_cli("scope", "show", "--authorization-path", str(path))

            self.assertEqual(code, 0, output)
            self.assertIn("scope.mode=implementation_approved", output)
            self.assertIn("scope.expired=false", output)
            self.assertIn("scope.allowed_actions=file_write,git_commit", output)

    def test_scope_check_allows_matching_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self.write_authorization(tmpdir)

            code, output = self.run_cli(
                "scope",
                "check",
                "file_write",
                "--path",
                "ace/operator_scope.py",
                "--authorization-path",
                str(path),
            )

            self.assertEqual(code, 0, output)
            self.assertIn("scope.allowed=true", output)

    def test_scope_check_denies_and_logs_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self.write_authorization(tmpdir, allowed_actions=[])
            block_log = Path(tmpdir) / "block-log.jsonl"

            code, output = self.run_cli(
                "scope",
                "check",
                "file_write",
                "--path",
                "ace/operator_scope.py",
                "--authorization-path",
                str(path),
                "--block-log-path",
                str(block_log),
                "--log-denial",
            )

            self.assertEqual(code, 1, output)
            self.assertIn("scope.allowed=false", output)
            rows = block_log.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(rows), 1)
            self.assertEqual(json.loads(rows[0])["action_class"], "file_write")


if __name__ == "__main__":
    unittest.main()
