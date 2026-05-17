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

## Remaining Blockers / Gaps
1. Supabase live DB inspection from OpenClaw/local shell is blocked:
   - stored direct pooler URL returns `Tenant or user not found`
   - no usable service-role key is visible in local env/readable files
   - GitHub Actions has working Supabase secrets for scheduled jobs, but those are not readable from OpenClaw/local shell
   - available GitHub Actions logs prove some service-role-backed jobs execute successfully, but do not expose table contents or prove ingest row landing end-to-end
2. Legacy scraper code still has CSV/mock/offline remnants:
   - `backend/ingest/scrape_all.py` still writes CSV
   - no `scrape_runs` / `parse_events` migration surfaced in grep
3. Frontend lint debt remains pre-existing.
4. CI Python coverage is lighter than the local backend/ingest validation performed here.
5. Local Apify skill token appears stale/scoped wrong; repo secret token remains the stronger available Apify signal.
6. A Google Cloud Build trigger attached to GitHub failed its Deploy step for `de62eb4`; Vercel/Railway production deploys remain green, so treat this as non-production/secondary until ownership is confirmed.

## Next High-Value Actions
1. Restore/rotate a current Supabase live inspection path:
   - service-role REST key or current direct DB URL
2. Verify live tables:
   - `webhook_log`
   - `opportunities`
   - `alert_log`
3. Decide whether local CSV scraper paths should be retired, wired to Supabase, or documented as non-production legacy.
4. If Apify inspection from OpenClaw is required, rotate/update the local Apify skill token to match the working GitHub Actions secret scope.
5. Decide whether the failing Google Cloud Build trigger should be disabled, repaired, or documented as non-production.
