# DealerScope Post-PR #30 Live Truth — 2026-05-17

## Verdict
PR #30 (`ingest-modularization-provenance-20260517`) was merged into canonical `origin/main` at commit `2c768ef`.

This was a safe modularization/provenance hardening slice, not a business-logic rewrite.

## Confirmed Live State
- `origin/main` is canonical.
- Vercel status: success.
- Railway status: success.
- Railway health endpoint responds OK: `https://dealscan-insight-production.up.railway.app/health`.
- Backend protected endpoints reject unauthenticated traffic as expected.
- `/api/ingest/apify` exists; GET returns 405 as expected for webhook route.
- GitHub scraper watchdog runs are green.
- Latest observed `DealerScope Watchdog Hunter` run reported: `Watchdog Hunter: all monitored scrapers healthy`.

## Production Ingest Authority
Production-relevant ingest path is:

`Apify actors → Railway /api/ingest/apify → backend/webapp ingest pipeline → Supabase`

Local legacy scrapers are not current production authority.

## Apify Truth
GitHub Actions repo secret `APIFY_TOKEN` is valid and can inspect actor runs. Local skill token appears stale/scoped wrong because it returned no runs/webhooks.

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

## Validation Before Merge
- Targeted backend/ingest tests: 268 passed.
- `tests/` suite: 268 passed.
- Import smoke checks passed.
- `npm build` passed.
- `npm lint` failed from pre-existing frontend debt.

## Remaining Blockers / Gaps
1. Supabase live DB inspection is blocked:
   - stored direct pooler URL returns `Tenant or user not found`
   - no usable service-role key is visible in local env/readable files
2. Unscoped `pytest` has repo hygiene failure:
   - legacy scripts collect as tests and require optional deps (`aiohttp`, `psutil`)
3. Legacy scraper code still has CSV/mock/offline remnants:
   - `backend/ingest/scrape_all.py` still writes CSV
   - no `scrape_runs` / `parse_events` migration surfaced in grep
4. CI Python coverage is lighter than the local backend/ingest validation performed here.

## Next High-Value Actions
1. Restore/rotate a current Supabase live inspection path:
   - service-role REST key or current direct DB URL
2. Verify live tables:
   - `webhook_log`
   - `opportunities`
   - `alert_log`
3. Add test hygiene guard so unscoped pytest does not collect legacy scripts by accident.
4. Decide whether local CSV scraper paths should be retired, wired to Supabase, or documented as non-production legacy.
