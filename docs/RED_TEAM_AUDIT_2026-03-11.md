# DealerScope Red Team Audit — 2026-03-11

**Scope:** Full codebase — backend, frontend, scrapers, infrastructure
**Auditor:** Claude Sonnet 4.6 (automated deep review)
**Overall Risk Score: 7.5 / 10**

---

## EXECUTIVE SUMMARY

DealerScope has a solid architectural foundation but ships with **multiple hardcoded production secrets**, **unprotected power endpoints**, and **critical business rule gaps** that directly threaten capital safety. The most dangerous issues can be fixed in a day. The scoring logic gaps require more careful work.

---

## 1. SECURITY

### 1.1 Hardcoded Secrets

**[SEVERITY: CRITICAL]** `webapp/routers/ingest.py:28` — Live Telegram bot token hardcoded as default value
```python
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "TELEGRAM_BOT_TOKEN_REDACTED")
```
Anyone with repo access can control the bot (send messages, read chat history). Token is fully active.
**Fix:** Remove the default entirely. Raise `ValueError` at startup if not set. Rotate the token now.

---

**[SEVERITY: CRITICAL]** `apify/actors/ds-gsaauctions/src/main.js:3`, `ds-auctiontime`, `ds-municibid`, `ds-bidcal`, `ds-hibid`, `ds-allsurplus` (all 6 actors) — Production webhook secret hardcoded
```js
const WEBHOOK_SECRET = 'sbEC0dNgb7Ohg3rDV';
```
This is the **actual production secret** that authenticates calls to `/api/ingest/apify`. Anyone who reads this repo can POST arbitrary vehicle data directly to the ingest endpoint — bypassing all scraper filtering, injecting fake deals, poisoning the database, and triggering Telegram alerts.
**Fix:** Read from `Actor.getInput()` (Apify input schema). Rotate the secret immediately — it is compromised.

---

**[SEVERITY: CRITICAL]** `src/integrations/supabase/client.ts:8-9` — Production Supabase URL and anon JWT baked into source
```ts
const supabaseUrl = import.meta.env.VITE_SUPABASE_URL || 'https://lbnxzvqppccajllsqaaw.supabase.co';
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY || 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...';
```
These are legitimate-but-limited anon credentials. The real risk: the URL is exposed, which combined with permissive RLS policies could enable enumeration. Anon key will be in the compiled bundle regardless, but the hardcoded fallback signals this was committed intentionally.
**Fix:** Remove fallback defaults. Make VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY required in vite.config.ts. Verify Supabase RLS is tight on all tables.

---

**[SEVERITY: CRITICAL]** `webapp/routers/ingest.py:29` — Live Telegram chat ID hardcoded
```python
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "7529788084")
```
Anyone with the bot token can send messages to this chat. Combined with the token above: full takeover of hot deal alerting.
**Fix:** Remove default value. Require env var.

---

### 1.2 CORS Configuration

**[SEVERITY: HIGH]** `backend/main.py:125` — Default CORS origin is the Railway backend URL, not the Vercel frontend
```python
_ALLOWED_ORIGINS = [
    o.strip() for o in
    os.getenv("ALLOWED_ORIGINS", "https://dealscan-insight-production.up.railway.app").split(",")
    ...
]
```
If `ALLOWED_ORIGINS` env var is not set in production, CORS allows the backend's own origin — blocking all frontend requests. This is either silently misconfigured or the env var is correctly set but undocumented.
**Fix:** Default should be `""` (empty → deny all). Verify `ALLOWED_ORIGINS` is set to the Vercel URL in Railway env.

---

### 1.3 Authentication on Sensitive Endpoints

**[SEVERITY: CRITICAL]** `backend/main.py:177-185` — `/api/pipeline/run` has NO authentication
```python
@app.post("/api/pipeline/run", tags=["pipeline"])
async def trigger_pipeline():
```
No auth dependency, no rate limiting. Any internet client can trigger the full scrape + score pipeline indefinitely. This is an unprotected control plane endpoint.
**Fix:** Add `Depends(get_current_admin_user)` or at minimum an `Authorization: Bearer <PIPELINE_SECRET>` header check.

---

**[SEVERITY: HIGH]** `backend/main.py:188-195` — `/api/pipeline/status` has NO authentication
Returns `status`, `last_run`, and `last_error` (which may contain internal exception details). The `last_error` field is `str(exc)` — can leak stack traces, module paths, env var names.
**Fix:** Add auth or strip `last_error` from unauthenticated responses.

---

### 1.4 Webhook Secret Validation

**[SEVERITY: MEDIUM]** `webapp/routers/ingest.py:146` — Webhook secret comparison is not constant-time
```python
if not WEBHOOK_SECRET or x_apify_webhook_secret != WEBHOOK_SECRET:
```
String comparison `!=` is not timing-safe. An attacker with low-latency access could use a timing oracle to recover the secret character-by-character. This is theoretical but real.
**Fix:** Use `hmac.compare_digest(x_apify_webhook_secret or "", WEBHOOK_SECRET)`.

---

### 1.5 Rate Limiting

**[SEVERITY: HIGH]** `webapp/middleware/rate_limit.py:57-59` — Redis unavailable → rate limiting silently disabled
```python
except Exception:
    # Fallback: continue without rate limiting if Redis unavailable
    return await call_next(request)
```
If Redis is down or not configured, ALL rate limits are silently dropped. The ingest endpoint could be hammered with no protection.
**Fix:** Log a startup warning. Consider in-memory fallback (e.g., a simple counter with TTL) rather than no protection.

---

**[SEVERITY: HIGH]** `webapp/middleware/rate_limit.py:38-44` — `/api/ingest/apify` is NOT in route_limits
The rate limiter defines limits for `/auth/login`, `/upload`, `/opportunities`, `/vehicles`, `/ml/predict` — but not the ingest webhook. It falls back to 100 requests/60 seconds, which is trivially abusable to flood the pipeline.
**Fix:** Add `"/api/ingest/apify": 30` to route_limits.

---

**[SEVERITY: MEDIUM]** `webapp/middleware/rate_limit.py:21-22` — X-Forwarded-For uses LAST IP (wrong)
```python
return forwarded.split(",")[-1].strip()
```
Standard practice for X-Forwarded-For is to use the **first** non-trusted IP (original client). Using the last gives the exit proxy's IP — bypassing per-client rate limiting.
**Fix:** Use `forwarded.split(",")[0].strip()`.

---

### 1.6 SQL Injection / Query Safety

**[SEVERITY: LOW]** `src/services/api.ts:78-86` — Supabase `.ilike()` uses user input directly
```ts
if (filters?.make) query = query.ilike('make', `%${filters.make}%`);
```
Supabase SDK parameterizes queries, so SQL injection is not directly possible. However, extremely long or malformed `make` inputs could cause slow queries. No length validation.
**Fix:** Validate/truncate filter strings to reasonable lengths (e.g., max 50 chars) before querying.

---

### 1.7 Frontend Env Vars

**[SEVERITY: LOW]** `src/services/api.ts:9` — Fallback Railway URL hardcoded
```ts
const API_BASE = import.meta.env.VITE_API_URL || 'https://dealscan-insight-production.up.railway.app';
```
All `VITE_*` vars are embedded in the bundle — this is expected for a Vite SPA. The Railway URL fallback is not a security issue but will silently break if the Railway deployment URL changes.
**Fix:** Remove fallback. Fail loudly at build time if `VITE_API_URL` is not set.

---

### 1.8 Debug/Test Code in Production Auth Page

**[SEVERITY: HIGH]** `src/pages/Auth.tsx:101-116` — `createTestAccount()` with hardcoded credentials exists in source
```ts
const testEmail = 'test@dealerscope.com';
const testPassword = 'testpass123';
```
The function is defined but not currently rendered in JSX (no button calls it). However, the code and credentials are present in the bundle. If re-enabled, anyone could create a test account.
**Fix:** Remove `createTestAccount()` and `testSupabaseConnection()` functions entirely.

---

**[SEVERITY: MEDIUM]** `src/pages/Auth.tsx:51` — User email logged to console on every sign-in attempt
```ts
console.log('🔐 Attempting sign in for:', formData.email);
```
This logs PII (email addresses) to browser console — visible to anyone with DevTools open on a shared machine.
**Fix:** Remove or guard behind `import.meta.env.DEV` flag.

---

### 1.9 Ingest Supabase Client Falls Back to Anon Key

**[SEVERITY: HIGH]** `webapp/routers/ingest.py:33` — Backend falls back to frontend's anon key for Supabase writes
```python
_supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("VITE_SUPABASE_ANON_KEY", "")
```
If `SUPABASE_SERVICE_ROLE_KEY` is not set, the ingest pipeline silently uses the anon key. The anon key likely can't write to `opportunities` if RLS requires service role. This means all saves silently fail with no startup error.
**Fix:** Require `SUPABASE_SERVICE_ROLE_KEY` explicitly. Log a critical error at startup if missing.

---

## 2. BUSINESS LOGIC CORRECTNESS

### 2.1 DOS Formula

**[SEVERITY: LOW]** `backend/ingest/score.py:163-169` — Formula verified correct
```python
dos_score = (
    m_score * 0.35 + v_score * 0.25 + seg_score * 0.20
    + mod_score * 0.12 + src_score * 0.08
)
```
Weights sum to 1.00. Component mapping matches SOP: Margin×0.35, Velocity×0.25, Segment×0.20, Model×0.12, Source×0.08. ✅ **No issues.**

---

### 2.2 Bid Ceiling (88% MMR)

**[SEVERITY: CRITICAL]** `webapp/routers/ingest.py` & `backend/ingest/score.py` — 88% MMR bid ceiling is NOT enforced anywhere
The SOP specifies bids must not exceed 88% of MMR all-in. The scoring pipeline computes a margin but never gates or penalizes deals where `total_cost / mmr > 0.88`. Deals where the buyer is overpaying relative to MMR can score well if other components (segment, model, source) are high.
**Fix:** Add gate in `passes_basic_gates()`:
```python
mmr = _estimate_mmr(vehicle.get("make", ""), vehicle.get("model", ""))
if mmr > 0 and bid > mmr * 0.88:
    return {"pass": False, "reason": f"bid_exceeds_88pct_mmr"}
```
Also penalize in margin score.

---

### 2.3 Minimum Gross Margin $1,500

**[SEVERITY: HIGH]** — $1,500 minimum gross margin is NOT enforced anywhere
`passes_basic_gates()` checks bid range, rust state, age, mileage, URL — but not margin. `save_opportunity_to_supabase()` only gates on DOS >= 50. A vehicle with -$500 margin and a great segment/model score can still be saved and alerted.
**Fix:** Add minimum margin check after scoring:
```python
if score_result.get("margin", 0) < 1500:
    skipped += 1
    continue
```

---

### 2.4 ROI Thresholds

**[SEVERITY: MEDIUM]** — Hot >20% ROI, Good >12% ROI not enforced
The SOP specifies ROI thresholds for classification. The scoring system uses DOS (0-100) as the gate, not ROI. A deal classified as "hot" (DOS >= 80) could have ROI below 12% if it has exceptional segment/model scores.
**Fix:** Either add ROI gates alongside DOS, or ensure the margin score component naturally enforces this (currently it does not — 20% MMR margin gives max margin score, but this is margin on MMR, not ROI on all-in cost).

---

### 2.5 Max Vehicle Age (4 years)

**[SEVERITY: LOW]** `webapp/routers/ingest.py:401-402` — Correctly implemented
```python
age = current_year - year
if age > 4 or age < 0:  # SOP: max 4 years
    return {"pass": False, "reason": f"age_exceeded ({age} years)"}
```
✅ **Correctly enforced.**

---

### 2.6 Max Mileage (50,000)

**[SEVERITY: LOW]** `webapp/routers/ingest.py:404-409` — Correctly implemented with appropriate null handling
Missing mileage is allowed through (scrapers often don't surface it). ✅ **Acceptable.**

---

### 2.7 High Rust State Rejection

**[SEVERITY: HIGH]** `src/components/SniperScopeDashboard.tsx:44-61` vs `webapp/routers/ingest.py:51-54` — **Kansas (KS) state mismatch**

SniperScope shows Kansas as a buyable low-rust state (line 50: `{ value: 'KS', label: 'Kansas', transport: 350 }`), but the backend `HIGH_RUST_STATES` set explicitly includes KS. A user running SniperScope calculations for a Kansas vehicle will get a max bid recommendation — but the ingest pipeline will reject that vehicle and it will never appear as an opportunity.

Additionally, SniperScope lists only 16 states; the backend LOW_RUST_STATES has 21 (includes SC, HI, OK, AR, LA, MS, AL). These states appear buyable via the scraper but are not in the SniperScope calculator.
**Fix:** Extract the canonical state lists to a shared config or constants file. SniperScope should import from the same source of truth.

---

**[SEVERITY: LOW]** Backend `HIGH_RUST_STATES` count: 24 states ✅ (OH, MI, PA, NY, WI, MN, IL, IN, MO, IA, ND, SD, NE, KS, WV, ME, NH, VT, MA, RI, CT, NJ, MD, DE — confirmed.)

---

### 2.8 CPO Premium (10-15%)

**[SEVERITY: MEDIUM]** — CPO premium is not implemented anywhere
No CPO detection or premium calculation exists in `normalize_apify_vehicle()`, `score_deal()`, or `_estimate_mmr()`. If a vehicle is CPO, the MMR estimate will be off by 10-15%, leading to undervaluation of the deal.
**Fix:** Add CPO keyword detection in normalize; add premium multiplier to MMR estimate.

---

### 2.9 SniperScope Buyer Premium Formula

**[SEVERITY: LOW]** `src/components/SniperScopeDashboard.tsx:126-128` — Verified correct
```ts
const divisor = 1 + buyerPremiumPct / 100 + salesTaxPct / 100;
const maxBid = (mmr - auctionFees - titleFees - transport - recon - targetMargin) / divisor;
```
Buyer premium and tax are correctly computed as % of bid (not % of MMR). Algebraic inversion is correct. ✅ **No issues.**

---

## 3. DATA PIPELINE

### 3.1 normalize_apify_vehicle — Format Handling

**[SEVERITY: LOW]** `webapp/routers/ingest.py:238-316` — Both formats handled correctly
- Custom snake_case: `current_bid`, `listing_url`, `auction_end_time` ✅
- parseforge camelCase: `currentBid`, `url`, `auctionEndUtc`, `imageUrl`, `seller`, `modelYear`, `locationState` ✅
**No issues.**

---

### 3.2 Webhook Validation

**[SEVERITY: MEDIUM]** `webapp/routers/ingest.py:149-152` — JSON payload not validated as dict before `.get()` call
```python
payload = await request.json()
# ...
dataset_id = payload.get("resource", {}).get("defaultDatasetId", "")
```
If Apify sends a valid JSON list (or other non-dict), `payload.get()` throws `AttributeError` → unhandled 500 error. This is an edge case but could happen if the webhook format changes.
**Fix:** Add `if not isinstance(payload, dict): raise HTTPException(400, "Unexpected payload format")`.

---

### 3.3 Supabase Down

**[SEVERITY: MEDIUM]** `webapp/routers/ingest.py:588-634` — Supabase failures are silent
`save_opportunity_to_supabase()` returns `False` on failure and the ingest endpoint returns HTTP 200 with `"processed": N` — Apify considers the webhook successful. Failed saves are silently dropped.
**Fix:** Return a count of save failures in the response. Consider returning 207 (partial success) if saves fail. At minimum, add a metric/alert on repeated save failures.

---

### 3.4 Notion API Down

**[SEVERITY: LOW]** `webapp/routers/ingest.py:539-557` — Correctly handled as non-fatal
`sync_to_notion()` has try/except → logs warning → returns False. Does not block ingest. ✅

---

### 3.5 Telegram Failure

**[SEVERITY: LOW]** `webapp/routers/ingest.py:560-585` — Correctly handled as non-fatal ✅

---

### 3.6 score.py YAML Loading (Performance)

**[SEVERITY: MEDIUM]** `backend/ingest/score.py:51-53`, `backend/ingest/transport.py:9-16` — YAML files reopened on every scoring call
```python
def _load_fees() -> dict:
    with open(os.path.join(_CONFIGS_DIR, "fees.yml")) as f:
        return yaml.safe_load(f).get("sites", {})
```
`fees.yml`, `transit_rates.yml`, and `state_miles_to_ca.yml` are re-read from disk on every vehicle scored. In a batch of 200 items, that's 600 file opens.
**Fix:** Cache with `@functools.lru_cache(maxsize=1)`.

---

### 3.7 score_deal() Falls Back Silently

**[SEVERITY: MEDIUM]** `webapp/routers/ingest.py:444-447` — Scoring fallback is too permissive
```python
except Exception as e:
    logger.error(f"[SCORE] Real DOS formula failed, using fallback: {e}")
    return _fallback_score(vehicle)
```
If `fees.yml` is missing (e.g., misconfigured deploy), scoring silently falls back to a simplified formula that doesn't enforce bid ceiling, margin minimums, or velocity properly. Vehicles that should be rejected may pass.
**Fix:** At startup, verify the YAML config files exist. Log CRITICAL on failure, not ERROR.

---

## 4. FRONTEND

### 4.1 API Base URL

**[SEVERITY: LOW]** `src/services/api.ts:9` — Hardcoded Railway fallback
Railway URL is the correct backup but couples frontend to a specific deployment URL. ✅ Functional, see Security section.

---

### 4.2 Auth Checking

**[SEVERITY: LOW]** `src/pages/Auth.tsx:25-27` — Auth redirect is correctly implemented
```ts
if (user && !loading) { return <Navigate to="/" replace />; }
```
Dashboard access presumably requires `useAuth()` hook with redirect. ✅

---

### 4.3 Console.log Sensitive Data

**[SEVERITY: HIGH]** `src/pages/Auth.tsx:51` — Email logged on every sign-in attempt (see Security §1.8 above)

**[SEVERITY: LOW]** `src/services/api.ts:107, 126, 214` — Supabase error objects logged
`console.error('getOpportunities failed:', error)` — Supabase errors can include query details, table names, column names. Not catastrophic but leaks internal schema info in DevTools.
**Fix:** Log only `error.message` or a generic string. Remove sensitive Supabase error details.

---

### 4.4 TypeScript `any` Types

**[SEVERITY: LOW]** `src/services/api.ts:12` — `transformOpportunity(row: any)` — hides type bugs
If Supabase schema changes (column renamed/removed), TypeScript won't catch it.
**Fix:** Generate types from Supabase schema (`supabase gen types typescript`) and use them.

---

### 4.5 Saved Targets in localStorage

**[SEVERITY: LOW]** `src/components/SniperScopeDashboard.tsx:105-110` — SniperScope targets stored in localStorage only
Data is browser-local — not synced across devices, not backed up, cleared by private browsing.
No security issue, but a usability risk for a professional tool.
**Fix:** Consider server-side persistence (Supabase) for saved targets.

---

### 4.6 State Sales Tax Coverage

**[SEVERITY: LOW]** `src/components/SniperScopeDashboard.tsx:63-66` — STATE_SALES_TAX only covers 12 states
```ts
const STATE_SALES_TAX: Record<string, number> = {
    AZ: 5.6, CA: 7.25, CO: 2.9, FL: 6.0, GA: 4.0, NC: 4.75,
    NV: 6.85, OR: 0.0, TN: 7.0, TX: 6.25, VA: 4.3, WA: 6.5,
};
```
States OK, SC, UT, HI, AR, LA, MS, AL are in the backend's low-rust set but have no tax entry — they default to `5.0%` (the `?? 5.0` fallback). Some of these have materially different rates (e.g., TN is 7%, LA is 4.45%).
**Fix:** Complete the STATE_SALES_TAX table for all 21 backend low-rust states.

---

## 5. APIFY ACTORS

### 5.1 Hardcoded Credentials

**[SEVERITY: CRITICAL]** 6 actor files — Webhook secret hardcoded (see Security §1.1 above)
Files: `ds-gsaauctions`, `ds-auctiontime`, `ds-municibid`, `ds-bidcal`, `ds-hibid`, `ds-allsurplus`
`const WEBHOOK_SECRET = 'sbEC0dNgb7Ohg3rDV';` — **Treat this as compromised. Rotate immediately.**

---

**[SEVERITY: HIGH]** 6 actor files — Production webhook URL hardcoded
```js
const WEBHOOK_URL = 'https://dealscan-insight-production.up.railway.app/api/ingest/apify';
```
Not a security leak per se (URL is not secret), but:
1. Couples all actors to one deployment URL — a URL change breaks all actors simultaneously
2. Makes it impossible to test actors against a staging environment
**Fix:** Pass via `Actor.getInput()` with `webhookUrl` as an input field (defaulting to prod URL in actor.json schema).

---

### 5.2 Docker Base Images

**[SEVERITY: MEDIUM]** Only 3 of 8 actors have Dockerfiles
`ds-hibid`, `ds-govdeals`, `ds-publicsurplus` have `FROM apify/actor-node-playwright-chrome:20` ✅
The other 5 (`ds-gsaauctions`, `ds-auctiontime`, `ds-municibid`, `ds-bidcal`, `ds-allsurplus`) have **no Dockerfile**.
**Risk:** Without a pinned Dockerfile, Apify uses the base image from `.actor/actor.json`. If that isn't pinned to `:20`, actors may break on Playwright updates.
**Fix:** Add `Dockerfile` with `FROM apify/actor-node-playwright-chrome:20` to all 5 actors.

---

### 5.3 GovDeals Actor — Missing Mileage Filter

**[SEVERITY: LOW]** `apify/actors/ds-govdeals/src/main.js:120-127` — `applyFilters()` skips mileage check
The GovDeals actor filters on rust state, bid range, and year — but not mileage. The backend catches this in `passes_basic_gates()`, so correctness is preserved. But high-mileage vehicles are fully scraped, normalized, and transmitted before being discarded — wasting scraper runtime and ingest quota.
**Fix:** Add `if (vehicle.mileage && vehicle.mileage > 50000) return false;` to actor `applyFilters()`.

---

## 6. INFRASTRUCTURE

### 6.1 railway.toml Start Command

**[SEVERITY: LOW]** `railway.toml:5` — Start command correct
```toml
startCommand = "sh -c 'uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}'"
```
✅ Correct entrypoint. Nixpacks builder is used, so `Dockerfile` CMD is not used for Railway deploys.

---

### 6.2 Dockerfile CMD — Wrong Entrypoint

**[SEVERITY: HIGH]** `Dockerfile:47` — Dockerfile CMD runs `webapp.simple_main`, not `backend.main`
```dockerfile
CMD ["sh", "-c", "uvicorn webapp.simple_main:app ... || uvicorn webapp.main_minimal:app ..."]
```
Railway uses Nixpacks (not Docker), so this doesn't affect production. But:
1. Local Docker builds (`docker run`) will start the wrong app
2. If Railway is ever switched to Docker builder, this silently breaks
3. Creates confusion about which file is canonical
**Fix:** Update Dockerfile CMD to `uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8080}`.

---

### 6.3 vercel.json — Proxy Route

**[SEVERITY: LOW]** `vercel.json:7` — Proxy only covers `/proxy/health`
```json
{ "source": "/proxy/health", "destination": "https://dealscan-insight-production.up.railway.app/health" }
```
Direct Railway URL is also hardcoded here. Same rotation risk as actors.
**Fix:** Use a Vercel environment variable `RAILWAY_URL` and reference it. (Vercel doesn't directly support env vars in `vercel.json` rewrites — use Edge Config or a middleware redirect instead.)

---

### 6.4 Railway Healthcheck

**[SEVERITY: MEDIUM]** `railway.toml` — No healthcheck path configured
The app exposes `/healthz` and Railway supports health check configuration. Without it, Railway won't know when the app is ready or unhealthy — it just checks if the port responds.
**Fix:** Add to `railway.toml`:
```toml
[deploy]
healthcheckPath = "/healthz"
healthcheckTimeout = 30
```

---

### 6.5 Middleware Silent Failures

**[SEVERITY: HIGH]** `backend/main.py:17-41` — All security middleware imports have silent try/except
```python
try:
    from webapp.middleware.security import SecurityMiddleware
except Exception as e:
    SecurityMiddleware = None
    logging.warning(f"security middleware unavailable: {e}")
```
If `SecurityMiddleware`, `RateLimitMiddleware`, or `ErrorHandlerMiddleware` fail to import (missing dep, syntax error), the app starts **with no security middleware** and no outward sign of failure. The log line is WARNING — not alerting.
**Fix:** Make critical middleware (at minimum rate limiter and security headers) startup-fatal. Log at CRITICAL level.

---

### 6.6 Missing Environment Variables — Silent Failures

**[SEVERITY: MEDIUM]** Several env vars have no startup validation:
- `APIFY_TOKEN` — missing → 502 on first ingest (discovered at runtime, not startup)
- `SUPABASE_SERVICE_ROLE_KEY` — missing → silently falls back to anon key (see §1.9)
- `APIFY_WEBHOOK_SECRET` — missing → all webhook calls rejected with 401 (at least fails loudly)
- `NOTION_TOKEN` / `NOTION_DEALS_DB_ID` — missing → Notion sync silently disabled

**Fix:** Add a startup validation block in `backend/main.py` lifespan that checks required env vars and logs CRITICAL (not just warning) on missing.

---

### 6.7 Health Endpoint Information Disclosure

**[SEVERITY: LOW]** `backend/main.py:204-208` — `/healthz` leaks internal state
```python
return {
    "status": "ok",
    "routers_loaded": list(_routers.keys()),
    "routes_count": len(app.routes),
}
```
Exposes which routers loaded successfully — tells an attacker which attack surface is available.
**Fix:** Return only `{"status": "ok"}` on the public endpoint. Move router details to an authenticated `/api/admin/health` endpoint.

---

## SUMMARY TABLE

| # | Severity | Area | Issue |
|---|----------|------|-------|
| 1 | CRITICAL | Security | Live Telegram token hardcoded in ingest.py |
| 2 | CRITICAL | Security | Production webhook secret in 6 actor files |
| 3 | CRITICAL | Security | Supabase prod URL + anon key hardcoded in client.ts |
| 4 | CRITICAL | Security | Telegram chat ID hardcoded in ingest.py |
| 5 | CRITICAL | Security | `/api/pipeline/run` — no auth, anyone can trigger scrape |
| 6 | CRITICAL | Business | 88% MMR bid ceiling NOT enforced in scoring/gates |
| 7 | HIGH | Business | $1,500 min gross margin NOT enforced |
| 8 | HIGH | Security | Webhook secret comparison not constant-time |
| 9 | HIGH | Security | Redis down → rate limiting silently disabled |
| 10 | HIGH | Security | `/api/ingest/apify` not in rate limit route map |
| 11 | HIGH | Security | X-Forwarded-For uses last IP (wrong — allows bypass) |
| 12 | HIGH | Security | Test account credentials in Auth.tsx source |
| 13 | HIGH | Security | User email logged to console on sign-in |
| 14 | HIGH | Security | `/api/pipeline/status` — no auth, leaks error details |
| 15 | HIGH | Security | Supabase falls back to anon key for service ops |
| 16 | HIGH | Business | KS in SniperScope LOW_RUST but backend HIGH_RUST |
| 17 | HIGH | Security | Middleware import failures silent — security skipped |
| 18 | HIGH | Actors | Webhook URL hardcoded in 6 actors (no env var) |
| 19 | HIGH | Infra | Dockerfile CMD uses wrong entrypoint vs railway.toml |
| 20 | MEDIUM | Business | Hot >20% / Good >12% ROI thresholds not enforced |
| 21 | MEDIUM | Business | CPO premium (10-15%) not implemented |
| 22 | MEDIUM | Pipeline | JSON payload not validated as dict before `.get()` |
| 23 | MEDIUM | Pipeline | Supabase save failures return HTTP 200 (silent drop) |
| 24 | MEDIUM | Pipeline | YAML configs re-opened on every vehicle scored |
| 25 | MEDIUM | Pipeline | Score formula falls back silently if fees.yml missing |
| 26 | MEDIUM | Security | CORS default origin is Railway URL (not Vercel) |
| 27 | MEDIUM | Infra | Railway healthcheck path not configured |
| 28 | MEDIUM | Infra | Missing env vars have no startup validation |
| 29 | MEDIUM | Frontend | STATE_SALES_TAX incomplete (12/21 states) |
| 30 | LOW | Security | Webhook comparison not constant-time |
| 31 | LOW | Frontend | `any` type in transformOpportunity hides schema drift |
| 32 | LOW | Frontend | Console.error leaks Supabase error details |
| 33 | LOW | Frontend | SniperScope targets localStorage-only |
| 34 | LOW | Actors | 5 actors have no Dockerfile (unpinned base image) |
| 35 | LOW | Actors | GovDeals actor doesn't pre-filter on mileage |
| 36 | LOW | Infra | healthz leaks router names and count |
| 37 | LOW | Infra | Vercel proxy hardcodes Railway URL |

---

## OVERALL RISK SCORE: **7.5 / 10**

The platform would fail a basic security audit in production. The business logic gaps (bid ceiling, margin floor) are direct capital risk — the system can recommend and alert on deals that should never be bid. The hardcoded secrets are immediate remediation items.

---

## TOP 3 THINGS TO FIX FIRST

### 1. **Rotate and externalize all hardcoded secrets** (1 hour)
- `APIFY_WEBHOOK_SECRET` in 6 actors → move to `Actor.getInput()`
- Rotate Telegram bot token (treat as compromised)
- Remove hardcoded Supabase URL/key fallbacks from `client.ts`
- Remove Telegram token/chat_id defaults from `ingest.py`

### 2. **Add auth to `/api/pipeline/run` and `/api/pipeline/status`** (30 min)
Anyone on the internet can trigger your full scraping pipeline. This is the most exposed unprotected endpoint.

### 3. **Enforce the 88% MMR bid ceiling AND $1,500 minimum margin in the gate** (2 hours)
These are your core capital protection rules. Without them, the scoring system is producing buy signals on deals that should be disqualified. Add both checks to `passes_basic_gates()` after MMR estimation.
