# Ingest Reconciliation Runbook

## Recovery Window To Reconcile First

The repo does not contain a checked-in production incident timeline, so the outage window below is inferred from today's recovery commits in `main`.

Treat **Sunday, March 15, 2026 05:15 PDT through 12:05 PDT** as the immediate degraded/recovery window to reconcile:

- `2026-03-15T05:15:09-07:00` `3c2ac1a` `fix: resolve missing Apify dataset ids from actor runs`
- `2026-03-15T08:14:20-07:00` `3f0de77` `fix: add direct db fallback for ingest saves`
- `2026-03-15T10:25:48-07:00` `d4b7ee3` `chore: improve ingest observability and duplicate reporting`
- `2026-03-15T10:36:36-07:00` `d2b3e72` `fix: harden ingest replay and save accounting`
- `2026-03-15T11:51:00-07:00` `674f597` `fix: harden ingest identity and replay semantics`
- `2026-03-15T11:59:48-07:00` `84316ad` `feat: add ingest delivery ledger for replay recovery`
- `2026-03-15T12:05:01-07:00` `6926f5b` `fix: defer canonical duplicate updates until save succeeds`

For production cleanup, widen the compare to **2026-03-15 00:00 PDT through now**, then prioritize any runs inside the 05:15-12:05 PDT band.

## What Exists In Production

The current ingest path already records the four surfaces needed for reconciliation:

- Apify run metadata and dataset ids feed `/api/ingest/apify` in `webapp/routers/ingest.py`
- Raw webhook receipts land in `public.webhook_log` from `supabase/migrations/20260313_webhook_log.sql`
- Saved ingest rows carry `run_id` in `public.opportunities` from `supabase/migrations/20260312_event_identity.sql`
- Per-listing save and delivery outcomes land in `public.ingest_delivery_log` from `supabase/migrations/20260315_ingest_delivery_log.sql`

Critical audit durability now works like this:

- `webhook_log` insert, `webhook_log` final status update, replay lookup, and every `db_save` delivery row are no longer best-effort.
- The app tries Supabase first, then falls back to direct Postgres for those audit surfaces.
- If both paths fail, `/api/ingest/apify` exits with `503 Critical ingest audit write failed`. Do not treat that as a harmless retry.
- When the fallback path is used, the webhook response includes `audit_status=fallback`, `audit_fallbacks=[...]`, and the durable `webhook_log.error_message` carries `audit_fallbacks=...` so reconciliation can surface `audit_backfilled`.

Webhook replay guardrails:
- Recent duplicate webhook deliveries for the same `run_id` are ignored for `APIFY_WEBHOOK_REPLAY_WINDOW_SECONDS` seconds. Default: 3600.
- Only recent `processed` and `pending` runs are suppressed; `degraded` or `error` runs can still be replayed immediately for recovery.
- Suppressed deliveries show up in `webhook_log.processing_status` as `ignored_replay`.
- If you truly need to force a replay of a recently processed run, wait for the replay window to expire or temporarily lower `APIFY_WEBHOOK_REPLAY_WINDOW_SECONDS` during the recovery window.
- `APIFY_WEBHOOK_MAX_AGE_SECONDS` is available for stricter freshness enforcement, but defaults to `0` because delayed webhook delivery has not yet been tightly characterized in production.

## Operator Plan

Before using this runbook tonight, run the rollout preflight in `docs/runbooks/ingest-tonight-rollout.md`. It catches the env, schema, and pager readiness gaps that can make reconciliation or paging misleading.

1. Run the run-level compare for the March 15 recovery window.

```bash
python3 scripts/reconcile_apify_ingest_runs.py \
  --env-file .env.live \
  --actors ds-govdeals ds-publicsurplus \
  --start 2026-03-15T05:15:00-07:00 \
  --end 2026-03-15T12:05:00-07:00
```

2. Widen to all of today so you catch any pre-fix or replayed runs.

```bash
python3 scripts/reconcile_apify_ingest_runs.py \
  --env-file .env.live \
  --actors ds-govdeals ds-publicsurplus \
  --start 2026-03-15T00:00:00-07:00
```

3. Triage runs by issue type.

- `missing_webhook`: Apify says the run succeeded, but `webhook_log` has no matching `run_id`. If `ingest_delivery_log` and `opportunities` are also empty for that `run_id`, treat it as a pre-app miss first, not a downstream ingest bug. Check Apify webhook delivery history for the configured webhook id, confirm the live webhook secret still matches `APIFY_WEBHOOK_SECRET` or `APIFY_WEBHOOK_SECRET_PREVIOUS`, confirm the live app is serving `/api/ingest/apify`, then replay the webhook or rerun from the same dataset.
- `webhook_degraded` or `webhook_error`: inspect `webhook_log.error_message` first, then review `db_save` status counts in `ingest_delivery_log` before replaying.
- `audit_backfilled`: the critical audit row landed via direct Postgres fallback. Evidence exists, but Supabase audit writes or replay lookup degraded. Inspect app logs and DB/API health before the next replay or deploy.
- `ignored_replay`: a duplicate delivery was suppressed inside the replay window. This is expected for rapid resubmits and is not, by itself, an ingest failure.
- `missing_delivery_log` or `missing_db_save_ledger`: the webhook landed, but the save ledger is missing. Check Railway app logs for the run before rerunning.
- `db_save_failures`: inspect `db_save` statuses for `supabase_error`, `direct_pg_error`, `direct_pg_unavailable`, or `duplicate_unresolved`. `saved_supabase_duplicate` and `saved_direct_pg_duplicate` are successful race recoveries, not failure states.
- `no_db_landing`: Apify produced items, but neither `opportunities` nor `db_save` shows a successful landing. Treat this as a replay candidate.

For a single suspect run with zero DB evidence, do these checks in order before repeated replays:

1. Confirm Apify marks the run `SUCCEEDED` and note the exact `run_id`, actor, dataset id, and finish time.
2. Inspect Apify webhook delivery attempts for the actor webhook id from `apify/deployment.json`. If Apify never attempted delivery, this is an Apify-side scheduling/webhook issue, not an app-side ingest failure.
3. If Apify attempted delivery, inspect the live app logs around that timestamp for `/api/ingest/apify` responses. A `401` with no `webhook_log` row usually means secret mismatch or stale-payload rejection before normal ingest logging.
4. Only after that, replay the exact webhook payload shape from a recent success or rerun from the same dataset.

Current save fallback behavior:

- `saved_supabase`: Supabase insert succeeded directly.
- `saved_supabase_duplicate`: the row initially lost the canonical unique race, then was re-saved as a duplicate against the winning canonical row.
- `saved_direct_pg`: Supabase insert failed or returned no row, and the direct Postgres fallback inserted successfully.
- `saved_direct_pg_duplicate`: the direct Postgres fallback hit the canonical unique index, recovered the winning canonical row, and re-saved the loser as a duplicate.
- `duplicate_existing`: a unique conflict was resolved by looking up the existing `opportunities.id`; this does not fall through to direct Postgres.
- `supabase_error`: legacy pre-fix status, or an unexpected regression if it appears on newly processed runs. Verify the app version before replaying.

Current audit fallback behavior:

- `audit_status=ok`: all critical audit surfaces stayed on the primary path.
- `audit_status=fallback`: at least one critical audit surface landed via direct Postgres fallback.
- `503 Critical ingest audit write failed`: neither Supabase nor direct Postgres could land the required audit evidence. Do not wave this through.

4. Deep-dive any single run id with direct SQL.

```sql
select received_at, processing_status, item_count, error_message
from public.webhook_log
where run_id = '<run_id>'
order by received_at asc;
```

```sql
select processed_at, id, listing_id, title, step_status, is_duplicate
from public.opportunities
where run_id = '<run_id>'
order by processed_at asc;
```

```sql
select channel, status, count(*) as row_count, max(updated_at) as last_updated_at
from public.ingest_delivery_log
where run_id = '<run_id>'
group by channel, status
order by channel, status;
```

## Scripts Added For Today

Detailed compare:

```bash
python3 scripts/reconcile_apify_ingest_runs.py --env-file .env.live --lookback-hours 12
```

Notes:

- Uses actor ids from `apify/deployment.json`
- For the March 15 incident, scope to `--actors ds-govdeals ds-publicsurplus` to avoid unrelated Apify runs polluting the report
- Reads Postgres DSN from `DATABASE_URL` or `--env-file`
- Reads Apify token from `APIFY_TOKEN` or `APIFY_API_TOKEN`
- If Python hits `CERTIFICATE_VERIFY_FAILED` against Apify, the script now retries the same HTTPS request via `curl` using the host system trust store and still keeps TLS verification on
- Supports `--runs-json <path>` if the shell cannot reach Apify and you need to compare against an exported runs list

Fail-fast check for existing schedulers/pagers:

```bash
python3 scripts/check_recent_ingest_runs.py --env-file .env.live --actors ds-govdeals ds-publicsurplus
```

This exits non-zero when a recent succeeded Apify run is missing a webhook, marked degraded/error, missing the save ledger, or showing save failures. The wrapper defaults to a 12-hour lookback so delayed webhooks/replays do not create noisy false alarms. Wire it into whatever existing job runner already pages on non-zero exit.

Database-only rows with a clean processed or ignored-replay webhook plus successful `db_save`/`opportunities` evidence are treated as historical replay artifacts rather than pager-worthy failures when the current Apify fetch no longer includes that run id.

Pager wrapper for tonight:

```bash
scripts/page_recent_ingest_health.sh --env-file .env.live --actors ds-govdeals ds-publicsurplus
```

Notes:

- Uses `scripts/check_recent_ingest_runs.py` as the health signal and preserves its exit code.
- Prints the failing check output to stderr and can send a Telegram page with the same summary when `INGEST_HEALTH_NOTIFY_ENABLED=true`.
- If you pass `--env-file .env.live`, the wrapper now loads the pager gating vars and Telegram credentials from that file for the wrapper itself, not just the underlying health check.
- Defaults to `INGEST_HEALTH_NOTIFY_DRY_RUN=true`, so the alert body is rendered locally but not sent until you explicitly flip the env to `false`.
- Treat a page as delivered only when Telegram returns `ok=true` and a `message_id`; the wrapper now fails loudly if Telegram rejects the request or returns an unacknowledged response body.
- The repo now includes a scheduled GitHub Actions runner for this wrapper. If you want Telegram paging from GitHub tonight, set repo variable `INGEST_HEALTH_NOTIFY_ENABLED=true`, set `INGEST_HEALTH_NOTIFY_DRY_RUN=false`, and provide `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `DATABASE_URL`, and `APIFY_TOKEN` as repo secrets.
