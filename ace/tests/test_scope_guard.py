from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ace.scope_guard import (
    ScopeAction,
    ScopeAuthorizationInvalid,
    ScopeDecisionType,
    ScopeGuard,
    compute_scope_hash,
    render_authorization,
)


class ScopeGuardTests(unittest.TestCase):
    def _write_authorization(self, directory: Path, **overrides: object) -> tuple[Path, Path, dict[str, object]]:
        authorization = render_authorization(
            mode="implementation_approved",
            approval_ref="telegram:operator-scope-v1-item3-slice1",
            issued_by="Andrew Pilson",
            issued_at="2026-05-22T20:30:00Z",
            expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
            allowed_actions=("file_write", "git_commit"),
            allowed_paths=("ace/scope_guard.py", "ace/tests/*.py"),
            denied_actions=(),
            denied_paths=("ace/state/*.db",),
            allowed_commands=(),
            allowed_external_destinations=(),
        )
        authorization.update(overrides)
        if "scope_hash" not in overrides:
            authorization["scope_hash"] = compute_scope_hash(authorization)
        authorization_path = directory / "authorization.json"
        block_log_path = directory / "operator-scope-block-log.jsonl"
        authorization_path.write_text(json.dumps(authorization, indent=2, sort_keys=True), encoding="utf-8")
        return authorization_path, block_log_path, authorization

    def test_authorize_allows_matching_side_effect(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            authorization_path, block_log_path, authorization = self._write_authorization(Path(temp_dir))
            guard = ScopeGuard(authorization_path, block_log_path)

            decision = guard.authorize(ScopeAction("file_write", paths=("ace/scope_guard.py",)))

            self.assertEqual(ScopeDecisionType.ALLOW, decision.decision)
            self.assertTrue(decision.allowed)
            self.assertEqual("implementation_approved", decision.mode)
            self.assertEqual(authorization["scope_hash"], decision.scope_hash)
            self.assertFalse(block_log_path.exists())

    def test_authorize_allows_read_only_without_mutation_grant(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            authorization_path, block_log_path, _ = self._write_authorization(Path(temp_dir), allowed_actions=[])
            guard = ScopeGuard(authorization_path, block_log_path)

            decision = guard.authorize(ScopeAction("read", paths=("ace/repository.py",)))

            self.assertEqual(ScopeDecisionType.ALLOW, decision.decision)
            self.assertFalse(block_log_path.exists())

    def test_authorize_blocks_unlisted_medium_risk_action_and_logs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            authorization_path, block_log_path, _ = self._write_authorization(Path(temp_dir), allowed_actions=[])
            guard = ScopeGuard(authorization_path, block_log_path)

            decision = guard.authorize(ScopeAction("file_write", paths=("ace/scope_guard.py",)))

            self.assertEqual(ScopeDecisionType.BLOCK, decision.decision)
            self.assertEqual("medium", decision.severity)
            record = json.loads(block_log_path.read_text(encoding="utf-8"))
            self.assertEqual("BLOCK", record["decision"])
            self.assertEqual("file_write", record["action_class"])

    def test_authorize_requires_approval_for_high_risk_action(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            authorization_path, block_log_path, _ = self._write_authorization(Path(temp_dir), allowed_actions=[])
            guard = ScopeGuard(authorization_path, block_log_path)

            decision = guard.authorize(ScopeAction("db_mutation", paths=("ace/state/ace.db",)))

            self.assertEqual(ScopeDecisionType.REQUIRE_APPROVAL, decision.decision)
            self.assertEqual("high", decision.severity)
            record = json.loads(block_log_path.read_text(encoding="utf-8"))
            self.assertEqual("REQUIRE_APPROVAL", record["decision"])

    def test_external_send_requires_named_allowed_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            authorization_path, block_log_path, _ = self._write_authorization(
                Path(temp_dir),
                allowed_actions=["external_send"],
                allowed_external_destinations=["telegram:7529788084"],
            )
            guard = ScopeGuard(authorization_path, block_log_path)

            missing_destination = guard.authorize(ScopeAction("external_send"))
            allowed = guard.authorize(
                ScopeAction("external_send", destination="telegram:7529788084"), log_block=False
            )
            wrong_destination = guard.authorize(
                ScopeAction("external_send", destination="telegram:other"), log_block=False
            )

            self.assertEqual(ScopeDecisionType.REQUIRE_APPROVAL, missing_destination.decision)
            self.assertEqual(ScopeDecisionType.ALLOW, allowed.decision)
            self.assertEqual(ScopeDecisionType.REQUIRE_APPROVAL, wrong_destination.decision)

    def test_denied_path_overrides_allowed_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            authorization_path, block_log_path, _ = self._write_authorization(
                Path(temp_dir),
                allowed_actions=["file_write"],
                allowed_paths=["ace/state/*"],
                denied_paths=["ace/state/*.db"],
            )
            guard = ScopeGuard(authorization_path, block_log_path)

            decision = guard.authorize(ScopeAction("file_write", paths=("ace/state/ace.db",)))

            self.assertEqual(ScopeDecisionType.BLOCK, decision.decision)
            self.assertIn("path denied", decision.reason)

    def test_expired_authorization_requires_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            authorization_path, block_log_path, _ = self._write_authorization(
                Path(temp_dir),
                expires_at="2026-01-01T00:00:00Z",
            )
            guard = ScopeGuard(authorization_path, block_log_path)

            decision = guard.authorize(ScopeAction("file_write", paths=("ace/scope_guard.py",)))

            self.assertEqual(ScopeDecisionType.REQUIRE_APPROVAL, decision.decision)
            self.assertIn("expired", decision.reason)

    def test_invalid_scope_hash_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            authorization_path, block_log_path, _ = self._write_authorization(
                Path(temp_dir),
                scope_hash="not-the-real-hash",
            )
            guard = ScopeGuard(authorization_path, block_log_path)

            with self.assertRaisesRegex(ScopeAuthorizationInvalid, "scope_hash"):
                guard.authorize(ScopeAction("read"))

    def test_path_escape_in_scope_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            authorization_path, block_log_path, _ = self._write_authorization(
                Path(temp_dir),
                allowed_paths=["../outside"],
            )
            guard = ScopeGuard(authorization_path, block_log_path)

            with self.assertRaisesRegex(ScopeAuthorizationInvalid, "outside workspace"):
                guard.authorize(ScopeAction("file_write", paths=("ace/scope_guard.py",)))

    def test_render_authorization_hash_round_trips(self) -> None:
        rendered = render_authorization(
            mode="consultation_only",
            approval_ref="telegram:test",
            issued_by="Andrew Pilson",
            issued_at="2026-05-22T20:30:00Z",
            expires_at="2026-05-22T21:30:00Z",
            allowed_actions=("file_write",),
            allowed_paths=("ace/state/v1_1_required_items/*.md",),
        )

        self.assertEqual(compute_scope_hash(rendered), rendered["scope_hash"])


if __name__ == "__main__":
    unittest.main()
