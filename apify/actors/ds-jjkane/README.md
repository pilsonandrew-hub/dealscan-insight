# ds-jjkane — JJ Kane Government Surplus Vehicle Scraper

## Overview

JJ Kane (jjkane.com) is one of the largest government surplus auction companies in the US.
They operate physical auction sites and online timed auctions covering 25+ states.

**Key coverage this actor adds:**
- **Nevada State Surplus** — officially uses JJ Kane Las Vegas (Henderson, NV) and Reno sites
- **Florida** — JJ Kane has 420+ vehicle lots active in FL at any given time (Tampa, West Palm Beach, Westlake, Riviera Beach)
- **California, Texas, Georgia, NC, VA** — major secondary markets

## Platform

JJ Kane exposes a **public Algolia search index** embedded in their website JavaScript:
- App ID: `ICB6K32PD0`
- Search API Key: `9d3241f7a3ee8947997deaa33cb0b249` (read-only, no auth required)
- Index: `api_items`

No Playwright needed — pure HTTP API calls. Very fast and reliable.

## Vehicle Categories Scraped

- PICKUP TRUCK
- SPORT UTILITY VEHICLE (SUV)  
- AUTOMOBILE
- VAN - FULLSIZE
- SERVICE TRUCK (1-TON AND UNDER)
- VAN BODY/BOX TRUCK
- FLATBED/SERVICE TRUCK
- CARGO VAN

## State Coverage

Targets non-rust-belt states: FL, NV, CA, TX, AZ, CO, UT, OR, WA, GA, NC, VA, TN, SC, AL, LA, OK, NM, ID, and more.

## Input

```json
{
  "targetStates": ["FL", "NV", "CA", "TX"],
  "minBid": 0,
  "maxBid": 35000,
  "maxYearAge": 15,
  "maxItemsPerState": 500
}
```

## Output Fields

| Field | Type | Description |
|-------|------|-------------|
| title | string | Full lot title |
| make | string | Vehicle make |
| model | string | Vehicle model |
| year | number | Model year |
| current_bid | number | Current bid in USD |
| state | string | 2-letter state code |
| location | string | City, State |
| auction_end_time | string | ISO 8601 close time |
| listing_url | string | Direct lot URL |
| photo_url | string | Primary lot photo |
| lot_number | string | JJ Kane lot number |
| auction_id | string | Auction ID |
| category | string | JJ Kane category |
| source_site | string | "jjkane" |
| scraped_at | string | ISO 8601 scrape time |

## Notes

- Nevada State Surplus program officially routes through JJ Kane
- floridabid.com is a procurement portal (not auction site) — FL surplus auctions are via JJ Kane
- Items with `currentBid: 0` are open-but-unbid lots — still valuable as early alerts
- JJ Kane also uses Proxibid for live auction bidding; this actor focuses on online timed auctions
