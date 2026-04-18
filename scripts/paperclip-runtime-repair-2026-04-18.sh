#!/usr/bin/env bash
set -euo pipefail

LIVE_ROOT="/Users/andrewpilson/.local/paperclip-clean/node_modules/@paperclipai/server/dist"
MIRROR_ONE="/Users/andrewpilson/.openclaw/workspace/.tmp/paperclip-clean-runtime/node_modules/@paperclipai/server/dist"
MIRROR_TWO="/Users/andrewpilson/.openclaw/workspace/.tmp/npm-global/lib/node_modules/paperclipai/node_modules/@paperclipai/server/dist"
FILES=(
  "adapters/http/execute.js"
  "services/activity.js"
  "services/heartbeat-run-summary.js"
)

for rel in "${FILES[@]}"; do
  src="$LIVE_ROOT/$rel"
  [[ -f "$src" ]] || { echo "missing live file: $src" >&2; exit 1; }
  for root in "$MIRROR_ONE" "$MIRROR_TWO"; do
    dst="$root/$rel"
    mkdir -p "$(dirname "$dst")"
    cp "$src" "$dst"
    echo "copied $src -> $dst"
  done
done

echo
echo "Verifying exact parity..."
for rel in "${FILES[@]}"; do
  live="$LIVE_ROOT/$rel"
  one="$MIRROR_ONE/$rel"
  two="$MIRROR_TWO/$rel"
  cmp -s "$live" "$one" && echo "MATCH paperclip-clean-runtime $rel" || { echo "DIFF paperclip-clean-runtime $rel" >&2; exit 1; }
  cmp -s "$live" "$two" && echo "MATCH npm-global $rel" || { echo "DIFF npm-global $rel" >&2; exit 1; }
done

echo
echo "Paperclip repaired runtime files mirrored successfully."
