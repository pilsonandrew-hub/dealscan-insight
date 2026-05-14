from __future__ import annotations

import atexit
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Union

from .storage import DB_PATH
from .supervisor_runtime import get_supervisor_runtime_status

_LAUNCHD_PID_RE = re.compile(r"\bpid = (\d+)")
_LAUNCHD_STATE_RE = re.compile(r"\bstate = ([^\n]+)")
_LAUNCHD_RUNS_RE = re.compile(r"\bruns = (\d+)")


class AcceptanceMonitorError(RuntimeError):
    pass


LaunchdCollector = Callable[[str], tuple[int, str]]
StatusCollector = Callable[[Union[Path, str]], dict[str, Any]]
SleepFn = Callable[[float], None]
NowFn = Callable[[], str]


def utc_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def default_launchd_collector(service_target: str) -> tuple[int, str]:
    completed = subprocess.run(
        ["launchctl", "print", service_target],
        capture_output=True,
        text=True,
        check=False,
    )
    combined = completed.stdout
    if completed.stderr:
        combined = f"{combined}\n{completed.stderr}" if combined else completed.stderr
    return completed.returncode, combined


def parse_launchd_snapshot(raw_output: str) -> dict[str, str]:
    pid_match = _LAUNCHD_PID_RE.search(raw_output)
    state_match = _LAUNCHD_STATE_RE.search(raw_output)
    runs_match = _LAUNCHD_RUNS_RE.search(raw_output)
    return {
        "pid": pid_match.group(1) if pid_match else "none",
        "state": state_match.group(1).strip() if state_match else "missing",
        "runs": runs_match.group(1) if runs_match else "none",
    }


def build_acceptance_log_line(
    *,
    timestamp: str,
    iteration: int,
    launchd_rc: int,
    launchd_snapshot: dict[str, str],
    status_rc: int,
    status: dict[str, Any] | None,
) -> str:
    current_runtime = status.get("current_runtime") if isinstance(status, dict) else None
    history = status.get("runtime_transition_history") if isinstance(status, dict) else None
    history_count = len(history) if isinstance(history, list) else "none"
    return (
        f"{timestamp} iter={iteration} "
        f"launchd_rc={launchd_rc} "
        f"launchd_state={launchd_snapshot.get('state', 'missing')} "
        f"pid={launchd_snapshot.get('pid', 'none')} "
        f"runs={launchd_snapshot.get('runs', 'none')} "
        f"status_rc={status_rc} "
        f"current_present={str(current_runtime is not None).lower()} "
        f"runtime_id={_runtime_field(current_runtime, 'runtime_instance_id')} "
        f"runtime_status={_runtime_field(current_runtime, 'status')} "
        f"started_at={_runtime_field(current_runtime, 'started_at')} "
        f"last_seen_at={_runtime_field(current_runtime, 'last_seen_at')} "
        f"shutdown_status={_runtime_field(current_runtime, 'shutdown_status')} "
        f"history_count={history_count}"
    )


def build_acceptance_err_line(*, timestamp: str, iteration: int, launchd_rc: int, status_rc: int) -> str:
    return f"{timestamp} iter={iteration} launchd_rc={launchd_rc} status_rc={status_rc}"


def run_supervisor_acceptance_monitor(
    db_path: Path | str = DB_PATH,
    *,
    service_target: str,
    log_path: Path | str,
    err_path: Path | str,
    pid_path: Path | str,
    iterations: int = 65,
    sleep_seconds: float = 60.0,
    append: bool = True,
    launchd_collector: LaunchdCollector = default_launchd_collector,
    status_collector: StatusCollector = get_supervisor_runtime_status,
    sleep_fn: SleepFn = time.sleep,
    now_fn: NowFn = utc_now_iso,
) -> int:
    if iterations <= 0:
        raise AcceptanceMonitorError("iterations must be > 0")
    if sleep_seconds < 0:
        raise AcceptanceMonitorError("sleep_seconds must be >= 0")

    log_file = Path(log_path)
    err_file = Path(err_path)
    pid_file = Path(pid_path)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    err_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.parent.mkdir(parents=True, exist_ok=True)

    _claim_pidfile(pid_file)
    try:
        err_mode = "a" if append else "w"
        with err_file.open(err_mode, encoding="utf-8") as err_handle:
            err_handle.write(f"MONITOR_START {now_fn()} service={service_target}\n")
            err_handle.flush()

            for iteration in range(iterations):
                timestamp = now_fn()
                launchd_rc, launchd_output = launchd_collector(service_target)
                launchd_snapshot = parse_launchd_snapshot(launchd_output)

                status_rc = 0
                status: dict[str, Any] | None = None
                try:
                    status = status_collector(db_path)
                except Exception:
                    status_rc = 1

                mode = "a" if append or iteration > 0 else "w"
                with log_file.open(mode, encoding="utf-8") as log_handle:
                    log_handle.write(
                        build_acceptance_log_line(
                            timestamp=timestamp,
                            iteration=iteration,
                            launchd_rc=launchd_rc,
                            launchd_snapshot=launchd_snapshot,
                            status_rc=status_rc,
                            status=status,
                        )
                        + "\n"
                    )
                err_handle.write(
                    build_acceptance_err_line(
                        timestamp=timestamp,
                        iteration=iteration,
                        launchd_rc=launchd_rc,
                        status_rc=status_rc,
                    )
                    + "\n"
                )
                err_handle.flush()
                if iteration < iterations - 1:
                    sleep_fn(sleep_seconds)

            err_handle.write(f"MONITOR_DONE {now_fn()} service={service_target}\n")
            err_handle.flush()
        return 0
    finally:
        _release_pidfile(pid_file)


def _runtime_field(current_runtime: Any, key: str) -> str:
    if isinstance(current_runtime, dict):
        value = current_runtime.get(key)
        if value is not None:
            return str(value)
    return "none"


def _claim_pidfile(pid_file: Path) -> None:
    if pid_file.exists():
        raw = pid_file.read_text(encoding="utf-8").strip()
        if raw:
            try:
                existing_pid = int(raw)
            except ValueError:
                existing_pid = None
            if existing_pid is not None:
                try:
                    os.kill(existing_pid, 0)
                except OSError:
                    pass
                else:
                    raise AcceptanceMonitorError(
                        f"acceptance monitor already running with pid {existing_pid}"
                    )
    pid_file.write_text(f"{os.getpid()}\n", encoding="utf-8")
    atexit.register(_release_pidfile, pid_file)


def _release_pidfile(pid_file: Path) -> None:
    try:
        if pid_file.exists():
            raw = pid_file.read_text(encoding="utf-8").strip()
            if raw == str(os.getpid()):
                pid_file.unlink()
    except OSError:
        pass
