#!/usr/bin/env bash
set -euo pipefail

PAPERCLIP_ENTRY="/Users/andrewpilson/.npm/_npx/43414d9b790239bb/node_modules/paperclipai/dist/index.js"
PAPERCLIP_LOG="/tmp/paperclip.log"
PATCH_SCRIPT="/Users/andrewpilson/.openclaw/workspace/scripts/paperclip-apply-plugin-loader-cache-bust.sh"
DEFAULT_PLUGIN_ID="d5e8d42d-c49d-4a38-ba25-5491b178c138"
DEFAULT_PLUGIN_PATH="/Users/andrewpilson/.openclaw/workspace/paperclip-plugins/external-review-ui"
WEB_URL="http://127.0.0.1:3100/api/plugins"
DB_HOST="127.0.0.1"
DB_PORT="54329"

PLUGIN_ID="${PAPERCLIP_PLUGIN_ID:-$DEFAULT_PLUGIN_ID}"
PLUGIN_PATH="${PAPERCLIP_PLUGIN_PATH:-$DEFAULT_PLUGIN_PATH}"
SKIP_PATCH="${PAPERCLIP_SKIP_PATCH:-0}"
SKIP_VERIFY="${PAPERCLIP_SKIP_VERIFY:-0}"

log() {
  printf '\n[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

require_file() {
  local path="$1"
  if [[ ! -e "$path" ]]; then
    echo "Required path missing: $path" >&2
    exit 1
  fi
}

require_file "$PAPERCLIP_ENTRY"
require_file "$PLUGIN_PATH"
require_file "$PATCH_SCRIPT"

log "Stopping any existing Paperclip run process"
pkill -f 'paperclipai/dist/index.js run' || true

log "Starting Paperclip through supported run path"
nohup node "$PAPERCLIP_ENTRY" run > "$PAPERCLIP_LOG" 2>&1 &

log "Waiting for embedded Postgres and web API"
WEB_URL="$WEB_URL" DB_HOST="$DB_HOST" DB_PORT="$DB_PORT" python3 - <<'PY'
import os, socket, time, urllib.request, sys
web_url = os.environ['WEB_URL']
db_host = os.environ['DB_HOST']
db_port = int(os.environ['DB_PORT'])
for i in range(60):
    db_ok = False
    try:
        s = socket.create_connection((db_host, db_port), timeout=1)
        s.close()
        db_ok = True
    except Exception:
        pass
    web_ok = False
    try:
        with urllib.request.urlopen(web_url, timeout=2) as r:
            web_ok = (r.status == 200)
    except Exception:
        pass
    print({'attempt': i + 1, 'db_ok': db_ok, 'web_ok': web_ok})
    if db_ok and web_ok:
        sys.exit(0)
    time.sleep(1)
sys.exit(1)
PY

if [[ "$SKIP_PATCH" != "1" ]]; then
  log "Reapplying local plugin loader cache-busting patch"
  "$PATCH_SCRIPT"

  log "Restarting Paperclip after patch"
  pkill -f 'paperclipai/dist/index.js run' || true
  nohup node "$PAPERCLIP_ENTRY" run > "$PAPERCLIP_LOG" 2>&1 &

  log "Waiting again for embedded Postgres and web API"
  WEB_URL="$WEB_URL" DB_HOST="$DB_HOST" DB_PORT="$DB_PORT" python3 - <<'PY'
import os, socket, time, urllib.request, sys
web_url = os.environ['WEB_URL']
db_host = os.environ['DB_HOST']
db_port = int(os.environ['DB_PORT'])
for i in range(60):
    db_ok = False
    try:
        s = socket.create_connection((db_host, db_port), timeout=1)
        s.close()
        db_ok = True
    except Exception:
        pass
    web_ok = False
    try:
        with urllib.request.urlopen(web_url, timeout=2) as r:
            web_ok = (r.status == 200)
    except Exception:
        pass
    print({'attempt': i + 1, 'db_ok': db_ok, 'web_ok': web_ok})
    if db_ok and web_ok:
        sys.exit(0)
    time.sleep(1)
sys.exit(1)
PY
else
  log "Skipping loader patch reapply because PAPERCLIP_SKIP_PATCH=1"
fi

if [[ "$SKIP_VERIFY" != "1" ]]; then
  log "Upgrading/verifying local plugin install"
  PLUGIN_ID="$PLUGIN_ID" PLUGIN_PATH="$PLUGIN_PATH" python3 - <<'PY'
import os, urllib.request, json
plugin = os.environ['PLUGIN_ID']
plugin_path = os.environ['PLUGIN_PATH']
url = f'http://127.0.0.1:3100/api/plugins/{plugin}/upgrade'
payload = {"packageName": plugin_path, "isLocalPath": True}
req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={'content-type': 'application/json'}, method='POST')
with urllib.request.urlopen(req, timeout=120) as r:
    body = r.read().decode()
    print(r.status)
    print(body)
PY
else
  log "Skipping plugin verify because PAPERCLIP_SKIP_VERIFY=1"
fi

log "Paperclip local runtime recovery flow completed"
