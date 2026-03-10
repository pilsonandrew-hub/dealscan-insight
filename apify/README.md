# DealerScope Apify Actors

Apify scraper actors for ingesting vehicle auction data into DealerScope for arbitrage analysis.

## Actors

### `ds-govdeals` — GovDeals Vehicle Scraper
Scrapes vehicle listings from [GovDeals.com](https://www.govdeals.com) (Category 1050: Automobiles & Trucks).

- **Buyer premium:** 12.5%
- **Doc fee:** $75
- **Source tag:** `govdeals`

### `ds-publicsurplus` — PublicSurplus Vehicle Scraper
Scrapes vehicle listings from [PublicSurplus.com](https://www.publicsurplus.com) (Category 1: Vehicles).

- **Buyer premium:** 10%
- **Doc fee:** $50
- **Source tag:** `publicsurplus`

## Actor Input Parameters

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `maxPages` | integer | 10 | Max listing pages to scrape |
| `minBid` | integer | 500 | Minimum current bid (USD) |
| `maxBid` | integer | 35000 | Maximum current bid (USD) |
| `targetStates` | string[] | AZ,CA,NV,CO,NM,UT,TX,FL,GA,SC,TN,NC,VA,WA,OR,HI | Low-rust states to prioritize |
| `vehicleCategories` | string[] | ["Automobiles & Trucks"] | Categories to scrape |

## Deploying to Apify

1. **Install Apify CLI:**
   ```bash
   npm install -g apify-cli
   apify login
   ```

2. **Deploy GovDeals actor:**
   ```bash
   cd apify/actors/ds-govdeals
   npm install
   apify push
   ```

3. **Deploy PublicSurplus actor:**
   ```bash
   cd apify/actors/ds-publicsurplus
   npm install
   apify push
   ```

4. **Configure webhook** in Apify Console → Actor → Settings → Webhooks:
   - Event: `ACTOR.RUN.SUCCEEDED`
   - URL: `https://your-dealerscope-domain.com/api/ingest/apify`
   - HTTP method: `POST`
   - Add header: `X-Apify-Webhook-Secret: <your APIFY_WEBHOOK_SECRET>`

5. **Schedule runs** in Apify Console → Schedules:
   - Recommended: every 2–4 hours for active auction monitoring

## Webhook Flow

```
Apify Actor Run Completes
        ↓
Apify sends POST to /api/ingest/apify
        ↓
DealerScope verifies X-Apify-Webhook-Secret header
        ↓
Fetches dataset items from Apify API
        ↓
Normalizes → Gate filters → DOS score calculation
        ↓
Hot deals (score ≥ 80) flagged in response
        ↓
(TODO) Save to Supabase opportunities table
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `APIFY_API_TOKEN` | Your Apify API token (from Apify Console → Settings → Integrations) |
| `APIFY_WEBHOOK_SECRET` | Shared secret for webhook verification (set same value in Apify webhook config) |

Set these in your `.env` file or deployment environment (Cloud Run, Railway, etc.).

## Rust State Filter

**Filtered OUT (high rust):** OH, MI, PA, NY, WI, MN, IL, IN, MO, IA, ND, SD, NE, KS, WV, ME, NH, VT, MA, RI, CT, NJ, MD, DE

**Targeted (low rust):** AZ, CA, NV, CO, NM, UT, TX, FL, GA, SC, TN, NC, VA, WA, OR, HI, OK, AR, LA, MS, AL
