# Paperclip Runtime Repair Runbook (2026-04-18)

## Purpose
Reconstruct and verify the known-good live Paperclip runtime repair state for the issue-path recovery fixes.

## Controlled repair set
These files are the repaired runtime set:
- `adapters/http/execute.js`
- `services/activity.js`
- `services/heartbeat-run-summary.js`

Live installed runtime source:
- `~/.local/paperclip-clean/node_modules/@paperclipai/server/dist/`

Known local mirrors:
- `.tmp/paperclip-clean-runtime/node_modules/@paperclipai/server/dist/`
- `.tmp/npm-global/lib/node_modules/paperclipai/node_modules/@paperclipai/server/dist/`

## Reconstruction procedure
Run:

```bash
./scripts/paperclip-runtime-repair-2026-04-18.sh
```

Expected behavior:
- copies all three repaired files into both mirror trees
- verifies exact parity using `cmp -s`
- exits non-zero on any missing file or mismatch

## Live service verification
After reconstruction, verify the live service is healthy:

```bash
curl -s http://127.0.0.1:3100/api/health
```

Expected:
- `status: ok`
- `authReady: true`
- `bootstrapStatus: ready`

## Runtime behavior verification
### 1. Issue-runs visibility
Verify `/api/issues/:id/runs` no longer collapses repaired runs to `{}`.

### 2. Full run payload persistence
Verify `/api/heartbeat-runs/:runId` contains structured `resultJson` including real response fields such as:
- `content`
- `summary`
- `lane`
- `model`
- `routing`

### 3. Comment materialization
Verify run-linked issue comments materialize useful returned text instead of only:
- `HTTP POST ...`
- shallow model-label stubs

## DEA-30 proof case
Primary live proof issue used on 2026-04-18:
- issue id: `028794ab-8b2a-4703-a98c-1a1563b64339`
- identifier: `DEA-30`

This issue was the enterprise proof case for:
- wake launch recovery
- HTTP adapter response preservation
- issue-runs visibility
- comment materialization quality

## Governed evidence
Canonical governed reports:
- `brains/dealerscope-brain/reports/paperclip-http-adapter-response-body-preservation-live-2026-04-18.md`
- `brains/dealerscope-brain/reports/paperclip-dea-30-issue-path-end-to-end-recovery-live-2026-04-18.md`
- `brains/dealerscope-brain/reports/paperclip-runtime-mirror-alignment-status-2026-04-18.md`
- `brains/dealerscope-brain/reports/paperclip-runtime-repair-reconstruction-procedure-2026-04-18.md`
- `brains/dealerscope-brain/reports/paperclip-runtime-hardening-program-status-2026-04-18.md`

## Closure standard
The repair state is only accepted when all of the following are true:
1. reconstruction script succeeds
2. mirror parity succeeds
3. live health endpoint is healthy
4. `/api/issues/:id/runs` shows meaningful result data
5. `/api/heartbeat-runs/:runId` shows full structured payload
6. run-linked issue comments materialize useful returned text
