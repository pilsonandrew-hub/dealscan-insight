#!/usr/bin/env bash
set -euo pipefail

CANON_ROOT="/Users/andrewpilson/.openclaw/workspace/brains/dealerscope-brain"
SYNC_SCRIPT="/Users/andrewpilson/.openclaw/workspace/scripts/dealerscope-brain-sync.py"
VERIFY_SCRIPT="/Users/andrewpilson/.openclaw/workspace/scripts/check-dealerscope-writeback-closeout.py"

usage() {
  cat <<'EOF'
DealerScope governed writeback closeout

Usage:
  dealerscope-writeback-closeout.sh <brain-relative-path> [more paths ...]

Purpose:
  1. Require named governed brain artifacts for closeout
  2. Run the Obsidian mirror sync
  3. Verify exact parity between canonical brain and mirror

Examples:
  dealerscope-writeback-closeout.sh \
    01_Standards/DealerScope-Knowledge-Writeback-Doctrine.md

  dealerscope-writeback-closeout.sh \
    reports/Some-Decision-Page.md \
    01_Standards/Some-Updated-Doctrine.md
EOF
}

if [[ $# -lt 1 ]]; then
  usage
  exit 2
fi

for raw in "$@"; do
  rel="$raw"
  rel="${rel#brains/dealerscope-brain/}"
  target="$CANON_ROOT/$rel"
  if [[ ! -f "$target" ]]; then
    echo "ERROR missing canonical governed artifact: $rel" >&2
    exit 2
  fi
done

echo "[1/3] Canonical governed artifacts present"
for raw in "$@"; do
  rel="${raw#brains/dealerscope-brain/}"
  echo "  - $rel"
done

echo "[2/3] Syncing canonical brain to Obsidian mirror"
python3 "$SYNC_SCRIPT"

echo "[3/3] Verifying closeout parity"
python3 "$VERIFY_SCRIPT" "$@"

echo "CLOSEOUT_COMPLETE governed writeback verified"
