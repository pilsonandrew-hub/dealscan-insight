#!/usr/bin/env bash
set -euo pipefail

CANON_ROOT="/Users/andrewpilson/.openclaw/workspace/brains/dealerscope-brain"
SYNC_SCRIPT="/Users/andrewpilson/.openclaw/workspace/scripts/dealerscope-brain-sync.py"
VERIFY_SCRIPT="/Users/andrewpilson/.openclaw/workspace/scripts/check-dealerscope-writeback-closeout.py"
VERIFY_FULL_SCRIPT="/Users/andrewpilson/.openclaw/workspace/scripts/verify-dealerscope-obsidian-mirror.py"

usage() {
  cat <<'EOF'
DealerScope governed writeback closeout

Usage:
  dealerscope-writeback-closeout.sh <brain-relative-path> [more paths ...]

Purpose:
  1. Require named governed brain artifacts for closeout
  2. Run the Obsidian mirror sync
  3. Verify exact parity between canonical brain and mirror for named artifacts
  4. Verify exact parity across the full governed included scope

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

echo "[1/4] Canonical governed artifacts present"
for raw in "$@"; do
  rel="${raw#brains/dealerscope-brain/}"
  echo "  - $rel"
done

echo "[2/4] Syncing canonical brain to Obsidian mirror"
python3 "$SYNC_SCRIPT"

echo "[3/4] Verifying named closeout artifacts"
python3 "$VERIFY_SCRIPT" "$@"

echo "[4/4] Verifying full governed mirror scope"
python3 "$VERIFY_FULL_SCRIPT"

echo "CLOSEOUT_COMPLETE governed writeback and full mirror parity verified"
