#!/bin/bash
set -euo pipefail

export PATH="$HOME/.bun/bin:$PATH"
cd "/Users/andrewpilson/.openclaw/workspace/tools/gbrain"

echo "[benchmark] doctrine"
gbrain search "DealerScope AI Operating Doctrine"

echo "[benchmark] paperclip"
gbrain search "Paperclip Mission Control"

echo "[benchmark] openrouter"
gbrain search "OpenRouter routing governor"

echo "[benchmark] restore"
gbrain search "restore rehearsal"
