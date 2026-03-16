#!/usr/bin/env python3
"""Run the operator preflight for tonight's ingest rollout."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import psycopg2

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from config.environment_validator import EnvironmentValidator
from backend.ingest.webhook_secret_posture import build_webhook_secret_posture
from live_verification_support import get_database_url


CHECK_RECENT_SCRIPT = REPO_ROOT / "scripts" / "check_recent_ingest_runs.py"
DEPLOYMENT_MANIFEST = REPO_ROOT / "apify" / "deployment.json"
DEFAULT_WEBHOOK_PROOF_ARTIFACT = REPO_ROOT / "runtime-artifacts" / "webhook-secret-proof.json"
REQUIRED_TABLE_COLUMNS = {
    ("public", "webhook_log"): {
        "actor_id",
        "error_message",
        "item_count",
        "processing_status",
        "raw_payload",
        "received_at",
        "run_id",
    },
    ("public", "ingest_delivery_log"): {
        "attempt_count",
        "channel",
        "created_at",
        "listing_id",
        "run_id",
        "status",
        "updated_at",
    },
    ("public", "opportunities"): {
        "is_duplicate",
        "processed_at",
        "run_id",
        "step_status",
    },
}
DEPLOY_SHA_ENV_KEYS = (
    "RAILWAY_GIT_COMMIT_SHA",
    "GITHUB_SHA",
    "SOURCE_VERSION",
    "COMMIT_SHA",
    "DEPLOY_SHA",
)


@contextmanager
def patched_environ(overrides: dict[str, str]) -> Iterator[None]:
    original = os.environ.copy()
    os.environ.clear()
    os.environ.update(overrides)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(original)


def build_runtime_env(env_file: str | None) -> dict[str, str]:
    runtime_env: dict[str, str] = {}
    if env_file:
        runtime_env.update(parse_env_file(Path(env_file)))
    runtime_env.update(os.environ)
    return runtime_env


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


def validate_environment(runtime_env: dict[str, str]) -> dict[str, object]:
    with patched_environ(runtime_env):
        return EnvironmentValidator().validate_all()


def summarize_webhook_secret_posture(runtime_env: dict[str, str]) -> dict[str, Any]:
    return build_webhook_secret_posture(
        runtime_env.get("APIFY_WEBHOOK_SECRET", ""),
        runtime_env.get("APIFY_WEBHOOK_SECRET_PREVIOUS", ""),
    )


def resolve_deploy_sha(runtime_env: dict[str, str]) -> str:
    for key in DEPLOY_SHA_ENV_KEYS:
        value = (runtime_env.get(key) or "").strip()
        if value:
            return value

    completed = subprocess.run(
        ["git", "rev-parse", "--short=12", "HEAD"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode == 0:
        return (completed.stdout or "").strip() or "unknown"
    return "unknown"


def load_webhook_proof_artifact(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


def validate_webhook_proof_artifact(
    runtime_env: dict[str, str],
    artifact_path: Path,
    *,
    expect_previous_secret_absent: bool,
) -> tuple[list[str], list[str], dict[str, Any] | None]:
    errors: list[str] = []
    notes: list[str] = []
    current_posture = summarize_webhook_secret_posture(runtime_env)
    artifact = load_webhook_proof_artifact(artifact_path)

    if artifact is None:
        errors.append(
            f"webhook secret proof artifact missing: {artifact_path}. "
            f"Capture it with scripts/capture_webhook_secret_proof.py before rollout."
        )
        return errors, notes, None

    artifact_posture = artifact.get("posture") or {}
    artifact_active = artifact_posture.get("active") or {}
    artifact_previous = artifact_posture.get("previous") or {}
    artifact_checks = artifact.get("checks") or {}
    artifact_deploy_sha = str(artifact.get("deploy_sha") or "").strip()
    current_deploy_sha = resolve_deploy_sha(runtime_env)

    if not artifact_deploy_sha:
        errors.append("webhook secret proof artifact missing deploy_sha")
    elif current_deploy_sha != "unknown" and artifact_deploy_sha != current_deploy_sha:
        errors.append(
            "webhook secret proof artifact deploy_sha does not match current repo HEAD: "
            f"{artifact_deploy_sha} != {current_deploy_sha}"
        )

    if artifact_active.get("fingerprint") != current_posture["active"]["fingerprint"]:
        errors.append(
            "webhook secret proof artifact active fingerprint does not match current runtime posture"
        )
    if artifact_active.get("state") != current_posture["active"]["state"]:
        errors.append(
            "webhook secret proof artifact active posture does not match current runtime posture"
        )
    if artifact_previous.get("fingerprint") != current_posture["previous"]["fingerprint"]:
        errors.append(
            "webhook secret proof artifact previous fingerprint does not match current runtime posture"
        )
    if artifact_previous.get("state") != current_posture["previous"]["state"]:
        errors.append(
            "webhook secret proof artifact previous posture does not match current runtime posture"
        )

    if expect_previous_secret_absent:
        previous_absent_check = artifact_checks.get("previous_secret_absent") or {}
        if current_posture["previous"]["state"] != "absent":
            errors.append("APIFY_WEBHOOK_SECRET_PREVIOUS is still configured; overlap is not over")
        if previous_absent_check.get("status") != "passed":
            errors.append(
                "webhook secret proof artifact does not record previous_secret_absent=passed"
            )
    notes.append(f"artifact: {artifact_path}")
    notes.append(f"artifact generated_at: {artifact.get('generated_at') or 'unknown'}")
    notes.append(f"artifact deploy_sha: {artifact_deploy_sha or 'unknown'}")

    for check_name in (
        "retired_secret_rejected",
        "current_secret_accepted",
        "replay_suppressed",
        "previous_secret_absent",
    ):
        check = artifact_checks.get(check_name) or {}
        notes.append(f"{check_name}: {check.get('status') or 'missing'}")

    return errors, notes, artifact


def inspect_ingest_schema(dsn: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    notes: list[str] = []
    with psycopg2.connect(dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select table_schema, table_name, column_name
                from information_schema.columns
                where (table_schema, table_name) in (
                  ('public', 'webhook_log'),
                  ('public', 'ingest_delivery_log'),
                  ('public', 'opportunities')
                )
                """
            )
            rows = cursor.fetchall()

    columns_by_table: dict[tuple[str, str], set[str]] = {}
    for schema_name, table_name, column_name in rows:
        columns_by_table.setdefault((schema_name, table_name), set()).add(column_name)

    for table_ref, required_columns in REQUIRED_TABLE_COLUMNS.items():
        present_columns = columns_by_table.get(table_ref)
        table_label = f"{table_ref[0]}.{table_ref[1]}"
        if not present_columns:
            errors.append(f"missing required table: {table_label}")
            continue
        missing_columns = sorted(required_columns - present_columns)
        if missing_columns:
            errors.append(
                f"missing required columns in {table_label}: {', '.join(missing_columns)}"
            )
        else:
            notes.append(f"{table_label}: ok")

    return errors, notes


def validate_actor_manifest(actor_names: list[str]) -> list[str]:
    import json

    payload = json.loads(DEPLOYMENT_MANIFEST.read_text(encoding="utf-8"))
    actors = payload.get("actors") or {}
    errors: list[str] = []
    for actor_name in actor_names:
        details = actors.get(actor_name)
        if not isinstance(details, dict):
            errors.append(f"actor missing from apify/deployment.json: {actor_name}")
            continue
        for required_key in ("id", "scheduleId", "webhookId"):
            if not details.get(required_key):
                errors.append(
                    f"actor {actor_name} missing {required_key} in apify/deployment.json"
                )
    return errors


def run_recent_health_check(
    runtime_env: dict[str, str],
    env_file: str | None,
    actor_names: list[str],
) -> tuple[int, str]:
    command = [sys.executable, str(CHECK_RECENT_SCRIPT)]
    if env_file:
        command.extend(["--env-file", env_file])
    if actor_names:
        command.extend(["--actors", *actor_names])
    completed = subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        env=runtime_env,
        capture_output=True,
        text=True,
        check=False,
    )
    output = (completed.stdout or "").strip()
    if completed.stderr:
        output = f"{output}\n{completed.stderr.strip()}".strip()
    return int(completed.returncode), output


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the repo-side prerequisites for tonight's ingest rollout and "
            "optionally run the recent-ingest health gate."
        )
    )
    parser.add_argument(
        "--env-file",
        help="Optional env file to layer under the current shell environment.",
    )
    parser.add_argument(
        "--actors",
        nargs="+",
        default=["ds-govdeals", "ds-publicsurplus"],
        help="Actors that must be schedulable and health-checked tonight.",
    )
    parser.add_argument(
        "--skip-recent-health",
        action="store_true",
        help="Skip the recent ingest health gate. Use only when Apify is intentionally unreachable.",
    )
    parser.add_argument(
        "--webhook-proof-artifact",
        default=str(DEFAULT_WEBHOOK_PROOF_ARTIFACT),
        help=(
            "JSON artifact produced by scripts/capture_webhook_secret_proof.py. "
            "Preflight fails when the current runtime secret posture is not backed by this artifact."
        ),
    )
    parser.add_argument(
        "--skip-webhook-proof",
        action="store_true",
        help="Skip webhook secret proof validation. Use only when explicitly running posture checks without rollout authority.",
    )
    parser.add_argument(
        "--expect-previous-secret-absent",
        action="store_true",
        help="Require APIFY_WEBHOOK_SECRET_PREVIOUS to be absent and proven absent in the artifact.",
    )
    args = parser.parse_args()

    runtime_env = build_runtime_env(args.env_file)
    validation_result = validate_environment(runtime_env)
    errors = list(validation_result["errors"])
    warnings = list(validation_result["warnings"])
    webhook_posture = summarize_webhook_secret_posture(runtime_env)
    webhook_proof_notes: list[str] = []
    webhook_proof_artifact: dict[str, Any] | None = None

    errors.extend(validate_actor_manifest(args.actors))

    with patched_environ(runtime_env):
        dsn = get_database_url(None, env_file=args.env_file)
    schema_notes: list[str] = []
    if not dsn:
        errors.append(
            "DATABASE_URL is required for ingest rollout preflight; provide it via the shell or --env-file"
        )
    else:
        try:
            schema_errors, schema_notes = inspect_ingest_schema(dsn)
            errors.extend(schema_errors)
        except Exception as exc:
            errors.append(f"failed to inspect live ingest tables: {exc}")

    health_exit_code: int | None = None
    health_output = ""
    if args.skip_recent_health:
        warnings.append("recent ingest health gate skipped")
    else:
        try:
            health_exit_code, health_output = run_recent_health_check(
                runtime_env,
                args.env_file,
                args.actors,
            )
            if health_exit_code != 0:
                errors.append(
                    "recent ingest health gate failed; inspect scripts/check_recent_ingest_runs.py output below"
                )
        except Exception as exc:
            errors.append(f"failed to run recent ingest health gate: {exc}")

    if args.skip_webhook_proof:
        warnings.append("webhook secret proof validation skipped")
    else:
        proof_errors, webhook_proof_notes, webhook_proof_artifact = validate_webhook_proof_artifact(
            runtime_env,
            Path(args.webhook_proof_artifact),
            expect_previous_secret_absent=args.expect_previous_secret_absent,
        )
        errors.extend(proof_errors)

    print("Ingest Rollout Preflight")
    print("========================")
    print(f"Environment: {validation_result['environment']}")
    print(f"Actors: {', '.join(args.actors)}")

    print("\nChecks")
    print("- environment validation: ok" if not validation_result["errors"] else "- environment validation: failed")
    if args.skip_webhook_proof:
        print("- webhook secret proof: skipped")
    elif webhook_proof_artifact is not None and not [
        e for e in errors if e.startswith("webhook secret proof artifact") or "APIFY_WEBHOOK_SECRET_PREVIOUS is still configured" in e
    ]:
        print("- webhook secret proof: ok")
    else:
        print("- webhook secret proof: failed")
    if dsn:
        print("- live ingest schema: ok" if not [e for e in errors if "ingest tables" in e or "missing required" in e] else "- live ingest schema: failed")
    else:
        print("- live ingest schema: skipped (no DATABASE_URL)")
    if args.skip_recent_health:
        print("- recent ingest health: skipped")
    elif health_exit_code == 0:
        print("- recent ingest health: ok")
    else:
        print("- recent ingest health: failed")

    if schema_notes:
        print("\nSchema")
        for note in schema_notes:
            print(f"- {note}")

    print("\nWebhook Secret Posture")
    print(
        "- active: "
        f"state={webhook_posture['active']['state']} "
        f"fingerprint={webhook_posture['active']['fingerprint'] or 'missing'} "
        f"length={webhook_posture['active']['length']}"
    )
    print(
        "- previous: "
        f"state={webhook_posture['previous']['state']} "
        f"fingerprint={webhook_posture['previous']['fingerprint'] or 'none'} "
        f"length={webhook_posture['previous']['length']}"
    )
    if webhook_proof_notes:
        print("\nWebhook Proof Artifact")
        for note in webhook_proof_notes:
            print(f"- {note}")

    if warnings:
        print("\nWarnings")
        for warning in warnings:
            print(f"- {warning}")

    if health_output:
        print("\nRecent Health Output")
        print(health_output)

    if errors:
        print("\nBlocking Issues")
        for error in errors:
            print(f"- {error}")
        print(
            "\nNot rollout-ready. Fix the blocking issues, rerun this preflight, then use "
            "docs/runbooks/ingest-reconciliation.md for recovery or paging."
        )
        return 1

    print(
        "\nRollout-ready. Next: enable live paging if desired, then keep "
        "docs/runbooks/ingest-reconciliation.md open for operator triage."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
