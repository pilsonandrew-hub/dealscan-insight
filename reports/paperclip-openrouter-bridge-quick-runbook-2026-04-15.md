# Paperclip OpenRouter Bridge Quick Runbook

Date: 2026-04-15
Status: live-confirmed

## What this is

This bridge is the local service that lets the Paperclip agent `Routing Governor HTTP Bridge` send eligible tasks through:

- Paperclip HTTP adapter
- local bridge
- Routing Governor
- OpenRouter

## Core files

- LaunchAgent: `~/Library/LaunchAgents/com.paperclipai.openrouter-bridge.plist`
- Launcher wrapper: `/Users/andrewpilson/.openclaw/workspace/scripts/paperclip-openrouter-bridge-launch.sh`
- Bridge server: `/Users/andrewpilson/.openclaw/workspace/scripts/paperclip-openrouter-bridge.js`
- Governor: `/Users/andrewpilson/.openclaw/workspace/scripts/paperclip-routing-governor.js`
- Governor config: `/Users/andrewpilson/.openclaw/workspace/reports/paperclip-routing-governor-config-v2-2026-04-16.json`
- Instance env: `/Users/andrewpilson/.paperclip/instances/default/.env`
- Log file: `/tmp/paperclip-openrouter-bridge.log`

## Normal health check

```bash
curl -sS http://127.0.0.1:8787/health
```

Healthy response should show:
- `"ok": true`
- provider `openrouter`
- configured lanes

## Restart cleanly

```bash
lsof -ti tcp:8787 | xargs -r kill
launchctl unload ~/Library/LaunchAgents/com.paperclipai.openrouter-bridge.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/com.paperclipai.openrouter-bridge.plist
curl -sS http://127.0.0.1:8787/health
```

## View logs

```bash
tail -n 50 /tmp/paperclip-openrouter-bridge.log
```

## Common failures

### 1. `fetch failed` in Paperclip run
Cause:
- bridge is not running or not reachable on `127.0.0.1:8787`
- or the request reached the bridge but Routing Governor rejected the task class

Check:
```bash
curl -sS http://127.0.0.1:8787/health
curl -sS http://127.0.0.1:8787/run \
  -H 'content-type: application/json' \
  -d '{
    "system_prompt":"Health check",
    "context":{"prompt":"Reply with exactly: BRIDGE_OK","task_class":"general_default"}
  }'
```

Healthy result:
- `/health` returns `"ok": true`
- `/run` returns 200 with `"content":"BRIDGE_OK"`
- response routing metadata should show `"task_class":"general_chat"`

Fix:
- restart the LaunchAgent using the restart block above
- if `/run` fails with `unsupported_task_class`, verify the bridge still normalizes `general_default` -> `general_chat`

### 2. `EADDRINUSE` on port 8787
Cause:
- a manual bridge process is already running, so LaunchAgent cannot bind

Fix:
```bash
lsof -ti tcp:8787 | xargs -r kill
launchctl unload ~/Library/LaunchAgents/com.paperclipai.openrouter-bridge.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/com.paperclipai.openrouter-bridge.plist
```

### 3. `.env` parsing / PATH with spaces
Cause:
- shell-sourcing `.env` can break on unquoted values like `Application Support`

Current safe design:
- do not `source` the instance `.env` directly from zsh startup logic
- use the wrapper script’s line-by-line export logic

## Paperclip agent using this bridge

- Name: `Routing Governor HTTP Bridge`
- Agent ID: `ce955356-b2a7-4eae-976c-04403f8c78ef`
- urlKey: `routing-governor-http-bridge`

## Scope rules

This bridge is for OpenRouter-eligible tasks.

Supported task classes:
- `external_review`
- `general_chat`
- compatibility alias accepted by bridge: `general_default` → `general_chat`

Do not route this through the bridge:
- `local_only_private`

That class should stay on a local adapter path.

## Live proof reference

See:
- `/Users/andrewpilson/.openclaw/workspace/reports/paperclip-routing-governor-live-confirmation-2026-04-15.md`
