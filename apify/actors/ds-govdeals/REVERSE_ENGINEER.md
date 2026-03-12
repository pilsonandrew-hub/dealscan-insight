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
