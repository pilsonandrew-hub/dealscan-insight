#!/bin/bash
set -euo pipefail

ROOT="/Users/andrewpilson/.openclaw/workspace/brains/dealerscope-brain/operations"

echo "[gbrain-ops-status] key docs"
for f in \
  "$ROOT/gbrain-operations-runbook.md" \
  "$ROOT/gbrain-secrets-and-config-policy.md" \
  "$ROOT/gbrain-fallback-and-failure-policy.md" \
  "$ROOT/gbrain-clean-machine-bootstrap.md" \
  "$ROOT/gbrain-backup-and-restore-standard.md" \
  "$ROOT/gbrain-validation-execution-policy.md" \
  "$ROOT/gbrain-restore-rehearsal-2026-04-12.md" \
  "$ROOT/env/gbrain-env-strategy.md" \
  "$ROOT/env/gbrain-environment-promotion-policy.md" \
  "$ROOT/env/gbrain-environment-activation-checklist.md" \
  "$ROOT/env/gbrain-environment-topology.md" \
  "$ROOT/env/gbrain-backend-allocation-plan.md" \
  "$ROOT/env/gbrain-dev-manifest.md" \
  "$ROOT/env/gbrain-dev-activation-procedure.md" \
  "$ROOT/env/gbrain-dev-config-template.json" \
  "$ROOT/env/gbrain-dev-activation-status.md" \
  "$ROOT/env/gbrain-staging-manifest.md" \
  "$ROOT/env/gbrain-prod-manifest.md"
do
  test -f "$f" && echo "OK  $f" || { echo "MISS $f"; exit 1; }
done

echo "[gbrain-ops-status] done"
