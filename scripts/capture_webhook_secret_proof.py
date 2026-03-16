#!/usr/bin/env python3
"""Capture a safe webhook-secret proof artifact without storing raw secrets."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request
import socket

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.ingest.webhook_secret_posture import build_webhook_secret_posture, secret_fingerprint
from scripts.run_ingest_rollout_preflight import DEFAULT_WEBHOOK_PROOF_ARTIFACT, resolve_deploy_sha


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return values

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key:
            values[key] = value
    return values


def build_runtime_env(env_file: str | None) -> dict[str, str]:
    runtime_env: dict[str, str] = {}
    if env_file:
        runtime_env.update(parse_env_file(Path(env_file)))
    runtime_env.update(os.environ)
    return runtime_env


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def redact_body(body_text: str) -> str | None:
    body = body_text.strip()
    if not body:
        return None
    return body[:200]


def payload_summary(payload: dict[str, Any], payload_bytes: bytes) -> dict[str, Any]:
    resource = payload.get("resource") or {}
    return {
        "run_id": resource.get("id"),
        "dataset_id": resource.get("defaultDatasetId"),
        "created_at": payload.get("createdAt"),
        "sha256": hashlib.sha256(payload_bytes).hexdigest(),
    }


def post_webhook(endpoint: str, payload_bytes: bytes, secret: str, *, timeout_seconds: int) -> dict[str, Any]:
    request = urllib_request.Request(
        endpoint,
        data=payload_bytes,
        headers={
            "Content-Type": "application/json",
            "X-Apify-Webhook-Secret": secret,
        },
        method="POST",
    )
    started_at = now_iso()
    try:
        with urllib_request.urlopen(request, timeout=timeout_seconds) as response:
            body_text = response.read().decode("utf-8")
            try:
                parsed_body = json.loads(body_text) if body_text else None
            except json.JSONDecodeError:
                parsed_body = None
            return {
                "observed_at": started_at,
                "http_status": int(response.status),
                "response_body_excerpt": redact_body(body_text),
                "response_json": parsed_body,
            }
    except urllib_error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        try:
            parsed_body = json.loads(body_text) if body_text else None
        except json.JSONDecodeError:
            parsed_body = None
        return {
            "observed_at": started_at,
            "http_status": int(exc.code),
            "response_body_excerpt": redact_body(body_text),
            "response_json": parsed_body,
        }
    except (TimeoutError, socket.timeout, urllib_error.URLError) as exc:
        return {
            "observed_at": started_at,
            "http_status": 0,
            "response_body_excerpt": None,
            "response_json": None,
            "transport_error": str(exc),
        }


def check_retired_secret(
    *,
    endpoint: str,
    payload_bytes: bytes,
    retired_secret: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    result = post_webhook(endpoint, payload_bytes, retired_secret, timeout_seconds=timeout_seconds)
    status = "passed" if result["http_status"] == 401 else "failed"
    return {
        "status": status,
        "expected_http_status": 401,
        "request_secret_fingerprint": secret_fingerprint(retired_secret),
        **result,
    }


def check_current_secret_acceptance(
    *,
    endpoint: str,
    payload_bytes: bytes,
    current_secret: str,
    timeout_seconds: int,
    accepts_previous_secret: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    accepted = post_webhook(endpoint, payload_bytes, current_secret, timeout_seconds=timeout_seconds)
    accepted_json = accepted.get("response_json") or {}
    acceptance_reason = None
    if accepted["http_status"] == 200 and not bool(accepted_json.get("replay_ignored")):
        acceptance_status = "passed"
        acceptance_reason = "current_secret_processed"
    elif (
        accepted["http_status"] == 200
        and bool(accepted_json.get("replay_ignored"))
        and not accepts_previous_secret
    ):
        acceptance_status = "passed"
        acceptance_reason = "replay_ignored_implies_prior_current_secret_acceptance"
    else:
        acceptance_status = "failed"

    replay = post_webhook(endpoint, payload_bytes, current_secret, timeout_seconds=timeout_seconds)
    replay_json = replay.get("response_json") or {}
    replay_status = (
        "passed"
        if replay["http_status"] == 200 and bool(replay_json.get("replay_ignored"))
        else "failed"
    )

    base_context = {"request_secret_fingerprint": secret_fingerprint(current_secret)}
    accepted_result = {
        "status": acceptance_status,
        "expected_http_status": 200,
        **base_context,
        **accepted,
    }
    if acceptance_reason:
        accepted_result["reason"] = acceptance_reason

    return (
        accepted_result,
        {
            "status": replay_status,
            "expected_http_status": 200,
            **base_context,
            **replay,
        },
    )


def previous_secret_absent_check(posture: dict[str, Any], *, expect_previous_absent: bool) -> dict[str, Any]:
    if not expect_previous_absent:
        return {
            "status": "not_expected",
            "observed_at": now_iso(),
        }
    return {
        "status": "passed" if posture["previous"]["state"] == "absent" else "failed",
        "observed_at": now_iso(),
        "observed_previous_state": posture["previous"]["state"],
        "observed_previous_fingerprint": posture["previous"]["fingerprint"],
    }


def build_artifact(
    runtime_env: dict[str, str],
    *,
    endpoint: str | None,
    payload_path: str | None,
    expect_previous_absent: bool,
    retired_secret_env: str,
    current_secret_env: str,
    timeout_seconds: int,
) -> tuple[dict[str, Any], bool]:
    posture = build_webhook_secret_posture(
        runtime_env.get("APIFY_WEBHOOK_SECRET", ""),
        runtime_env.get("APIFY_WEBHOOK_SECRET_PREVIOUS", ""),
    )
    artifact: dict[str, Any] = {
        "artifact_version": 1,
        "generated_at": now_iso(),
        "generated_by": "scripts/capture_webhook_secret_proof.py",
        "deploy_sha": resolve_deploy_sha(runtime_env),
        "endpoint": endpoint,
        "posture": posture,
        "checks": {
            "retired_secret_rejected": {"status": "skipped"},
            "current_secret_accepted": {"status": "skipped"},
            "replay_suppressed": {"status": "skipped"},
            "previous_secret_absent": previous_secret_absent_check(
                posture, expect_previous_absent=expect_previous_absent
            ),
        },
    }

    failed = artifact["checks"]["previous_secret_absent"]["status"] == "failed"
    if not endpoint or not payload_path:
        return artifact, failed

    payload_bytes = Path(payload_path).read_bytes()
    payload = json.loads(payload_bytes.decode("utf-8"))
    artifact["request_context"] = {
        "payload_path": payload_path,
        "payload": payload_summary(payload, payload_bytes),
    }

    current_secret = (runtime_env.get(current_secret_env) or "").strip()
    if current_secret:
        current_accepted, replay_suppressed = check_current_secret_acceptance(
            endpoint=endpoint,
            payload_bytes=payload_bytes,
            current_secret=current_secret,
            timeout_seconds=timeout_seconds,
            accepts_previous_secret=bool(posture.get("accepts_previous_secret")),
        )
        artifact["checks"]["current_secret_accepted"] = current_accepted
        artifact["checks"]["replay_suppressed"] = replay_suppressed
        failed = failed or current_accepted["status"] == "failed" or replay_suppressed["status"] == "failed"
    else:
        artifact["checks"]["current_secret_accepted"] = {
            "status": "skipped",
            "reason": f"{current_secret_env} is not set",
        }
        artifact["checks"]["replay_suppressed"] = {
            "status": "skipped",
            "reason": f"{current_secret_env} is not set",
        }

    retired_secret = (runtime_env.get(retired_secret_env) or "").strip()
    if retired_secret:
        retired_secret_result = check_retired_secret(
            endpoint=endpoint,
            payload_bytes=payload_bytes,
            retired_secret=retired_secret,
            timeout_seconds=timeout_seconds,
        )
        artifact["checks"]["retired_secret_rejected"] = retired_secret_result
        failed = failed or retired_secret_result["status"] == "failed"
    else:
        artifact["checks"]["retired_secret_rejected"] = {
            "status": "skipped",
            "reason": f"{retired_secret_env} is not set",
        }

    return artifact, failed


def write_artifact(path: Path, artifact: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture safe webhook secret proof artifacts for live ingest validation."
    )
    parser.add_argument("--env-file", help="Optional env file layered under the current shell.")
    parser.add_argument(
        "--artifact-path",
        default=str(DEFAULT_WEBHOOK_PROOF_ARTIFACT),
        help="Destination JSON artifact path.",
    )
    parser.add_argument(
        "--endpoint",
        help="Webhook endpoint to probe, for example https://host/api/ingest/apify.",
    )
    parser.add_argument(
        "--payload-file",
        help="JSON payload file used for current/retired secret checks. Use a real recent payload, not a fabricated one.",
    )
    parser.add_argument(
        "--retired-secret-env",
        default="APIFY_WEBHOOK_SECRET_RETIRED",
        help="Env var holding the retired secret used for the 401 check.",
    )
    parser.add_argument(
        "--current-secret-env",
        default="APIFY_WEBHOOK_SECRET",
        help="Env var holding the active secret used for acceptance and replay checks.",
    )
    parser.add_argument(
        "--expect-previous-absent",
        action="store_true",
        help="Fail the artifact when APIFY_WEBHOOK_SECRET_PREVIOUS is still present.",
    )
    parser.add_argument(
        "--require-live-checks",
        action="store_true",
        help="Fail when endpoint/payload/secret inputs are missing or any live check is skipped.",
    )
    parser.add_argument(
        "--request-timeout-seconds",
        type=int,
        default=120,
        help="HTTP timeout for each live webhook proof request. Increase for slower real ingest runs.",
    )
    args = parser.parse_args()

    runtime_env = build_runtime_env(args.env_file)
    if args.require_live_checks and (not args.endpoint or not args.payload_file):
        print("endpoint and payload-file are required when --require-live-checks is set", file=sys.stderr)
        return 1

    artifact, failed = build_artifact(
        runtime_env,
        endpoint=args.endpoint,
        payload_path=args.payload_file,
        expect_previous_absent=args.expect_previous_absent,
        retired_secret_env=args.retired_secret_env,
        current_secret_env=args.current_secret_env,
        timeout_seconds=args.request_timeout_seconds,
    )
    write_artifact(Path(args.artifact_path), artifact)

    print(f"Webhook secret proof artifact: {args.artifact_path}")
    print(f"deploy_sha={artifact['deploy_sha']}")
    print(
        "active="
        f"{artifact['posture']['active']['state']} "
        f"{artifact['posture']['active']['fingerprint'] or 'missing'}"
    )
    print(
        "previous="
        f"{artifact['posture']['previous']['state']} "
        f"{artifact['posture']['previous']['fingerprint'] or 'none'}"
    )
    for check_name, result in artifact["checks"].items():
        print(f"{check_name}={result.get('status')}")

    if args.require_live_checks:
        for check_name in ("retired_secret_rejected", "current_secret_accepted", "replay_suppressed"):
            if artifact["checks"][check_name].get("status") == "skipped":
                failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
