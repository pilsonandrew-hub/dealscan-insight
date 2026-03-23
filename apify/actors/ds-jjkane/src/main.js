/**
 * ds-jjkane — JJ Kane Government Surplus Vehicle Auction Scraper
 *                + Marketcheck Retail Pricing
 *
 * STATUS: WORKING — Algolia API + Marketcheck price estimation
 *
 * Architecture:
 *   JJ Kane (jjkane.com) is a major government surplus auctioneer.
 *   Uses public Algolia search index.
 *
 *   After scraping each vehicle, calls Marketcheck to get retail price:
 *     estimated_auction_price = marketcheck_median * 0.70
 *   (Government auctions clear at ~60-75% of retail — 70% is conservative floor)
 *
 * Key Algolia fields:
 *   make, model, year, odometer (string like "046379"), offSitePhysicalState,
 *   ringCloseOutDate, catalogDescription, category, webDescription
 *
 * Marketcheck API:
 *   https://mc-api.marketcheck.com/v2/search/car/active
 *   api_key=cwOBTpHcggdsdrDjQVtXPe5tsWsrU5aD
 *   params: year, make, model, miles_min, miles_max (±20% of odometer)
 */

import { Actor } from 'apify';

const SOURCE = 'jjkane';
const ALGOLIA_APP_ID = 'ICB6K32PD0';
const ALGOLIA_SEARCH_KEY = '9d3241f7a3ee8947997deaa33cb0b249';
const ALGOLIA_INDEX = 'api_items';
const ALGOLIA_URL = `https://${ALGOLIA_APP_ID}-dsn.algolia.net/1/indexes/${ALGOLIA_INDEX}/query`;

const MARKETCHECK_KEY = 'cwOBTpHcggdsdrDjQVtXPe5tsWsrU5aD';
const MARKETCHECK_URL = 'https://mc-api.marketcheck.com/v2/search/car/active';

// Auction-to-retail discount factor (government surplus clears at 60-75% retail)
const AUCTION_DISCOUNT = 0.70;

// Vehicle categories we want
const VEHICLE_CATEGORIES = [
    'PICKUP TRUCK',
    'SPORT UTILITY VEHICLE (SUV)',
    'AUTOMOBILE',
    'VAN - FULLSIZE',
    'SERVICE TRUCK (1-TON AND UNDER)',
    'VAN BODY/BOX TRUCK',
    'FLATBED/SERVICE TRUCK',
    'CARGO VAN',
    'SEDAN',
];

const TARGET_STATES = [
    'FL', 'NV', 'CA', 'TX', 'AZ', 'CO', 'UT', 'OR', 'WA', 'GA',
    'NC', 'VA', 'TN', 'SC', 'AL', 'LA', 'OK', 'NM', 'ID', 'MT',
    'WY', 'ND', 'SD', 'NE', 'KS',
];

const HIGH_RUST_STATES = new Set([
    'OH', 'MI', 'PA', 'NY', 'WI', 'MN', 'IL', 'IN', 'MO', 'IA',
    'WV', 'ME', 'NH', 'VT', 'MA', 'RI', 'CT', 'NJ', 'MD', 'DE',
]);

// ── Helpers ───────────────────────────────────────────────────────────────────

function normalizeText(v) {
    return String(v ?? '').replace(/\s+/g, ' ').trim();
}

function parseYear(v) {
    const y = parseInt(String(v ?? '').replace(/\D/g, ''), 10);
    return (y >= 1980 && y <= new Date().getFullYear() + 1) ? y : null;
}

function parseOdometer(v) {
    // e.g. "046379" or "46,379" or "46379 Miles"
    if (!v) return null;
    const clean = String(v).replace(/[^\d]/g, '');
    const miles = parseInt(clean, 10);
    return (!isNaN(miles) && miles > 0 && miles < 1000000) ? miles : null;
}

function parseBid(v) {
    if (!v) return 0;
    const m = String(v).replace(/,/g, '').match(/[\d]+(?:\.\d+)?/);
    return m ? parseFloat(m[0]) : 0;
}

function parseDate(v) {
    if (!v) return null;
    // "MM/DD/YYYY" or "YYYY-MM-DD" or Unix timestamp
    const asNum = Number(v);
    if (!isNaN(asNum) && asNum > 1000000000) {
        return new Date(asNum * 1000).toISOString();
    }
    const m = String(v).match(/(\d{1,2})\/(\d{1,2})\/(\d{4})/);
    if (m) {
        const d = new Date(`${m[3]}-${m[1].padStart(2, '0')}-${m[2].padStart(2, '0')}T23:59:00-05:00`);
        return isNaN(d.getTime()) ? null : d.toISOString();
    }
    try {
        const d = new Date(v);
        return isNaN(d.getTime()) ? null : d.toISOString();
    } catch { return null; }
}

function buildListingUrl(itemId) {
    return `https://www.jjkane.com/items/${itemId}`;
}

function buildImageUrl(itemId) {
    return `https://prod.cdn.jjkane.com/${itemId}-1?template=Medium`;
}

function median(arr) {
    if (!arr || arr.length === 0) return null;
    const sorted = [...arr].sort((a, b) => a - b);
    const mid = Math.floor(sorted.length / 2);
    return sorted.length % 2 === 0
        ? (sorted[mid - 1] + sorted[mid]) / 2
        : sorted[mid];
}

// ── Marketcheck API ───────────────────────────────────────────────────────────

// Cache to avoid re-querying same make/model/year/mileage band
const marketcheckCache = new Map();
const MAX_MARKETCHECK_CALLS_PER_RUN = 50; // Protect 500/month quota
let marketcheckCallsThisRun = 0;

async function getMarketcheckPrice(year, make, model, odometer) {
    if (!year || !make || !model) return null;

    const makeLower = make.toLowerCase().trim();
    const modelRaw = model.toLowerCase().trim();

    // Normalize model name for Marketcheck API
    const modelNormalized = modelRaw
        .replace(/\s*(police|interceptor|package|special|fleet|pursuit|4x4|4wd|awd|rwd|fwd|diesel|hybrid|hev|phev|turbo|sport|limited|xl|xlt|lariat|stx|slt|lt|ltz|ls|le|se|sel|ex|exl|touring|platinum|king\s*ranch|raptor|rebel|laramie|tradesman|big\s*horn|lone\s*star).*$/i, '')
        .replace(/\bf(\d{3})\b/g, 'f-$1')   // f150 → f-150, f250 → f-250, f350 → f-350
        .replace(/\be(\d{3})\b/g, 'e-$1')   // e250 → e-250, e350 → e-350
        .replace(/\bram\b\s+(\d{3,4})/g, '$1') // "ram 1500" → "1500" (Dodge/Ram model)
        .replace(/\bsierr?a\b\s+(\d{3,4})/g, 'sierra $1')
        .replace(/\bsilverado\b\s+(\d{3,4})/g, 'silverado $1')
        .trim();

    // Miles band: ±20% of odometer (or 0–999999 if no odometer)
    let milesMin = 0;
    let milesMax = 999999;
    if (odometer && odometer > 0) {
        milesMin = Math.max(0, Math.floor(odometer * 0.80));
        milesMax = Math.ceil(odometer * 1.20);
    }

    // Round to nearest 5000 for cache key
    const milesKey = odometer ? Math.round(odometer / 5000) * 5000 : 0;
    const cacheKey = `${year}|${makeLower}|${modelNormalized}|${milesKey}`;
    if (marketcheckCallsThisRun >= MAX_MARKETCHECK_CALLS_PER_RUN) {
            return { estimated_auction_price: 0, pricing_source: 'quota_exceeded' };
        }
        if (marketcheckCache.has(cacheKey)) {
        return marketcheckCache.get(cacheKey);
    }

    const params = new URLSearchParams({
        api_key: MARKETCHECK_KEY,
        year: String(year),
        make: makeLower,
        model: modelNormalized,
        miles_min: String(milesMin),
        miles_max: String(milesMax),
        rows: '20',
        start: '0',
        fields: 'price,miles',
    });

    try {
        marketcheckCallsThisRun++; // count every actual API call (success or error)
        const resp = await fetch(`${MARKETCHECK_URL}?${params}`, {
            signal: AbortSignal.timeout(10000),
            headers: { 'Accept': 'application/json' },
        });

        if (!resp.ok) {
            console.warn(`[MC] HTTP ${resp.status} for ${year} ${make} ${model}`);
            marketcheckCache.set(cacheKey, null);
            return null;
        }

        const data = await resp.json();
        const listings = data?.listings ?? [];

        if (listings.length === 0) {
            marketcheckCache.set(cacheKey, null);
            return null;
        }

        // Extract valid prices
        const prices = listings
            .map(l => parseFloat(String(l.price ?? '0').replace(/,/g, '')))
            .filter(p => p > 500 && p < 500000);

        if (prices.length === 0) {
            marketcheckCache.set(cacheKey, null);
            return null;
        }

        const medianPrice = median(prices);
        const result = {
            retail_median: Math.round(medianPrice),
            estimated_auction_price: Math.round(medianPrice * AUCTION_DISCOUNT),
            sample_count: prices.length,
        };

        marketcheckCache.set(cacheKey, result);
        return result;

    } catch (err) {
        console.warn(`[MC] Error for ${year} ${make} ${model}: ${err.message}`);
        marketcheckCache.set(cacheKey, null);
        return null;
    }
}

// ── Algolia Query ─────────────────────────────────────────────────────────────

async function queryAlgolia({ categoryFilter, stateFilter, page = 0, hitsPerPage = 100 }) {
    const filters = [categoryFilter, stateFilter].filter(Boolean).join(' AND ');

    const body = JSON.stringify({
        query: '',
        filters,
        page,
        hitsPerPage,
        attributesToRetrieve: [
            'id', 'kp_title', 'webDescription', 'make', 'model', 'year',
            'category', 'odometer', 'catalogDescription',
            'offSitePhysicalCity', 'offSitePhysicalState',
            'ringCloseOutDate', 'currentBid', 'shortDescription',
            'lotNumber', 'auctionId', 'vin',
        ],
    });

    const resp = await fetch(ALGOLIA_URL, {
        method: 'POST',
        headers: {
            'X-Algolia-Application-Id': ALGOLIA_APP_ID,
            'X-Algolia-API-Key': ALGOLIA_SEARCH_KEY,
            'Content-Type': 'application/json',
        },
        body,
        signal: AbortSignal.timeout(15000),
    });

    if (!resp.ok) {
        throw new Error(`Algolia error: ${resp.status} ${await resp.text()}`);
    }

    return await resp.json();
}

// ── Main ──────────────────────────────────────────────────────────────────────

await Actor.init();
const input = await Actor.getInput() ?? {};
const {
    targetStates = TARGET_STATES,
    minBid = 0,
    maxBid = 75000,
    maxYearAge = 15,
    maxItemsPerState = 500,
    enableMarketcheck = true,
    webhookUrl = null,
    webhookSecret = null,
} = input;

const currentYear = new Date().getFullYear();
let totalFound = 0;
let totalPassed = 0;
let totalMarketcheck = 0;

// Build Algolia filter for vehicle categories
const categoryFilter = `(${VEHICLE_CATEGORIES.map(c => `category:"${c}"`).join(' OR ')})`;

for (const state of targetStates) {
    const stateFilter = `offSitePhysicalState:${state}`;
    let page = 0;
    let statePassed = 0;

    console.log(`[JJKANE] Querying state: ${state}`);

    try {
        const firstPage = await queryAlgolia({ categoryFilter, stateFilter, page: 0, hitsPerPage: 100 });
        const nbHits = firstPage.nbHits ?? 0;
        const nbPages = firstPage.nbPages ?? 1;

        console.log(`[JJKANE] ${state}: ${nbHits} vehicle lots across ${nbPages} pages`);

        const allPages = [firstPage];

        for (let p = 1; p < nbPages && statePassed < maxItemsPerState; p++) {
            await new Promise(r => setTimeout(r, 250));
            const pageData = await queryAlgolia({ categoryFilter, stateFilter, page: p, hitsPerPage: 100 });
            allPages.push(pageData);
        }

        for (const pageData of allPages) {
            for (const hit of (pageData.hits ?? [])) {
                totalFound++;

                const itemId = hit.id;
                const title = normalizeText(
                    hit.webDescription || hit.kp_title || hit.shortDescription || ''
                );
                const make = normalizeText(hit.make || '');
                const model = normalizeText(hit.model || '');
                const year = parseYear(hit.year);
                const odometer = parseOdometer(hit.odometer);
                const state_code = normalizeText(hit.offSitePhysicalState || state);
                const city = normalizeText(hit.offSitePhysicalCity || '');
                const catalogDescription = normalizeText(hit.catalogDescription || '');
                const vin = normalizeText(hit.vin || '');

                // ── Filters ──────────────────────────────────────────────────
                // Rust state — bypass for ≤3yr old
                if (HIGH_RUST_STATES.has(state_code)) {
                    if (!(year && year >= currentYear - 2)) continue;
                    console.log(`[BYPASS] Rust ${state_code} — year ${year}`);
                }

                // Year age
                if (year && (currentYear - year) > maxYearAge) continue;

                // ── Marketcheck pricing ───────────────────────────────────────
                let marketcheckMedian = null;
                let estimatedAuctionPrice = 0;
                let pricingSource = 'jjkane_no_bid';

                if (enableMarketcheck && make && model && year) {
                    const mcResult = await getMarketcheckPrice(year, make, model, odometer);
                    if (mcResult) {
                        marketcheckMedian = mcResult.retail_median;
                        estimatedAuctionPrice = mcResult.estimated_auction_price;
                        pricingSource = `marketcheck_jjkane_estimated_${mcResult.sample_count}samples`;
                        totalMarketcheck++;
                    }
                    // Polite delay after Marketcheck call
                    await new Promise(r => setTimeout(r, 300));
                }

                // Existing currentBid from Algolia (may be 0 early in auction)
                const currentBid = parseBid(hit.currentBid);

                // Use whichever is higher: actual current bid or estimated floor
                const effectiveBid = currentBid > 0 ? currentBid : estimatedAuctionPrice;

                // Bid range filter (only applies if we have a real bid or estimate)
                if (effectiveBid > 0 && effectiveBid > maxBid) continue;
                if (effectiveBid > 0 && effectiveBid < minBid && currentBid > 0) continue;

                const record = {
                    listing_id: `jjkane-${itemId}`,
                    title,
                    make,
                    model,
                    year,
                    odometer,
                    vin: vin || null,
                    // Pricing fields
                    current_bid: effectiveBid,
                    actual_current_bid: currentBid,
                    mmr: marketcheckMedian,               // retail reference price
                    estimated_auction_price: estimatedAuctionPrice,
                    pricing_source: pricingSource,
                    // Location
                    state: state_code,
                    city,
                    location: [city, state_code].filter(Boolean).join(', '),
                    // Auction info
                    auction_end_date: parseDate(hit.ringCloseOutDate),
                    listing_url: buildListingUrl(itemId),
                    image_url: buildImageUrl(itemId),
                    lot_number: String(hit.lotNumber || ''),
                    auction_id: String(hit.auctionId || ''),
                    category: normalizeText(hit.category || ''),
                    description: catalogDescription,
                    agency_name: 'JJ Kane Government Surplus',
                    source_site: SOURCE,
                    scraped_at: new Date().toISOString(),
                };

                await Actor.pushData(record);
                totalPassed++;
                statePassed++;
                console.log(`[PASS] ${title || `${year} ${make} ${model}`} | bid=$${effectiveBid} mmr=$${marketcheckMedian ?? 'N/A'} | ${state_code}`);
            }
        }

        console.log(`[JJKANE] ${state}: ${statePassed} vehicles passed filters`);

    } catch (err) {
        console.error(`[JJKANE] Error querying state ${state}: ${err.message}`);
    }

    await new Promise(r => setTimeout(r, 500));
}

// ── Webhook notification ──────────────────────────────────────────────────────

const effectiveWebhookUrl = webhookUrl
    || process.env.WEBHOOK_URL
    || 'https://dealscan-insight-production.up.railway.app/api/ingest/apify';
const effectiveWebhookSecret = webhookSecret || process.env.WEBHOOK_SECRET || '';

if (effectiveWebhookUrl && totalPassed > 0) {
    try {
        const resp = await fetch(effectiveWebhookUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'x-webhook-secret': effectiveWebhookSecret,
            },
            body: JSON.stringify({
                source: SOURCE,
                actorRunId: process.env.APIFY_ACTOR_RUN_ID ?? 'local',
                itemCount: totalPassed,
                totalScraped: totalFound,
                marketcheckPriced: totalMarketcheck,
                timestamp: new Date().toISOString(),
            }),
            signal: AbortSignal.timeout(10000),
        });
        console.log(`[WEBHOOK] Notified ingest: HTTP ${resp.status}`);
    } catch (err) {
        console.warn(`[WEBHOOK] Failed: ${err.message}`);
    }
}

console.log(`[JJKANE COMPLETE] Found: ${totalFound} | Passed: ${totalPassed} | Marketcheck priced: ${totalMarketcheck}`);

await Actor.exit();
