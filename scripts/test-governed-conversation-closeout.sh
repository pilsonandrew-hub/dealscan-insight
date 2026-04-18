#!/usr/bin/env bash
set -euo pipefail

SCRIPT="/Users/andrewpilson/.openclaw/workspace/scripts/closeout-governed-conversation.sh"

"$SCRIPT" \
  --summary "Doctrine and sync contract remain canonical and mirrored" \
  --artifacts "01_Standards/DealerScope-Knowledge-Writeback-Doctrine.md,01_Standards/DealerScope-Feed-Protocol-and-Sync-Contract.md"

echo "governed conversation closeout test passed"
