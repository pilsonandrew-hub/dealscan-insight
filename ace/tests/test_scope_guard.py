from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ace.scope_guard import (
    DEFAULT_BLOCK_LOG_PATH,
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

    def _write_repo_authorization(self, directory: Path, **overrides: object) -> tuple[Path, Path, dict[str, object]]:
        authorization = render_authorization(
            mode="implementation_approved",
            approval_ref="telegram:operator-scope-v1-item3-slice2",
            issued_by="Andrew Pilson",
            issued_at="2026-05-22T20:30:00Z",
            expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
            allowed_actions=("db_mutation",),
            allowed_paths=("ace/state/*.db",),
            denied_actions=(),
            denied_paths=(),
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

    def test_guarded_repository_blocks_before_item_insert(self) -> None:
        from ace.repository import ItemRepository
        from ace.storage import bootstrap_db, connect

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            db_path = temp_path / "ace" / "state" / "ace.db"
            bootstrap_db(db_path)
            authorization_path, block_log_path, _ = self._write_repo_authorization(
                temp_path,
                allowed_actions=[],
                denied_actions=[],
                denied_paths=[],
            )
            repo = ItemRepository(
                db_path,
                scope_guard=ScopeGuard(authorization_path, block_log_path, workspace_root=temp_path),
            )

            decision = repo.create_item(item_type="task", title="blocked")

            self.assertEqual(ScopeDecisionType.REQUIRE_APPROVAL, decision.decision)
            with connect(db_path) as connection:
                item_count = connection.execute("SELECT COUNT(*) AS c FROM items").fetchone()["c"]
            self.assertEqual(0, item_count)
            record = json.loads(block_log_path.read_text(encoding="utf-8"))
            self.assertEqual("db_mutation", record["action_class"])
            self.assertIn(str(db_path), record["paths"])

    def test_guarded_repository_allows_item_insert_when_authorized(self) -> None:
        from ace.repository import ItemRepository
        from ace.storage import bootstrap_db

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            db_path = temp_path / "ace" / "state" / "ace.db"
            bootstrap_db(db_path)
            authorization_path, block_log_path, _ = self._write_repo_authorization(temp_path)
            repo = ItemRepository(
                db_path,
                scope_guard=ScopeGuard(authorization_path, block_log_path, workspace_root=temp_path),
            )

            item = repo.create_item(item_type="task", title="allowed")

            self.assertEqual("allowed", item.title)
            self.assertFalse(block_log_path.exists())

    def test_unguarded_repository_preserves_existing_test_contract(self) -> None:
        from ace.repository import ItemRepository
        from ace.storage import bootstrap_db

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "ace.db"
            bootstrap_db(db_path)
            repo = ItemRepository(db_path)

            item = repo.create_item(item_type="task", title="existing contract")

            self.assertEqual("existing contract", item.title)
            self.assertFalse(DEFAULT_BLOCK_LOG_PATH.exists())


    def test_action_runtime_enqueue_blocks_before_queue_insert(self) -> None:
        from ace.action_runtime import enqueue_record_operator_followup
        from ace.repository import ItemRepository
        from ace.storage import bootstrap_db, connect

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            db_path = temp_path / "ace" / "state" / "ace.db"
            bootstrap_db(db_path)
            repo = ItemRepository(db_path)
            item = repo.create_item(item_type="task", title="target")
            authorization_path, block_log_path, _ = self._write_repo_authorization(
                temp_path,
                allowed_actions=[],
                denied_actions=[],
                denied_paths=[],
            )

            result = enqueue_record_operator_followup(
                db_path,
                item.id,
                note="blocked",
                scope_guard=ScopeGuard(authorization_path, block_log_path, workspace_root=temp_path),
            )

            self.assertEqual("scope_blocked", result["status"])
            with connect(db_path) as connection:
                action_count = connection.execute("SELECT COUNT(*) AS c FROM action_queue").fetchone()["c"]
            self.assertEqual(0, action_count)
            record = json.loads(block_log_path.read_text(encoding="utf-8"))
            self.assertEqual("db_mutation", record["action_class"])

    def test_action_runtime_enqueue_allows_queue_insert_when_authorized(self) -> None:
        from ace.action_runtime import enqueue_record_operator_followup
        from ace.repository import ItemRepository
        from ace.storage import bootstrap_db, connect

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            db_path = temp_path / "ace" / "state" / "ace.db"
            bootstrap_db(db_path)
            repo = ItemRepository(db_path)
            item = repo.create_item(item_type="task", title="target")
            authorization_path, block_log_path, _ = self._write_repo_authorization(temp_path)

            result = enqueue_record_operator_followup(
                db_path,
                item.id,
                note="allowed",
                scope_guard=ScopeGuard(authorization_path, block_log_path, workspace_root=temp_path),
            )

            self.assertEqual("queued", result["status"])
            with connect(db_path) as connection:
                action_count = connection.execute("SELECT COUNT(*) AS c FROM action_queue").fetchone()["c"]
            self.assertEqual(1, action_count)
            self.assertFalse(block_log_path.exists())


    def test_governed_run_create_blocks_before_insert(self) -> None:
        from ace.governed_run_runtime import create_governed_cycle_run
        from ace.storage import bootstrap_db, connect

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            db_path = temp_path / "ace" / "state" / "ace.db"
            bootstrap_db(db_path)
            authorization_path, block_log_path, _ = self._write_repo_authorization(
                temp_path,
                allowed_actions=[],
                denied_actions=[],
                denied_paths=[],
            )

            result = create_governed_cycle_run(
                db_path,
                scope_guard=ScopeGuard(authorization_path, block_log_path, workspace_root=temp_path),
            )

            self.assertEqual("scope_blocked", result["status"])
            with connect(db_path) as connection:
                run_count = connection.execute("SELECT COUNT(*) AS c FROM governed_runs").fetchone()["c"]
            self.assertEqual(0, run_count)
            record = json.loads(block_log_path.read_text(encoding="utf-8"))
            self.assertEqual("db_mutation", record["action_class"])

    def test_governed_run_create_allows_insert_when_authorized(self) -> None:
        from ace.governed_run_runtime import create_governed_cycle_run
        from ace.storage import bootstrap_db, connect

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            db_path = temp_path / "ace" / "state" / "ace.db"
            bootstrap_db(db_path)
            authorization_path, block_log_path, _ = self._write_repo_authorization(temp_path)

            result = create_governed_cycle_run(
                db_path,
                scope_guard=ScopeGuard(authorization_path, block_log_path, workspace_root=temp_path),
            )

            self.assertEqual("pending", result["status"])
            with connect(db_path) as connection:
                run_count = connection.execute("SELECT COUNT(*) AS c FROM governed_runs").fetchone()["c"]
            self.assertEqual(1, run_count)
            self.assertFalse(block_log_path.exists())


    def test_supervisor_start_blocks_before_runtime_insert(self) -> None:
        from ace.storage import bootstrap_db, connect
        from ace.supervisor_runtime import start_supervisor_runtime

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            db_path = temp_path / "ace" / "state" / "ace.db"
            bootstrap_db(db_path)
            authorization_path, block_log_path, _ = self._write_repo_authorization(
                temp_path,
                allowed_actions=[],
                denied_actions=[],
                denied_paths=[],
            )

            result = start_supervisor_runtime(
                db_path,
                scope_guard=ScopeGuard(authorization_path, block_log_path, workspace_root=temp_path),
            )

            self.assertEqual("scope_blocked", result["status"])
            with connect(db_path) as connection:
                runtime_count = connection.execute("SELECT COUNT(*) AS c FROM runtime_instances").fetchone()["c"]
            self.assertEqual(0, runtime_count)
            record = json.loads(block_log_path.read_text(encoding="utf-8"))
            self.assertEqual("db_mutation", record["action_class"])

    def test_supervisor_start_allows_runtime_insert_when_authorized(self) -> None:
        from ace.storage import bootstrap_db, connect
        from ace.supervisor_runtime import start_supervisor_runtime

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            db_path = temp_path / "ace" / "state" / "ace.db"
            bootstrap_db(db_path)
            authorization_path, block_log_path, _ = self._write_repo_authorization(temp_path)

            result = start_supervisor_runtime(
                db_path,
                scope_guard=ScopeGuard(authorization_path, block_log_path, workspace_root=temp_path),
            )

            self.assertEqual("starting", result["status"])
            with connect(db_path) as connection:
                runtime_count = connection.execute("SELECT COUNT(*) AS c FROM runtime_instances").fetchone()["c"]
            self.assertEqual(1, runtime_count)
            self.assertFalse(block_log_path.exists())


    def test_sweep_blocks_before_event_insert(self) -> None:
        from ace.repository import ItemRepository
        from ace.storage import bootstrap_db, connect
        from ace.sweep import SweepThresholds, run_sweep

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            db_path = temp_path / "ace" / "state" / "ace.db"
            bootstrap_db(db_path)
            repo = ItemRepository(db_path)
            repo.create_item(item_type="task", title="stale")
            authorization_path, block_log_path, _ = self._write_repo_authorization(
                temp_path,
                allowed_actions=[],
                denied_actions=[],
                denied_paths=[],
            )

            result = run_sweep(
                db_path,
                thresholds=SweepThresholds(triage_after_seconds=0),
                now="2026-05-05T12:00:00Z",
                scope_guard=ScopeGuard(authorization_path, block_log_path, workspace_root=temp_path),
            )

            self.assertEqual("scope_blocked", result["status"])
            with connect(db_path) as connection:
                event_count = connection.execute(
                    "SELECT COUNT(*) AS c FROM events WHERE event_type = 'ace.sweep.completed'"
                ).fetchone()["c"]
            self.assertEqual(0, event_count)
            record = json.loads(block_log_path.read_text(encoding="utf-8"))
            self.assertEqual("db_mutation", record["action_class"])

    def test_sweep_allows_event_insert_when_authorized(self) -> None:
        from ace.repository import ItemRepository
        from ace.storage import bootstrap_db, connect
        from ace.sweep import SweepThresholds, run_sweep

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            db_path = temp_path / "ace" / "state" / "ace.db"
            bootstrap_db(db_path)
            repo = ItemRepository(db_path)
            repo.create_item(item_type="task", title="stale")
            authorization_path, block_log_path, _ = self._write_repo_authorization(temp_path)

            result = run_sweep(
                db_path,
                thresholds=SweepThresholds(triage_after_seconds=0),
                now="2026-05-05T12:00:00Z",
                scope_guard=ScopeGuard(authorization_path, block_log_path, workspace_root=temp_path),
            )

            self.assertEqual(1, result["emitted_count"])
            with connect(db_path) as connection:
                event_count = connection.execute(
                    "SELECT COUNT(*) AS c FROM events WHERE event_type = 'ace.sweep.completed'"
                ).fetchone()["c"]
            self.assertEqual(1, event_count)
            self.assertFalse(block_log_path.exists())



if __name__ == "__main__":
    unittest.main()
