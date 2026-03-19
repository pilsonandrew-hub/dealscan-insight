/**
 * ds-jjkane — JJ Kane Government Surplus Vehicle Auction Scraper
 *
 * STATUS: NEW — API-based (Algolia), no Playwright needed
 *
 * Architecture:
 *   JJ Kane (jjkane.com) is a major government surplus auctioneer with sites
 *   across the US (NV, FL, CA, OH, TX, etc.). Nevada State Surplus uses JJ Kane
 *   as its primary auction platform. Florida also has significant JJ Kane presence.
 *
 *   JJ Kane exposes a public Algolia search index (discovered from their website):
 *     App ID: ICB6K32PD0
 *     Search API Key: 9d3241f7a3ee8947997deaa33cb0b249 (read-only)
 *     Index: api_items
 *
 *   This is completely public (no auth needed, key is embedded in page JS).
 *
 * Strategy:
 *   1. Query Algolia index for vehicle categories in target (non-rust) states
 *   2. Filter by year, make, category, and location
 *   3. Paginate using Algolia's page/hitsPerPage params
 *   4. Push normalized records to Apify dataset
 *
 * Vehicle categories on JJ Kane:
 *   - PICKUP TRUCK
 *   - SPORT UTILITY VEHICLE (SUV)
 *   - AUTOMOBILE
 *   - VAN - FULLSIZE
 *   - SERVICE TRUCK (1-TON AND UNDER)
 *   - VAN BODY/BOX TRUCK
 *   - DUMP TRUCK
 *   - FLATBED/SERVICE TRUCK
 *
 * Note: JJ Kane has ~5600 total items, ~420 vehicles in FL alone. High value target.
 * Nevada State Surplus auctions route through JJ Kane Las Vegas/Reno sites.
 */

import { Actor } from 'apify';

const SOURCE = 'jjkane';
const ALGOLIA_APP_ID = 'ICB6K32PD0';
const ALGOLIA_SEARCH_KEY = '9d3241f7a3ee8947997deaa33cb0b249';
const ALGOLIA_INDEX = 'api_items';
const ALGOLIA_URL = `https://${ALGOLIA_APP_ID}-dsn.algolia.net/1/indexes/${ALGOLIA_INDEX}/query`;

// Vehicle categories on JJ Kane (capitalized exactly as they appear)
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

// States with real vehicle volume at JJ Kane (non-rust belt)
const TARGET_STATES = [
    'FL', 'NV', 'CA', 'TX', 'AZ', 'CO', 'UT', 'OR', 'WA', 'GA',
    'NC', 'VA', 'TN', 'SC', 'AL', 'LA', 'OK', 'NM', 'ID', 'MT',
    'WY', 'ND', 'SD', 'NE', 'KS',
];

const HIGH_RUST_STATES = new Set([
    'OH', 'MI', 'PA', 'NY', 'WI', 'MN', 'IL', 'IN', 'MO', 'IA',
    'WV', 'ME', 'NH', 'VT', 'MA', 'RI', 'CT', 'NJ', 'MD', 'DE',
]);

// ── Helpers ──────────────────────────────────────────────────────────────────

function normalizeText(v) {
    return String(v ?? '').replace(/\s+/g, ' ').trim();
}

function parseYear(v) {
    const y = parseInt(v, 10);
    return (y >= 1980 && y <= new Date().getFullYear() + 1) ? y : null;
}

function parseBid(v) {
    if (!v) return 0;
    const m = String(v).replace(/,/g, '').match(/[\d]+(?:\.\d+)?/);
    return m ? parseFloat(m[0]) : 0;
}

function parseDate(v) {
    if (!v) return null;
    // JJ Kane format: "MM/DD/YYYY"
    const m = String(v).match(/(\d{1,2})\/(\d{1,2})\/(\d{4})/);
    if (m) {
        const d = new Date(`${m[3]}-${m[1].padStart(2, '0')}-${m[2].padStart(2, '0')}T23:59:00-05:00`);
        return isNaN(d.getTime()) ? null : d.toISOString();
    }
    return null;
}

function buildListingUrl(itemId) {
    return `https://www.jjkane.com/items/${itemId}`;
}

function buildImageUrl(itemId) {
    return `https://prod.cdn.jjkane.com/${itemId}-1?template=Medium`;
}

// ── Algolia Query ──────────────────────────────────────────────────────────────

async function queryAlgolia({ categoryFilter, stateFilter, page = 0, hitsPerPage = 100 }) {
    const filters = [categoryFilter, stateFilter].filter(Boolean).join(' AND ');

    const body = JSON.stringify({
        query: '',
        filters,
        page,
        hitsPerPage,
        attributesToRetrieve: [
            'id', 'kp_title', 'make', 'model', 'year', 'category',
            'offSitePhysicalCity', 'offSitePhysicalState',
            'ringCloseOutDate', 'currentBid', 'shortDescription',
            'lotNumber', 'auctionId',
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
    maxBid = 35000,
    maxYearAge = 15,
    maxItemsPerState = 500,
} = input;

const currentYear = new Date().getFullYear();
let totalFound = 0;
let totalPassed = 0;

// Build Algolia filter string for vehicle categories
const categoryFilter = `(${VEHICLE_CATEGORIES.map(c => `category:"${c}"`).join(' OR ')})`;

for (const state of targetStates) {
    if (HIGH_RUST_STATES.has(state)) continue;

    const stateFilter = `offSitePhysicalState:${state}`;
    let page = 0;
    let statePassed = 0;

    console.log(`[JJKANE] Querying state: ${state}`);

    try {
        // Get first page to check nbHits
        const firstPage = await queryAlgolia({ categoryFilter, stateFilter, page: 0, hitsPerPage: 100 });
        const nbHits = firstPage.nbHits ?? 0;
        const nbPages = firstPage.nbPages ?? 1;

        console.log(`[JJKANE] ${state}: ${nbHits} vehicle lots across ${nbPages} pages`);

        const allPages = [firstPage];

        // Fetch remaining pages (up to limit)
        for (let p = 1; p < nbPages && statePassed < maxItemsPerState; p++) {
            await new Promise(r => setTimeout(r, 250)); // polite delay
            const pageData = await queryAlgolia({ categoryFilter, stateFilter, page: p, hitsPerPage: 100 });
            allPages.push(pageData);
        }

        for (const pageData of allPages) {
            for (const hit of (pageData.hits ?? [])) {
                totalFound++;

                const itemId = hit.id;
                const title = normalizeText(hit.kp_title || hit.shortDescription || '');
                const make = normalizeText(hit.make || '');
                const model = normalizeText(hit.model || '');
                const year = parseYear(hit.year);
                const state_code = hit.offSitePhysicalState || state;
                const city = normalizeText(hit.offSitePhysicalCity || '');
                const location = [city, state_code].filter(Boolean).join(', ');
                const current_bid = parseBid(hit.currentBid);
                const auction_end_time = parseDate(hit.ringCloseOutDate);
                const listing_url = buildListingUrl(itemId);
                const photo_url = buildImageUrl(itemId);

                // Filter: rust states (belt check already done at state level, but extra safety)
                if (HIGH_RUST_STATES.has(state_code)) continue;

                // Filter: year age
                if (year && (currentYear - year) > maxYearAge) continue;

                // Filter: bid range (skip items with no bid yet — they're still valuable at $0)
                if (current_bid > 0 && current_bid > maxBid) continue;
                if (current_bid > 0 && current_bid < minBid) continue;

                const record = {
                    title,
                    make,
                    model,
                    year,
                    current_bid,
                    state: state_code,
                    location,
                    city,
                    auction_end_time,
                    listing_url,
                    photo_url,
                    lot_number: String(hit.lotNumber || ''),
                    auction_id: String(hit.auctionId || ''),
                    category: normalizeText(hit.category || ''),
                    agency_name: 'JJ Kane Government Surplus',
                    source_site: SOURCE,
                    scraped_at: new Date().toISOString(),
                };

                await Actor.pushData(record);
                totalPassed++;
                statePassed++;
            }
        }

        console.log(`[JJKANE] ${state}: ${statePassed} vehicles passed filters`);

    } catch (err) {
        console.error(`[JJKANE] Error querying state ${state}: ${err.message}`);
    }

    // Pause between states
    await new Promise(r => setTimeout(r, 500));
}

console.log(`[JJKANE] Scrape complete. Found: ${totalFound} | Passed filters: ${totalPassed}`);

await Actor.exit();
