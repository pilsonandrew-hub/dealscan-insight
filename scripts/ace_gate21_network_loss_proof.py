#!/usr/bin/env python3
"""Gate 2.1 ACE resilience proof: network-loss + reconnect.

By default this is a non-destructive validation gate: it does not toggle Wi-Fi,
but it proves the harness configuration, captures live ACE state, runs a
post-recovery cycle, verifies audit integrity, and runs the full ACE suite with
an explicit timeout budget recorded in the JSON artifact.

To run the disruptive Wi-Fi proof, set ACE_GATE21_TOGGLE_WIFI=1. The Wi-Fi toggle
path always attempts to restore Wi-Fi in a finally block.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "ace/state/ace.db"
DEVICE = os.environ.get("ACE_GATE21_WIFI_DEVICE", "en0")
DEFAULT_FULL_SUITE_TIMEOUT_SECONDS = 900
FULL_SUITE_TIMEOUT_SECONDS = int(
    os.environ.get("ACE_GATE21_FULL_SUITE_TIMEOUT_SECONDS", str(DEFAULT_FULL_SUITE_TIMEOUT_SECONDS))
)
TOGGLE_WIFI = os.environ.get("ACE_GATE21_TOGGLE_WIFI", "0") == "1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sh(cmd: list[str], *, timeout: int = 120) -> dict[str, Any]:
    started = utc_now()
    try:
        p = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=timeout)
        return {
            "cmd": cmd,
            "started_at": started,
            "finished_at": utc_now(),
            "timeout_seconds": timeout,
            "timed_out": False,
            "returncode": p.returncode,
            "stdout": p.stdout[-8000:],
            "stderr": p.stderr[-8000:],
        }
    except subprocess.TimeoutExpired as e:
        return {
            "cmd": cmd,
            "started_at": started,
            "finished_at": utc_now(),
            "timeout_seconds": timeout,
            "timed_out": True,
            "returncode": None,
            "stdout": (e.stdout or "")[-8000:] if isinstance(e.stdout, str) else "",
            "stderr": (e.stderr or "")[-8000:] if isinstance(e.stderr, str) else f"TimeoutExpired: {e}",
        }
    except Exception as e:  # noqa: BLE001
        return {
            "cmd": cmd,
            "started_at": started,
            "finished_at": utc_now(),
            "timeout_seconds": timeout,
            "timed_out": False,
            "returncode": None,
            "stdout": "",
            "stderr": f"{type(e).__name__}: {e}",
        }


def rows(sql: str, args: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(sql, args)]
    finally:
        con.close()


def scalar(sql: str, args: tuple[Any, ...] = ()) -> Any:
    r = rows(sql, args)
    if not r:
        return None
    return next(iter(r[0].values()))


def capture_state(label: str) -> dict[str, Any]:
    return {
        "label": label,
        "captured_at": utc_now(),
        "wifi_power": sh(["networksetup", "-getairportpower", DEVICE], timeout=20),
        "live_runtime": rows(
            "select runtime_instance_id,status,last_seen_at,started_at,ended_at,metadata_json "
            "from runtime_instances where status='live' order by started_at desc limit 5"
        ),
        "latest_runtime": rows(
            "select runtime_instance_id,status,last_seen_at,started_at,ended_at,failure_code,failure_summary,metadata_json "
            "from runtime_instances order by started_at desc limit 5"
        ),
        "active_governed_runs": rows(
            "select run_id,status,trigger_kind,started_at,created_at,failure_code,failure_summary "
            "from governed_runs where status in ('starting','running') order by created_at desc"
        ),
        "item_count": scalar("select count(*) from items"),
        "event_count": scalar("select count(*) from events"),
        "event_hash_head": rows(
            "select event_id,event_hash,created_at,event_type from events order by id desc limit 1"
        ),
    }


def check_audit_ok(result: dict[str, Any]) -> bool:
    text = (result.get("stdout") or "") + "\n" + (result.get("stderr") or "")
    required = [
        "audit.verify.event_hash_chain=ok",
        "audit.verify.evidence_consistency=ok",
        "audit.verify.governed_run_integrity=ok",
        "audit.verify.runtime_instance_integrity=ok",
    ]
    return result.get("returncode") == 0 and all(x in text for x in required)


def run_network_step(artifact: dict[str, Any], *, toggle_wifi: bool) -> None:
    artifact["network_step"] = {
        "mode": "wifi_toggle" if toggle_wifi else "non_destructive_validation",
        "wifi_toggle_enabled_by_env": toggle_wifi,
        "wifi_device": DEVICE,
        "description": (
            "Wi-Fi was toggled off/on for the disruptive proof."
            if toggle_wifi
            else "Wi-Fi was not toggled; this run validates the corrected harness without disrupting network."
        ),
    }
    if not toggle_wifi:
        artifact["post_network_state"] = capture_state("post_network_non_destructive")
        return

    wifi_was_on = "On" in (sh(["networksetup", "-getairportpower", DEVICE], timeout=20).get("stdout") or "")
    try:
        artifact["commands"]["wifi_off"] = sh(["networksetup", "-setairportpower", DEVICE, "off"], timeout=30)
        time.sleep(30)
    finally:
        artifact["commands"]["wifi_on"] = sh(["networksetup", "-setairportpower", DEVICE, "on"], timeout=30)
        if wifi_was_on:
            time.sleep(3)
            artifact["commands"]["wifi_on_confirm"] = sh(["networksetup", "-setairportpower", DEVICE, "on"], timeout=30)
    time.sleep(30)
    artifact["post_network_state"] = capture_state("post_network")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run ACE Gate 2.1 network-loss/reconnect proof harness.")
    parser.add_argument(
        "--toggle-wifi",
        action="store_true",
        help="Actually toggle Wi-Fi off/on. Also enabled by ACE_GATE21_TOGGLE_WIFI=1.",
    )
    parser.add_argument(
        "--artifact-path",
        help="Optional JSON artifact path. Defaults to /tmp/ace-resilience-network-loss-<timestamp>.json.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    artifact_path = Path(args.artifact_path or f"/tmp/ace-resilience-network-loss-{ts}.json")
    toggle_wifi = bool(args.toggle_wifi or TOGGLE_WIFI)
    artifact: dict[str, Any] = {
        "gate": "2.1-network-loss-reconnect",
        "started_at": utc_now(),
        "artifact_path": str(artifact_path),
        "wifi_device": DEVICE,
        "full_suite_timeout_seconds": FULL_SUITE_TIMEOUT_SECONDS,
        "full_suite_timeout_source": (
            "env:ACE_GATE21_FULL_SUITE_TIMEOUT_SECONDS"
            if "ACE_GATE21_FULL_SUITE_TIMEOUT_SECONDS" in os.environ
            else f"default:{DEFAULT_FULL_SUITE_TIMEOUT_SECONDS}"
        ),
        "commands": {},
        "checks": {},
    }

    artifact["pre_state"] = capture_state("pre")
    run_network_step(artifact, toggle_wifi=toggle_wifi)

    artifact["commands"]["post_recovery_cycle"] = sh([
        sys.executable,
        "-m",
        "ace.ace",
        "cycle",
        "--disable-notifications",
        "--actor",
        "gate2.1-network-loss-proof",
    ], timeout=180)
    artifact["post_cycle_state"] = capture_state("post_cycle")
    artifact["commands"]["audit_verify"] = sh([sys.executable, "-m", "ace.ace", "audit", "verify"], timeout=120)
    artifact["commands"]["full_suite"] = sh(
        [sys.executable, "-m", "unittest", "discover", "ace/tests"],
        timeout=FULL_SUITE_TIMEOUT_SECONDS,
    )
    artifact["final_state"] = capture_state("final")

    pre = artifact["pre_state"]
    final = artifact["final_state"]
    pre_live_ids = {r["runtime_instance_id"] for r in pre["live_runtime"]}
    final_live_ids = {r["runtime_instance_id"] for r in final["live_runtime"]}
    full_suite = artifact["commands"]["full_suite"]

    artifact["checks"]["supervisor_still_live"] = {
        "status": "PASS" if final_live_ids else "FAIL",
        "pre_live_runtime_ids": sorted(pre_live_ids),
        "final_live_runtime_ids": sorted(final_live_ids),
        "same_runtime_survived": bool(pre_live_ids & final_live_ids),
    }
    artifact["checks"]["hash_chain_intact"] = {
        "status": "PASS" if check_audit_ok(artifact["commands"]["audit_verify"]) else "FAIL",
        "audit_returncode": artifact["commands"]["audit_verify"].get("returncode"),
    }
    artifact["checks"]["no_duplicate_cycles"] = {
        "status": "PASS" if len(final["active_governed_runs"]) <= 1 else "FAIL",
        "active_governed_runs": final["active_governed_runs"],
    }
    artifact["checks"]["no_corrupted_state"] = {
        "status": "PASS" if final["item_count"] >= pre["item_count"] and final["event_count"] >= pre["event_count"] else "FAIL",
        "pre_item_count": pre["item_count"],
        "final_item_count": final["item_count"],
        "pre_event_count": pre["event_count"],
        "final_event_count": final["event_count"],
    }
    artifact["checks"]["post_recovery_cycle_completes"] = {
        "status": "PASS" if artifact["commands"]["post_recovery_cycle"].get("returncode") == 0 else "FAIL",
        "returncode": artifact["commands"]["post_recovery_cycle"].get("returncode"),
    }
    artifact["checks"]["full_suite_green"] = {
        "status": "PASS" if full_suite.get("returncode") == 0 and not full_suite.get("timed_out") and "OK" in (full_suite.get("stderr", "") + full_suite.get("stdout", "")) else "FAIL",
        "returncode": full_suite.get("returncode"),
        "timed_out": full_suite.get("timed_out"),
        "timeout_seconds": full_suite.get("timeout_seconds"),
    }
    artifact["overall_result"] = "PASS" if all(c.get("status") == "PASS" for c in artifact["checks"].values()) else "FAIL"
    artifact["finished_at"] = utc_now()

    artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({
        "overall_result": artifact["overall_result"],
        "artifact_path": str(artifact_path),
        "network_step": artifact["network_step"],
        "full_suite_timeout_seconds": FULL_SUITE_TIMEOUT_SECONDS,
        "checks": artifact["checks"],
    }, indent=2, sort_keys=True))
    return 0 if artifact["overall_result"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
