#!/usr/bin/env python3
"""Bounded ACE Item 3 sleep/wake proof runner.

One run, six checks, evidence artifact under /tmp.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACE_DB = ROOT / "ace" / "state" / "ace.db"
ARTIFACT = Path("/tmp") / f"ace-item3-sleep-wake-proof-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
VALID_ITEM_STATES = {
    "TRIAGE",
    "ACTIVE",
    "WAITING",
    "DONE",
    "VERIFIED_DONE",
    "CLOSED",
    "FAILED",
}
TERMINAL_ITEM_STATES = {"DONE", "VERIFIED_DONE", "CLOSED", "FAILED"}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run(cmd: list[str] | str, *, timeout: int = 120, check: bool = False) -> dict:
    started = now_utc()
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=isinstance(cmd, str),
        timeout=timeout,
    )
    ended = now_utc()
    result = {
        "cmd": cmd,
        "started_at": started,
        "ended_at": ended,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }
    if check and proc.returncode != 0:
        raise RuntimeError(json.dumps(result, indent=2))
    return result


def one(sql: str, params: tuple = ()): 
    with sqlite3.connect(ACE_DB) as con:
        con.row_factory = sqlite3.Row
        row = con.execute(sql, params).fetchone()
        if row is None:
            return None
        return dict(row)


def all_rows(sql: str, params: tuple = ()):
    with sqlite3.connect(ACE_DB) as con:
        con.row_factory = sqlite3.Row
        return [dict(r) for r in con.execute(sql, params).fetchall()]


def snapshot(label: str) -> dict:
    runtime = one("select * from runtime_instances order by updated_at desc limit 1")
    hash_head = one("select id, event_id, event_hash, previous_event_hash, created_at from events order by id desc limit 1")
    active_runs = one("select count(*) as count from governed_runs where status='running'")
    item_count = one("select count(*) as count from items")
    invalid_states = all_rows(
        """
        select id, state, closed_at, closed_by, closed_reason, verdict, updated_at
        from items
        where state not in ('TRIAGE','ACTIVE','WAITING','DONE','VERIFIED_DONE','CLOSED','FAILED')
           or (state in ('DONE','VERIFIED_DONE','CLOSED','FAILED') and closed_at is null)
        order by updated_at desc
        limit 25
        """
    )
    running_runs = all_rows(
        "select run_id, trigger_kind, status, started_at, ended_at, failure_code from governed_runs where status='running' order by started_at"
    )
    return {
        "label": label,
        "captured_at": now_utc(),
        "runtime": runtime,
        "hash_head": hash_head,
        "governed_runs_active_count": active_runs["count"],
        "governed_runs_running": running_runs,
        "items_count": item_count["count"],
        "invalid_item_state_rows": invalid_states,
    }


def parse_iso(value: str | None):
    if not value:
        return None
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return dt.datetime.fromisoformat(value)


def main() -> int:
    record: dict = {
        "item": "ACE Item 3 sleep/wake resilience proof",
        "artifact_path": str(ARTIFACT),
        "started_at": now_utc(),
        "cwd": str(ROOT),
        "commands": {},
        "checks": {},
    }

    record["commands"]["git_pre"] = run(["git", "status", "-sb"])
    pre = snapshot("pre")
    record["pre_state"] = pre
    record["commands"]["audit_pre"] = run([sys.executable, "-m", "ace.ace", "audit", "verify"], timeout=120)

    wake_at = dt.datetime.now() + dt.timedelta(seconds=90)
    wake_str = wake_at.strftime("%m/%d/%y %H:%M:%S")
    record["sleep_trigger"] = {
        "wake_interval_minimum_seconds": 60,
        "scheduled_wake_local": wake_str,
        "sleep_command_start_at": now_utc(),
    }
    record["commands"]["pmset_schedule_wake"] = run(["pmset", "schedule", "wake", wake_str], timeout=30)
    record["commands"]["pmset_sched_after_schedule"] = run(["pmset", "-g", "sched"], timeout=30)
    record["commands"]["pmset_sleepnow"] = run(["pmset", "sleepnow"], timeout=30)
    record["sleep_trigger"]["sleep_command_returned_at"] = now_utc()
    # Post-wake stabilization requested by Andrew.
    time.sleep(30)
    record["post_wake_stabilized_at"] = now_utc()
    record["commands"]["pmset_assertions_post"] = run(["pmset", "-g", "assertions"], timeout=30)
    mid = snapshot("post_wake_pre_cycle")
    record["post_state_before_cycle"] = mid

    # Trigger one launchd cycle after wake and wait for completion.
    record["commands"]["launchd_cycle_kickstart"] = run(["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/ai.superace.cycle"], timeout=30)
    polls = []
    post_cycle_run = None
    for _ in range(80):
        status_cmd = run([sys.executable, "-m", "ace.ace", "cycle-status"], timeout=60)
        polls.append(status_cmd)
        latest = one("select * from governed_runs order by created_at desc limit 1")
        if latest:
            post_cycle_run = latest
        if latest and latest.get("status") != "running" and latest.get("created_at") >= pre["captured_at"]:
            break
        time.sleep(3)
    record["cycle_status_polls"] = polls
    record["post_wake_cycle_run"] = post_cycle_run
    post = snapshot("post_cycle")
    record["post_state_after_cycle"] = post

    record["commands"]["audit_post"] = run([sys.executable, "-m", "ace.ace", "audit", "verify"], timeout=120)
    record["commands"]["tests"] = run("PYTHONWARNINGS=error python3 -m unittest discover ace/tests -t .", timeout=240)
    record["commands"]["git_post"] = run(["git", "status", "-sb"])

    # Six checks.
    pre_runtime = pre["runtime"] or {}
    post_runtime = post["runtime"] or {}
    prior_after = one("select * from runtime_instances where runtime_instance_id=?", (pre_runtime.get("runtime_instance_id"),)) if pre_runtime.get("runtime_instance_id") else None
    prior_failed_replaced = bool(
        pre_runtime.get("runtime_instance_id")
        and post_runtime.get("runtime_instance_id") != pre_runtime.get("runtime_instance_id")
        and prior_after
        and prior_after["status"] == "failed"
        and post_runtime.get("status") in {"live", "running"}
    )
    recent_heartbeat = False
    heartbeat_advanced_after_wake = False
    pre_last_seen = parse_iso(pre_runtime.get("last_seen_at")) if pre_runtime else None
    post_last_seen = parse_iso(post_runtime.get("last_seen_at")) if post_runtime else None
    if post_last_seen:
        recent_heartbeat = (dt.datetime.now(dt.timezone.utc) - post_last_seen.astimezone(dt.timezone.utc)).total_seconds() <= 120
    if pre_last_seen and post_last_seen:
        heartbeat_advanced_after_wake = post_last_seen.astimezone(dt.timezone.utc) > pre_last_seen.astimezone(dt.timezone.utc)
    same_runtime_survived_sleep = bool(
        pre_runtime.get("runtime_instance_id")
        and post_runtime.get("runtime_instance_id") == pre_runtime.get("runtime_instance_id")
        and post_runtime.get("status") in {"live", "running"}
        and recent_heartbeat
        and heartbeat_advanced_after_wake
    )
    # Sleep-survival is continuity for this single-user personal tool; crash/kill restart
    # recovery is the separate failure mode proven by contained restart proof 021c546.
    supervisor_continuity_ok = prior_failed_replaced or same_runtime_survived_sleep
    record["checks"]["1_supervisor_restart_semantics"] = {
        "status": "PASS" if supervisor_continuity_ok else "FAIL",
        "expected": "same runtime survives sleep with advancing heartbeat, or prior failed runtime is replaced by new live runtime",
        "pre_runtime_instance_id": pre_runtime.get("runtime_instance_id"),
        "prior_runtime_after": prior_after,
        "post_runtime_instance_id": post_runtime.get("runtime_instance_id"),
        "post_runtime_status": post_runtime.get("status"),
        "pre_runtime_last_seen_at": pre_runtime.get("last_seen_at"),
        "post_runtime_last_seen_at": post_runtime.get("last_seen_at"),
        "recent_heartbeat_within_120s": recent_heartbeat,
        "heartbeat_advanced_after_wake": heartbeat_advanced_after_wake,
        "same_runtime_survived_sleep": same_runtime_survived_sleep,
        "prior_failed_replaced": prior_failed_replaced,
    }

    pre_hash = pre["hash_head"] or {}
    post_hash = post["hash_head"] or {}
    audit_ok = record["commands"]["audit_post"]["returncode"] == 0 and "event_hash_chain=ok" in record["commands"]["audit_post"]["stdout"]
    hash_not_regressed = bool(pre_hash.get("id") is not None and post_hash.get("id") is not None and post_hash["id"] >= pre_hash["id"])
    record["checks"]["2_hash_chain_integrity"] = {
        "status": "PASS" if audit_ok and hash_not_regressed else "FAIL",
        "expected": "audit verify ok and chain head same or advanced, not regressed",
        "pre_hash_head": pre_hash,
        "post_hash_head": post_hash,
        "audit_post_stdout": record["commands"]["audit_post"]["stdout"],
        "audit_post_returncode": record["commands"]["audit_post"]["returncode"],
        "hash_not_regressed": hash_not_regressed,
    }

    max_running = one("select max(cnt) as max_running from (select count(*) as cnt from governed_runs where status='running')")
    running_after = all_rows("select run_id, status, started_at from governed_runs where status='running'")
    # Since SQLite stores final state not historical sampled counts, use pre/mid/post active counts and current rows.
    sampled_counts = [pre["governed_runs_active_count"], mid["governed_runs_active_count"], post["governed_runs_active_count"]]
    record["checks"]["3_no_duplicate_cycles"] = {
        "status": "PASS" if max(sampled_counts) <= 1 and len(running_after) <= 1 else "FAIL",
        "expected": "no two governed_runs rows status=running simultaneously across sampled boundary",
        "sampled_active_counts": {"pre": sampled_counts[0], "post_wake_pre_cycle": sampled_counts[1], "post_cycle": sampled_counts[2]},
        "current_running_rows": running_after,
    }

    record["checks"]["4_no_corrupted_state"] = {
        "status": "PASS" if post["items_count"] >= pre["items_count"] and not post["invalid_item_state_rows"] else "FAIL",
        "expected": "items count monotonically non-decreasing and no invalid item state combinations",
        "pre_items_count": pre["items_count"],
        "post_items_count": post["items_count"],
        "invalid_item_state_rows": post["invalid_item_state_rows"],
    }

    cycle_ok = bool(post_cycle_run and post_cycle_run.get("status") == "completed" and post_cycle_run.get("failure_code") is None)
    record["checks"]["5_cycle_execution_post_wake"] = {
        "status": "PASS" if cycle_ok else "FAIL",
        "expected": "one post-wake launchd cycle completes with no failure_code",
        "post_wake_cycle_run": post_cycle_run,
    }

    tests_out = record["commands"]["tests"]["stdout"] + record["commands"]["tests"]["stderr"]
    record["checks"]["6_test_suite_green"] = {
        "status": "PASS" if record["commands"]["tests"]["returncode"] == 0 and "OK" in tests_out else "FAIL",
        "expected": "full ACE suite passes",
        "test_returncode": record["commands"]["tests"]["returncode"],
        "test_output_tail": "\n".join(tests_out.splitlines()[-20:]),
    }

    record["overall_result"] = "PASS" if all(c["status"] == "PASS" for c in record["checks"].values()) else "FAIL"
    record["ended_at"] = now_utc()
    ARTIFACT.write_text(json.dumps(record, indent=2, sort_keys=True))
    print(str(ARTIFACT))
    print(json.dumps({"overall_result": record["overall_result"], "checks": {k: v["status"] for k, v in record["checks"].items()}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
