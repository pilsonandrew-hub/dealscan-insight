# DealerScope Post-PR #30/#31 Live Truth — 2026-05-17

## Verdict
PR #30 (`ingest-modularization-provenance-20260517`) was merged into canonical `origin/main` at commit `2c768ef`.

PR #31 (`post-pr30-live-truth-pytest-scope-20260517`) was merged into canonical `origin/main` at commit `fb97585`.

These were safe modularization/provenance/test-hygiene hardening slices, not business-logic rewrites.

## Confirmed Live State
- `origin/main` is canonical.
- Local `main` was re-synced after PR #32; latest observed canonical `origin/main` was `03c7a94`.
- Vercel status: success.
- Railway status: success.
- Google Cloud Build status on `de62eb4`: failure in Deploy step after Build/Push succeeded; this appears to be a secondary/stale Cloud Build trigger because repo production authority is Railway/Vercel and no repo-owned Cloud Build config was found beyond incidental docs.
- Railway health endpoint responds OK: `https://dealscan-insight-production.up.railway.app/health`.
- Backend protected endpoints reject unauthenticated traffic as expected.
- `/api/ingest/apify` exists; GET returns 405 as expected for webhook route.
- GitHub scraper watchdog runs are green.
- Latest inspected `DealerScope Watchdog Hunter` run: `25999101570`.
- Latest inspected watchdog output: `Watchdog Hunter: all monitored scrapers healthy`.
- Open PR list was empty after closing stale PR #1 and merging PRs #30–#32.

## Production Ingest Authority
Production-relevant ingest path is:

`Apify actors → Railway /api/ingest/apify → backend/webapp ingest pipeline → Supabase`

Local legacy scrapers are not current production authority.

## Apify Truth
GitHub Actions repo secret `APIFY_TOKEN` is valid enough for watchdog actor-run monitoring. Local skill token appears stale/scoped wrong because it returned no runs/webhooks.

Watchdog-monitored actors from GitHub workflow:
- ds-govdeals: `CuKaIAcWyFS0EPrAz`
- ds-publicsurplus: `9xxQLlRsROnSgA42i`
- ds-municibid: `svmsItf3CRBZuIntp`
- ds-gsaauctions: `fvDnYmGuFBCrwpEi9`
- ds-allsurplus: `gYGIfHeYeN3EzmLnB`
- ds-govplanet: `pO2t5UDoSVmO1gvKJ`
- ds-proxibid: `bxhncvtHEP712WX2e`
- ds-usgovbid: `6XO9La81aEmtsCT3g`
- ds-jjkane: `lvb7T6VMFfNUQpqlq`

Proof boundary: watchdog success proves latest actor run recency/status within its workflow rules. It does **not** prove Supabase insertion, opportunity quality, or Telegram alert delivery.

## Validation Before / Around Merge
- Targeted backend/ingest tests: 268 passed.
- `tests/` suite: 268 passed.
- Import smoke checks passed.
- `npm build` passed.
- `npm lint` failed from pre-existing frontend debt.
- PR #30 checks passed and merged.
- PR #31 checks passed and merged.
- PR #32 docs-only live-truth report update checks passed and merged.
- Post-PR #31/#32 live health remained OK.
- Latest inspected `Saved Searches Check` run `25999166075` returned HTTP 200 from Railway `/api/saved-searches/check`.
- Latest inspected `DealerScope Daily Digest` run `25996273988` completed successfully using GitHub Actions Supabase secrets.
- Latest inspected `Deal Expiry Sweeper` run `25990870351` completed successfully using GitHub Actions Supabase secrets.

## Test Hygiene Fixed
The prior unscoped pytest gap is now fixed by `pytest.ini` in PR #31:
- pytest default collection is scoped to `tests/`.
- `scripts/` is excluded from default recursion.
- Validation after patch: `268 passed`.

This does not remove the legacy scripts or their optional dependencies; it prevents accidental default test collection from treating operational/performance scripts as unit tests.


## Additional GitHub Actions Signals — 2026-05-17
- `Saved Searches Check` run `25999166075`: success; Railway endpoint returned HTTP 200 for `/api/saved-searches/check`.
- `DealerScope Daily Digest` run `25996273988`: success; workflow is configured with `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` GitHub secrets.
- `Deal Expiry Sweeper` run `25990870351`: success; workflow is configured with `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` GitHub secrets.
- `DealerScope Watchdog Hunter` run `25999101570`: success; workflow used GitHub `APIFY_TOKEN` and reported `Watchdog Hunter: all monitored scrapers healthy`.

Proof boundary: these runs prove repo secrets and scheduled endpoint/API paths are functioning at the workflow level. They still do not prove the recent Apify webhook payloads landed in `webhook_log`, produced `opportunities`, or emitted Telegram hot-deal alerts.


## Supabase Live Inspection — 2026-05-17 19:06 UTC
A manual read-only GitHub Actions workflow now exists: `DealerScope Supabase Live Inspection` (`.github/workflows/supabase-live-inspection.yml`). It uses existing GitHub Actions `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` secrets and prints aggregate table evidence only; it does not print row payloads or secrets and performs no writes.

Run `25999990822` succeeded. Aggregate evidence from Supabase REST:
- `webhook_log`: 3,649 rows; latest `received_at` = `2026-05-15T12:03:37.241992+00:00`; sample `processing_status`: processed 179, ignored_replay 15, error 6.
- `opportunities`: 5,997 rows; latest `created_at` = `2026-05-15T12:11:33.849763+00:00`; latest 200-row source-site sample showed `allsurplus`.
- `alert_log`: 226 rows; latest `sent_at` = `2026-05-15T13:07:57.259535+00:00`; latest sample channel: telegram.
- `ingest_delivery_log`: 199,692 rows; latest `created_at` = `2026-05-15T13:07:57.056366+00:00`; sample statuses included `sent`, `saved_supabase`, `saved_supabase_duplicate`, `duplicate_existing`, and skip statuses.

Proof boundary: this closes the prior “no Supabase inspection path” blocker at aggregate level. It proves the service-role GitHub secret can read live Supabase and that the core live evidence tables contain recent rows through 2026-05-15. It still does not prove today’s Apify runs generated DB rows, that any individual deal is profitable, or that Telegram delivery content was received by a human.



## Supabase Per-Run Reconciliation — 2026-05-17 19:11 UTC
A second manual read-only GitHub Actions workflow now exists: `DealerScope Ingest Reconciliation` (`.github/workflows/supabase-ingest-reconciliation.yml`). It wraps the existing `scripts/reconcile_apify_ingest_runs.py` and uses GitHub Actions `APIFY_TOKEN`, `SUPABASE_URL`, and `SUPABASE_SERVICE_ROLE_KEY` secrets. It performs read-only Apify/API + Supabase REST inspection and does not print secrets.

Run `26000106495` succeeded. Evidence from the default 72-hour window:
- data path: `SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY` via Supabase REST
- window: `2026-05-14T19:11:53+00:00` → `2026-05-17T19:11:53+00:00`
- actors checked: 10
- Apify runs found: 60
- DB webhook runs found: 12
- DB opportunity runs found: 7
- issue summary:
  - `missing_webhook`: 48
  - `missing_delivery_log`: 38
  - `missing_db_save_ledger`: 38
  - `no_db_landing`: 38

The script classified many successful Apify runs as `pre_app_webhook_miss`: Apify reports a successful actor run, but DealerScope has no matching webhook, delivery, or opportunity evidence for the run. Examples include successful runs for `ds-govplanet`, `ds-govdeals`, `ds-hibid-v2`, `ds-gsaauctions`, `ds-allsurplus`, `ds-proxibid`, `ds-usgovbid`, `ds-jjkane`, and `ds-publicsurplus` within the 72-hour window.

Proof boundary: this is stronger than watchdog actor health and changes the live truth. Actor execution is healthy, but per-run landing is not broadly proven. The next operational investigation should focus on Apify webhook delivery configuration/history and webhook secret alignment for the actors, not additional ingest refactoring.

## Remaining Blockers / Gaps
1. Local shell direct Supabase inspection remains blocked, but GitHub Actions now has two proven read-only Supabase evidence paths:
   - aggregate inspection run `25999990822` read live table counts/freshness from Supabase REST
   - per-run reconciliation run `26000106495` compared Apify actor runs to `webhook_log`, `opportunities`, and `ingest_delivery_log`
   - stored direct pooler URL returns `Tenant or user not found`
   - no usable service-role key is visible in local env/readable files
2. Per-run reconciliation found a real live landing gap: 48 of 60 Apify runs in the inspected 72-hour window had missing webhook evidence, and 38 had no DB landing/delivery ledger evidence.
3. Legacy scraper code still has CSV/mock/offline remnants:
   - `backend/ingest/scrape_all.py` still writes CSV
   - no `scrape_runs` / `parse_events` migration surfaced in grep
4. Frontend lint debt remains pre-existing.
5. CI Python coverage is lighter than the local backend/ingest validation performed here.
6. Local Apify skill token appears stale/scoped wrong; repo secret token remains the stronger available Apify signal.
7. A Google Cloud Build trigger attached to GitHub failed its Deploy step for `de62eb4`; Vercel/Railway production deploys remain green, so treat this as non-production/secondary until ownership is confirmed.

## Next High-Value Actions
1. Investigate Apify webhook delivery configuration/history and webhook secret alignment for the actors with missing webhook evidence.
2. Re-run `DealerScope Ingest Reconciliation` after any Apify webhook/config fix and require per-run landing evidence in:
   - `webhook_log`
   - `opportunities`
   - `ingest_delivery_log`
   - `alert_log` when applicable
3. Decide whether local CSV scraper paths should be retired, wired to Supabase, or documented as non-production legacy.
4. If Apify inspection from OpenClaw is required, rotate/update the local Apify skill token to match the working GitHub Actions secret scope.
5. Decide whether the failing Google Cloud Build trigger should be disabled, repaired, or documented as non-production.
