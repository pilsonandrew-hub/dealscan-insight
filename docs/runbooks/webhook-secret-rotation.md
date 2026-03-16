# Webhook Secret Rotation Runbook

## Scope

This runbook covers safe rotation of the shared Apify webhook secret used by `POST /api/ingest/apify`.

Current behavior:
- DealerScope accepts `APIFY_WEBHOOK_SECRET` as the active secret.
- DealerScope also accepts `APIFY_WEBHOOK_SECRET_PREVIOUS` as a temporary fallback during rotation.
- Startup and preflight report safe fingerprints for the active and previous secret posture.
- If a request is accepted with `APIFY_WEBHOOK_SECRET_PREVIOUS`, the backend emits a warning log with safe fingerprints so stale webhook config is visible.

This is a repo-side safety mechanism only. Do not store or rotate the real secret in source control.

Proof artifact path:
- `runtime-artifacts/webhook-secret-proof.json`

Proof tooling:
- Capture/update artifact: `python scripts/capture_webhook_secret_proof.py ...`
- Verify artifact against current runtime env: `python scripts/run_ingest_rollout_preflight.py ...`

No raw secret goes into the artifact. Only posture, truncated fingerprints, payload hash, deploy SHA, endpoint, timestamps, and HTTP results.

## Preconditions

- The backend release that supports `APIFY_WEBHOOK_SECRET_PREVIOUS` is deployed first.
- The replacement secret is generated and stored in the deployment secret manager or platform env UI.
- The old secret is still available so it can be placed in `APIFY_WEBHOOK_SECRET_PREVIOUS` during overlap.

## Rotation Steps

1. Stage backend env for overlap.

Set:
- `APIFY_WEBHOOK_SECRET=<new secret>`
- `APIFY_WEBHOOK_SECRET_PREVIOUS=<old secret>`

Redeploy or restart the backend so the new env is loaded before changing Apify.

2. Update Apify webhook headers.

For each active actor webhook, change:
- `X-Apify-Webhook-Secret: <old secret>`

to:
- `X-Apify-Webhook-Secret: <new secret>`

Do not change the webhook URL during this procedure unless there is a separate ingress migration in flight.

3. Verify live delivery.

Check:
- Railway/backend logs for successful `/api/ingest/apify` traffic.
- `webhook_log` rows continuing to land and process normally.
- Warning logs mentioning `APIFY_WEBHOOK_SECRET_PREVIOUS`.
- The proof artifact shows the current active fingerprint and previous-secret posture you intended to deploy.

Interpretation:
- No warnings: all observed webhook traffic is already on the new secret.
- Warnings still present: at least one webhook is still using the old secret.

4. Capture the proof artifact. Do not improvise this.

Use a real recent webhook payload captured outside source control. Do not fabricate one.

Required inputs:
- `APIFY_WEBHOOK_SECRET` in env
- `APIFY_WEBHOOK_SECRET_RETIRED` in env for the stale-secret `401` check
- optional `APIFY_WEBHOOK_SECRET_PREVIOUS` in env if overlap is still active
- deployed ingest endpoint
- JSON payload file for one real recent webhook body

Example:

```bash
python scripts/capture_webhook_secret_proof.py \
  --endpoint https://<deploy-host>/api/ingest/apify \
  --payload-file /secure/path/recent-apify-webhook.json \
  --artifact-path runtime-artifacts/webhook-secret-proof.json \
  --require-live-checks
```

What the artifact must record:
- `retired_secret_rejected`: retired secret returns `401`
- `current_secret_accepted`: current secret returns `200`
- `replay_suppressed`: second current-secret submit returns `200` with `replay_ignored=true`
- `previous_secret_absent`: only after overlap is supposed to be over

If any check fails, stop. Fix the deploy or env drift first.

5. Remove overlap.

After observed traffic is consistently on the new secret:
- unset `APIFY_WEBHOOK_SECRET_PREVIOUS`
- redeploy/restart the backend
- rerun the proof capture with `--expect-previous-absent`

This returns the system to a single accepted webhook secret.

6. Run preflight against the artifact.

```bash
python scripts/run_ingest_rollout_preflight.py \
  --webhook-proof-artifact runtime-artifacts/webhook-secret-proof.json \
  --expect-previous-secret-absent
```

Preflight now prints:
- active secret state and safe fingerprint
- previous secret state and safe fingerprint
- artifact path, deploy SHA, and recorded proof statuses

Preflight fails if the artifact is missing or if its secret posture does not match the current runtime env.

## Rollback

If webhook deliveries fail immediately after the Apify change:

1. Put the old secret back into Apify webhook headers.
2. Keep backend env as:
- `APIFY_WEBHOOK_SECRET=<new secret>`
- `APIFY_WEBHOOK_SECRET_PREVIOUS=<old secret>`
3. Re-verify webhook flow before attempting another cutover.

Do not swap the values back and forth in source-controlled files. Handle the rollback in deployment env only.

## Guardrails

- Never commit the real webhook secret into `apify/deployment.json`, docs, scripts, or notes.
- Never commit `runtime-artifacts/webhook-secret-proof.json`. It is local runtime evidence.
- `APIFY_WEBHOOK_SECRET_PREVIOUS` is temporary by design; leaving it set expands the trust window unnecessarily.
- Treat placeholder or reused fallback secrets as misconfiguration. A short `APIFY_WEBHOOK_SECRET_PREVIOUS` is tolerated only for a brief overlap with a retiring legacy secret and should still be removed promptly.
- If you suspect the secret was exposed publicly, rotate both the backend env and every Apify webhook header on the same day.
