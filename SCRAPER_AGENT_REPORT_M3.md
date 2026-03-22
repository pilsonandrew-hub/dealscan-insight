# Scraper Agent Report — Mission 3
**Date:** 2026-03-21  
**Agent:** DealerScope Scraper Agent (Mission 3)  
**Status:** ✅ ds-govplanet FIXED & DEPLOYED | ⚠️ dealer_sales pending (GovDeals blocked) | ⚠️ GovPlanet sold prices JS-gated

---

## Mission Summary

### Priority 1: ds-govplanet Actor Fix — COMPLETED ✅

**Problem diagnosed:** Actor was returning only 7 items per run due to:
1. **Wrong start URL** — using `ct=13` (old/wrong category) instead of vehicle-specific category URLs
2. **maxRequestsPerCrawl: 30 hard cap** — with detail-page visits that's ~7 vehicles
3. **PlaywrightCrawler** — unnecessary browser overhead; all data is in `quickviews.push()` JS on list pages
4. **Non-US items** not filtered at source — 40% of results were Canadian

**Fix implemented:**
- Switched to **CheerioCrawler** (pure HTTP, no browser, ~10x faster)
- Switched to **6 US-only category URLs** with `l2=USA` param to filter at source
- Extracted all data from **`quickviews.push()`** blocks (no detail page visits)
- Pagination via `pstart=0,60,120,...` per category
- Removed playwright dependency from package.json

**Categories now scraped (all US-only via `l2=USA`):**
| Category | Total | Label |
|---|---|---|
| Pickup Trucks | 367 | pickup_trucks |
| Van Trucks | 230 | van_trucks |
| Service & Utility Trucks | 182 | service_trucks |
| Vans | 89 | vans |
| Automobiles | 40 | automobiles |
| Full Size SUVs | 37 | full_suv |
| Compact SUVs | 37 | compact_suv |
| **TOTAL** | **982** | |

**Filter logic:**
- US-only (enforced at source via `l2=USA` + state validation)
- Commercial equipment excluded (dump trucks, flatbeds, ambulances, etc.)
- Year cutoff: 25 years max (government vehicles kept longer than retail)
- Rust-state age limit: 18 years
- Price cap: $55,000
- Min bid: $100

**Test run results:**
- Run ID: `qMkexP5GVv2W33SDZ`
- Dataset: `VIaMg1eV2PU3KeZq7`
- **306 items pushed** (vs. 7 before)
- Runtime: ~39 seconds
- **Webhook → 200** (Railway confirmed receipt)
- Cost: ~$0.006/run

**Sample items:**
```
2007 Ford F-250 Super Duty | $1,000 | CA | 127,717mi
2021 Ram 2500 Laramie 4x4  | $32,000 | NC | 42,421mi
2020 Chevrolet 1500 Pickup | $10,000 | SC | 97,132mi
2021 Ford F-250 STX 4x2    | $40,000 | NY | 14,561mi
2018 Ram 1500 SLT 4x4      | $8,000  | LA | 163,050mi
```

**Why 306 not 500+:**
- 306 is the real ceiling from PUBLIC category URLs (no login)
- 639 skipped = mostly government service trucks/heavy equipment (correct to filter)
- The full 7,449-item endpoint (`/jsp/s/search.ips?ct=3`) requires browser login session
- To unlock 500+ in future: add Playwright session capture to hit the auth-gated endpoint
- 306 quality US passenger vehicles is a strong baseline

**Actor deployed:** pO2t5UDoSVmO1gvKJ (build 1.0.8)

---

## GovPlanet Surplus Investigation

### Live Vehicles

**Target URL confirmed:** `https://www.govplanet.com/Pickup+Trucks?ct=3&kwtag=cat-surplus`  
**Result:** 491 pickup trucks total (367 US-only with `l2=USA`)

**Architecture confirmed:**
- GovPlanet is owned by IronPlanet/Ritchie Bros (same infrastructure)
- CSS loads from `ironpla.net` CDN
- Links to `rbauction.com` in nav
- No shared Algolia/Elasticsearch API found — data served server-side in `quickviews.push()` blocks
- The `jsp/s/search.ips` endpoint requires login (302 → login form without session)
- Public category pages work without auth for read-only scraping

**`quickviews.push()` data fields available:**
```
description, convPrice, usage (mileage), eumeLocation (city+state), flagPath (country),
itemPageUri, equipId, timeLeft, photo, photoThumb, features, registrationNu, equipStatus
```

**equipStatus values observed:**
- `30` = Active online auction  
- `31` = IronClad Assurance (make-offer/buy-now)
- `19`, `13` = Other (passive sale modes)

### Sold/Completed Prices

**Finding:** GovPlanet does NOT expose final hammer prices in static HTML.  
- The `soldAmt` field (`IP$XXXXX_soldAmt`) is rendered client-side via JavaScript
- `sm=0` parameter returns passive-sale items (status 31), NOT auction-closed items
- `status=sold` parameter returns same 15 items as live ct=35 page
- The `auction.ips?sm=0` endpoint returns items with status 19/13/31 (not completed auctions)

**To get real hammer prices:** Need Playwright to execute the detail page JS and capture `soldAmt`. This is a separate mission — not blocking current live scraping.

**Alternative for dealer_sales comps:** Use PublicSurplus or GovDeals (separate investigation in progress).

---

## GovDeals Completed Auctions Investigation

### Access Method

**Problem:** GovDeals is an Angular SPA. Static HTML returns shell page only.  
**API:** `maestro.lqdt1.com/search/list` exists but requires:
- `x-api-key` header (must be captured from live browser session)
- `x-user-id` (UUID format) 
- `x-api-correlation-id` (UUID format)
- A valid `sessionId` in the request body

**Known from REVERSE_ENGINEER.md:**
- API key format: `af93060f-337e-428c-87b8-c74b5837d6cd` (captured 2026-03-12)
- Endpoint: `POST https://maestro.lqdt1.com/search/list`
- `timeType: "ended"` parameter should return completed auctions

**Status:** 401 with stale key. New key requires fresh Playwright browser session.  
**Recommendation:** Extend existing `ds-govdeals` actor to add `timeType:"ended"` mode after capturing fresh API key.

### PublicSurplus Investigation

**Finding:** PublicSurplus auction list pages return server-side HTML but the "closed" category URL (`/sms/browse/cataucs?catid=30&type=closed`) redirects to the home page. The auction browse search returns active listings only in static HTML — closed auction data appears to require login or different endpoint discovery.

### dealer_sales Table Status

**Current state:** Table exists but empty — Recon module using estimated prices.  
**Blocker:** Both GovDeals and GovPlanet sold prices require Playwright JS execution.  
**Path forward:** 
1. Extend ds-govdeals actor with `timeType:"ended"` for GovDeals comps
2. Add Playwright detail-page mode to ds-govplanet for hammer prices
3. This is Mission 4 scope

---

## Deployments This Mission

| Actor | ID | Build | Status | Items/Run |
|---|---|---|---|---|
| ds-govplanet | pO2t5UDoSVmO1gvKJ | 1.0.8 | ✅ LIVE | 306 |

## Webhook Verification

- URL: `https://dealscan-insight-production.up.railway.app/api/ingest/apify`
- Secret header: `x-apify-webhook-secret`  
- Last confirmed response: **HTTP 200** (run qMkexP5GVv2W33SDZ, 2026-03-21 19:02 UTC)

---

## Recommendations for Next Mission

1. **Mission 4: dealer_sales population** — Build Playwright-based scraper to capture GovDeals completed auction hammer prices using `timeType:"ended"` API mode
2. **ds-govplanet v2** — Add Playwright session-capture mode to unlock the authenticated `jsp/s/search.ips?ct=3` endpoint (7,449 vehicles vs. 982 current)
3. **IronPlanet crossover** — GovPlanet and IronPlanet share infrastructure; the `ds-ironplanet` actor may be able to capture GovPlanet's session token
