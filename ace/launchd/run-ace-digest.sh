#!/bin/zsh
set -euo pipefail

WORKSPACE="/Users/andrewpilson/.openclaw/workspace"
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
cd "$WORKSPACE"

DB_PATH="${ACE_DB_PATH:-/Users/andrewpilson/.openclaw/workspace/ace/state/ace.db}"
DIGEST_DAYS="${ACE_DIGEST_DAYS:-7}"
CHAT_ID="${ACE_TELEGRAM_CHAT_ID:-${ACE_NOTIFICATION_TARGET:-7529788084}}"

exec python3 ace/ace.py \
  --db "$DB_PATH" \
  digest \
  --days "$DIGEST_DAYS" \
  --chat-id "$CHAT_ID" \
  --actor launchd
