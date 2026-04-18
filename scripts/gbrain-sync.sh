#!/bin/bash
set -euo pipefail

export PATH="$HOME/.bun/bin:$PATH"
GBRAIN_DIR="/Users/andrewpilson/.openclaw/workspace/tools/gbrain"
BRAIN_REPO="/Users/andrewpilson/.openclaw/workspace/brains/dealerscope-brain"

cd "$GBRAIN_DIR"

echo "[gbrain-sync] doctor"
gbrain doctor

echo "[gbrain-sync] import"
gbrain import "$BRAIN_REPO" --no-embed

echo "[gbrain-sync] stats"
gbrain stats

echo "[gbrain-sync] smoke search"
gbrain search "DealerScope AI Operating Doctrine" >/dev/null

echo "[gbrain-sync] done"
