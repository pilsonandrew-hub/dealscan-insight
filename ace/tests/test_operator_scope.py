from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ace.operator_scope import (
    OperatorAction,
    OperatorScopeDenied,
    OperatorScopeInvalid,
    compute_scope_hash,
    evaluate_action,
    load_authorization,
    render_authorization_template,
    require_action,
)


class OperatorScopeTests(unittest.TestCase):
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

    def test_render_authorization_template_produces_loadable_hash_bound_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "authorization.json"
            content = render_authorization_template(
                mode="consultation_only",
                approval_ref="telegram:1",
                issued_by="Andrew",
                issued_at="2026-05-22T19:00:00Z",
                expires_at="2099-01-01T00:00:00Z",
                allowed_actions=["file_write", "git_commit"],
                allowed_paths=["ace/state/v1_1_required_items/*.md"],
            )
            path.write_text(content, encoding="utf-8")

            authorization = load_authorization(path)

            self.assertEqual(authorization.mode, "consultation_only")
            self.assertRegex(authorization.scope_hash, r"^[0-9a-f]{64}$")

    def test_invalid_scope_hash_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self.write_authorization(tmpdir)
            data = json.loads(path.read_text(encoding="utf-8"))
            data["allowed_actions"] = ["file_write", "external_send"]
            path.write_text(json.dumps(data), encoding="utf-8")

            with self.assertRaisesRegex(OperatorScopeInvalid, "scope_hash"):
                load_authorization(path)

    def test_read_only_action_is_allowed_without_mutation_grant(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self.write_authorization(
                tmpdir,
                mode="investigation_only",
                allowed_actions=[],
                allowed_paths=[],
            )

            decision = evaluate_action(OperatorAction("read", paths=("ace/ace.py",)), authorization_path=path)

            self.assertTrue(decision.allowed)
            self.assertEqual(decision.reason, "read-only action allowed")

    def test_side_effect_action_requires_allowed_action_class(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self.write_authorization(tmpdir, allowed_actions=[])

            decision = evaluate_action(OperatorAction("file_write", paths=("ace/operator_scope.py",)), authorization_path=path)

            self.assertFalse(decision.allowed)
            self.assertIn("not allowed", decision.reason)

    def test_side_effect_action_requires_allowed_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self.write_authorization(tmpdir, allowed_paths=["ace/state/v1_1_required_items/*.md"])

            decision = evaluate_action(OperatorAction("file_write", paths=("ace/operator_scope.py",)), authorization_path=path)

            self.assertFalse(decision.allowed)
            self.assertIn("paths not allowed", decision.reason)

    def test_denied_path_overrides_allowed_glob(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self.write_authorization(tmpdir, allowed_paths=["ace/**"], denied_paths=["ace/state/*.db"])

            decision = evaluate_action(OperatorAction("file_write", paths=("ace/state/ace.db",)), authorization_path=path)

            self.assertFalse(decision.allowed)
            self.assertIn("explicitly denied", decision.reason)

    def test_denied_action_overrides_allowed_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self.write_authorization(
                tmpdir,
                allowed_actions=["external_send"],
                denied_actions=["external_send"],
                allowed_external_destinations=["telegram:7529788084"],
            )

            decision = evaluate_action(
                OperatorAction("external_send", destination="telegram:7529788084"),
                authorization_path=path,
            )

            self.assertFalse(decision.allowed)
            self.assertIn("explicitly denied", decision.reason)

    def test_external_send_requires_named_destination(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self.write_authorization(
                tmpdir,
                allowed_actions=["external_send"],
                denied_actions=[],
                allowed_external_destinations=["telegram:7529788084"],
            )

            decision = evaluate_action(
                OperatorAction("external_send", destination="telegram:-1003672399222"),
                authorization_path=path,
            )

            self.assertFalse(decision.allowed)
            self.assertIn("destination", decision.reason)

    def test_external_send_without_destination_is_denied(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self.write_authorization(
                tmpdir,
                allowed_actions=["external_send"],
                denied_actions=[],
                allowed_external_destinations=["telegram:7529788084"],
            )

            decision = evaluate_action(OperatorAction("external_send"), authorization_path=path)

            self.assertFalse(decision.allowed)
            self.assertIn("requires a destination", decision.reason)

    def test_expired_scope_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            expired = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
            path = self.write_authorization(tmpdir, expires_at=expired)

            decision = evaluate_action(OperatorAction("file_write", paths=("ace/operator_scope.py",)), authorization_path=path)

            self.assertFalse(decision.allowed)
            self.assertEqual(decision.reason, "operator authorization expired")

    def test_require_action_logs_block_before_raising(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            authorization_path = self.write_authorization(tmpdir, allowed_actions=[])
            block_log_path = Path(tmpdir) / "block-log.jsonl"

            with self.assertRaises(OperatorScopeDenied):
                require_action(
                    OperatorAction("file_write", paths=("ace/operator_scope.py",), description="unit test"),
                    authorization_path=authorization_path,
                    block_log_path=block_log_path,
                )

            rows = block_log_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(rows), 1)
            payload = json.loads(rows[0])
            self.assertEqual(payload["action_class"], "file_write")
            self.assertEqual(payload["paths"], ["ace/operator_scope.py"])
            self.assertFalse(payload["allowed"])
            self.assertIn("not allowed", payload["reason"])

    def test_path_escape_is_denied_before_matching(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self.write_authorization(tmpdir, allowed_paths=["**"])

            with self.assertRaisesRegex(OperatorScopeInvalid, "outside workspace"):
                evaluate_action(OperatorAction("file_write", paths=("../outside.txt",)), authorization_path=path)

    def test_unknown_action_class_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self.write_authorization(tmpdir, allowed_actions=["invented_action"])

            with self.assertRaisesRegex(OperatorScopeInvalid, "unknown action"):
                load_authorization(path)


if __name__ == "__main__":
    unittest.main()
