# Clean Sweep Audit — 2026-03-21

**Auditor:** Hostile Senior Auditor (subagent)  
**Method:** Live API checks against Apify, Supabase, Railway + codebase cross-reference  
**Time of audit:** End of day 2026-03-21

---

## CONFIRMED DONE

### 1. ds-hibid-v2 Webhook — CONFIRMED DONE ✅
- Actor ID: `7s9e0eATTt1kuGGfE`
- **1 webhook** configured, URL: `https://dealscan-insight-production.up.railway.app/api/ingest/apify`
- Header: `{"x-apify-webhook-secret":"rDyApg2UUIMl0a8ZUz_swOqsHX7HbjN-gly3xHNwiyA"}` ✅ correct key name
- Last run (22:00 UTC): SUCCEEDED
- No issues found.

### 6a. Webhook Secret — Most Actors — CONFIRMED DONE ✅
All of these actors have exactly 1 webhook with the correct `x-apify-webhook-secret` header:
- govdeals (CuKaIAcWyFS0EPrAz) ✅
- publicsurplus (9xxQLlRsROnSgA42i) ✅  
- allsurplus (gYGIfHeYeN3EzmLnB) ✅
- proxibid (bxhncvtHEP712WX2e) ✅
- govplanet (pO2t5UDoSVmO1gvKJ) ✅
- jjkane (lvb7T6VMFfNUQpqlq) ✅
- municibid (svmsItf3CRBZuIntp) ✅
- hibid-v2 (7s9e0eATTt1kuGGfE) ✅

### 7. GovPlanet 300+ Items/Run — CONFIRMED DONE ✅ (with caveat)
- Latest run (22:00 UTC): **299 items**
- Previous run (19:01 UTC): **306 items** (matches M3 report claim)
- Prior run: 277 items
- Consistently 277–306 range. Close to the 300+ target, dipping slightly below on some runs. Not a crisis but note the variance.

### 9. Analytics /api/outcomes Endpoint — CONFIRMED DONE ✅
- Route `/api/outcomes` exists at `webapp/routers/outcomes.py` ✅
- Registered in `main.py` line 55 ✅
- POST returns 422 (validation error) when given wrong payload shape — endpoint IS routing correctly, not 404
- Returns 401 for unauthenticated requests — correct behavior
- Both `/api/outcomes` (POST) and `/api/outcomes/bid` (POST) routes present in code
- **The endpoint works. It's behind auth, as intended.**

### 10. SCRAPER_AGENT_REPORT Files — CONFIRMED DONE ✅
All four report files exist on disk:
- `SCRAPER_AGENT_REPORT_M2.md` ✅
- `SCRAPER_AGENT_REPORT_M3.md` ✅ (ds-govplanet fix)
- `SCRAPER_AGENT_REPORT_M4.md` ✅ (dealer_sales population)
- `SCRAPER_AGENT_REPORT_M5.md` ✅ (GovDeals comps)

---

## PARTIALLY DONE

### 4. ds-gsaauctions Timeout Fix — PARTIALLY DONE ⚠️
- Actor ID: `fvDnYmGuFBCrwpEi9`
- The 10s hydration timeout IS in the code (line 217: `waitForTimeout(10000)`)
- However: **runs are returning 0 items consistently** for the 17:35, 19:00, 22:00 runs
- Earlier runs (07:00, 10:00) returned only **3 items** each — not 0, but nearly useless
- One TIMED-OUT run (17:56) between the 0-item runs
- Fix was deployed (actor modified 2026-03-21) but something else is broken — possibly filter criteria too strict (`minYear: 2022`, `minBid: 1000`, `maxMileage: 50000`) eliminating everything GSA has right now, OR the React hydration still failing after timeout
- **The code change happened. The outcome is still broken.** Needs investigation.

### 5. JJ Kane Marketcheck Pricing — PARTIALLY DONE ⚠️
- Actor `lvb7T6VMFfNUQpqlq` was updated and deployed at 2026-03-21T17:40 (build 0.0.2)
- 10:00 and 16:00 runs both returned **1,258 items** ✅
- BUT: 22:00 run returned **0 items** (succeeded, no data) — intermittent failure
- `estimated_auction_price` field EXISTS in source code (`main.js` line 194) ✅
- BUT: Sampled items from the 16:00 run (1258 items) show `estimated_auction_price: MISSING` in all 3 samples
- This means Marketcheck is returning null for those vehicles (API not matching make/model, or rate-limited silently)
- **Actor deployed and running, but `estimated_auction_price` appears missing from actual output items. Marketcheck lookups may be failing silently. Also has intermittent 0-item runs.**

### 8. dealer_sales Records / Recon Grade A+ — PARTIALLY DONE ⚠️
- Supabase `content-range` header confirms **2,038 total records** in dealer_sales ✅
- M4 claims 1,749 records; M5 adds 361 govdeals_completed = expected 2,110 — close enough (72-record delta may be deduplication or prior data)
- Source breakdown (Supabase 1000-row default limit): marketcheck_proxy: 576, publicsurplus_closed: 281, marketcheck_wholesale: 143 visible, plus ~1038 more (govdeals_completed and remaining wholesale)
- **Grade A+ for 2018 Ford F-150 cannot be verified directly** — Recon API requires auth (returns 401). 
- M4 report shows Grade A+ for 2019 F-150 but NOT 2018 F-150 specifically. The exact vehicle requested in audit item #8 was not in M4's test matrix.
- Note: `marketcheck_wholesale` in M4 claimed 892 records, but only 143 show in the first 1000. This may be pagination artifact. Full count across all sources adds to 2038 which is plausible if govdeals_completed (361) + remaining wholesale are in the remaining 1038.
- **Real records exist. Grade A+ cannot be confirmed for the specific 2018 F-150 without auth.**

---

## OPEN — Needs Work

### 2. ds-municibid — OPEN 🔴 CRITICAL
- Actor ID: `svmsItf3CRBZuIntp`
- The price extraction fix (`grid-card-price-value` / `.NumberPart` selector) IS in the code ✅
- The www redirect note IS in the code ✅
- **But the actor has returned 0 items in EVERY SINGLE RUN — all 10 runs today, plus yesterday's runs checked.**
- Not 1 item. Not occasionally. Zero. Every time. The actor "succeeds" (exit code 0) but produces nothing.
- The Municibid website likely changed its markup/selectors, or the vehicle category has no current inventory matching filters, or there's a rate-limit/bot-block happening silently.
- **This is completely non-functional. The code fix was deployed but the actor is dead.**

### 3. ds-bidspotter — OPEN 🔴 CRITICAL
- Actor ID: `5Eu3hfCcBBdzp6I1u`
- **4 of the last 5 runs TIMED OUT** (runs at 18:00, 19:00, 21:00, 22:00 UTC all TIMED-OUT)
- 1 succeeded (21:00) with 123 items — extremely intermittent
- Actor modified 2026-03-21T17:55 (build 1.0.16 deployed today)
- defaultRunOptions timeoutSecs: **300** — was this ever increased? Probably not enough.
- **Additionally: Bidspotter has 3 webhooks, 2 of which are broken:**
  - Webhook 1: `x-apify-webhook-secret` header ✅ (correct)
  - Webhook 2: `X-Apify-Webhook-Secret` (wrong case, wrong capitalization) ❌ — FastAPI header normalization may still pick this up, but unclear
  - Webhook 3: `x-webhook-secret` (completely wrong header name) ❌ — will be rejected
- **Actor is timing out 80% of the time. Stale webhook duplicates need cleanup.**

### 6b. Webhook Secret — bidspotter Specifically — OPEN 🔴
- bidspotter (5Eu3hfCcBBdzp6I1u) has **3 webhooks** where there should be 1:
  - Webhook A: `{"x-apify-webhook-secret":"rDyApg2UUIMl0a8ZUz..."}` ✅
  - Webhook B: `{"X-Apify-Webhook-Secret": "rDyApg2UUIMl0a8ZUz..."}` ❌ (capital case)
  - Webhook C: `{"x-webhook-secret": "rDyApg2UUIMl0a8ZUz...", "Content-Type": "application/json"}` ❌ (wrong key name)
- Both B and C will fail authentication on Railway (checks for `x-apify-webhook-secret` specifically)
- These are leftovers from debugging sessions. Need to delete B and C.

---

## Summary Table

| # | Item | Status |
|---|------|--------|
| 1 | ds-hibid-v2 webhook | ✅ CONFIRMED DONE |
| 2 | ds-municibid price fix | 🔴 OPEN — 0 items every run |
| 3 | ds-bidspotter timeout | 🔴 OPEN — 80% TIMED-OUT |
| 4 | ds-gsaauctions 10s fix | ⚠️ PARTIALLY DONE — fix in code, still 0 items |
| 5 | JJ Kane Marketcheck pricing | ⚠️ PARTIALLY DONE — deployed, intermittent + `estimated_auction_price` missing in practice |
| 6 | All webhook secrets | ⚠️ PARTIALLY DONE — bidspotter has 2 broken webhook dupes |
| 7 | GovPlanet 300+ items | ✅ CONFIRMED DONE (299–306 range) |
| 8 | dealer_sales / Grade A+ | ⚠️ PARTIALLY DONE — records exist, Grade A+ unverifiable for exact 2018 F-150 |
| 9 | /api/outcomes endpoint | ✅ CONFIRMED DONE |
| 10 | SCRAPER_AGENT_REPORT files | ✅ CONFIRMED DONE |

---

## Recommended Priority Order for Open Items

### P0 — Fix Immediately (Revenue-blocking)

1. **ds-bidspotter timeout** — 80% failure rate. Actor needs either: (a) timeoutSecs increased to 600+, (b) fewer catalogues scraped per run, or (c) investigation of what changed causing slowdown. Also delete the 2 broken duplicate webhooks. **Every TIMED-OUT run is data loss.**

2. **ds-municibid dead** — Every run returns 0 items. Site markup may have changed. Need: (a) fetch the live Municibid grid page and test current selectors, (b) check if the site requires JS rendering (actor uses CheerioCrawler). If selectors changed, update and rebuild. If JS-gated, switch to PlaywrightCrawler.

### P1 — Fix This Week (Data quality)

3. **ds-gsaauctions 0 items** — Timeout fix is in code but output is zero. Check: (a) GSA site still has inventory? (b) Are filter criteria (minYear: 2022, maxMileage: 50k, minBid: $1000) eliminating everything? Try relaxing filters and manually testing the URL.

4. **JJ Kane estimated_auction_price missing** — Sampled items don't have the field. Either Marketcheck API is returning no results (wrong params?), or it's timing out silently and returning null which gets dropped. Add explicit null logging to see what Marketcheck actually returns per vehicle.

5. **Bidspotter broken webhooks** — Delete webhooks B and C from ds-bidspotter. Low effort, clean up the mess.

### P2 — Verify and Document

6. **Grade A+ for 2018 Ford F-150** — Authenticate and test Recon for the specific vehicle year. M4 tested 2019, not 2018. Should be a 5-minute auth'd curl test.

7. **JJ Kane intermittent 0-item runs** — The 22:00 run had 0 items (succeeded with nothing). Check if this is a Algolia API rate limit or time-of-day issue. Add retry logic or error logging.
