#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ace.false_closure_advisory import run_commit_msg_advisory
from ace.storage import DB_PATH


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: advisory_commit_msg.py <commit-message-file>", file=sys.stderr)
        return 2
    return run_commit_msg_advisory(argv[1], db_path=DB_PATH)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
