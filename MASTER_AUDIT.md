# DealerScope Master Red Team Audit
_Synthesized from Codex + Gemini 3.1 Pro — 2026-03-26_

---

## 🔴 CRITICAL (Fix immediately — real money at risk)

### 1. Hardcoded Webhook Secret in Source Code
**FILE:** `apify/actors/ds-allsurplus/src/main.js:391`
**ISSUE:** Production webhook secret is hardcoded. Anyone with repo access can forge ingest webhooks and push fake deals into your pipeline.
**FIX:** Move to env var, rotate the leaked secret NOW.

---

## 🟠 HIGH (Fix this week)

### 2. Business Rules Gutted for Gov Sources
**FILE:** `webapp/routers/ingest.py:1794`
**ISSUE:** `passes_basic_gates()` relaxes ALL rules for gov auction sources — zero bids allowed, rust states get 8yr bypass, age relaxed to 20yr, mileage up to 200k. This directly violates your SOP.
**FIX:** Remove source-specific exceptions. Same rules apply everywhere.

### 3. Mileage Gate Bypassed When Missing
**FILE:** `webapp/routers/ingest.py:1841`
**ISSUE:** If mileage field is missing or malformed, the try block is skipped entirely and vehicle passes. Any scraper omitting mileage bypasses the 50k cap.
**FIX:** Reject vehicles with missing mileage outright.

### 4. Bid Ceiling Hardcoded to 0.88 for ALL Vehicles
**FILE:** `backend/ingest/score.py` → `_compute_max_bid_v2()`
**ISSUE:** Standard lane should use 0.80 ceiling but `_compute_max_bid_v2` hardcodes 0.88 for everything. You're overbidding on Standard lane deals.
**FIX:** Pass `tier` parameter to `_compute_max_bid_v2`, use 0.80 for standard.

### 5. Zero Bid Causes Infinite ROI — False "Hot Deal" Grade
**FILE:** `backend/ingest/score.py`
**ISSUE:** When `bid=0`, division by zero causes `roi_pct` to be infinite. Vehicle gets top score and fires an alert on a deal with no real bid data.
**FIX:** If bid is 0, skip scoring or use a proxy value. Never score a zero-bid vehicle.

### 6. min_margin_target Stored as $500 (Below Business Rule)
**FILE:** `webapp/routers/ingest.py:1651`
**ISSUE:** `normalize_apify_vehicle()` stores `min_margin_target = 500`, which is below the $1500/$2500 SOP. Downstream logic trusting this field makes wrong decisions.
**FIX:** Store actual tier-specific targets ($1500 Premium / $2500 Standard) or leave null until scoring fills it.

### 7. Outcomes Summary Leaks All Users' Data
**FILE:** `webapp/routers/outcomes.py:177`
**ISSUE:** `get_outcomes_summary()` validates JWT but doesn't filter by `user_id`. Any authenticated user can see aggregate metrics for the entire table.
**FIX:** Add `user_id` filter to the query.

### 8. PATCH Outcome Missing user_id in Upsert
**FILE:** `webapp/routers/outcomes.py:147`
**ISSUE:** `patch_outcome()` upserts with `on_conflict="opportunity_id,user_id"` but omits `user_id` from payload — can create null-user rows or corrupt outcome history.
**FIX:** Include and validate `user_id` in payload.

### 9. Rover Auth Error Leaks Stack Trace to Client
**FILE:** `webapp/routers/rover.py:84`
**ISSUE:** `get_user_supabase_client()` returns raw exception text in HTTP error body. Leaks internal implementation details.
**FIX:** Return generic "auth failed" message; log exception server-side only.

### 10. Rust State Filter Not Applied in Score Path
**FILE:** `backend/ingest/score.py`
**ISSUE:** Rust state rejection happens in ingest gate but `determine_vehicle_tier()` doesn't check state — a vehicle from OH/MI/PA can still get scored and stored if it sneaks past the gate.
**FIX:** Pass `state` into `determine_vehicle_tier()` and hard-reject rust states there too.

### 11. Zero/Invalid Bid Bypasses Min-Bid Filters (AllSurplus)
**FILE:** `apify/actors/ds-allsurplus/src/main.js:291`
**ISSUE:** `parseBid()` converts missing/invalid bids to `0`. Min/max checks only run when `bid > 0`. Malformed lots bypass bid filters entirely.
**FIX:** Reject missing/invalid bids instead of normalizing to zero.

---

## 🟡 MEDIUM (Fix this month)

### 12. Broad Exception Handler Hides Scoring Failures — Marks as PASSING
**FILE:** `webapp/routers/ingest.py:1959`
**ISSUE:** Exception around `score_vehicle()` falls back to a synthetic object with `ceiling_pass=True`. Pricing outages silently mark bad data as passing deals.
**FIX:** Fail closed. Never mark a fallback as passing.

### 13. CURRENT_YEAR Frozen at Import Time
**FILE:** `backend/ingest/score.py:6`
**ISSUE:** `CURRENT_YEAR` set once at startup. If process runs across New Year, year-based filters are stale. Also allows future model years through.
**FIX:** Compute year dynamically at call time with `datetime.now().year`.

### 14. pass_opportunity() Swallows DB Write Failures
**FILE:** `webapp/routers/ingest.py:1398`
**ISSUE:** DB write failures are caught and discarded — endpoint returns success even when "pass" was never recorded.
**FIX:** Return HTTP 500 if write fails.

### 15. Duplicate Check Fails Open
**FILE:** `webapp/routers/ingest.py`
**ISSUE:** `check_and_handle_duplicate` catches all exceptions and returns `is_duplicate=False`. DB timeout = all vehicles treated as new = massive duplication.
**FIX:** Raise exception so caller skips/retries the item.

### 16. Rover Fetches select("*") with Large Blobs
**FILE:** `webapp/routers/rover.py:208`
**ISSUE:** Recommendations endpoint fetches all columns including `raw_data` blobs, then sorts in Python. Memory and latency bomb at scale.
**FIX:** Select only columns needed for display, push filtering to DB.

### 17. Timestamp Timezone Bug in Rover Decay
**FILE:** `webapp/routers/rover.py:238`
**ISSUE:** Event timestamps stripped of `Z` and parsed as naive local datetime — skews decay calculations and ranking.
**FIX:** Parse as timezone-aware UTC.

### 18. AllSurplus Memory Leak
**FILE:** `apify/actors/ds-allsurplus/src/main.js:223`
**ISSUE:** `allListings` accumulates every record in memory even though `Actor.pushData()` already persists them. Large runs grow memory without bound.
**FIX:** Remove the in-memory buffer.

### 19. Unguarded Date Parsing Crashes Page Loop (AllSurplus)
**FILE:** `apify/actors/ds-allsurplus/src/main.js:309`
**ISSUE:** `new Date(...).toISOString()` unguarded — one bad auction timestamp throws and aborts the entire page loop, dropping all remaining listings.
**FIX:** Wrap in per-item try/catch.

---

## ✅ Confirmed Correct (Don't Touch)
- `min_margin_target` logic in `score_deal`: $2500 Standard / $1500 Premium ✅
- Auth ownership check on PATCH /outcomes ✅
- Rover auth required on both endpoints ✅

---

## Priority Build Order
1. **TODAY:** Rotate the webhook secret (item #1) — takes 5 mins
2. **TODAY:** Fix zero-bid infinite ROI (item #5) — live money risk
3. **THIS WEEK:** Fix bid ceiling 0.88 for Standard lane (item #4)
4. **THIS WEEK:** Fix gov source rule relaxation (item #2)
5. **THIS WEEK:** Fix mileage gate bypass (item #3)
6. **THIS MONTH:** Everything else in order listed

---
_Codex (gpt-5.4-mini) + Gemini 3.1 Pro — independent audits, cross-validated_
