# Paperclip Local Runtime Recovery Runbook

Last updated: 2026-04-16
Owner: Ja'various
Status: active

## Purpose

Recover the local Paperclip runtime when the web UI is up but plugin operations fail, especially when embedded Postgres is down or when local plugin manifest changes are not being reloaded after install or upgrade.

## Symptoms

### Embedded Postgres failure
Typical signs:
- Paperclip dashboard loads, but plugin install/upgrade calls fail
- `POST /api/plugins/:id/upgrade` returns 500
- logs show `connect ECONNREFUSED 127.0.0.1:54329`
- `lsof -iTCP:54329 -sTCP:LISTEN` returns nothing

### Local plugin manifest cache failure
Typical signs:
- plugin worker code updates seem to take effect but manifest changes do not
- local plugin `upgrade` still returns old manifest version or stale launcher shape
- new `entrypoints.ui`, launcher action changes, or manifest version bumps do not appear in `GET /api/plugins`

## Environment

- Instance root: `/Users/andrewpilson/.paperclip/instances/default`
- Config: `/Users/andrewpilson/.paperclip/instances/default/config.json`
- Embedded Postgres dir: `/Users/andrewpilson/.paperclip/instances/default/db`
- Embedded Postgres port: `54329`
- Paperclip web port: `3100`
- Runtime entrypoint: `/Users/andrewpilson/.npm/_npx/43414d9b790239bb/node_modules/paperclipai/dist/index.js`
- Local loader patch script: `/Users/andrewpilson/.openclaw/workspace/scripts/paperclip-apply-plugin-loader-cache-bust.sh`

## Fast health check

```bash
curl -s http://127.0.0.1:3100/api/plugins | head
lsof -iTCP:54329 -sTCP:LISTEN
```

Healthy state:
- `/api/plugins` returns JSON
- port `54329` is listening

## Standard recovery procedure

### Preferred one-shot helper

Use this first:

```bash
/Users/andrewpilson/.openclaw/workspace/scripts/paperclip-recover-local-runtime.sh
```

What it does:
- stops existing Paperclip run process
- starts Paperclip through the supported `run` path
- waits for embedded Postgres and web API health
- reapplies the local plugin loader cache-busting patch
- restarts Paperclip again
- verifies the local `external-review-ui` plugin with a real upgrade call
- runs lightweight smoke checks for drawer exposure and action dispatch

Expected smoke-check success markers:
- `SMOKE_UI_OK` with launcher `invoke-external-review` and drawer target `ExternalReviewLauncherPanel`
- `SMOKE_ACTION_OK` with a validation/downstream error like `Agent not found` or UUID/input validation, which proves the dispatch chain is alive without requiring a real operator task

Optional environment overrides:

```bash
PAPERCLIP_SKIP_PATCH=1 /Users/andrewpilson/.openclaw/workspace/scripts/paperclip-recover-local-runtime.sh
PAPERCLIP_SKIP_VERIFY=1 /Users/andrewpilson/.openclaw/workspace/scripts/paperclip-recover-local-runtime.sh
PAPERCLIP_SKIP_SMOKE=1 /Users/andrewpilson/.openclaw/workspace/scripts/paperclip-recover-local-runtime.sh
PAPERCLIP_PLUGIN_ID=<plugin-id> PAPERCLIP_PLUGIN_PATH=<local-plugin-path> /Users/andrewpilson/.openclaw/workspace/scripts/paperclip-recover-local-runtime.sh
```

### Manual recovery sequence

### 1. Restart Paperclip through the supported run path

```bash
pkill -f 'paperclipai/dist/index.js run' || true
nohup node /Users/andrewpilson/.npm/_npx/43414d9b790239bb/node_modules/paperclipai/dist/index.js run > /tmp/paperclip.log 2>&1 &
```

### 2. Wait for both web and embedded Postgres

```bash
python3 - <<'PY'
import socket, time, urllib.request
for i in range(30):
    db_ok = False
    try:
        s = socket.create_connection(('127.0.0.1', 54329), timeout=1)
        s.close()
        db_ok = True
    except Exception:
        pass
    web_ok = False
    try:
        with urllib.request.urlopen('http://127.0.0.1:3100/api/plugins', timeout=2) as r:
            web_ok = (r.status == 200)
    except Exception:
        pass
    print({'attempt': i + 1, 'db_ok': db_ok, 'web_ok': web_ok})
    if db_ok and web_ok:
        break
    time.sleep(1)
PY
```

Do not continue until both are true.

### 3. Reapply the local plugin loader patch after reinstall/update if needed

Use this when local plugin manifest upgrades are stale again:

```bash
/Users/andrewpilson/.openclaw/workspace/scripts/paperclip-apply-plugin-loader-cache-bust.sh
```

This patches the installed runtime loader so local plugin manifest imports include file-mtime cache busting.

### 4. Restart Paperclip again after patching

```bash
pkill -f 'paperclipai/dist/index.js run' || true
nohup node /Users/andrewpilson/.npm/_npx/43414d9b790239bb/node_modules/paperclipai/dist/index.js run > /tmp/paperclip.log 2>&1 &
```

### 5. Re-run the plugin upgrade

Example for `external-review-ui`:

```bash
python3 - <<'PY'
import urllib.request, json
plugin='d5e8d42d-c49d-4a38-ba25-5491b178c138'
url=f'http://127.0.0.1:3100/api/plugins/{plugin}/upgrade'
payload={"packageName":"/Users/andrewpilson/.openclaw/workspace/paperclip-plugins/external-review-ui","isLocalPath":True}
req=urllib.request.Request(url,data=json.dumps(payload).encode(),headers={'content-type':'application/json'},method='POST')
with urllib.request.urlopen(req, timeout=120) as r:
    print(r.status)
    print(r.read().decode())
PY
```

### 6. Verify manifest freshness

Check that the returned manifest reflects the actual on-disk version and entrypoints. For the current external review plugin, expected markers are:
- `version: 0.0.4`
- `entrypoints.ui = ./ui.js`
- launcher action type `openDrawer`
- launcher target `ExternalReviewLauncherPanel`

## Logs to inspect

Primary logs:
- `/tmp/paperclip.log`
- `/Users/andrewpilson/.paperclip/instances/default/logs/server.log`

Useful commands:

```bash
tail -n 120 /tmp/paperclip.log
tail -n 120 /Users/andrewpilson/.paperclip/instances/default/logs/server.log
```

## Root cause notes

### Embedded Postgres failure mode
The Paperclip web server can be reachable while embedded Postgres is not. In that state, plugin upgrade/install and scheduler behavior fail with database connection refusals even though the dashboard still renders.

### Manifest cache failure mode
Local plugin manifest reload used dynamic import in a long-lived server process. Without cache busting, upgrade calls could return stale manifest content even after real on-disk edits and version bumps.

## Durable local patch behavior

The patch script changes the installed Paperclip loader so `loadManifestFromPath()`:
- stats the manifest file
- converts the local path to a file URL
- appends `?t=<mtimeMs>`
- imports via the cache-busted URL

This makes local plugin manifest edits refresh correctly during install/upgrade.

## Current known limits

- This is still a local installed-runtime patch, not an upstream merge into Paperclip source control
- If the npx-installed Paperclip bundle is replaced, the patch must be re-applied
- The script is safe to re-run and is intended for that purpose

## Recommended future hardening

1. Upstream the loader cache-busting fix into the real Paperclip source repo
2. Add a lightweight `paperclip doctor plugins` check for embedded Postgres + manifest freshness
3. Add a small operator command wrapper that combines restart, wait, patch, and verify into one routine
