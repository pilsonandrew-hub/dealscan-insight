# ds-usgovbid — USGovBid Impound Vehicle Scraper

Scrapes government impound and surplus vehicle listings from [usgovbid.com](https://usgovbid.com).

## Architecture

USGovBid uses a two-layer architecture:

1. **usgovbid.com** — WordPress site with The Events Calendar plugin
   - Public REST API: `GET /wp-json/tribe/events/v1/events`
   - Returns auction events with title, venue (city/state), dates, and links to bid platform

2. **bid.usgovbid.com** — Maxanet auction platform
   - Individual lot pages loaded via AJAX: `POST /Public/Auction/GetAuctionItems`
   - Requires session cookie + CSRF token (obtained from page load via Playwright)

## Strategy

1. Fetch upcoming auction events via WordPress Events Calendar REST API
2. For each auction that links to `bid.usgovbid.com`:
   - Load the AuctionItems page in Playwright to capture session/CSRF
   - POST to `GetAuctionItems` endpoint from within browser context to load lot HTML
   - Parse lot cards: title, current bid, end date, lot URL, photo
3. Filter for vehicles (by keyword and make detection)
4. Apply rust-state, bid range ($500–$35k), and vehicle age (≤12yr) filters
5. Push normalized records to Apify dataset

## Filters

- **Rust states excluded**: OH, MI, PA, NY, WI, MN, IL, IN, MO, IA, ND, SD, NE, KS, WV, ME, NH, VT, MA, RI, CT, NJ, MD, DE
- **Bid range**: $500–$35,000 (configurable)
- **Vehicle age**: ≤ 12 years

## Output Fields

| Field | Description |
|-------|-------------|
| `title` | Lot title as listed |
| `make` | Extracted vehicle make |
| `model` | Extracted vehicle model |
| `year` | Model year |
| `current_bid` | Current bid amount |
| `state` | 2-letter state code |
| `location` | City, State |
| `auction_end_time` | ISO 8601 auction end datetime |
| `listing_url` | Direct link to lot on bid.usgovbid.com |
| `photo_url` | Primary lot photo URL |
| `agency_name` | Selling agency name |
| `source_site` | `"usgovbid"` |
| `scraped_at` | ISO 8601 scrape timestamp |

## Apify Deployment

| Resource | ID |
|----------|-----|
| Actor | `6XO9La81aEmtsCT3g` |
| Schedule | `PZRUZq76opvUAxTzV` (every 3hr: `0 */3 * * *`) |
| Webhook | `QhPfZWcztslsbKDlm` → Railway ingest endpoint |

## Site Notes

- USGovBid typically has 3–10 active auctions at any time
- Each auction covers one government agency (county sheriff, state surplus, etc.)
- Lot counts range from 20–200 per auction; not all lots are vehicles
- Vehicle lots are usually labeled "Vehicles" category on the Maxanet platform
- The Maxanet AJAX endpoint requires a live session — Playwright is required
