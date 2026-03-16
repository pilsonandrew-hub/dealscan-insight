# Webhook Secret Rotation Runbook

## Scope

This runbook covers safe rotation of the shared Apify webhook secret used by `POST /api/ingest/apify`.

Current behavior:
- DealerScope accepts `APIFY_WEBHOOK_SECRET` as the active secret.
- DealerScope also accepts `APIFY_WEBHOOK_SECRET_PREVIOUS` as a temporary fallback during rotation.
- If a request is accepted with `APIFY_WEBHOOK_SECRET_PREVIOUS`, the backend emits a warning log so stale webhook config is visible.

This is a repo-side safety mechanism only. Do not store or rotate the real secret in source control.

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

Interpretation:
- No warnings: all observed webhook traffic is already on the new secret.
- Warnings still present: at least one webhook is still using the old secret.

4. Remove overlap.

After observed traffic is consistently on the new secret:
- unset `APIFY_WEBHOOK_SECRET_PREVIOUS`
- redeploy/restart the backend

This returns the system to a single accepted webhook secret.

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
- `APIFY_WEBHOOK_SECRET_PREVIOUS` is temporary by design; leaving it set expands the trust window unnecessarily.
- Treat placeholder, reused, or short secrets as misconfiguration even if the route still functions.
- If you suspect the secret was exposed publicly, rotate both the backend env and every Apify webhook header on the same day.
