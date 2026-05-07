#!/bin/zsh
set -euo pipefail

WORKSPACE="/Users/andrewpilson/.openclaw/workspace"
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
cd "$WORKSPACE"

: "${ACE_OPERATOR_CHANNEL:?ACE_OPERATOR_CHANNEL is required}"
: "${ACE_OPERATOR_TARGET:?ACE_OPERATOR_TARGET is required}"

BRIEFING_PATH="${ACE_BRIEFING_PATH:-/Users/andrewpilson/.openclaw/workspace/ace/state/ace_briefing.md}"
DB_PATH="${ACE_DB_PATH:-/Users/andrewpilson/.openclaw/workspace/ace/state/ace.db}"
THREAD_ARG=()
if [[ -n "${ACE_OPERATOR_THREAD_ID:-}" ]]; then
  THREAD_ARG=(--notification-thread-id "$ACE_OPERATOR_THREAD_ID")
fi

exec python3 ace/ace.py \
  --db "$DB_PATH" \
  cycle \
  --briefing-path "$BRIEFING_PATH" \
  --notification-channel "$ACE_OPERATOR_CHANNEL" \
  --notification-target "$ACE_OPERATOR_TARGET" \
  "${THREAD_ARG[@]}" \
  --actor launchd
