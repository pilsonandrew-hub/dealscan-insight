from __future__ import annotations

import io
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from ace.ace import main
from ace.supervisor_runtime import mark_supervisor_runtime_live, start_supervisor_runtime
from ace.storage import bootstrap_db, connect


class SupervisorCliTests(unittest.TestCase):
    def run_cli(self, *argv: str) -> tuple[int, str]:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main(list(argv))
        return code, buffer.getvalue()

    def test_supervisor_run_creates_distinct_runtime_and_stops_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "ace.db"
            code, output = self.run_cli(
                "--db",
                str(db_path),
                "supervisor-run",
                "--heartbeat-count",
                "1",
                "--heartbeat-interval-seconds",
                "0",
                "--host-identity",
                "hq-mac",
            )

            self.assertEqual(code, 0, output)
            self.assertIn("runtime_instance_id=runtime_", output)
            self.assertIn("runtime_status=stopped", output)
            self.assertIn("duplicate_start=false", output)
            self.assertIn("auto_stopped=true", output)

            with connect(db_path) as connection:
                runtime_count = connection.execute("SELECT COUNT(*) FROM runtime_instances").fetchone()[0]
                governed_count = connection.execute("SELECT COUNT(*) FROM governed_runs").fetchone()[0]
            self.assertEqual(runtime_count, 1)
            self.assertEqual(governed_count, 0)

    def test_supervisor_status_reports_live_runtime_independent_from_cycle_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "ace.db"
            bootstrap_db(db_path)
            runtime = start_supervisor_runtime(db_path, stale_after_seconds=60)
            mark_supervisor_runtime_live(db_path, runtime["runtime_instance_id"])

            code, output = self.run_cli("--db", str(db_path), "supervisor-status")
            self.assertEqual(code, 0, output)
            self.assertIn("inspection_family=resident_supervisor_runtime", output)
            self.assertIn("inspection_scope=bounded_resident_supervisor_seam", output)
            self.assertIn("bounded_runtime_claims.0=distinct_resident_runtime_ledger", output)
            self.assertIn("anti_inflation_non_claims.0=not_v1", output)
            self.assertIn("anti_inflation_non_claims.2=not_platform_or_runtime_fabric", output)
            self.assertIn("minimal_slice_definition.0=launchagent_scheduled_real_ace_cycle", output)
            self.assertIn("evidence_artifact_bundle.4=reports/ace-e5-anti-inflation-boundary-proof-verdict-2026-05-07.md", output)
            self.assertIn("non_reduction_proof.3=inspection_surface_exposes_transition_recovery_history_and_non_claims_beyond_bounded_ace_cycle", output)
            self.assertIn("current_runtime_present=true", output)
            self.assertIn("current_runtime.status=live", output)
            self.assertIn("current_runtime.startup_status=completed", output)
            self.assertIn("current_runtime.shutdown_status=not_requested", output)
            self.assertIn("runtime_transition_history_count=2", output)
            self.assertIn("runtime_transition_history.0.event_type=ace.supervisor.started", output)
            self.assertIn("runtime_transition_history.1.event_type=ace.supervisor.live", output)

            code, cycle_output = self.run_cli("--db", str(db_path), "cycle-status")
            self.assertEqual(code, 0, cycle_output)
            self.assertIn("current_run_present=false", cycle_output)
            self.assertIn("last_terminal_run_present=false", cycle_output)


    def test_supervisor_status_reports_terminal_startup_shutdown_truth(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "ace.db"
            code, run_output = self.run_cli(
                "--db",
                str(db_path),
                "supervisor-run",
                "--heartbeat-count",
                "0",
                "--heartbeat-interval-seconds",
                "0",
            )
            self.assertEqual(code, 0, run_output)

            code, output = self.run_cli("--db", str(db_path), "supervisor-status")
            self.assertEqual(code, 0, output)
            self.assertIn("last_terminal_runtime_present=true", output)
            self.assertIn("last_terminal_runtime.startup_status=completed", output)
            self.assertIn("last_terminal_runtime.shutdown_status=completed", output)
            self.assertIn("last_terminal_runtime.shutdown_requested_at=", output)
            self.assertIn("last_terminal_runtime.shutdown_completed_at=", output)
            self.assertIn("runtime_transition_history_count=4", output)
            self.assertIn("runtime_transition_history.0.event_type=ace.supervisor.started", output)
            self.assertIn("runtime_transition_history.3.event_type=ace.supervisor.stopped", output)

    def test_supervisor_run_can_hold_until_explicit_shutdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "ace.db"
            result_holder: dict[str, tuple[int, str]] = {}

            def _target() -> None:
                result_holder["result"] = self.run_cli(
                    "--db",
                    str(db_path),
                    "supervisor-run",
                    "--run-until-shutdown",
                    "--heartbeat-interval-seconds",
                    "0.01",
                )

            thread = threading.Thread(target=_target)
            thread.start()

            runtime_instance_id = None
            deadline = time.time() + 5
            while time.time() < deadline:
                code, status_output = self.run_cli("--db", str(db_path), "supervisor-status")
                if code == 0 and "current_runtime_present=true" in status_output:
                    for line in status_output.splitlines():
                        if line.startswith("current_runtime.runtime_instance_id="):
                            runtime_instance_id = line.split("=", 1)[1]
                            break
                    if runtime_instance_id is not None:
                        break
                time.sleep(0.01)

            self.assertIsNotNone(runtime_instance_id)

            from ace.supervisor_runtime import request_supervisor_shutdown

            request_supervisor_shutdown(db_path, runtime_instance_id)
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())

            code, output = result_holder["result"]
            self.assertEqual(code, 0, output)
            self.assertIn("auto_stopped=false", output)
            self.assertIn("runtime_status=stopped", output)

    def test_supervisor_status_reports_recovery_history_for_failed_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "ace.db"
            bootstrap_db(db_path)
            runtime = start_supervisor_runtime(db_path, stale_after_seconds=60)
            mark_supervisor_runtime_live(db_path, runtime["runtime_instance_id"])
            from ace.supervisor_runtime import fail_supervisor_runtime, request_supervisor_recovery, complete_supervisor_recovery
            fail_supervisor_runtime(
                db_path,
                runtime["runtime_instance_id"],
                failure_code="runtime_failure",
                failure_summary="runtime failed",
            )
            request_supervisor_recovery(db_path, runtime["runtime_instance_id"])
            complete_supervisor_recovery(db_path, runtime["runtime_instance_id"], result_summary="restart succeeded")

            code, output = self.run_cli("--db", str(db_path), "supervisor-status")
            self.assertEqual(code, 0, output)
            self.assertIn("last_terminal_runtime.recovery_status=completed", output)
            self.assertIn("last_terminal_runtime.recovery_attempt_count=1", output)
            self.assertIn("runtime_transition_history_count=5", output)
            self.assertIn("runtime_transition_history.3.event_type=ace.supervisor.recovery_requested", output)
            self.assertIn("runtime_transition_history.4.event_type=ace.supervisor.recovery_completed", output)


if __name__ == "__main__":
    unittest.main()
