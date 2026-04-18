#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/andrewpilson/.openclaw/workspace"

cd "$ROOT"

echo "[1/2] Reconstructing repaired Paperclip runtime mirrors"
./scripts/paperclip-runtime-repair-2026-04-18.sh

echo
echo "[2/2] Verifying repaired runtime manifest parity"
python3 "$ROOT/scripts/verify-paperclip-runtime-repair-2026-04-18.py"

echo
echo "Paperclip runtime repair control completed successfully."
