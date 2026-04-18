#!/bin/zsh
set -euo pipefail

INSTANCE_ENV="/Users/andrewpilson/.paperclip/instances/default/.env"

if [[ -f "$INSTANCE_ENV" ]]; then
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ -z "$line" ]] && continue
    [[ "$line" == \#* ]] && continue
    key="${line%%=*}"
    value="${line#*=}"
    export "$key=$value"
  done < "$INSTANCE_ENV"
fi

export PAPERCLIP_BRIDGE_TRACE_REQUESTS="${PAPERCLIP_BRIDGE_TRACE_REQUESTS:-false}"

exec /usr/local/bin/node /Users/andrewpilson/.openclaw/workspace/projects/dealerscope/scripts/paperclip-openrouter-bridge.cjs
