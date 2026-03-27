# Round 2 Audit — Remaining 7 Files
_Claude (direct read) + Gemini 3.1 Pro | 2026-03-26_
_Files: auth.py, sniper.py, opportunities.py, admin.py, heuristic_scorer.py, normalize.py, alert_gating.py_

---

## 🔴 CRITICAL

**C1 | alert_gating.py:12**
Investment grades defined as "Gold"/"Platinum" but business rules say "Premium"/"Standard". Every alert is being blocked because the grade check never matches.
FIX: `ALERT_ALLOWED_GRADES = frozenset({"Premium", "Standard"})`

**C2 | alert_gating.py:123**
Missing bid ceiling enforcement — alert can fire on a deal that violates 0.88/0.80 ceiling.
FIX: Add ceiling check in evaluate_alert_gate before returning eligible=True.

**C3 | opportunities.py:273**
IDOR — `save_opportunity` overwrites the global `Opportunity.user_id`. If User A saves an opportunity, it overwrites User B's state for that same opportunity.
FIX: Create a `UserOpportunity` association table for user-specific save/ignore/pass actions.

**C4 | opportunities.py:321**
Same IDOR — `ignore_opportunity` has identical global state mutation problem.
FIX: Same as C3.

**C5 | sniper.py:238**
No DealerScope business rules enforced when arming a sniper target — accepts any max_bid for any vehicle with no ceiling, margin, age, mileage, or rust state checks.
FIX: Validate vehicle against tier rules before allowing target to be armed.

---

## 🟠 HIGH

**H1 | sniper.py:35-38**
Uses `SUPABASE_SERVICE_ROLE_KEY` bypassing RLS — same risk as rover.py.
FIX: Use anon key for user-facing operations, service key only for internal cron.

**H2 | normalize.py:6**
`.title()` destroys acronyms — "BMW" → "Bmw", "GMC" → "Gmc", "VW" → "Vw". Breaks all downstream exact-match lookups and pricing tier classification.
FIX: Use a known-acronyms whitelist: `if m.upper() in {"BMW", "GMC", "VW", "RAM"}: m = m.upper()`

**H3 | auth.py**
Backup TOTP codes not validated during login — user can be locked out permanently if phone is lost with no recovery path.
FIX: Check backup codes in login flow, consume on use.

**H4 | sniper.py — empty SNIPER_CHECK_SECRET**
If `SNIPER_CHECK_SECRET` env var is not set, it defaults to `""`. The cron check endpoint compares against `""` — any request with an empty Authorization header passes the secret check.
FIX: `if not SNIPER_CHECK_SECRET: raise RuntimeError("SNIPER_CHECK_SECRET not configured")`

---

## 🟡 MEDIUM

**M1 | admin.py:29**
`func.interval('24 hours')` is PostgreSQL-specific — will 500 on other DB engines.
FIX: Use `datetime.now(timezone.utc) - timedelta(hours=24)` instead.

**M2 | auth.py:320-323**
Password change only enforces 8 char minimum — no complexity requirements.
FIX: Add uppercase, number, symbol requirements.

**M3 | heuristic_scorer.py**
`build_preference_vector` has no bounds on output scores — many events could accumulate unbounded affinity values.
FIX: Cap affinity scores per dimension.

**M4 | alert_gating.py — min_confidence=55.0**
55% confidence threshold is too low for financial decisions. Deals with unreliable pricing data will alert.
FIX: Raise to 70% minimum or make configurable per lane.

---

## ✅ Clean (No Issues Found)
- `admin.py` — thin, properly gated behind admin auth
- `heuristic_scorer.py` — logic correct per spec, no security issues
- `normalize.py` — except the .title() acronym bug above
- `opportunities.py` auth and pagination — solid

---

## Key New Findings vs Round 1

| Finding | Severity | File |
|---------|----------|------|
| Alert grades wrong ("Gold/Platinum" vs "Premium/Standard") | 🔴 CRITICAL | alert_gating.py |
| Alerts firing on ceiling-violating deals | 🔴 CRITICAL | alert_gating.py |
| Save/ignore IDOR — overwrites all users' state | 🔴 CRITICAL | opportunities.py |
| Sniper accepts any bid, no business rules | 🔴 CRITICAL | sniper.py |
| normalize.py .title() breaks BMW/GMC/VW lookups | 🟠 HIGH | normalize.py |
| Empty SNIPER_CHECK_SECRET passes auth check | 🟠 HIGH | sniper.py |

_DeepSeek R1 findings will be added when complete_
SEVERITY: CRITICAL  
FILE: api.ts  
ISSUE: Exposed hardcoded APIFY_TOKEN in frontend via `import.meta.env.VITE_APIFY_TOKEN` used in `getApifyActorStatus()`. This credential should never be client-side accessible. Attackers can extract token from built JS and abuse Apify API access.  
FIX: Move all Apify API calls to backend services. Replace client-side fetch with authenticated API endpoint that proxies requests through your secured backend.

SEVERITY: CRITICAL  
FILE: api.ts  
ISSUE: Missing authentication checks on multiple direct Supabase database queries (e.g., `buildOpportunityQuery()`, `getDashboardMetrics()`, `getScraperSources()`, `loadHistoricalData()` in AnomalyDetector). Frontend directly queries 'opportunities' table without user session validation, allowing unauthorized data access if RLS is misconfigured.  
FIX: Implement mandatory Row Level Security (RLS) policies on all Supabase tables. Add explicit `user_id` filtering to all queries. Consider migrating all database access through authenticated backend APIs.

SEVERITY: HIGH  
FILE: api.ts  
ISSUE: Auth token leakage risk in `getRoverRecommendations()` and other API calls. Authentication token (`session?.access_token`) passed via URL parameters (`user_id=${userId}`) exposes tokens in server logs and browser history.  
FIX: Pass user context in Authorization header only. Move user_id resolution to backend using the validated JWT token. Remove user_id from URL parameters.

SEVERITY: HIGH  
FILE: AnomalyDetector.ts  
ISSUE: Direct Supabase writes without validation in `createAnomalyAlerts()`. Frontend inserts arbitrary alert data into `user_alerts` table using `supabase.from().insert()`, bypassing backend business logic.  
FIX: Replace direct Supabase insert with authenticated API call. Implement alert creation through backend service with input validation and rate limiting.

SEVERITY: HIGH  
FILE: AnomalyDetector.ts  
ISSUE: Direct Supabase data access in `loadHistoricalData()` and `updateThresholds()`. Client-side code queries sensitive historical opportunity data without access control, potentially exposing competitive intelligence.  
FIX: Restrict data access to aggregated/anonymized sets. Move threshold calculation and historical data loading to backend services with proper authorization.