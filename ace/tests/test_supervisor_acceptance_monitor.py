from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from ace.storage import bootstrap_db
from ace.supervisor_acceptance_monitor import (
    AcceptanceMonitorError,
    build_acceptance_err_line,
    build_acceptance_log_line,
    parse_launchd_snapshot,
    run_supervisor_acceptance_monitor,
)


class SupervisorAcceptanceMonitorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.tmp = Path(self.tempdir.name)
        self.db_path = self.tmp / "ace.db"
        bootstrap_db(self.db_path)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_parse_launchd_snapshot_extracts_state_pid_and_runs(self) -> None:
        parsed = parse_launchd_snapshot("active count = 1\nstate = running\nruns = 2\npid = 78780\n")
        self.assertEqual(parsed, {"pid": "78780", "state": "running", "runs": "2"})

    def test_build_log_line_renders_runtime_truth(self) -> None:
        line = build_acceptance_log_line(
            timestamp="2026-05-07T08:13:01Z",
            iteration=0,
            launchd_rc=0,
            launchd_snapshot={"pid": "78780", "state": "running", "runs": "2"},
            status_rc=0,
            status={
                "current_runtime": {
                    "runtime_instance_id": "runtime_123",
                    "status": "live",
                    "started_at": "2026-05-07T07:36:07.325609Z",
                    "last_seen_at": "2026-05-07T08:12:57.522644Z",
                    "shutdown_status": "not_requested",
                },
                "runtime_transition_history": [{"event_type": "a"}, {"event_type": "b"}],
            },
        )
        self.assertIn("launchd_rc=0", line)
        self.assertIn("runtime_id=runtime_123", line)
        self.assertIn("history_count=2", line)

    def test_build_err_line_includes_return_codes(self) -> None:
        line = build_acceptance_err_line(
            timestamp="2026-05-07T08:13:01Z",
            iteration=0,
            launchd_rc=0,
            status_rc=1,
        )
        self.assertEqual(line, "2026-05-07T08:13:01Z iter=0 launchd_rc=0 status_rc=1")

    def test_monitor_appends_and_writes_pidfile(self) -> None:
        log_path = self.tmp / "acceptance.log"
        err_path = self.tmp / "acceptance.err"
        pid_path = self.tmp / "acceptance.pid"
        log_path.write_text("seed\n", encoding="utf-8")

        timestamps = iter(["2026-05-07T08:13:01Z", "2026-05-07T08:13:02Z", "2026-05-07T08:13:03Z"])

        code = run_supervisor_acceptance_monitor(
            self.db_path,
            service_target="gui/501/ai.superace.supervisor",
            log_path=log_path,
            err_path=err_path,
            pid_path=pid_path,
            iterations=1,
            sleep_seconds=0,
            append=True,
            launchd_collector=lambda _: (0, "state = running\nruns = 2\npid = 78780\n"),
            status_collector=lambda _: {
                "current_runtime": {
                    "runtime_instance_id": "runtime_123",
                    "status": "live",
                    "started_at": "2026-05-07T07:36:07.325609Z",
                    "last_seen_at": "2026-05-07T08:12:57.522644Z",
                    "shutdown_status": "not_requested",
                },
                "runtime_transition_history": [{"event_type": "a"}],
            },
            sleep_fn=lambda _: None,
            now_fn=lambda: next(timestamps),
        )

        self.assertEqual(code, 0)
        lines = log_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[0], "seed")
        self.assertIn("runtime_id=runtime_123", lines[1])
        err_text = err_path.read_text(encoding="utf-8")
        self.assertIn("MONITOR_START 2026-05-07T08:13:01Z", err_text)
        self.assertIn("MONITOR_DONE 2026-05-07T08:13:03Z", err_text)
        self.assertFalse(pid_path.exists())

    def test_monitor_can_truncate_when_requested(self) -> None:
        log_path = self.tmp / "acceptance.log"
        err_path = self.tmp / "acceptance.err"
        pid_path = self.tmp / "acceptance.pid"
        log_path.write_text("stale\n", encoding="utf-8")

        timestamps = iter(["2026-05-07T08:13:01Z", "2026-05-07T08:13:02Z", "2026-05-07T08:13:03Z"])

        run_supervisor_acceptance_monitor(
            self.db_path,
            service_target="gui/501/ai.superace.supervisor",
            log_path=log_path,
            err_path=err_path,
            pid_path=pid_path,
            iterations=1,
            sleep_seconds=0,
            append=False,
            launchd_collector=lambda _: (0, "state = running\nruns = 2\npid = 78780\n"),
            status_collector=lambda _: {"current_runtime": None, "runtime_transition_history": []},
            sleep_fn=lambda _: None,
            now_fn=lambda: next(timestamps),
        )

        lines = log_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        self.assertIn("current_present=false", lines[0])

        err_lines = err_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(err_lines), 3)
        self.assertTrue(err_lines[0].startswith("MONITOR_START 2026-05-07T08:13:01Z"))
        self.assertIn("iter=0 launchd_rc=0 status_rc=0", err_lines[1])
        self.assertTrue(err_lines[2].startswith("MONITOR_DONE 2026-05-07T08:13:03Z"))

    def test_monitor_rejects_invalid_iterations(self) -> None:
        with self.assertRaises(AcceptanceMonitorError):
            run_supervisor_acceptance_monitor(
                self.db_path,
                service_target="gui/501/ai.superace.supervisor",
                log_path=self.tmp / "acceptance.log",
                err_path=self.tmp / "acceptance.err",
                pid_path=self.tmp / "acceptance.pid",
                iterations=0,
            )

    def test_monitor_refuses_second_live_pidfile_owner(self) -> None:
        pid_path = self.tmp / "acceptance.pid"
        pid_path.write_text(f"{os.getpid()}\n", encoding="utf-8")
        with self.assertRaises(AcceptanceMonitorError):
            run_supervisor_acceptance_monitor(
                self.db_path,
                service_target="gui/501/ai.superace.supervisor",
                log_path=self.tmp / "acceptance.log",
                err_path=self.tmp / "acceptance.err",
                pid_path=pid_path,
                iterations=1,
                sleep_seconds=0,
            )


if __name__ == "__main__":
    unittest.main()
