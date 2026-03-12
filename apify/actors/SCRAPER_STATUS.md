# Scraper Status

Updated: 2026-03-12

| Actor | Current status | Last known issue | What is needed to fix |
| --- | --- | --- | --- |
| `ds-publicsurplus` | Fixed in Phase 3 | Wrong category seed (`catid=57`) redirected to all categories; list selectors were looking for `/sms/auction/view` and missing the locale-aware `/sms/all,wa/auction/view?auc=` paths. | Re-test in Apify against live pagination and confirm the current `#auctionTableView` row parsing still matches production markup. |
| `ds-municibid` | Fixed in Phase 3 | Web fallback was pointed at a dead path (`/government-surplus-auction/vehicles`) and list/detail selectors did not match current `Browse` / `Listing/Details` markup. | Re-test pagination and confirm API-first fallback stays harmless if Municibid changes private endpoints again. |
| `ds-allsurplus` | Blocked in current environment | `https://www.allsurplus.com/` returns `Access Denied` from Akamai before usable listing DOM is available; selector work cannot be validated from this environment. Direct POST remains removed. | Browser recon with a real session that can reach the Angular app, then inspect rendered auction card markup and patch selectors from live DOM. |
| `ds-bidcal` | Blocked in current environment | `https://bidcal.com/` presents a certificate mismatch and the root responds `404 Not Found`; current target path cannot be trusted. | Browser recon plus domain verification to confirm the live BidCal host/path before any selector work. |
| `ds-auctiontime` | Blocked in current environment | AuctionTime serves a Distil/hCaptcha interruption page instead of listings, including in headless browser inspection from this workspace. | Browser recon with a session that can clear bot protection, then inspect live list/detail markup and patch selectors. |
| `ds-govdeals` | Blocked for Phase 5 | Angular SPA backed by authenticated Liquidity Services APIs; DOM scraping is the wrong layer. Reverse-engineering notes already show token capture is required. | OpenClaw browser recon to intercept auth headers and replay the real lot/search API. See `apify/actors/ds-govdeals/REVERSE_ENGINEER.md`. |
| `ds-gsaauctions` | Blocked for Phase 5 | Marked Phase 5 blocked alongside GovDeals per triage instructions; current actor should not be treated as selector-fixable in this phase. | OpenClaw browser recon in Phase 5 to confirm the real navigation/data path before further implementation. |
| `ds-hibid` | Not triaged in this phase | Out of scope for this request; no Phase 3 changes made. | Separate validation pass if HiBid is part of the next scraper triage batch. |
