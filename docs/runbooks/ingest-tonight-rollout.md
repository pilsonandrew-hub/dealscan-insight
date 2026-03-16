# Tonight Ingest Rollout

Use this when you need to make today’s ingest hardening and reconciliation changes operational tonight without touching the live path casually.

## Best Next Move

Run the rollout preflight before relying on the new pager wrapper or reconciliation tooling:

```bash
python3 scripts/run_ingest_rollout_preflight.py \
  --env-file .env.live \
  --actors ds-govdeals ds-publicsurplus
```

What it checks:

- production env requirements for live ingest: `DATABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `APIFY_TOKEN` or `APIFY_API_TOKEN`, webhook secrets, and pager notification gating
- `apify/deployment.json` still contains `id`, `scheduleId`, and `webhookId` for tonight’s actors
- live Postgres still has the required `webhook_log`, `ingest_delivery_log`, and `opportunities` columns that the new recovery flow depends on
- the recent-ingest health gate still passes for the trusted actors

## Operator Flow

1. Run the preflight.
2. If it fails on environment or schema, stop and fix that before using the pager or replay tooling.
3. If it fails on recent ingest health, move to `docs/runbooks/ingest-reconciliation.md` immediately and triage the failing runs before enabling live paging.
4. If it passes, decide whether tonight’s pager should stay dry-run or send live Telegram alerts.
5. Keep `docs/runbooks/ingest-reconciliation.md` open during the rollout window.
6. After Step 5 baseline validation is green, execute `docs/runbooks/ingest-closeout-steps-6-10.md` in order. Do not remove `APIFY_WEBHOOK_SECRET_PREVIOUS` or enable live paging ad hoc.

## Pager Decision

Safe default:

- `INGEST_HEALTH_NOTIFY_ENABLED=true`
- `INGEST_HEALTH_NOTIFY_DRY_RUN=true`

This proves the wrapper path and renders the exact alert body without sending pages.

Only switch to live Telegram delivery after the preflight is green and the destination chat is confirmed:

- `INGEST_HEALTH_NOTIFY_ENABLED=true`
- `INGEST_HEALTH_NOTIFY_DRY_RUN=false`
- `TELEGRAM_BOT_TOKEN` set
- `TELEGRAM_CHAT_ID` set

Do not rotate or paste production secrets into repo files while doing this.
