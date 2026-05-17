# DealerScope Post-PR #30/#31 Live Truth — 2026-05-17

## Verdict
PR #30 (`ingest-modularization-provenance-20260517`) was merged into canonical `origin/main` at commit `2c768ef`.

PR #31 (`post-pr30-live-truth-pytest-scope-20260517`) was merged into canonical `origin/main` at commit `fb97585`.

These were safe modularization/provenance/test-hygiene hardening slices, not business-logic rewrites.

## Confirmed Live State
- `origin/main` is canonical.
- Local `main` is up to date with `origin/main` at `fb97585` after PR #31.
- Vercel status: success.
- Railway status: success.
- Railway health endpoint responds OK: `https://dealscan-insight-production.up.railway.app/health`.
- Backend protected endpoints reject unauthenticated traffic as expected.
- `/api/ingest/apify` exists; GET returns 405 as expected for webhook route.
- GitHub scraper watchdog runs are green.
- Latest inspected `DealerScope Watchdog Hunter` run: `25998277401`.
- Latest inspected watchdog output: `Watchdog Hunter: all monitored scrapers healthy`.
- Open PR list is empty after closing stale PR #1.

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
- Post-PR #31 live health remained OK.

## Test Hygiene Fixed
The prior unscoped pytest gap is now fixed by `pytest.ini` in PR #31:
- pytest default collection is scoped to `tests/`.
- `scripts/` is excluded from default recursion.
- Validation after patch: `268 passed`.

This does not remove the legacy scripts or their optional dependencies; it prevents accidental default test collection from treating operational/performance scripts as unit tests.

## Remaining Blockers / Gaps
1. Supabase live DB inspection is blocked:
   - stored direct pooler URL returns `Tenant or user not found`
   - no usable service-role key is visible in local env/readable files
2. Legacy scraper code still has CSV/mock/offline remnants:
   - `backend/ingest/scrape_all.py` still writes CSV
   - no `scrape_runs` / `parse_events` migration surfaced in grep
3. Frontend lint debt remains pre-existing.
4. CI Python coverage is lighter than the local backend/ingest validation performed here.
5. Local Apify skill token appears stale/scoped wrong; repo secret token remains the stronger available Apify signal.

## Next High-Value Actions
1. Restore/rotate a current Supabase live inspection path:
   - service-role REST key or current direct DB URL
2. Verify live tables:
   - `webhook_log`
   - `opportunities`
   - `alert_log`
3. Decide whether local CSV scraper paths should be retired, wired to Supabase, or documented as non-production legacy.
4. If Apify inspection from OpenClaw is required, rotate/update the local Apify skill token to match the working GitHub Actions secret scope.
