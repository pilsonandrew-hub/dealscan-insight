#!/usr/bin/env python3
"""Run the operator preflight for tonight's ingest rollout."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import psycopg2

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from config.environment_validator import EnvironmentValidator
from live_verification_support import get_database_url


CHECK_RECENT_SCRIPT = REPO_ROOT / "scripts" / "check_recent_ingest_runs.py"
DEPLOYMENT_MANIFEST = REPO_ROOT / "apify" / "deployment.json"
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
    args = parser.parse_args()

    runtime_env = build_runtime_env(args.env_file)
    validation_result = validate_environment(runtime_env)
    errors = list(validation_result["errors"])
    warnings = list(validation_result["warnings"])

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

    print("Ingest Rollout Preflight")
    print("========================")
    print(f"Environment: {validation_result['environment']}")
    print(f"Actors: {', '.join(args.actors)}")

    print("\nChecks")
    print("- environment validation: ok" if not validation_result["errors"] else "- environment validation: failed")
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
