#!/usr/bin/env python3
"""Fail CI when money-path constants appear outside the canonical business_rules package."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "backend" / "business_rules"

# Paths allowed to contain numeric policy literals (tests may assert values).
ALLOWED_PREFIXES = (
    "backend/business_rules/",
    "tests/test_business_rules",
    "tests/test_alert_thresholds",
    "tests/test_ingest_scoring",
    "tests/test_env_utils.py",
    "docs/",
)

FORBIDDEN_PATTERNS = [
    (re.compile(r"wholesale_margin.*<\s*1500"), "flat $1500 margin gate"),
    (re.compile(r"min_margin_target\s*=\s*1500\s+if"), "inline min_margin_target premium literal"),
    (re.compile(r"bid_ceiling_pct\s*=\s*0\.88\s+if"), "inline bid_ceiling_pct premium literal"),
    (re.compile(r'"min_margin_target":\s*1500\s+if'), "dict min_margin_target premium literal"),
    (re.compile(r'"bid_ceiling_pct":\s*0\.88\s+if'), "dict bid_ceiling_pct premium literal"),
    (re.compile(r'HOT_DEAL_MIN_SCORE",\s*70'), "hot deal threshold 70"),
    (re.compile(r"min_score=env_float\([^)]*70\.0"), "alert min_score default 70"),
    (re.compile(r"ANDREW_UUID"), "hardcoded operator UUID"),
]

SCAN_EXTENSIONS = {".py", ".ts", ".tsx"}


def main() -> int:
    failures: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in SCAN_EXTENSIONS:
            continue
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith(".git/") or "/node_modules/" in rel:
            continue
        if any(rel.startswith(prefix) for prefix in ALLOWED_PREFIXES):
            continue
        if rel == "scripts/check_business_rules_drift.py":
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern, label in FORBIDDEN_PATTERNS:
            if pattern.search(text):
                failures.append(f"{rel}: forbidden pattern ({label})")
    if failures:
        print("Business rules drift detected:")
        for line in failures:
            print(f"  - {line}")
        print(f"\nCanonical module: {CANONICAL}")
        return 1
    print("OK: no forbidden money-path drift patterns detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
