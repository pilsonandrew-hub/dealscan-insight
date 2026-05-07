#!/bin/zsh
set -euo pipefail

WORKSPACE="/Users/andrewpilson/.openclaw/workspace"
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
cd "$WORKSPACE"

DB_PATH="${ACE_DB_PATH:-/Users/andrewpilson/.openclaw/workspace/ace/state/ace.db}"
HOST_IDENTITY="${ACE_HOST_IDENTITY:-mac-hq}"
STALE_AFTER_SECONDS="${ACE_SUPERVISOR_STALE_AFTER_SECONDS:-120}"
HEARTBEAT_INTERVAL_SECONDS="${ACE_SUPERVISOR_HEARTBEAT_INTERVAL_SECONDS:-5}"
RUNTIME_FAMILY="${ACE_SUPERVISOR_RUNTIME_FAMILY:-single_tenant_local_supervisor}"

exec python3 ace/ace.py \
  --db "$DB_PATH" \
  supervisor-run \
  --runtime-family "$RUNTIME_FAMILY" \
  --stale-after-seconds "$STALE_AFTER_SECONDS" \
  --heartbeat-interval-seconds "$HEARTBEAT_INTERVAL_SECONDS" \
  --host-identity "$HOST_IDENTITY" \
  --run-until-shutdown
