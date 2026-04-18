#!/bin/bash
set -euo pipefail

export PATH="$HOME/.bun/bin:$PATH"
GBRAIN_DIR="/Users/andrewpilson/.openclaw/workspace/tools/gbrain"

cd "$GBRAIN_DIR"

echo "[gbrain-validate] doctor"
gbrain doctor

echo "[gbrain-validate] stats"
gbrain stats

echo "[gbrain-validate] doctrine search"
gbrain search "DealerScope AI Operating Doctrine" >/dev/null

echo "[gbrain-validate] paperclip search"
gbrain search "Paperclip Mission Control" >/dev/null

echo "[gbrain-validate] openrouter search"
gbrain search "OpenRouter routing governor" >/dev/null

echo "[gbrain-validate] done"
