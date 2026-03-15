#!/usr/bin/env python3
"""Run the live production verification workflow as an operator step."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from live_verification_support import get_database_url


REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_SCRIPT = REPO_ROOT / "scripts" / "verify_live_opportunities_schema.py"
SMALL_SET_SCRIPT = REPO_ROOT / "scripts" / "verify_small_set_live_pipe.py"


def _run_step(step_name: str, script_path: Path, env: dict[str, str], extra_args: list[str]) -> int:
    print(f"\n== {step_name} ==")
    completed = subprocess.run(
        [sys.executable, str(script_path), *extra_args],
        cwd=str(REPO_ROOT),
        env=env,
        check=False,
    )
    return int(completed.returncode)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run canonical live schema verification and trusted-source live pipe verification in sequence."
    )
    parser.add_argument("--dsn", help="Postgres connection string. Defaults to DATABASE_URL/SUPABASE_DB_URL.")
    parser.add_argument(
        "--env-file",
        help="Optional env file to read DATABASE_URL from when it is not exported in the shell.",
    )
    parser.add_argument(
        "--sources",
        nargs="+",
        default=["govdeals", "publicsurplus"],
        help="Trusted source set to verify. Default: govdeals publicsurplus",
    )
    parser.add_argument(
        "--lookback-hours",
        type=int,
        default=24,
        help="How far back to inspect processed_at rows. Default: 24",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=12,
        help="How many recent rows to print in the small-set verification. Default: 12",
    )
    parser.add_argument(
        "--probe-outcome-write",
        action="store_true",
        help="Attempt a rolled-back write to outcome fields on a recent row.",
    )
    parser.add_argument(
        "--outcome-opportunity-id",
        help="Specific opportunity id to use for the rolled-back outcome write probe.",
    )
    args = parser.parse_args()

    dsn = get_database_url(args.dsn, env_file=args.env_file)
    if not dsn:
        print("Live production verification could not run from this environment.", file=sys.stderr)
        print(
            "Manual step required: provide DATABASE_URL via the shell, --dsn, or --env-file and rerun.",
            file=sys.stderr,
        )
        print(
            "Example: DATABASE_URL='postgresql://...sslmode=require' "
            "python3 scripts/run_live_production_verification.py --lookback-hours 24",
            file=sys.stderr,
        )
        return 2

    child_env = dict(os.environ)
    child_env["DATABASE_URL"] = dsn

    schema_exit = _run_step("Schema Verification", SCHEMA_SCRIPT, child_env, [])
    if schema_exit != 0:
        return schema_exit

    small_set_args = [
        "--lookback-hours",
        str(args.lookback_hours),
        "--sample-limit",
        str(args.sample_limit),
        "--sources",
        *args.sources,
    ]
    if args.probe_outcome_write:
        small_set_args.append("--probe-outcome-write")
    if args.outcome_opportunity_id:
        small_set_args.extend(["--outcome-opportunity-id", args.outcome_opportunity_id])

    return _run_step("Trusted Source Small-Set Verification", SMALL_SET_SCRIPT, child_env, small_set_args)


if __name__ == "__main__":
    raise SystemExit(main())
