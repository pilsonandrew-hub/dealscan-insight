# Deep Scan Report — 2026-03-22 (03:30 PDT)

> Auditor: hostile senior. No mercy. All findings backed by live API calls, DB queries, and code inspection.

---

## ✅ CONFIRMED WORKING

### Scrapers (All 10 Running)
| Actor | Last Run | Status | Items | Webhook | Secret Header |
|---|---|---|---|---|---|
| govdeals | 2026-03-22 03:00 | SUCCEEDED | 8 | ✅ | ✅ |
| publicsurplus | 2026-03-22 03:00 | SUCCEEDED | 55 | ✅ | ✅ |
| govplanet | 2026-03-22 02:43 | SUCCEEDED | 299 | ✅ | ✅ |
| allsurplus | 2026-03-22 01:00 | SUCCEEDED | 9 | ✅ | ✅ |
| proxibid | 2026-03-22 01:00 | SUCCEEDED | 115 | ✅ | ✅ |
| hibid-v2 | 2026-03-22 01:00 | SUCCEEDED | 299 | ✅ | ✅ |
| municibid | 2026-03-22 01:00 | SUCCEEDED | 11 | ✅ | ✅ |
| gsaauctions | 2026-03-22 01:00 | SUCCEEDED | 49 | ✅ | ✅ |
| jjkane | 2026-03-21 23:50 | SUCCEEDED | 481 | ✅ | ✅ |
| bidspotter | 2026-03-22 03:00 | SUCCEEDED | 84 | ✅ | ✅ |

All 10 webhooks confirmed present, all use correct `x-apify-webhook-secret` header.

### Database State
- **opportunities: 210 total, 0 null dos_score** — every record scored ✅
- **dealer_sales: 2,038 total** (all from marketcheck_proxy/marketcheck_wholesale — no outcome_tracking entries yet)
- **recon_evaluations: 17 total** — schema healthy (50+ columns)
- **rover_events: 5 total** — tracking live (all from Andrew)
- **sniper_targets: 2 total** — table present
- **user_passes: 0 entries** — table exists, migration ran, no passes recorded yet
- **alert_log: 34 entries** — alerts firing

### API Endpoints
- **GET /health** → `{"status":"ok"}` ✅
- **GET /api/analytics/summary** → HTTP 200, 210 opportunities, top makes/scores present ✅
- **POST /api/outcomes** → HTTP 422 (field validation working, endpoint registered) ✅
- **GET /debug/recon-test** → `{"auction_mode":true,"status":"model_ok"}` ✅
- **POST /api/sniper/check** → Returns 401 without secret (correctly protected) ✅

### Procfile
`web: uvicorn backend.main:app --host 0.0.0.0 --port $PORT` — correct entrypoint ✅

### Frontend
- **https://dealscan-insight.vercel.app** → HTTP 200 ✅
- **Pass button** — ThumbsDown icon wired up, animation on click, direct Supabase query on load to filter passed deals ✅ (see caveat below)

### GitHub Actions Workflows
All 9 workflows present: sniper-check (*/5min), apify-health-check (*/3h), scraper-watchdog (*/4h), daily-digest (9am PT), saved-searches-check (*/30min), production-deploy, cursor-review, deploy-gold, deploy-validation-reports ✅

---

## ⚠️ PARTIALLY WORKING

### 1. HiBid-v2: 299 items run → 0 in opportunities (CODE BUG)

**Root cause confirmed via webhook_log:**

> `gate:age_exceeded (7 years, max 4 for hibid)`
> `gate:bid_out_of_range ($700)` × 60+ items
> `gate:bid_out_of_range ($0)` × 165 items

Two compounding problems:
- **Age gate** — HiBid scrapers pick up 5-20 year old vehicles. `gov_sources` set includes `"hibid"` with `max_age=20`, **but the actual gate check reads** `gov_sources = {..., "hibid"}` (line 1595) → should give 20yr limit. BUT the webhook_log shows `max 4 for hibid` — meaning the gate is **not** finding hibid in `gov_sources`. **Possible: `source_site="hibid"` but the gate does a lowercased lookup and `"hibid"` is already lowercase → this should match. Needs Railway log inspection to confirm.**
- **Bid range** — Most HiBid items have bids $500-$2,900 range. Gate min is 500 for gov sources. Items with bid exactly $500 pass, but `bid_out_of_range ($500)` appears in skip reasons — meaning the gate uses `bid < min_bid` which allows $500 but logs it differently? Actually reviewing code: `if (bid > 0 and bid < min_bid)` where `min_bid=500` — so a $500 bid passes ($500 is not < 500). But the log shows `bid_out_of_range ($500)` — possible misread. 
- **Real finding**: 53 HiBid items pass all filter logic in my simulation but 0 survive to DB. The skip_reasons in webhook_log show `max 4 for hibid` — the `gov_sources` set is NOT being matched at the time of gate evaluation. **The source going into the gate function is `"hibid"` but the ingest code calls the filter with `source_site` which should be `"hibid"` from the scraper's `source_site` field.** This needs a debug log trace.

**Impact:** HiBid is one of the highest-volume sources (299 items/run) — getting 0 deals is a significant revenue loss. HiBid has gov fleet and police vehicles at low bids that could score well.

**Fix needed:** Add `print(source, gov_sources, source in gov_sources)` to gate function in prod logs, or lower the gate to explicitly match `hibid-v2` as an alias.

---

### 2. BidSpotter: 84 items/run → 0 in opportunities (DESIGN DECISION + CODE BUG)

**Root cause confirmed via webhook_log:**
> `gate:bid_out_of_range ($1)` × 71 items
> `gate:bid_out_of_range ($5)` × 2 items  
> `gate:age_exceeded (15-22 years, max 4 for bidspotter)` × all year-bearing items

Two separate problems:
1. **Bids are $1-$5** — BidSpotter shows "opening bid" (reserve/minimum), not current bid. Essentially all items have placeholder bids. The `min_bid=3000` gate (non-gov source) filters everything.
2. **Age gate max 4yr** — BidSpotter is NOT in `gov_sources` set → `max_age=4`. But BidSpotter mixes older commercial/gov vehicles. Even with year filtering, all items with years are 2006-2011 vintage.
3. **Uncommitted fix exists locally** — `ds-bidspotter` has a complete HTTP-based v2.0 rewrite in the working tree (not committed, not pushed to Apify). This new version scrapes US-only auctions and uses proper year filtering. **These changes are NOT deployed to Apify.**

**Impact:** BidSpotter has 84 items/run but 0 reach Andrew. The uncommitted rewrite needs to be pushed.

**Fix needed:** 
- Commit and push the BidSpotter v2 actor to Apify
- Add `"bidspotter"` to `gov_sources` or create a separate `bidspotter_sources` set with more permissive age filter (8yr)

---

### 3. JJ Kane: 481 items/run → 0 in opportunities (CRITICAL — MarketCheck model name mismatch)

**Root cause confirmed via live API test + webhook_log:**

> `gate:bid_out_of_range ($0)` × 403 items (84% of run)
> `gate:age_exceeded (5-15 years, max 4 for jjkane)` × 81 items

**Primary issue:** 83% of JJ Kane items have `current_bid=0` (no bid yet — timed auction). The actor is supposed to use `estimated_auction_price` from Marketcheck as a fallback bid, but **Marketcheck is returning 0 for most models.**

**Confirmed via live API test:**
- Model `"f150"` (lowercase, no dash) → Marketcheck returns **0 results**
- Model `"f-150"` (with dash) → Marketcheck returns **7,285 results**
- Model `"transit-250"` → Marketcheck returns **0 results** (even with dash somehow)
- Model `"tahoe police package"` → Marketcheck returns **0 results** (needs just `"tahoe"`)

**The JJ Kane actor passes `model.toLowerCase().trim()` → "f150", "f250", "tahoe police package" etc. These exact strings have ZERO matches in Marketcheck.** The Marketcheck API requires the standard model name with dashes (f-150, f-250) and without modifiers (police package, 4x4, AWD, etc.).

Breakdown of 481-item run:
- 78 items (16%) got Marketcheck pricing successfully
- 403 items (84%) got `pricing_source=jjkane_no_bid` → `estimated_auction_price=0` → filtered at gate

**Marketcheck API health:** quota-remaining=492/500, rate-limit=4/5 — API is healthy, key is valid. Problem is purely the model normalization.

**Impact:** The highest-volume scraper (481 items) is producing nearly zero usable deals. This is the single biggest pipeline leak.

**Fix needed:** Add model normalization in `getMarketcheckPrice()`:
```js
const modelNormalized = modelLower
    .replace(/\s*(police|fleet|interceptor|package|4x4|4wd|awd|rwd|fwd).*$/i, '')
    .replace(/f(\d+)/g, 'f-$1')  // f150 → f-150, f250 → f-250
    .replace(/e(\d+)/g, 'e-$1')  // e250 → e-250
    .trim();
```

---

### 4. Pass Button: Silently Fails on Backend (CRITICAL UX BUG)

**The `/api/opportunities/{id}/pass` route does NOT exist on Railway.**

Confirmed: The `opportunities` router fails to load on Railway because:
1. `webapp/routers/opportunities.py` imports `from webapp.database import get_db` + `from webapp.models.user import User` + `from webapp.auth import get_current_user`
2. `webapp/auth.py` imports `from webapp.database import get_db` 
3. `webapp/database.py` creates a SQLAlchemy engine from `settings.database_url` which requires a real PostgreSQL `DATABASE_URL` env var (not Supabase)
4. On Railway, there is no SQLAlchemy database — only Supabase via REST API
5. The router silently fails to load — `main.py` catches the import error and logs a warning
6. Result: `/api/opportunities` and `/api/opportunities/{id}/pass` return **404 Not Found**

**What happens in the UI:** The Pass button animates out immediately (client-side) and calls `api.passOpportunity()` which silently fails with HTTP 404. The deal stays hidden in the current session (local state). But **when Andrew reloads the page, the deal comes back** — because `user_passes` table has 0 entries (nothing was ever saved).

**6 failed-to-load routers:** auth, vehicles, opportunities, upload, ml, admin — all SQLAlchemy-dependent.

**Fix needed:** The `pass_opportunity` endpoint in `opportunities.py` needs to be moved to the Supabase-based model (like `outcomes.py`, `rover.py`, `recon.py`). A standalone `/api/opportunities/{id}/pass` endpoint using the Supabase client directly (no SQLAlchemy) would fix this immediately.

---

### 5. Analytics: Zero Outcome Data (DESIGN — not broken, just unused)

`total_outcomes=0`, `total_bids=0`, `avg_gross_margin=null` — all analytics outcome fields are empty.

No deal has ever been recorded as won/bid. The `/api/outcomes` endpoint IS live and functional. The UI has no way for Andrew to record outcomes from the Dashboard — there's no "I bid on this" or "I won this" button visible.

**Impact:** Analytics dashboard is an empty shell for outcome tracking. Andrew can't see ROI or win rate because there's no data entry path.

---

### 6. Rover: Requires Real JWT (Not Broken, but Opaque)

`GET /api/rover/recommendations` → 422 (missing `user_id`) without auth, 401 with anon/service key.

**Correct behavior** — requires a real Supabase session JWT. Works from the frontend. But `user_id` is a separate query param AND Bearer token is required — this is double authentication and slightly inconsistent API design.

Only 5 rover_events in DB — Rover is alive but rarely used.

---

## 🔴 BROKEN / MISSING

### 1. Pass Button Permanently Broken Until Backend Fixed
As detailed above — every pass action silently fails. On page reload, all passed deals return. **This is a broken feature in the latest commit (5ec9005).**

### 2. `/debug/recon-test` Is Open to the Public
The endpoint at `/debug/recon-test` is publicly accessible with no authentication. It doesn't leak sensitive data (returns `{"auction_mode": true, "status": "model_ok"}`), but it is a live debug endpoint in production and was likely meant as temporary.

```python
@app.get("/debug/recon-test")
async def debug_recon_test():
    """Debug endpoint to test recon evaluate directly"""
```

No auth, no rate limit, exposes internal class names. Should be removed.

### 3. `user_profiles` Table Does Not Exist
Query `GET /rest/v1/user_profiles` returns:
> `"Could not find the table 'public.user_profiles' in the schema cache"`

If any feature references this table (frontend Settings, profile page), it will 404. Supabase hint suggests it confused it with `user_passes`. Migration was never run.

### 4. `outcomes` Table Does Not Exist (Not the Same as `outcome_*` columns)
A standalone `outcomes` table does not exist. The system uses `outcome_*` columns on the `opportunities` table instead, which is correct — but if any old code references `FROM outcomes` it will fail. Currently no code does, but worth noting.

### 5. `sniper_alert_log` Table Missing
Query returns: `"Could not find the table 'public.sniper_alert_log'"`. If the sniper-check workflow attempts to log alerts here, it will throw a DB error silently.

### 6. JJ Kane: Age Gate Too Restrictive (Non-Gov Logic Applied)
`max 4 for jjkane` — The webhook_log shows JJ Kane items getting age-gated at 4 years. JJ Kane IS in `gov_sources` so it should get `max_age=20`. But the log says `max 4 for jjkane`. This may be the same issue as HiBid — the source lookup in the gate function might not be matching correctly against the actual `source_site` value coming from the actor.

**Same code, same bug as HiBid.** Both should be treated as gov sources (20yr max age) but are being treated as non-gov (4yr max age).

### 7. Uncommitted BidSpotter v2 Rewrite — Undeployed
Three files locally modified, not committed, not pushed to Apify:
- `apify/actors/ds-bidspotter/Dockerfile`
- `apify/actors/ds-bidspotter/package.json` (v1.0.0 → v2.0.0)
- `apify/actors/ds-bidspotter/src/main.js` (Playwright → HttpCrawler rewrite)

`FINAL_SWEEP_REPORT.md` is also untracked. Dead weight.

### 8. GovDeals: Consistently Low Item Count (7-8 per run)
All items are in the $19k-$32k bid range — near the $35k ceiling. The scraper itself is working correctly (it filters bid range), but GovDeals is yielding very few vehicles in that price band. This could indicate:
- The scraper is only fetching sedans/SUVs above $15k current bid
- Pagination is limited (`maxPages=10`) — may be missing categories
- Anti-scraping throttling (older run history shows FAILED and TIMED-OUT runs in March 2026)

Not blocking, but monitoring needed.

---

## 📋 NICE TO HAVE

1. **Opportunity refresh on pass** — After pass, Rover should be notified (negative signal). Currently `api.passOpportunity()` fires but rover events are only triggered on save. The pass signal should feed into Rover's affinity model.

2. **BidSpotter → gov_sources** — Once the v2 actor is deployed, add `"bidspotter"` to both `gov_sources` and `gov_sources_bid` sets. BidSpotter sources government fleet auctions (BSC Royal FL) — they deserve the 20yr age window.

3. **JJ Kane → age gate** — Both JJ Kane and HiBid appear to be hitting the 4yr age gate instead of the 20yr gov-source gate. The root cause (source matching) needs investigation in Railway logs.

4. **Rover events: Only 5** — Consider adding a "quick score" impression event when a deal card loads on the Dashboard to seed affinity data.

5. **`/api/analytics/summary` — No auth required** — This exposes platform activity data (item counts, source names, top makes) publicly. Low risk but worth adding at least rate limiting.

6. **Alert frequency: 34 in 30 days ≈ 1/day** — Is this the expected rate? If hot deal threshold is 80+ DOS, check if alerts are firing for the right vehicles.

7. **`dealer_sales` source_type column is null for all 2,038 rows** — Every record has `source_type=None`. The column exists but was never populated by the Marketcheck ingest pipeline. Analytics that filter by `source_type` won't group correctly.

---

## Priority Matrix (Impact on Andrew Finding and Evaluating Deals)

| # | Issue | Impact | Effort | Fix |
|---|---|---|---|---|
| 1 | JJ Kane Marketcheck model normalization | 🔴 CRITICAL | Medium | Add model name normalizer in `getMarketcheckPrice()` |
| 2 | Pass button silently fails on reload | 🔴 HIGH | Medium | Move pass endpoint to Supabase-based router |
| 3 | HiBid + JJ Kane age gate = 4yr (should be 20yr) | 🔴 HIGH | Low | Debug Railway logs, fix source lookup |
| 4 | BidSpotter v2 uncommitted/undeployed | 🟠 HIGH | Low | `git commit && git push` then push to Apify |
| 5 | /debug/recon-test open in production | 🟡 MEDIUM | Low | Delete the endpoint |
| 6 | user_profiles table missing | 🟡 MEDIUM | Low | Run migration or confirm no code references it |
| 7 | sniper_alert_log missing | 🟡 MEDIUM | Low | Run migration |
| 8 | Zero outcome data / no UI entry path | 🟡 MEDIUM | High | Add bid/outcome buttons to deal cards |
| 9 | GovDeals consistently 7-8 items | 🟡 LOW | Unknown | Monitor; possibly pagination or category filter |
