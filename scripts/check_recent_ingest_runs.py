#!/usr/bin/env python3
"""Fail-fast wrapper for recent ingest reconciliation."""

from __future__ import annotations

import sys

from reconcile_apify_ingest_runs import main as reconcile_main


def main() -> int:
    default_args = [
        "--lookback-hours",
        "12",
        "--pending-grace-minutes",
        "30",
        "--summary-only",
        "--fail-on-issues",
    ]
    return reconcile_main([*default_args, *sys.argv[1:]])


if __name__ == "__main__":
    raise SystemExit(main())
