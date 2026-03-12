# GovDeals API Reverse Engineering Notes
_Research date: 2026-03-11 | Goal: replace parseforge~govdeals-scraper ($14.99/mo)_

---

## Summary

GovDeals is a Liquidity Services Angular SPA. All lot/search data comes from a
backend API at **maestro.lqdt1.com** — but the API requires authentication.
parseforge captures the auth token from the Angular app's initial page load, then
calls the API directly for bulk data.

---

## Probe Results

| Endpoint | GET | POST | Notes |
|---|---|---|---|
| `maestro.lqdt1.com/menus/categories/alphabetical` | 405 | **401** | EXISTS, needs auth |
| `maestro.lqdt1.com/richrelevance/recommendations` | 405 | **401** | EXISTS, needs auth |
| `maestro.lqdt1.com/assets?siteId=1&...` | 404 | — | Wrong URL prefix |
| `maestro.lqdt1.com/lots?siteId=1&...` | 404 | — | Wrong URL prefix |
| `maestro.lqdt1.com/` | 301 → index.html | — | Azure CDN |
| All other guessed paths | 404 | — | — |

**Key finding:** 401 on POST (not 403) = auth token required, not IP-blocked.
The token is likely a per-session JWT or Bearer token issued when the Angular
app boots.

---

## How parseforge Likely Works

1. **Playwright loads GovDeals homepage** → Angular boots
2. **Angular calls maestro.lqdt1.com** with an auth token (JWT/Bearer) in the
   Authorization header — this token is likely obtained from the Angular app's
   init sequence (possibly from `environment.js` or a `/auth/token` endpoint)
3. **parseforge intercepts that request**, extracts the auth token + discovers
   the exact search API endpoint + URL structure
4. **Calls the search API directly** with the captured token, paginating
   through all pages — no DOM scraping needed, pure API
5. Token is short-lived → must re-capture on each run

---

## Path Forward: Free Replacement Strategy

### Approach A — Token Capture (Best)
Use Playwright to:
1. Load `https://www.govdeals.com/`
2. Intercept network requests to `maestro.lqdt1.com`
3. Capture the **full request headers** (Authorization, Cookie, x-api-key, etc.)
   from the FIRST API call that returns lot/asset data
4. Use those headers to call the search/assets API directly for all pages
5. No more DOM scraping — pure JSON API calls

Key: capture `request.headers()` not just `response.json()`. We were only
capturing responses before.

### Approach B — Full Intercept Replay
Capture the complete URL + headers + method of the search API call, then
replay it with page params incremented.

### Approach C — Stay on parseforge
At $14.99/mo it's the cheapest option until we have paying users. Revisit
when volume justifies the engineering time.

---

## Known Data Shape (parseforge output)
```json
{
  "title": "2008 Chevrolet C6C042 Mobile Office / Interview Truck",
  "url": "https://www.govdeals.com/en/asset/{accountId}/{assetId}",
  "make": "Chevrolet",
  "model": "C6C042",
  "modelYear": "2008",
  "currentBid": 825,
  "locationState": "LA",
  "locationCity": "New Orleans",
  "auctionEndUtc": "2026-03-12T01:09:00Z",
  "seller": "Navy Region Southeast",
  "imageUrl": "https://webassets.lqdt1.com/assets/photos/...",
  "photos": ["url1", "url2", ...],
  "vin": null,
  "meterCount": null,
  "breadcrumbs": ["Transportation", "Specialized Vehicles"]
}
```

---

## Files
- `src/main.js` — current Playwright click-nav + intercept attempt (partial)
- `src/main_api.js` — token-capture replacement (see below, TODO: implement)

---

## TODO for Free Replacement
- [ ] Intercept `request.headers()` (not just response) in Playwright
- [ ] Find the exact Authorization header format (Bearer JWT vs API key vs cookie)
- [ ] Identify the search API endpoint path (not just /menus/ or /recommendations)
- [ ] Implement `src/main_api.js` with token-capture + bulk API calls
- [ ] Test on Apify, validate output matches parseforge format
- [ ] Cancel parseforge subscription once validated

## Phase 5 Browser Recon - Thu Mar 12 06:48:31 PDT 2026

OpenClaw browser profile `openclaw` was started successfully and GovDeals loaded
cleanly in Chrome over CDP port `18800`. `openclaw browser snapshot` confirmed
the Angular-rendered homepage DOM, including direct category routes like
`/en/automobiles-cars` and `/en/passenger-vehicles`.

`openclaw browser requests > /tmp/govdeals_requests.json` only emitted a single
StackAdapt tracking request in this environment, so I supplemented the recon by
attaching Playwright to the same OpenClaw-backed Chrome target and replaying the
homepage plus `/en/passenger-vehicles`. That capture was saved to
`/tmp/govdeals_requests_cdp.json`.

Observed `maestro.lqdt1.com` requests:

- `GET /buyers/servertimestamp`
- `POST /menus/categories/alphabetical`
- `POST /richrelevance/recommendations`
- `POST /search/list`

Observed auth pattern:

- No `Authorization` bearer header was present on the captured GovDeals flow.
- No request `Cookie` header was required on the captured maestro requests.
- All captured maestro requests carried the same `x-api-key` header:
  `af93060f-337e-428c-87b8-c74b5837d6cd`

Observed search endpoint:

- `POST https://maestro.lqdt1.com/search/list`
- Content type: JSON
- Response header `x-total-count` exposed total hits (`2363` on passenger
  vehicles)
- Response body contains `assetSearchResults`, which includes fields like
  `accountId`, `assetId`, `assetShortDescription`, `makebrand`, `model`,
  `modelYear`, `currentBid`, `locationCity`, `locationState`,
  `assetAuctionEndDateUtc`, `photo`, and `categoryDescription`

Observed payload pattern for passenger vehicles:

```json
{
  "categoryIds": "",
  "businessId": "GD",
  "searchText": "*",
  "isQAL": false,
  "locationId": null,
  "model": "",
  "makebrand": "",
  "auctionTypeId": null,
  "page": 1,
  "displayRows": 24,
  "sortField": "currentbid",
  "sortOrder": "desc",
  "sessionId": "02a65be3-bb8a-4985-99b6-c8b39608e614",
  "requestType": "search",
  "responseStyle": "productsOnly",
  "facets": [
    "categoryName",
    "auctionTypeID",
    "condition",
    "saleEventName",
    "sellerDisplayName",
    "product_pricecents",
    "isReserveMet",
    "hasBuyNowPrice",
    "isReserveNotMet",
    "sellerType",
    "warehouseId",
    "region",
    "currencyTypeCode",
    "categoryName",
    "tierId"
  ],
  "facetsFilter": [
    "{!tag=product_category_external_id}product_category_external_id:\"t6\"",
    "{!tag=product_category_external_id}product_category_external_id:\"94Q\""
  ],
  "timeType": "",
  "sellerTypeId": null,
  "accountIds": []
}
```

Vehicle-link probe result:

- `openclaw browser evaluate --fn '() => document.querySelectorAll("a[href*=vehicle], a[href*=Vehicle], a[href*=automobile]").length + " vehicle links found"'`
  returned `21 vehicle links found`

Conclusion:

- GovDeals does expose the lot search API directly.
- The practical replay path is `POST /search/list` with JSON body pagination and
  the captured `x-api-key`.
- The remaining implementation risk is recapturing a valid `sessionId` and the
  relevant `facetsFilter` set for the category being scraped.
