#!/usr/bin/env bash
set -euo pipefail

CONFIG_PATH="${GBRAIN_CONFIG:-$HOME/.gbrain/config.dev.json}"

if [[ ! -f "$CONFIG_PATH" ]]; then
  echo "Missing GBrain config: $CONFIG_PATH" >&2
  exit 1
fi

OPENAI_KEY="$(python3 - "$CONFIG_PATH" <<'PY'
import json, sys
path = sys.argv[1]
with open(path, 'r') as f:
    data = json.load(f)
print(data.get('openai_api_key', ''))
PY
)"

if [[ -z "$OPENAI_KEY" ]]; then
  echo "openai_api_key missing in $CONFIG_PATH" >&2
  exit 1
fi

export OPENAI_API_KEY="$OPENAI_KEY"
exec gbrain embed --stale
