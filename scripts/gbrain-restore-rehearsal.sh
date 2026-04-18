#!/bin/bash
set -euo pipefail

export PATH="$HOME/.bun/bin:$PATH"
export GBRAIN_CONFIG="$HOME/.gbrain/config.restore-test.json"
GBRAIN_DIR="/Users/andrewpilson/.openclaw/workspace/tools/gbrain"
BRAIN_REPO="/Users/andrewpilson/.openclaw/workspace/brains/dealerscope-brain"

cd "$GBRAIN_DIR"

echo "[gbrain-restore] config=$GBRAIN_CONFIG"
echo "[gbrain-restore] doctor"
gbrain doctor

echo "[gbrain-restore] import fresh"
gbrain import "$BRAIN_REPO" --no-embed --fresh

echo "[gbrain-restore] stats"
gbrain stats

echo "[gbrain-restore] smoke search"
gbrain search "DealerScope AI Operating Doctrine" >/dev/null
gbrain search "Paperclip Mission Control" >/dev/null
gbrain search "OpenRouter routing governor" >/dev/null

echo "[gbrain-restore] rehearsal complete"
