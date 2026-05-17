from __future__ import annotations

import tempfile
import time
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ace.repository import ValidationError
from ace.supervisor_runtime import (
    FAILURE_PHASE_SHUTDOWN,
    FAILURE_PHASE_STARTUP,
    RECOVERY_STATUS_COMPLETED,
    RECOVERY_STATUS_FAILED,
    RECOVERY_STATUS_REQUESTED,
    RUNTIME_FAMILY_SINGLE_TENANT,
    SHUTDOWN_STATUS_COMPLETED,
    SHUTDOWN_STATUS_FAILED,
    SHUTDOWN_STATUS_REQUESTED,
    STARTUP_STATUS_COMPLETED,
    STARTUP_STATUS_FAILED,
    STATUS_FAILED,
    STATUS_LIVE,
    STATUS_STALE,
    STATUS_STOPPED,
    complete_supervisor_recovery,
    fail_supervisor_recovery,
    fail_supervisor_runtime,
    get_supervisor_runtime_status,
    heartbeat_supervisor_runtime,
    mark_supervisor_runtime_live,
    request_supervisor_recovery,
    request_supervisor_shutdown,
    run_supervisor_runtime,
    start_supervisor_runtime,
    stop_supervisor_runtime,
)
from ace.storage import bootstrap_db, connect


class SupervisorRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "ace.db"
        bootstrap_db(self.db_path)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_start_live_heartbeat_and_stop_persist_distinct_runtime_truth(self) -> None:
        runtime = start_supervisor_runtime(
            self.db_path,
            runtime_family=RUNTIME_FAMILY_SINGLE_TENANT,
            stale_after_seconds=30,
            host_identity="hq-mac",
            metadata={"slice": "e1"},
        )
        self.assertEqual(runtime["status"], "starting")
        self.assertTrue(runtime["created"])
        self.assertFalse(runtime["duplicate_start"])

        live = mark_supervisor_runtime_live(self.db_path, runtime["runtime_instance_id"])
        self.assertEqual(live["status"], STATUS_LIVE)

        heartbeat = heartbeat_supervisor_runtime(self.db_path, runtime["runtime_instance_id"])
        self.assertEqual(heartbeat["status"], STATUS_LIVE)
        self.assertGreaterEqual(heartbeat["last_seen_at"], live["last_seen_at"])

        stopped = stop_supervisor_runtime(self.db_path, runtime["runtime_instance_id"])
        self.assertEqual(stopped["status"], STATUS_STOPPED)
        self.assertIsNotNone(stopped["ended_at"])

        with connect(self.db_path) as connection:
            row = connection.execute(
                "SELECT status, host_identity, metadata_json FROM runtime_instances WHERE runtime_instance_id = ?",
                (runtime["runtime_instance_id"],),
            ).fetchone()
        self.assertEqual(row["status"], STATUS_STOPPED)
        self.assertEqual(row["host_identity"], "hq-mac")
        self.assertEqual(row["metadata_json"], '{"slice":"e1"}')
        self.assertEqual(stopped["startup_status"], STARTUP_STATUS_COMPLETED)
        self.assertEqual(stopped["shutdown_status"], SHUTDOWN_STATUS_COMPLETED)
        self.assertIsNotNone(stopped["shutdown_requested_at"])
        self.assertIsNotNone(stopped["shutdown_completed_at"])

    def test_duplicate_start_is_explicit_and_reuses_active_runtime(self) -> None:
        first = start_supervisor_runtime(self.db_path)
        second = start_supervisor_runtime(self.db_path)

        self.assertEqual(first["runtime_instance_id"], second["runtime_instance_id"])
        self.assertFalse(second["created"])
        self.assertTrue(second["duplicate_start"])

    def test_status_inspection_classifies_stale_and_is_independent_from_governed_runs(self) -> None:
        runtime = start_supervisor_runtime(self.db_path, stale_after_seconds=5)
        live = mark_supervisor_runtime_live(self.db_path, runtime["runtime_instance_id"])

        last_seen = datetime.fromisoformat(live["last_seen_at"].replace("Z", "+00:00")).astimezone(timezone.utc)
        inspection_now = (last_seen + timedelta(seconds=10)).isoformat().replace("+00:00", "Z")

        status = get_supervisor_runtime_status(self.db_path, now=inspection_now)
        self.assertEqual(status["inspection_family"], "resident_supervisor_runtime")
        self.assertEqual(status["inspection_scope"], "bounded_resident_supervisor_seam")
        self.assertIn("distinct_resident_runtime_ledger", status["bounded_runtime_claims"])
        self.assertIn("not_v1", status["anti_inflation_non_claims"])
        self.assertIn("not_platform_or_runtime_fabric", status["anti_inflation_non_claims"])
        self.assertIn("launchagent_scheduled_real_ace_cycle", status["minimal_slice_definition"])
        self.assertIn("reports/ace-e5-anti-inflation-boundary-proof-verdict-2026-05-07.md", status["evidence_artifact_bundle"])
        self.assertIn("inspection_surface_exposes_transition_recovery_history_and_non_claims_beyond_bounded_ace_cycle", status["non_reduction_proof"])
        self.assertIsNotNone(status["current_runtime"])
        self.assertEqual(status["current_runtime"]["status"], STATUS_STALE)
        self.assertIsNone(status["last_terminal_runtime"])
        self.assertGreaterEqual(len(status["runtime_transition_history"]), 3)
        self.assertEqual(status["runtime_transition_history"][0]["event_type"], "ace.supervisor.started")
        self.assertEqual(status["runtime_transition_history"][-1]["event_type"], "ace.supervisor.stale")

        with connect(self.db_path) as connection:
            governed_count = connection.execute("SELECT COUNT(*) FROM governed_runs").fetchone()[0]
            current_status = connection.execute(
                "SELECT status FROM runtime_instances WHERE runtime_instance_id = ?",
                (runtime["runtime_instance_id"],),
            ).fetchone()[0]
            event_count = connection.execute(
                "SELECT COUNT(*) FROM events WHERE source = ? AND json_extract(payload_json, '$.runtime_instance_id') = ?",
                ("ace.supervisor_runtime", runtime["runtime_instance_id"]),
            ).fetchone()[0]
        self.assertEqual(governed_count, 0)
        self.assertEqual(current_status, STATUS_STALE)
        self.assertGreaterEqual(event_count, 3)

    def test_run_supervisor_runtime_auto_stops_cleanly(self) -> None:
        result = run_supervisor_runtime(
            self.db_path,
            heartbeat_count=2,
            heartbeat_interval_seconds=0.0,
            stale_after_seconds=60,
        )

        self.assertFalse(result["duplicate_start"])
        self.assertTrue(result["auto_stopped"])
        self.assertEqual(result["heartbeat_count"], 2)
        self.assertEqual(result["runtime"]["status"], STATUS_STOPPED)

    def test_run_supervisor_runtime_can_hold_until_explicit_shutdown(self) -> None:
        result_holder: dict[str, object] = {}

        def _target() -> None:
            result_holder["result"] = run_supervisor_runtime(
                self.db_path,
                heartbeat_interval_seconds=0.01,
                stale_after_seconds=60,
                run_until_shutdown=True,
            )

        thread = threading.Thread(target=_target)
        thread.start()

        runtime_instance_id = None
        for _ in range(200):
            status = get_supervisor_runtime_status(self.db_path)
            current_runtime = status["current_runtime"]
            if current_runtime is not None and current_runtime["status"] == STATUS_LIVE:
                runtime_instance_id = current_runtime["runtime_instance_id"]
                break
            time.sleep(0.01)

        self.assertIsNotNone(runtime_instance_id)
        status = get_supervisor_runtime_status(self.db_path)
        self.assertIsNotNone(status["current_runtime"])
        self.assertEqual(status["current_runtime"]["runtime_instance_id"], runtime_instance_id)
        self.assertEqual(status["current_runtime"]["status"], STATUS_LIVE)

        request_supervisor_shutdown(self.db_path, runtime_instance_id)
        thread.join(timeout=5)
        self.assertFalse(thread.is_alive())

        result = result_holder["result"]
        self.assertFalse(result["auto_stopped"])
        self.assertEqual(result["runtime"]["status"], STATUS_STOPPED)
        self.assertGreaterEqual(result["heartbeat_count"], 0)

    def test_fail_path_persists_terminal_failure_state(self) -> None:
        runtime = start_supervisor_runtime(self.db_path)
        mark_supervisor_runtime_live(self.db_path, runtime["runtime_instance_id"])

        failed = fail_supervisor_runtime(
            self.db_path,
            runtime["runtime_instance_id"],
            failure_code="supervisor_bounded_failure",
            failure_summary="bounded failure",
        )
        self.assertEqual(failed["status"], STATUS_FAILED)
        self.assertEqual(failed["failure_code"], "supervisor_bounded_failure")
        self.assertEqual(failed["failure_summary"], "bounded failure")
        self.assertEqual(failed["failure_phase"], "runtime")

    def test_startup_failure_marks_explicit_startup_failure_truth(self) -> None:
        runtime = start_supervisor_runtime(self.db_path)
        failed = fail_supervisor_runtime(
            self.db_path,
            runtime["runtime_instance_id"],
            failure_code="startup_failure",
            failure_summary="startup failed",
            failure_phase=FAILURE_PHASE_STARTUP,
        )
        self.assertEqual(failed["status"], STATUS_FAILED)
        self.assertEqual(failed["startup_status"], STARTUP_STATUS_FAILED)
        self.assertEqual(failed["failure_phase"], FAILURE_PHASE_STARTUP)
        self.assertEqual(failed["shutdown_status"], "not_requested")

    def test_shutdown_request_and_failure_are_explicit(self) -> None:
        runtime = start_supervisor_runtime(self.db_path)
        mark_supervisor_runtime_live(self.db_path, runtime["runtime_instance_id"])
        requested = request_supervisor_shutdown(self.db_path, runtime["runtime_instance_id"])
        self.assertEqual(requested["shutdown_status"], SHUTDOWN_STATUS_REQUESTED)
        self.assertIsNotNone(requested["shutdown_requested_at"])

        failed = fail_supervisor_runtime(
            self.db_path,
            runtime["runtime_instance_id"],
            failure_code="shutdown_failure",
            failure_summary="shutdown failed",
            failure_phase=FAILURE_PHASE_SHUTDOWN,
        )
        self.assertEqual(failed["status"], STATUS_FAILED)
        self.assertEqual(failed["shutdown_status"], SHUTDOWN_STATUS_FAILED)
        self.assertEqual(failed["failure_phase"], FAILURE_PHASE_SHUTDOWN)

    def test_run_supervisor_runtime_records_shutdown_request_before_stop(self) -> None:
        result = run_supervisor_runtime(
            self.db_path,
            heartbeat_count=1,
            heartbeat_interval_seconds=0.0,
            stale_after_seconds=60,
        )
        shutdown_requested = result["shutdown_requested_runtime"]
        self.assertEqual(shutdown_requested["shutdown_status"], SHUTDOWN_STATUS_REQUESTED)
        self.assertEqual(result["runtime"]["shutdown_status"], SHUTDOWN_STATUS_COMPLETED)

        status = get_supervisor_runtime_status(self.db_path)
        history = status["runtime_transition_history"]
        self.assertGreaterEqual(len(history), 5)
        self.assertEqual(
            [entry["event_type"] for entry in history[-3:]],
            [
                "ace.supervisor.heartbeat",
                "ace.supervisor.shutdown_requested",
                "ace.supervisor.stopped",
            ],
        )

    def test_illegal_live_transition_after_stop_fails_loudly(self) -> None:
        runtime = start_supervisor_runtime(self.db_path)
        mark_supervisor_runtime_live(self.db_path, runtime["runtime_instance_id"])
        stop_supervisor_runtime(self.db_path, runtime["runtime_instance_id"])

        with self.assertRaises(ValidationError):
            heartbeat_supervisor_runtime(self.db_path, runtime["runtime_instance_id"])

    def test_shutdown_request_requires_live_or_stale_runtime(self) -> None:
        runtime = start_supervisor_runtime(self.db_path)
        with self.assertRaises(ValidationError):
            request_supervisor_shutdown(self.db_path, runtime["runtime_instance_id"])

    def test_failed_runtime_can_record_recovery_request_and_completion(self) -> None:
        runtime = start_supervisor_runtime(self.db_path)
        mark_supervisor_runtime_live(self.db_path, runtime["runtime_instance_id"])
        failed = fail_supervisor_runtime(
            self.db_path,
            runtime["runtime_instance_id"],
            failure_code="runtime_failure",
            failure_summary="runtime failed",
        )
        self.assertEqual(failed["recovery_status"], "not_requested")

        requested = request_supervisor_recovery(self.db_path, runtime["runtime_instance_id"])
        self.assertEqual(requested["recovery_status"], RECOVERY_STATUS_REQUESTED)
        self.assertEqual(requested["recovery_attempt_count"], 1)
        self.assertIsNotNone(requested["recovery_last_requested_at"])

        completed = complete_supervisor_recovery(
            self.db_path,
            runtime["runtime_instance_id"],
            result_summary="restart succeeded",
        )
        self.assertEqual(completed["recovery_status"], RECOVERY_STATUS_COMPLETED)
        self.assertEqual(completed["recovery_last_result"], "restart succeeded")
        self.assertIsNotNone(completed["recovery_last_completed_at"])

        status = get_supervisor_runtime_status(self.db_path)
        history = [entry["event_type"] for entry in status["runtime_transition_history"]]
        self.assertIn("ace.supervisor.recovery_requested", history)
        self.assertIn("ace.supervisor.recovery_completed", history)

    def test_failed_runtime_can_record_recovery_failure(self) -> None:
        runtime = start_supervisor_runtime(self.db_path)
        mark_supervisor_runtime_live(self.db_path, runtime["runtime_instance_id"])
        fail_supervisor_runtime(
            self.db_path,
            runtime["runtime_instance_id"],
            failure_code="runtime_failure",
            failure_summary="runtime failed",
        )
        request_supervisor_recovery(self.db_path, runtime["runtime_instance_id"])
        failed_recovery = fail_supervisor_recovery(
            self.db_path,
            runtime["runtime_instance_id"],
            result_summary="restart failed",
        )
        self.assertEqual(failed_recovery["recovery_status"], RECOVERY_STATUS_FAILED)
        self.assertEqual(failed_recovery["recovery_last_result"], "restart failed")
        status = get_supervisor_runtime_status(self.db_path)
        history = [entry["event_type"] for entry in status["runtime_transition_history"]]
        self.assertIn("ace.supervisor.recovery_failed", history)

    def test_recovery_request_requires_failed_runtime(self) -> None:
        runtime = start_supervisor_runtime(self.db_path)
        with self.assertRaises(ValidationError):
            request_supervisor_recovery(self.db_path, runtime["runtime_instance_id"])

    def test_status_history_uses_terminal_runtime_when_no_active_runtime_exists(self) -> None:
        result = run_supervisor_runtime(
            self.db_path,
            heartbeat_count=0,
            heartbeat_interval_seconds=0.0,
            stale_after_seconds=60,
        )
        status = get_supervisor_runtime_status(self.db_path)
        self.assertIsNone(status["current_runtime"])
        self.assertIsNotNone(status["last_terminal_runtime"])
        self.assertEqual(status["last_terminal_runtime"]["runtime_instance_id"], result["runtime"]["runtime_instance_id"])
        self.assertGreaterEqual(len(status["runtime_transition_history"]), 4)
        self.assertEqual(status["runtime_transition_history"][0]["event_type"], "ace.supervisor.started")
        self.assertEqual(status["runtime_transition_history"][-1]["event_type"], "ace.supervisor.stopped")

    def test_start_reconciles_stale_runtime_with_requested_shutdown_before_duplicate_start(self) -> None:
        runtime = start_supervisor_runtime(self.db_path, runtime_family=RUNTIME_FAMILY_SINGLE_TENANT)
        mark_supervisor_runtime_live(self.db_path, runtime["runtime_instance_id"])
        request_supervisor_shutdown(self.db_path, runtime["runtime_instance_id"])

        with connect(self.db_path) as connection:
            connection.execute(
                "UPDATE runtime_instances SET status = ?, updated_at = ? WHERE runtime_instance_id = ?",
                (STATUS_STALE, "2026-05-07T06:59:38.749701Z", runtime["runtime_instance_id"]),
            )
            connection.commit()

        restarted = start_supervisor_runtime(self.db_path, runtime_family=RUNTIME_FAMILY_SINGLE_TENANT)
        self.assertTrue(restarted["created"])
        self.assertFalse(restarted["duplicate_start"])
        self.assertNotEqual(restarted["runtime_instance_id"], runtime["runtime_instance_id"])

        status = get_supervisor_runtime_status(self.db_path)
        self.assertIsNotNone(status["current_runtime"])
        self.assertEqual(status["current_runtime"]["runtime_instance_id"], restarted["runtime_instance_id"])
        self.assertIsNotNone(status["last_terminal_runtime"])
        self.assertEqual(status["last_terminal_runtime"]["runtime_instance_id"], runtime["runtime_instance_id"])
        self.assertEqual(status["last_terminal_runtime"]["status"], STATUS_STOPPED)
        self.assertEqual(status["last_terminal_runtime"]["shutdown_status"], SHUTDOWN_STATUS_COMPLETED)

    def test_start_reconciles_stale_runtime_without_shutdown_request_before_duplicate_start(self) -> None:
        runtime = start_supervisor_runtime(self.db_path, runtime_family=RUNTIME_FAMILY_SINGLE_TENANT)
        mark_supervisor_runtime_live(self.db_path, runtime["runtime_instance_id"])

        with connect(self.db_path) as connection:
            connection.execute(
                "UPDATE runtime_instances SET status = ?, updated_at = ? WHERE runtime_instance_id = ?",
                (STATUS_STALE, "2026-05-07T07:00:00Z", runtime["runtime_instance_id"]),
            )
            connection.commit()

        restarted = start_supervisor_runtime(self.db_path, runtime_family=RUNTIME_FAMILY_SINGLE_TENANT)
        self.assertTrue(restarted["created"])
        self.assertFalse(restarted["duplicate_start"])
        self.assertNotEqual(restarted["runtime_instance_id"], runtime["runtime_instance_id"])

        status = get_supervisor_runtime_status(self.db_path)
        self.assertIsNotNone(status["current_runtime"])
        self.assertEqual(status["current_runtime"]["runtime_instance_id"], restarted["runtime_instance_id"])
        self.assertIsNotNone(status["last_terminal_runtime"])
        self.assertEqual(status["last_terminal_runtime"]["runtime_instance_id"], runtime["runtime_instance_id"])
        self.assertEqual(status["last_terminal_runtime"]["status"], STATUS_FAILED)
        self.assertEqual(status["last_terminal_runtime"]["failure_code"], "supervisor_stale_runtime_reconciled")

    def test_start_reconciles_live_runtime_with_dead_process_before_duplicate_start(self) -> None:
        runtime = start_supervisor_runtime(
            self.db_path,
            runtime_family=RUNTIME_FAMILY_SINGLE_TENANT,
            host_identity="mac-hq",
            metadata={"process_pid": 999999},
        )
        live = mark_supervisor_runtime_live(self.db_path, runtime["runtime_instance_id"])
        self.assertEqual(live["status"], STATUS_LIVE)

        restarted = start_supervisor_runtime(
            self.db_path,
            runtime_family=RUNTIME_FAMILY_SINGLE_TENANT,
            host_identity="mac-hq",
        )
        self.assertTrue(restarted["created"])
        self.assertFalse(restarted["duplicate_start"])
        self.assertNotEqual(restarted["runtime_instance_id"], runtime["runtime_instance_id"])

        status = get_supervisor_runtime_status(self.db_path)
        self.assertIsNotNone(status["current_runtime"])
        self.assertEqual(status["current_runtime"]["runtime_instance_id"], restarted["runtime_instance_id"])
        self.assertIsNotNone(status["last_terminal_runtime"])
        self.assertEqual(status["last_terminal_runtime"]["runtime_instance_id"], runtime["runtime_instance_id"])
        self.assertEqual(status["last_terminal_runtime"]["status"], STATUS_FAILED)
        self.assertEqual(status["last_terminal_runtime"]["failure_code"], "supervisor_process_missing")


if __name__ == "__main__":
    unittest.main()
