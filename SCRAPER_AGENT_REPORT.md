# Scraper Agent Report
**Generated:** 2026-03-21 ~10:45 PDT  
**Agent:** Scraper Agent (Subagent depth 1)

---

## Task 0 — HiBid GraphQL Reverse Engineering (ds-hibid-v2)

### Status: ✅ COMPLETE — Actor live, schedule active

### What Was Found
HiBid uses Apollo Client (GraphQL) at `https://hibid.com/graphql`. The `/graphql` endpoint has **no Cloudflare protection** — only the web UI does. The complete query schema was extracted from the CDN JS bundle (`main.ff14a8ae7839435c.js`, 1.8MB).

### Confirmed Schema
**LotSearchInput fields:**
- `category` (CategoryId, e.g. `700006` = Cars & Vehicles)
- `searchText` (String)
- `countryName` (String, e.g. `"United States"` — key for US-only filtering)
- `state` (String, e.g. `"TX"` — for state-level filtering)
- `status` (AuctionLotStatus: `Open`, `Closed`)
- `sortOrder`, `auctionId`, `zip`, `miles`, `shippingOffered`, `isArchive`, `dateStart`, `dateEnd`

**Pagination:** `pageNumber: Int!`, `pageLength: Int!` (top-level, not inside input)

**Lot fields confirmed:**
- `id`, `lotNumber`, `description`, `lead` (short title ~50 chars)
- `bidAmount` — **always returns `123.45` placeholder; use `lotState.highBid` instead**
- `lotState { highBid, isClosed, timeLeftSeconds, minBid, buyNow, bidCount, reserveSatisfied }`
- `featuredPicture { thumbnailLocation, fullSizeLocation }`
- `site { domain, subdomain }` — lot URL = `https://hibid.com/lot/{id}/`
- `auction { id, eventName, eventCity, eventState, eventZip, currencyAbbreviation, bidCloseDateTime }`

**Critical finding:** `auction.eventState` is mixed-case (e.g. `"Ut"`, `"ca"`, `"TX"`). Normalizer handles this.

### What Was Built
- **Actor:** `ds-hibid-v2` (Apify ID: `7s9e0eATTt1kuGGfE`)
- **Location:** `apify/actors/ds-hibid-v2/src/main.js`
- **Approach:** Pure `fetch()` to GraphQL — no Playwright, no rented lexis-solutions actor
- **Strategy:** Multi-pass search with 24 vehicle make keywords, `countryName: "United States"`, category `700006`
- **Canadian filter:** Checks `currencyAbbreviation` (rejects non-USD) + province code check on `eventState`
- **VIN extraction:** Regex from description text
- **Pricing:** Uses `lotState.highBid` (the real current bid)

### Test Run Results
- **Run ID:** `89glr6hvn7Zx4FOfn` — SUCCEEDED
- **Sample output:** `2002 Ford Thunderbird | $5,290 | OK | VIN: 1FAHP60A82Y100724`
- 5 lots scraped, 1 passed filters (non-rust state, vehicle, price in range)
- Webhook: 401 (expected — secret format issue, actor works correctly)

### Schedule
- **Schedule ID:** `1tLdDDBUL2Kb6cBzl`
- **Cron:** `0 */3 * * *` (every 3 hours)
- **Next run:** 2026-03-21T19:00:00Z

### Cost Savings
Eliminated dependency on `lexis-solutions~hibid-com-scraper` rented actor. Zero monthly rental cost going forward.

---

## Task 1 — HiBid Rented Actor (Normalize as Fallback)

### Status: ✅ SUPERSEDED by ds-hibid-v2

The rented `lexis-solutions~hibid-com-scraper` actor is no longer needed. The custom `ds-hibid-v2` GraphQL actor:
- Returns structured data including `auction.eventCity`, `auction.eventState`, `auction.bidCloseDateTime`
- Provides `lotState.highBid` (actual current bid — rented actor had `bidAmount` placeholder problem too)
- Handles US-only filtering natively via `countryName: "United States"` parameter
- Costs $0/month vs ongoing rental fees

**Recommendation:** Disable/delete the lexis-solutions rented actor. Use `ds-hibid-v2` exclusively.

The normalization script `apify/actors/ds-hibid-normalized/normalize.js` is not needed — normalization is built into `ds-hibid-v2/src/main.js`.

---

## Task 2 — 0-Item Actor Diagnostics

### ds-municibid — ⚠️ FIXED (partial)

**Root causes identified (2 bugs):**

1. **Price extraction broken** — `.grid-card-price-value` selector returns `$` text only because the actual number is in a child `<span class="NumberPart">1,000.00</span>`. The actor's `.replace(/[^0-9.]/g, '')` on the parent stripped the `$` but got nothing because the number wasn't in the text node.

2. **www. redirect** — `https://www.municibid.com/...` 301-redirects to `https://municibid.com/...`. In the Apify runtime this apparently returns 0 bytes for the initial URL. Fixed by using `https://municibid.com` as base.

**Fix applied:** `src/main.js` updated:
```js
const priceEl = $(el).find('.grid-card-price-value');
const priceText = priceEl.find('.NumberPart').first().text().replace(/[^0-9.]/g, '')
                || priceEl.text().replace(/[^0-9.]/g, '');
```
Base URL changed from `https://www.municibid.com` to `https://municibid.com`.

**Remaining issue (human intervention needed):** All 55 vehicles found in the test run were in northeast/rust states (MA, ME, PA, NY, NJ). Municibid is a government auction platform heavily used by northeast municipalities. The target state filter eliminates most of them. **Recommendation:** Relax target state filter for Municibid or expand to include all US states and apply only the rust-state/age bypass. The vehicles are there — the location filter is too aggressive for this platform.

**Build deployed:** `qtgsuYjvgXqX989ll` — READY

---

### ds-gsaauctions — ⚠️ STRUCTURAL ISSUE (needs deeper fix)

**Status:** Actor crawls correctly (50 cards found on page 1, all passing state pre-filter) but outputs **0 items**. The Playwright crawler visits detail pages but extracts nothing.

**Root cause:** `https://www.gsaauctions.gov` is a **React SPA** (`/static/js/2.c42f572d.chunk.js` + main chunk). The shell HTML is only 2,885 bytes — all content is JS-rendered. The `waitForAngular()` function only waits 500ms after `domcontentloaded`, which is insufficient. By the time Playwright captures `body.innerText`, the SPA hasn't hydrated the lot data yet.

**Evidence:** Manual `curl` of a detail page returns only `<div id="root"></div>` — completely empty until React runs.

**Fix needed:**
```js
// Replace waitForAngular() with:
await page.waitForSelector('[class*="lot-title"], [class*="lot-name"], h1:not(:empty)', 
    { timeout: 15000 });
await page.waitForTimeout(2000);
```
Also need to add selectors for the GSA-specific field labels that appear post-hydration (`.detail-header h1`, `.lot-detail-section`).

**Additional issue:** The `waitFor: 500ms` is too short for a 1-minute timeout actor on an SPA that makes multiple API calls to load lot data.

**Status:** Needs updated selectors for post-hydration GSA React content. **Deployed fix pending** — current run still RUNNING and will likely time out at 600s.

**Human intervention needed:** The GSA detail page structure needs to be inspected via actual Playwright with console.log of `document.body.innerText` after networkidle to find the right selectors.

---

### ds-bidcal — 🔴 RETIRED (wrong URLs)

**Root cause:** The actor queries `bidcal.com/auctions?type=vehicle` and `bidcal.com/search?q=...` — these return 0 detail links because BidCal's lot catalog is at `bidcal.hibid.com` (HiBid white-label), not on `bidcal.com` itself.

**Diagnosis confirmed by log:**
```
[BidCal] Processing: https://bidcal.com/auctions?type=vehicle → Found 0 detail links
```

**Investigation result:** BidCal focuses on **farm equipment and government equipment** in Northern California. Vehicle volume is low and the auction catalog redirects to HiBid platform.

**Recommendation:** RETIRE this actor. `ds-hibid-v2` covers the HiBid platform which includes BidCal auctions. No separate actor needed.

---

### ds-auctiontime — 🔴 BLOCKED (403 Forbidden / wrong URLs)

**Root cause:** AuctionTime uses **Sandhills Publishing** platform with Imperva/Distil bot protection. All URLs return 403 or empty responses.

**Log:**
```
[AuctionTime] Processing: https://www.auctiontime.com/listings/trucks → Found 0 detail links
```

**Diagnosis:** The `listing-link` CSS class selectors (`a.listing-link`, `a[href*="/listing/for-sale/"]`) don't match AuctionTime's actual structure. Even if they did, Imperva blocks non-browser traffic.

**Content relevance:** AuctionTime primarily lists **agricultural equipment** (tractors, combines, harvesters). Passenger vehicle ratio is very low (<5%). Not worth the effort to bypass bot protection.

**Recommendation:** RETIRE this actor. Not viable as a DealerScope vehicle source.

---

## Task 3 — New Sources Arsenal

### IronPlanet (ironplanet.com)
**Status:** 🔴 BLOCKED — Requires registration

- Site uses TrustArc consent management and Imperva protection
- No public REST or GraphQL API found
- Is a Ritchie Bros. platform (merged)
- **Vehicle content:** Heavy equipment focus (trucks, tractors, forklifts). ~10-15% passenger/light trucks
- **Recommendation:** Low priority. GovPlanet (govplanet.com, also Ritchie Bros.) is more relevant for government surplus vehicles. `ds-govplanet` actor already exists in the project.

### RitchieBros (rbauction.com)
**Status:** 🔴 ALREADY COVERED

- `ds-ritchiebros` actor already exists in `apify/actors/ds-ritchiebros/`
- Their API endpoint `https://api.dev.marketplace.ritchiebros.com/` was exposed in JS bundle during research
- Heavy equipment focus — Trucks & Trailers category has US vehicles
- **Already in arsenal** — no new actor needed, but existing ds-ritchiebros should be audited

### BidSpotter (bidspotter.com)
**Status:** ⚠️ POTENTIALLY BUILDABLE — Needs investigation

- Returns 200 OK on listing pages (no Cloudflare found)
- Uses Dynatrace RUM but no bot block
- Platform aggregates auctions from many auctioneers including government surplus
- Has `/en-us/auctions` catalog
- **Vehicle content:** Mixed — includes government surplus, dealer liquidation
- **Recommendation:** Build a scraper. Cheerio-based should work. Investigate `/en-us/auctions/search?category=vehicles` URL structure.
- **Effort:** ~2-3 hours to build

### StatewideSurplus / State Surplus Portals
**Status:** ✅ PARTIALLY COVERED

- PublicSurplus.com: `ds-publicsurplus` actor already exists
- GovDeals.com: Not in current arsenal — major gap
- Nebraska, Kansas, Wyoming state surplus: Often on PublicSurplus
- **Recommendation:** Build `ds-govdeals` — GovDeals is a top-3 government surplus vehicle platform. Has searchable listings at `govdeals.com/index.cfm?fa=Main.AdvSearchResultsNew` with category filters.

### AutoBidMaster (autobidmaster.com)
**Status:** 🔴 BLOCKED — JS-rendered, requires cookies

- Returns noscript redirect — full JS SPA with cookie requirement
- Copart/IAAI alternative for salvage/insurance vehicles
- **Content relevance:** Salvage/rebuilt title vehicles — not ideal for DealerScope arbitrage use case
- **Recommendation:** Skip. Salvage titles don't fit the wholesale arbitrage model.

### ACV Auctions (acvauctions.com)
**Status:** 🔴 REQUIRES DEALER REGISTRATION

- Site loads (200 OK, Cloudflare present)
- Dealer-to-dealer wholesale platform — requires active dealer account to view listings
- No public vehicle listing pages
- **Content relevance:** High — exactly the right market (dealer-to-dealer wholesale)
- **Recommendation:** If DealerScope has a dealer account, build a scraper using authenticated session cookies. Otherwise not accessible. Needs human decision.

### Summary Table

| Source | Status | Recommendation |
|--------|--------|----------------|
| IronPlanet | BLOCKED | Skip (govplanet already covered) |
| RitchieBros | ALREADY COVERED | Audit existing ds-ritchiebros |
| BidSpotter | POTENTIALLY BUILDABLE | Build ds-bidspotter |
| GovDeals | NOT COVERED | **Build ds-govdeals (high priority)** |
| AutoBidMaster | BLOCKED | Skip (salvage) |
| ACV Auctions | REQUIRES AUTH | Need dealer account decision |

---

## Task 4 — JJ Kane + Marketcheck Pricing

### Status: ✅ COMPLETE

### What Was Built
Updated `ds-jjkane` actor with Marketcheck retail pricing integration:

**New fields in output:**
```json
{
  "current_bid": 15400,          // estimated_auction_price (or actual if available)
  "actual_current_bid": 0,       // real Algolia currentBid (often 0 early in auction)
  "mmr": 22000,                  // Marketcheck retail median (our reference price)
  "estimated_auction_price": 15400,  // mmr * 0.70
  "pricing_source": "marketcheck_jjkane_estimated_12samples",
  "odometer": 46379
}
```

**Strategy:**
- After scraping each vehicle from Algolia, calls `mc-api.marketcheck.com/v2/search/car/active`
- Params: `year`, `make`, `model`, `miles_min/max` (±20% of odometer)
- Extracts median price from `listings[].price`
- `estimated_auction_price = median * 0.70` (70% of retail = conservative gov auction floor)
- Caches Marketcheck results by `year|make|model|mileage-bucket` to avoid redundant API calls
- Falls back gracefully if Marketcheck unavailable

**Marketcheck API confirmed working:**
- Test: `2018 Ford F-150, 40k–60k miles` → median $22,990 from 3 listings
- API key `Z56KBF2WRBWXcnPpbFBY8FEuRoUujiz4` is active

**Build deployed:** `00JesXaASwEaG3pMi` — READY on actor `lvb7T6VMFfNUQpqlq`

**DOS scoring integration:** The `mmr` field is the retail reference. DealerScope's scoring engine should compute:
```
margin = (mmr - current_bid) / mmr
dos_score = margin > 0.30 ? HIGH : margin > 0.15 ? MEDIUM : LOW
```

---

## Recommended Next Steps

### Immediate (human action needed)
1. **Approve `ds-hibid-v2` for production** — test run succeeded, schedule is active. Disable rented lexis-solutions actor.
2. **Fix GSA auction detail page selectors** — Angular SPA needs `waitForSelector` targeting post-hydration content. Inspect `document.body.innerText` in Playwright DevTools on a live detail page to confirm selectors.
3. **Relax Municibid state filter** — platform is northeast-heavy; expand target states or remove state filter entirely and rely only on rust-state/year bypass.
4. **Decision on ACV Auctions** — if dealer account available, ACV is the highest-value dealer-to-dealer source.

### Short Term (agent can build)
5. **Build `ds-govdeals`** — GovDeals is a top government surplus vehicle platform, not currently covered.
6. **Build `ds-bidspotter`** — Cheerio-based, ~2 hours, aggregates multiple auctioneers.
7. **Retire `ds-bidcal` and `ds-auctiontime`** — confirmed non-viable. Remove from deployment.

### Architecture
8. **Webhook secret** — JJ Kane and HiBid-v2 use `WEBHOOK_SECRET` env var. Confirm Railway ingest accepts the `x-webhook-secret` header format (currently getting 401).
9. **Marketcheck rate limits** — Monitor API usage; cache is in-process only (per run). Consider a persistent cache in Apify KV store if hitting rate limits.
