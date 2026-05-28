# Production Readiness

DealerScope is production-ready only when machine-checkable gates pass.

## Required checks (CI)

- `business-rules-drift` — `scripts/check_business_rules_drift.py`
- `backend-tests` — `pytest tests/`
- `frontend-tests` — `npm test` + `npm run build`

Workflow: `.github/workflows/ci.yml`

## Production environment contract

See `.env.example` for required values, including:

- `ALERTS_ENABLED=true`
- `HOT_DEAL_MIN_SCORE=80`
- `TELEGRAM_WEBHOOK_SECRET` + `TELEGRAM_OPERATOR_MAP`
- `DEALERSCOPE_OPERATOR_USER_ID`
- `INTERNAL_API_SECRET` or `LIFECYCLE_CRON_SECRET`

## RLS verification

Run against live Postgres:

```bash
SUPABASE_DB_URL='postgresql://...' python3 scripts/audit_supabase_rls.py
```

Expected behavior:

- **PASS** — exit code `0`, JSON `"status": "PASS"`, `table.rls_enabled` is true, and no `public`/`anon` `SELECT` or `ALL` policy.
- **FAIL** — exit code `1`, JSON `"status": "FAIL"` with `failures` (RLS disabled, missing table, public/anon read policy, permissive `USING (true)`, missing env, or DB connection error).
- Missing `SUPABASE_DB_URL` / `DATABASE_URL` is **FAIL**, not skip.

Apply migration `supabase/migrations/20260525_opportunities_rls_single_operator.sql` if the audit fails on public read policies or disabled RLS.

## Canonical business rules

Authoritative module: `backend/business_rules/`
