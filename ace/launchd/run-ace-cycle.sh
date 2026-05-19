#!/bin/zsh
set -euo pipefail

WORKSPACE="/Users/andrewpilson/.openclaw/workspace"
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
cd "$WORKSPACE"

: "${ACE_OPERATOR_CHANNEL:?ACE_OPERATOR_CHANNEL is required}"
: "${ACE_OPERATOR_TARGET:?ACE_OPERATOR_TARGET is required}"

if [[ "${ACE_OPERATOR_CHANNEL}" == "telegram" && -z "${ACE_OPENCLAW_CHAT_ID:-}" ]]; then
  export ACE_OPENCLAW_CHAT_ID="telegram:${ACE_OPERATOR_TARGET}"
fi

if [[ -n "${ACE_OPENCLAW_CHAT_ID:-}" && -z "${ACE_TELEGRAM_BOOTSTRAP_EXISTING_AS_PROCESSED:-}" ]]; then
  export ACE_TELEGRAM_BOOTSTRAP_EXISTING_AS_PROCESSED="true"
fi

BRIEFING_PATH="${ACE_BRIEFING_PATH:-/Users/andrewpilson/.openclaw/workspace/ace/state/ace_briefing.md}"
DB_PATH="${ACE_DB_PATH:-/Users/andrewpilson/.openclaw/workspace/ace/state/ace.db}"
THREAD_ARG=()
if [[ -n "${ACE_OPERATOR_THREAD_ID:-}" ]]; then
  THREAD_ARG=(--notification-thread-id "$ACE_OPERATOR_THREAD_ID")
fi

NOTIFICATION_CHANNEL="${ACE_NOTIFICATION_CHANNEL:-jace}"
NOTIFICATION_TARGET="${ACE_NOTIFICATION_TARGET:-${ACE_OPERATOR_TARGET}}"
TRIAGE_AFTER_HOURS="${ACE_TRIAGE_AFTER_HOURS:-24}"
APPROVED_AFTER_HOURS="${ACE_APPROVED_AFTER_HOURS:-72}"
BLOCKED_AFTER_HOURS="${ACE_BLOCKED_AFTER_HOURS:-24}"
CLAIMED_DONE_AFTER_HOURS="${ACE_CLAIMED_DONE_AFTER_HOURS:-24}"
ACTIVE_AFTER_HOURS="${ACE_ACTIVE_AFTER_HOURS:-72}"

exec python3 ace/ace.py \
  --db "$DB_PATH" \
  cycle \
  --briefing-path "$BRIEFING_PATH" \
  --triage-after-hours "$TRIAGE_AFTER_HOURS" \
  --approved-after-hours "$APPROVED_AFTER_HOURS" \
  --blocked-after-hours "$BLOCKED_AFTER_HOURS" \
  --claimed-done-after-hours "$CLAIMED_DONE_AFTER_HOURS" \
  --active-after-hours "$ACTIVE_AFTER_HOURS" \
  --notification-channel "$NOTIFICATION_CHANNEL" \
  --notification-target "$NOTIFICATION_TARGET" \
  "${THREAD_ARG[@]}" \
  --actor launchd
