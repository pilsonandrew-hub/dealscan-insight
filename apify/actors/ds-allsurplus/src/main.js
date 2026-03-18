/**
 * ds-allsurplus — AllSurplus (Ritchie Bros.) Scraper
 *
 * Uses the maestro API (maestro.lqdt1.com/search/list) discovered via network
 * interception. API is a POST endpoint with Solr-based facets filtering.
 *
 * Vehicle category IDs (product_category_external_id):
 *   - t6:  Transportation (parent)
 *   - 94Q: Passenger Vehicles
 *     - 94A: Automobiles/Cars
 *     - 94L: SUV
 *     - 94D: Vans
 *     - 94R: Electric/Hybrid Vehicle
 *     - 94:  Vehicles, Miscellaneous
 *   - 94C: Trucks (all)
 *     - 94B: Pickup Trucks
 *   - 94B: Pickup Trucks (standalone)
 *
 * Authentication: static API keys embedded in AllSurplus JS bundle.
 *   x-api-key: af93060f-337e-428c-87b8-c74b5837d6cd
 *   ocp-apim-subscription-key: cf620d1d8f904b5797507dc5fd1fdb80
 *
 * Note: These keys are public (embedded in the browser app) and used for
 * unauthenticated search. No login required.
 */

import { Actor } from 'apify';
import { v4 as uuidv4 } from 'uuid';

const SOURCE = 'allsurplus';
const BASE = 'https://www.allsurplus.com';
const MAESTRO_API = 'https://maestro.lqdt1.com/search/list';
const PHOTO_BASE = 'https://assets.allsurplus.com/assets/photos';

// API keys (embedded in AllSurplus browser bundle - public)
const API_KEY = 'af93060f-337e-428c-87b8-c74b5837d6cd';
const SUBSCRIPTION_KEY = 'cf620d1d8f904b5797507dc5fd1fdb80';

// Vehicle categories to target (Passenger Vehicles + Trucks)
// Using separate facetsFilter requests per category for stability
const VEHICLE_CATEGORY_FILTERS = [
    // Passenger Vehicles (Cars, SUVs, Vans, Electric)
    '{!tag=product_category_external_id}product_category_external_id:"94Q"',
    // Trucks (Pickup, Box, Service, etc.)
    '{!tag=product_category_external_id}product_category_external_id:"94C"',
    // Pickup Trucks specifically (also under 94C but separate for completeness)
    '{!tag=product_category_external_id}product_category_external_id:"94B"',
];

// Deduplicated single filter for all vehicle categories using Solr multi-value
// Note: facetsFilter is an array; the API takes the FIRST filter as the category constraint
// Use Transportation parent t6 to get all transportation, then filter in JS
const TRANSPORT_FILTER = '{!tag=product_category_external_id}product_category_external_id:"t6"';

// Sub-categories that are actual driveable vehicles (exclude aircraft, boats, etc.)
const VEHICLE_CATEGORY_IDS = new Set([
    '94Q', // Passenger Vehicles
    '94A', // Automobiles/Cars
    '94L', // SUV
    '94D', // Vans
    '94R', // Electric/Hybrid Vehicle
    '94',  // Vehicles, Miscellaneous
    '94O', // Classic/Custom Cars
    '94C', // Trucks (all)
    '94B', // Pickup Trucks
    '64A', // Service & Utility Vehicles
    '643', // Box Trucks
    '645', // Dump Trucks
    '646', // Flatbed Trucks
    '64G', // Truck Tractors
    '385', // Specialized Vehicles
    '94G', // All Terrain Vehicles
]);

const TARGET_STATES = new Set([
    'AZ','CA','NV','CO','NM','UT','TX','FL','GA','SC','TN','NC','VA','WA','OR','HI'
]);

const HIGH_RUST_STATES = new Set([
    'OH','MI','PA','NY','WI','MN','IL','IN','MO','IA',
    'ND','SD','NE','KS','WV','ME','NH','VT','MA','RI',
    'CT','NJ','MD','DE'
]);

const VEHICLE_MAKES = ['ford','chevrolet','chevy','dodge','ram','toyota','honda','nissan','jeep','gmc','chrysler',
    'hyundai','kia','subaru','mazda','volkswagen','vw','bmw','mercedes','audi','lexus','acura','infiniti',
    'cadillac','lincoln','buick','pontiac','mitsubishi','volvo','tesla','rivian','lucid','genesis',
    'land rover','landrover','jaguar','porsche','fiat','alfa romeo','maserati','bentley','rolls royce'];

await Actor.init();

const input = await Actor.getInput() ?? {};
const {
    maxPages = 20,
    minBid = 3000,
    maxBid = 35000,
    maxMileage = 50000,
    minYear = 2022,
    targetStates = [...TARGET_STATES],
    displayRows = 120,
} = input;

const targetStateSet = new Set(targetStates.map(s => s.toUpperCase()));
const allListings = new Map(); // dedup by listing_id
let totalFound = 0;
let totalAfterFilters = 0;

const log = {
    info: (...args) => console.log('[INFO]', ...args),
    debug: (...args) => {}, // suppress debug in prod
    error: (...args) => console.error('[ERROR]', ...args),
    warn: (...args) => console.warn('[WARN]', ...args),
};

// ─── Helpers ────────────────────────────────────────────────────────────────

function isVehicleCategory(assetCategory) {
    return VEHICLE_CATEGORY_IDS.has(assetCategory);
}

function parseVehicleTitle(title, makebrand, model, modelYear) {
    const titleStr = String(title || '');
    const makeStr = String(makebrand || '');
    const modelStr = String(model || '');
    const yearStr = String(modelYear || '');

    // Year
    const yearMatch = yearStr.match(/\b(20\d{2}|19[89]\d)\b/) ||
                      titleStr.match(/\b(20\d{2}|19[89]\d)\b/);
    const year = yearMatch ? parseInt(yearMatch[1]) : null;

    // Make — prefer the API field, fall back to title parse
    let make = null;
    if (makeStr && makeStr.length > 1 && makeStr !== ' ') {
        make = makeStr.trim();
        // Normalize
        const makeLower = make.toLowerCase();
        if (makeLower === 'chevy') make = 'Chevrolet';
        if (makeLower === 'vw') make = 'Volkswagen';
        if (makeLower === 'land rover' || makeLower === 'landrover') make = 'Land Rover';
    } else {
        const lower = titleStr.toLowerCase();
        for (const m of VEHICLE_MAKES) {
            if (lower.includes(m)) {
                make = m.charAt(0).toUpperCase() + m.slice(1);
                if (make === 'Chevy') make = 'Chevrolet';
                if (make === 'Vw') make = 'Volkswagen';
                break;
            }
        }
    }

    // Model — prefer API field
    const resolvedModel = modelStr && modelStr.length > 1 && modelStr !== ' '
        ? modelStr.trim()
        : null;

    return { year, make, model: resolvedModel };
}

function parseState(stateCode, country) {
    if (country && country !== 'USA') return null; // only US vehicles
    if (!stateCode) return null;
    // AllSurplus uses 2-letter state codes directly
    const s = stateCode.replace(/^US-/, '').toUpperCase();
    return s.length === 2 ? s : null;
}

function parseBid(value) {
    if (!value && value !== 0) return 0;
    const match = String(value).replace(/,/g, '').match(/[\d]+\.?\d*/);
    return match ? parseFloat(match[0]) : 0;
}

function parseDate(dateStr) {
    if (!dateStr) return null;
    try {
        const d = new Date(dateStr);
        if (!isNaN(d.getTime())) return d.toISOString();
    } catch {}
    return null;
}

function buildPhotoUrl(photoFile) {
    if (!photoFile) return null;
    if (photoFile.startsWith('http')) return photoFile;
    return `${PHOTO_BASE}/${photoFile}`;
}

function applyFilters(listing) {
    const state = listing.state;

    if (state && HIGH_RUST_STATES.has(state)) {
        log.debug(`[SKIP] High-rust state: ${state} — ${listing.title}`);
        return false;
    }
    if (state && !targetStateSet.has(state)) {
        log.debug(`[SKIP] Out-of-target state: ${state}`);
        return false;
    }
    if (!state) {
        log.debug(`[SKIP] No US state — ${listing.title}`);
        return false;
    }
    if (listing.current_bid > 0 && listing.current_bid < minBid) {
        log.debug(`[SKIP] Bid too low: $${listing.current_bid}`);
        return false;
    }
    if (listing.current_bid > 0 && listing.current_bid > maxBid) {
        log.debug(`[SKIP] Bid too high: $${listing.current_bid}`);
        return false;
    }
    if (listing.year && listing.year < minYear) {
        log.debug(`[SKIP] Too old: ${listing.year}`);
        return false;
    }
    if (listing.mileage && listing.mileage > maxMileage) {
        log.debug(`[SKIP] Too many miles: ${listing.mileage}`);
        return false;
    }
    return true;
}

// ─── Maestro API ─────────────────────────────────────────────────────────────

async function maestroSearch({ categoryFilter, page = 1, rows = displayRows }) {
    const correlationId = uuidv4();
    const sessionId = uuidv4();

    const body = {
        categoryIds: '',
        businessId: 'AD',
        searchText: '*',
        isQAL: false,
        locationId: null,
        model: '',
        makebrand: '',
        auctionTypeId: null,
        page,
        displayRows: rows,
        sortField: 'enddate',
        sortOrder: 'asc',
        requestType: 'search',
        responseStyle: 'productsOnly',
        facets: ['categoryName', 'region'],
        facetsFilter: [categoryFilter],
        timeType: '',
        sellerTypeId: null,
        accountIds: [],
    };

    const res = await fetch(MAESTRO_API, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'x-api-key': API_KEY,
            'ocp-apim-subscription-key': SUBSCRIPTION_KEY,
            'x-api-correlation-id': correlationId,
            'x-ecom-session-id': sessionId,
            'x-user-id': '-1',
            'x-user-timezone': 'America/Los_Angeles',
            'Referer': `${BASE}/`,
            'x-referer': `${BASE}/en/search`,
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        },
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(30000),
    });

    if (!res.ok) {
        const text = await res.text().catch(() => '');
        throw new Error(`Maestro API HTTP ${res.status}: ${text.slice(0, 200)}`);
    }

    const data = await res.json();
    return {
        items: data.assetSearchResults || [],
        total: data.totalAssets || 0,
    };
}

function processItem(item) {
    const listingId = `allsurplus-${item.accountId}-${item.assetId}`;
    if (allListings.has(listingId)) return null; // deduplicate

    // Only process US vehicles in our target categories
    if (item.country !== 'USA') return null;

    const assetCategory = item.assetCategory || '';
    if (!isVehicleCategory(assetCategory)) {
        log.debug(`[SKIP-CAT] ${assetCategory}: ${item.assetShortDescription}`);
        return null;
    }

    totalFound++;

    const title = String(item.assetShortDescription || '');
    const state = parseState(item.locationState, item.country);
    const { year, make, model } = parseVehicleTitle(title, item.makebrand, item.model, item.modelYear);
    const bid = parseBid(item.currentBid);

    // Mileage from odometer field if present (API sometimes includes it)
    const mileageRaw = item.odometer || item.mileage || null;
    const mileage = mileageRaw ? parseInt(String(mileageRaw).replace(/,/g, '')) : null;

    const listing = {
        listing_id: listingId,
        title,
        current_bid: bid,
        buy_now_price: parseBid(item.buyNowPrice || item.assetBuyNow || null) || null,
        auction_end_date: parseDate(item.assetAuctionEndDate || item.assetAuctionEndDateUtc || null),
        state,
        listing_url: `${BASE}/asset/${item.assetId}/${item.accountId}`,
        image_url: buildPhotoUrl(item.photo),
        lot_number: String(item.lotNumber || item.assetId || ''),
        mileage: mileage && mileage > 0 ? mileage : null,
        vin: item.vin || null,
        year,
        make,
        model,
        category: item.categoryDescription || assetCategory,
        source: SOURCE,
        scraped_at: new Date().toISOString(),
    };

    return listing;
}

// ─── Main Scrape Loop ─────────────────────────────────────────────────────────

log.info('[AllSurplus] Starting maestro API scrape');
log.info(`[AllSurplus] Target: ${targetStateSet.size} states, bid $${minBid}-$${maxBid}, year >=${minYear}`);

// We use the Passenger Vehicles (94Q) and Trucks (94C) filters separately
// to maximize coverage. Pickup trucks (94B) are under 94C so no need for separate query.
const CATEGORY_QUERIES = [
    { label: 'Passenger Vehicles', filter: '{!tag=product_category_external_id}product_category_external_id:"94Q"' },
    { label: 'Trucks', filter: '{!tag=product_category_external_id}product_category_external_id:"94C"' },
];

for (const { label, filter } of CATEGORY_QUERIES) {
    log.info(`[AllSurplus] Fetching category: ${label}`);

    try {
        // First page to get total
        const { items: firstPage, total } = await maestroSearch({ categoryFilter: filter, page: 1 });
        const totalPages = Math.min(Math.ceil(total / displayRows), maxPages);
        log.info(`[AllSurplus] ${label}: ${total} total items, ${totalPages} pages`);

        // Process first page
        for (const item of firstPage) {
            const listing = processItem(item);
            if (!listing) continue;
            if (applyFilters(listing)) {
                totalAfterFilters++;
                log.info(`[PASS] ${listing.title} | $${listing.current_bid} | ${listing.state}`);
                allListings.set(listing.listing_id, listing);
                await Actor.pushData(listing);
            }
        }

        // Fetch remaining pages
        for (let pageNum = 2; pageNum <= totalPages; pageNum++) {
            log.info(`[AllSurplus] ${label}: page ${pageNum}/${totalPages}`);

            try {
                const { items } = await maestroSearch({ categoryFilter: filter, page: pageNum });
                if (!items || items.length === 0) break;

                for (const item of items) {
                    const listing = processItem(item);
                    if (!listing) continue;
                    if (applyFilters(listing)) {
                        totalAfterFilters++;
                        log.info(`[PASS] ${listing.title} | $${listing.current_bid} | ${listing.state}`);
                        allListings.set(listing.listing_id, listing);
                        await Actor.pushData(listing);
                    }
                }

                // Polite delay
                await new Promise(r => setTimeout(r, 500));
            } catch (err) {
                log.error(`[AllSurplus] Page ${pageNum} error: ${err.message}`);
                break;
            }
        }
    } catch (err) {
        log.error(`[AllSurplus] Category "${label}" failed: ${err.message}`);
    }

    // Delay between category queries
    await new Promise(r => setTimeout(r, 1000));
}

log.info(`[ALLSURPLUS COMPLETE] Found: ${totalFound} | Passed filters: ${totalAfterFilters} | Unique: ${allListings.size}`);

await Actor.exit();
