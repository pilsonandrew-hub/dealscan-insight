# DealerScope Phase 1 Forensic Audit

Scope: recon only. No code was changed.

Confidence labels:
- `CONFIRMED` = the code I read directly shows the behavior or defect.
- `HYPOTHESIS` = the code strongly suggests the issue, but runtime confirmation is still needed.
- `UNKNOWN` = I could not prove it from static inspection alone.

## Method

I read the primary backend entrypoint, legacy backend entrypoint, router surface, scheduler, frontend API surface, scraper actors, and CI/CD workflows. I focused on the flows named in the task and traced them end-to-end through the code paths that exist in this repo snapshot.

## A. System Map

### Entry points and deployment

- Primary runtime entrypoint is `backend.main:app`:
  - `backend/main.py:1-5` marks it as the primary entrypoint.
  - `backend/main.py:55-60` imports the routers dynamically.
  - `backend/main.py:164-206` runs startup validation, DB init, monitoring, and scheduler startup.
  - `backend/main.py:362-368` exposes a retired pipeline trigger.
  - `backend/main.py:393-396` is the local `uvicorn` launcher.
- Railway and Docker both point to `backend.main:app`:
  - `railway.toml:5`
  - `Dockerfile:47`
- Legacy entrypoint still exists:
  - `webapp/main.py:1-23` says deprecated but still wires routers and scheduler.
  - `webapp/main.py:41-51` starts/stops the scheduler.

### Backend router surface

- `webapp/routers/ingest.py` handles Apify webhook ingest, scoring, Supabase persistence, pass actions, and alert dispatch.
- `webapp/routers/rover.py` handles Rover recommendations and event tracking.
- `webapp/routers/sniper.py` handles sniper target CRUD and internal sniper checks.
- `webapp/routers/saved_searches.py` handles saved searches and scheduled search alerts.
- `webapp/routers/outcomes.py` handles outcome recording and summary reporting.
- `webapp/routers/recon.py` handles VIN decode, market-value lookup, and manual evaluation.
- `webapp/routers/vin.py`, `auth.py`, `vehicles.py`, `opportunities.py`, `upload.py`, `ml.py`, `admin.py`, `analytics.py`, `minimal.py` also exist in the router tree.

### Background jobs and cron surfaces

- Internal APScheduler is wired into the app process:
  - `webapp/scheduler.py:1-50`
  - schedules SniperScope every 5 minutes, GovDeals sold daily, GovDeals active every 3 hours.
- GitHub Actions still carries cron and watchdog jobs:
  - `.github/workflows/sniper-check.yml`
  - `.github/workflows/saved-searches-check.yml`
  - `.github/workflows/dealerscope-scraper-watchdog.yml`
  - `.github/workflows/apify-health-check.yml`
  - `.github/workflows/dealerscope-daily-digest.yml`
  - `.github/workflows/apify-deploy.yml`
  - `.github/workflows/production-deploy.yml`
  - `.github/workflows/deploy-validation-reports.yml`
  - `.github/workflows/deploy-gold.yml`
  - `.github/workflows/cursor-review.yml`

### Frontend surface

- React app routes:
  - `src/App.tsx:35-53`
  - `/auth` -> auth page
  - `/` -> protected dashboard
  - `/deal/:id` -> deal detail
- Auth is Supabase-based:
  - `src/contexts/ModernAuthContext.tsx:31-57`
  - `src/pages/Auth.tsx:13-78`
  - `src/components/ProtectedRoute.tsx:14-30`
- Core frontend service layer:
  - `src/services/api.ts`
  - `src/services/roverAPI.ts`
  - `src/integrations/supabase/client.ts`

### External integrations

- Supabase:
  - used in backend routers and frontend client helpers.
- Redis:
  - rate limiting and Rover affinity use Redis.
  - `backend/rover/redis_affinity.py:1-80`
  - `webapp/middleware/rate_limit.py:1-120`
- Apify:
  - webhook ingest, actor status checks, and scraper actors.
  - `webapp/routers/ingest.py:1264-1356`
  - `src/services/api.ts:466-485`
  - `apify/actors/ds-govdeals/src/main_api.js`
  - `apify/actors/ds-govdeals-sold/src/main_api.js`
- Telegram:
  - alert delivery in ingest, sniper, saved-searches, and workflows.
- DeepSeek / OpenRouter:
  - ingest uses DeepSeek for hot-deal validation.
  - `webapp/routers/ingest.py:105-110`, `webapp/routers/ingest.py:2345-2428`
- Marketcheck:
  - `webapp/routers/recon.py:1-116`
- NHTSA:
  - VIN decode in `webapp/routers/recon.py:119-140`
- Manheim:
  - backend market-data abstraction in `backend/ingest/manheim_market.py`

## B. Critical Paths

### a. Apify webhook -> ingest -> score -> Supabase save

Confirmed path:
- Webhook auth and replay checks live in `webapp/routers/ingest.py:1264-1356`.
- Background processing fetches the Apify dataset in `_process_webhook_items()`:
  - `webapp/routers/ingest.py:845-1225`
- Each item is normalized, gated, scored, deduplicated, and saved:
  - `normalize_apify_vehicle()` is called inside `_process_webhook_items()`
  - `passes_basic_gates()` is called before scoring
  - `score_vehicle()` is called at `webapp/routers/ingest.py:1763+`
  - `save_opportunity_to_supabase()` is called at `webapp/routers/ingest.py:2973+`
- If hot deals are found, they are AI-validated and alerted:
  - `webapp/routers/ingest.py:1210-1211`
  - `webapp/routers/ingest.py:2099-2428`

Uncertainty:
- The scoring module itself looks broken, so the runtime behavior of this path needs verification.

### b. Frontend auth -> API call -> data display

Confirmed path:
- Supabase auth client and session handling:
  - `src/integrations/supabase/client.ts:1-18`
  - `src/contexts/ModernAuthContext.tsx:31-57`
- Protected route guard:
  - `src/components/ProtectedRoute.tsx:14-30`
- Dashboard and auth routes:
  - `src/App.tsx:35-53`
- Example API flows:
  - Rover recommendations from frontend:
    - `src/pages/Dashboard.tsx:885`
    - `src/services/roverAPI.ts:103-140`
  - Sniper target fetch/display:
    - `src/components/SniperButton.tsx:54-83`
    - `src/components/SniperScopeDashboard.tsx:144-151`
  - Saved-search creation:
    - `src/components/CrosshairSearch.tsx:177-200`

### c. DOS 80+ deal -> alert gate -> DeepSeek validation -> Telegram alert

Confirmed path:
- Alert gate is evaluated in ingest after save:
  - `webapp/routers/ingest.py:1124-1211`
- Gate policy lives in:
  - `backend/ingest/alert_gating.py:14-18`
  - `backend/ingest/alert_gating.py:120-184`
- DeepSeek validation:
  - `webapp/routers/ingest.py:2345-2428`
- Telegram alert dispatch:
  - `webapp/routers/ingest.py:2099-2290`

### d. Rover recommendation flow

Confirmed path:
- Backend recommendation endpoint:
  - `webapp/routers/rover.py:154-260`
- Heuristic scoring logic:
  - `backend/rover/heuristic_scorer.py:1-133`
- Redis affinity:
  - `backend/rover/redis_affinity.py:1-80`
  - `backend/rover/redis_affinity.py:108-163`
- Frontend call sites:
  - `src/services/roverAPI.ts:103-140`
  - `src/pages/Dashboard.tsx:885`
  - `src/components/RoverDashboard.tsx:46-67`
  - `src/hooks/useRoverRecommendations.ts:24-80`

### e. SniperScope alert flow

Confirmed path:
- Target creation/list/cancel:
  - `webapp/routers/sniper.py:203-303`
- Internal check logic:
  - `webapp/routers/sniper.py:404-520`
- Telegram alert helpers:
  - `webapp/routers/sniper.py:61-99`
- Frontend arm/restore/cancel:
  - `src/components/SniperButton.tsx:54-171`
  - `src/components/SniperScopeDashboard.tsx:144-151`

## C. Top 15 Likely Fractures

| # | Status | Evidence | Symptom | Business impact |
|---|---|---|---|---|
| 1 | CONFIRMED | `backend/ingest/score.py:1-15` plus callers `webapp/routers/ingest.py:1769`, `backend/scrapers/govdeals_active.py:263`, `scripts/backfill_grades.py:19` | The module as read does not define `score_deal`, and it references `Optional` without importing it. | Scoring, backfill, and downstream ingest paths can fail or skip scoring, which breaks DOS-based filtering and reporting. |
| 2 | CONFIRMED | `webapp/routers/ingest.py:105-110` | Hardcoded secret-like fallbacks exist for `OPENROUTER_API_KEY` and `DEEPSEEK_API_KEY`. | Secret leakage risk and non-obvious runtime dependency on embedded credentials. |
| 3 | CONFIRMED | `src/integrations/supabase/client.ts:8-9`, `src/services/api.ts:466-485` | Browser bundle contains a hardcoded Supabase anon key and browser-side Apify token use. | Credential exposure and token abuse risk; front-end health/status checks depend on secrets in client code. |
| 4 | CONFIRMED | `webapp/routers/ingest.py:2114-2119` | `ALERTS_ENABLED` defaults to false, so hot-deal Telegram alerts are suppressed unless env is explicitly enabled. | Revenue-critical alerts can silently stop even when ingest and scoring are healthy. |
| 5 | CONFIRMED | `webapp/routers/ingest.py:2345-2428` | AI validation fails open: malformed DeepSeek responses or API errors append the deal anyway. | Invalid deals can still trigger Telegram alerts and operator attention. |
| 6 | CONFIRMED | `webapp/routers/ingest.py:1395-1432` | `pass_opportunity()` returns success even when the `user_passes` upsert fails. | UI and users see success even though the pass record may never persist. |
| 7 | CONFIRMED | `webapp/routers/saved_searches.py:246-340` | Saved-search polling only considers the latest three matches and only new deals after `last_alerted_at` or the last 30-minute cutoff. | Legitimate matches can be missed without any error signal. |
| 8 | CONFIRMED | `backend/scrapers/govdeals_active.py:260-360` | Low-DOS rows are deleted from `opportunities` when score < 50. | Live inventory can disappear from the primary table, distorting analytics and user feeds. |
| 9 | CONFIRMED | `webapp/routers/sniper.py:203-303` | Unparseable `auction_end_date` is allowed through, and expiration handling is tolerant of parse failures. | Users can arm sniper targets against dead or already-closed auctions. |
| 10 | CONFIRMED | `backend/main.py:199-205`, `webapp/scheduler.py:1-50`, `.github/workflows/sniper-check.yml`, `.github/workflows/saved-searches-check.yml`, `.github/workflows/apify-health-check.yml` | APScheduler starts inside the app process while GitHub Actions cron still exists for adjacent jobs. | Duplicate alerts / duplicate scrapes are likely during multi-worker deploys or failover events. |
| 11 | CONFIRMED | `webapp/routers/rover.py:29-33`, `webapp/routers/recon.py:29-33` | Service-role Supabase keys are used in backend routers, with comments explicitly stating RLS bypass. | Multi-tenant isolation is not enforced by these endpoints. |
| 12 | CONFIRMED | `config/settings.py:1-14`, `webapp/database.py:27-40` | `SECRET_KEY` is required at import time, and DB engine creation depends on `settings.database_url`. | Missing env configuration can prevent startup or create an unusable DB layer. |
| 13 | CONFIRMED | `src/services/roverAPI.ts:311-319` | `createIntent()` uses `supabase.auth.getUser().user.id` without awaiting the async call. | Rover intent creation can fail or write an invalid user id, breaking premium recommendation workflow. |
| 14 | CONFIRMED | `webapp/main.py:1-23`, `webapp/main.py:41-51`, `webapp/main.py:66-73` | Deprecated entrypoint still wires routers and starts the scheduler, with a different CORS policy path from the primary backend. | Operator confusion and duplicate-process risk if the wrong entrypoint is launched. |
| 15 | CONFIRMED | `scripts/backfill_grades.py:19` | Backfill script imports `score_deal` from the broken score module. | Historical grade backfills are likely dead on arrival, blocking repair/reconciliation work. |

## D. 5 Most Dangerous Business-Logic Risks

1. `CONFIRMED` `webapp/routers/ingest.py:2345-2428` plus `webapp/routers/ingest.py:2099-2290`: fail-open AI validation can turn a model outage into false-positive Telegram alerts.
2. `CONFIRMED` `webapp/routers/ingest.py:2114-2119`: alerts can be silently disabled by environment state, which is a direct revenue path failure.
3. `CONFIRMED` `webapp/routers/saved_searches.py:246-340`: only top-3 and recent-only matching means the alerting product can miss valid matches without any explicit error.
4. `CONFIRMED` `backend/scrapers/govdeals_active.py:260-360`: deleting low-DOS rows from the live opportunity table can erase inventory that other flows expect to see.
5. `CONFIRMED` `src/services/roverAPI.ts:311-319`: the premium Rover intent path is vulnerable to a user-id insertion bug, so personalization can degrade while the UI appears functional.

## E. 5 Most Dangerous Infra / Runtime Risks

1. `CONFIRMED` `backend/main.py:199-205` and `webapp/scheduler.py:1-50`: scheduler duplication can cause repeated scrapes and repeated alerts.
2. `CONFIRMED` `config/settings.py:1-14`: missing `SECRET_KEY` aborts import immediately.
3. `CONFIRMED` `webapp/database.py:27-40`: invalid or empty `database_url` can break DB engine initialization.
4. `CONFIRMED` `src/services/api.ts:466-485`: browser-side Apify status checks depend on a token in client code, so runtime behavior is coupled to exposed credentials.
5. `CONFIRMED` `webapp/routers/rover.py:29-33` and `webapp/routers/recon.py:29-33`: service-role clients bypass RLS, so a route bug becomes a data-isolation bug rather than a limited auth bug.

## F. 5 Most Suspicious Areas of AI-Generated or Guessed Code

1. `webapp/routers/ingest.py`
   - Strong signal: hardcoded keys, over-commented decision trail, fail-open paths, and many fallback layers in one router.
   - Evidence: `webapp/routers/ingest.py:105-110`, `webapp/routers/ingest.py:2099-2428`, `webapp/routers/ingest.py:2973-3070`.
2. `src/services/roverAPI.ts`
   - Strong signal: duplicated recommendation logic, mixed async/sync assumptions, and a clear `createIntent()` bug.
   - Evidence: `src/services/roverAPI.ts:140-360`.
3. `src/services/api.ts`
   - Strong signal: very broad façade with browser Apify token usage, many silent fallbacks, and multiple overlapping health/status implementations.
   - Evidence: `src/services/api.ts:1-90`, `src/services/api.ts:466-485`, `src/services/api.ts:620-760`.
4. `webapp/routers/sniper.py` and `webapp/routers/saved_searches.py`
   - Strong signal: near-mirrored structure, phrasing, and non-fatal patterns with copy-paste style comments.
   - Evidence: `webapp/routers/sniper.py:1-18`, `webapp/routers/saved_searches.py:1-17`.
5. `src/components/RoverDashboard.tsx` plus `src/hooks/useRoverRecommendations.ts`
   - Strong signal: the UI layer contains business rules, refresh logic, and multiple overlapping recommendation flows.
   - Evidence: `src/components/RoverDashboard.tsx:46-123`, `src/hooks/useRoverRecommendations.ts:24-80`.

## G. Phase 2 Verification Commands

Use these in a clean shell with the intended environment variables set for the service under test.

```bash
# 1) Prove the score module import shape and catch hard failures early
python -m py_compile backend/ingest/score.py scripts/backfill_grades.py webapp/routers/ingest.py backend/main.py webapp/main.py webapp/routers/rover.py webapp/routers/sniper.py webapp/routers/saved_searches.py

# 2) Verify whether the score module is actually importable
python -c "from backend.ingest.score import score_deal"

# 3) Confirm the backfill script can import its dependency
python -c "import scripts.backfill_grades"

# 4) Start the app with representative env and inspect startup logs
env SECRET_KEY=test SUPABASE_SERVICE_ROLE_KEY=test TELEGRAM_BOT_TOKEN=test APIFY_WEBHOOK_SECRET=test APIFY_TOKEN=test uvicorn backend.main:app --host 127.0.0.1 --port 8000

# 5) Sanity-check health
curl -sS http://127.0.0.1:8000/healthz

# 6) Verify Rover auth gate and response shape
curl -i -H 'Authorization: Bearer test' 'http://127.0.0.1:8000/api/rover/recommendations?user_id=test&limit=1'

# 7) Verify the Apify webhook auth gate
curl -i -X POST \
  -H 'Content-Type: application/json' \
  -H 'X-Apify-Webhook-Secret: test' \
  http://127.0.0.1:8000/api/ingest/apify \
  -d '{}'

# 8) Verify the pass endpoint behavior on DB failure vs success
curl -i -X POST -H 'Authorization: Bearer test' http://127.0.0.1:8000/api/ingest/opportunities/test-pass-id/pass

# 9) Verify sniper and saved-search internal cron endpoints reject missing secrets
curl -i -X POST -H 'Authorization: Bearer test' http://127.0.0.1:8000/api/sniper/check
curl -i -X POST -H 'Authorization: Bearer test' http://127.0.0.1:8000/api/saved-searches/check

# 10) Verify the deprecated entrypoint does not get used accidentally
python -c "import webapp.main; print(webapp.main.app.title)"
```

## H. Uncertainties / Requires Runtime Verification

- `UNKNOWN`: I did not execute the webhook, DeepSeek, Telegram, Supabase, or Redis paths against live services in this phase.
- `UNKNOWN`: whether `backend.main` runs with multiple workers on Railway needs runtime / deployment verification to quantify duplicate-scheduler risk.
- `UNKNOWN`: whether the hardcoded key fallbacks in `webapp/routers/ingest.py` are active credentials or dead placeholders cannot be proven statically.
- `UNKNOWN`: whether the browser-side Apify token is actually populated in deployed builds requires environment review.
- `UNKNOWN`: whether every workflow job is still enabled in the current GitHub repository state should be checked in Phase 2 with the workflow runs page.

## Bottom Line

The highest-confidence fractures are concentrated in ingest/scoring, alerting, and credential handling. The most important unresolved question for Phase 2 is whether the broken score module is already causing runtime fallback or outright import failure in production; static inspection strongly suggests that path is unsafe either way.
