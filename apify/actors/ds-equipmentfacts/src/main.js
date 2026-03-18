/**
 * ds-equipmentfacts — EquipmentFacts.com Auction Scraper (Sandhills Cloud Platform)
 *
 * Strategy:
 * EquipmentFacts is a Sandhills Cloud platform serving live auction listings for trucks,
 * RVs, and heavy equipment. Key auctioneers: ADESA Mercer (auto auction, NJ), Indiana
 * Auto Auction, and various truck/commercial vehicle auctions.
 *
 * Approach:
 * 1. Load the equipmentsearch page in Playwright, capturing XHR/fetch traffic
 * 2. Intercept the Sandhills API calls (api.sandhills.com or similar)
 * 3. Filter for Trucks/Autos categories
 * 4. Paginate via captured API key/endpoint
 * 5. Flag ADESA Mercer lots as source_type=equipmentfacts_adesa
 *
 * Sandhills Cloud API pattern (observed from AuctionTime sibling platform):
 * - Uses REST endpoints at api.sandhills.com or auction-specific subdomains
 * - Lot detail URLs follow /equipmentfacts/listing/<id> pattern
 * - Vehicle categories: Trucks, Automobiles, RVs, Vans
 */

import { Actor } from 'apify';
import { PlaywrightCrawler } from 'crawlee';

const SOURCE = 'equipmentfacts';
const BASE_URL = 'https://www.equipmentfacts.com';

// ADESA Mercer and Indiana Auto Auction keywords for flagging
const ADESA_KEYWORDS = ['adesa', 'adesa mercer'];
const INDIANA_AUTO_KEYWORDS = ['indiana auto auction'];

// Vehicle/truck relevant categories on EquipmentFacts
const VEHICLE_CATEGORIES = [
    'trucks-trailers',
    'automobiles',
    'rvs-motorhomes',
    'vans',
];

// EquipmentFacts search URLs for vehicle/truck categories
const SEARCH_URLS = [
    `${BASE_URL}/equipmentsearch?category=trucks-trailers&subcat=semi-trucks`,
    `${BASE_URL}/equipmentsearch?category=trucks-trailers&subcat=pickup-trucks`,
    `${BASE_URL}/equipmentsearch?category=trucks-trailers`,
    `${BASE_URL}/equipmentsearch?category=automobiles`,
    `${BASE_URL}/equipmentsearch?category=rvs-motorhomes`,
];

const TARGET_STATES = new Set([
    'AZ', 'CA', 'NV', 'CO', 'NM', 'UT', 'TX', 'FL', 'GA', 'SC', 'TN', 'NC', 'VA', 'WA', 'OR',
    'HI', 'KY', 'AL', 'MS', 'AR', 'OK', 'LA', 'ID', 'MT', 'WY',
]);

const HIGH_RUST_STATES = new Set([
    'OH', 'MI', 'PA', 'NY', 'WI', 'MN', 'IL', 'IN', 'MO', 'IA',
    'ND', 'SD', 'NE', 'KS', 'WV', 'ME', 'NH', 'VT', 'MA', 'RI',
    'CT', 'NJ', 'MD', 'DE',
]);

const STATE_ABBR = new Map([
    ['ALABAMA', 'AL'], ['ALASKA', 'AK'], ['ARIZONA', 'AZ'], ['ARKANSAS', 'AR'],
    ['CALIFORNIA', 'CA'], ['COLORADO', 'CO'], ['CONNECTICUT', 'CT'], ['DELAWARE', 'DE'],
    ['FLORIDA', 'FL'], ['GEORGIA', 'GA'], ['HAWAII', 'HI'], ['IDAHO', 'ID'],
    ['ILLINOIS', 'IL'], ['INDIANA', 'IN'], ['IOWA', 'IA'], ['KANSAS', 'KS'],
    ['KENTUCKY', 'KY'], ['LOUISIANA', 'LA'], ['MAINE', 'ME'], ['MARYLAND', 'MD'],
    ['MASSACHUSETTS', 'MA'], ['MICHIGAN', 'MI'], ['MINNESOTA', 'MN'], ['MISSISSIPPI', 'MS'],
    ['MISSOURI', 'MO'], ['MONTANA', 'MT'], ['NEBRASKA', 'NE'], ['NEVADA', 'NV'],
    ['NEW HAMPSHIRE', 'NH'], ['NEW JERSEY', 'NJ'], ['NEW MEXICO', 'NM'], ['NEW YORK', 'NY'],
    ['NORTH CAROLINA', 'NC'], ['NORTH DAKOTA', 'ND'], ['OHIO', 'OH'], ['OKLAHOMA', 'OK'],
    ['OREGON', 'OR'], ['PENNSYLVANIA', 'PA'], ['RHODE ISLAND', 'RI'], ['SOUTH CAROLINA', 'SC'],
    ['SOUTH DAKOTA', 'SD'], ['TENNESSEE', 'TN'], ['TEXAS', 'TX'], ['UTAH', 'UT'],
    ['VERMONT', 'VT'], ['VIRGINIA', 'VA'], ['WASHINGTON', 'WA'], ['WEST VIRGINIA', 'WV'],
    ['WISCONSIN', 'WI'], ['WYOMING', 'WY'], ['DISTRICT OF COLUMBIA', 'DC'],
]);

const VEHICLE_KEYWORDS = [
    'truck', 'pickup', 'automobile', 'car', 'suv', 'van', 'vehicle', 'sedan', 'coupe',
    'f-150', 'f-250', 'f-350', 'silverado', 'sierra', 'ram', 'tundra', 'tacoma',
    'ranger', 'colorado', 'canyon', 'diesel', '4x4', 'crew cab', 'extended cab',
    'ford', 'chevrolet', 'dodge', 'toyota', 'gmc', 'honda', 'nissan', 'jeep',
];

function normalizeState(stateRaw) {
    if (!stateRaw) return '';
    const s = stateRaw.trim().toUpperCase();
    if (s.length === 2) return s;
    return STATE_ABBR.get(s) || s;
}

function isAdesa(sellerName) {
    if (!sellerName) return false;
    const lower = sellerName.toLowerCase();
    return ADESA_KEYWORDS.some(k => lower.includes(k));
}

function isVehicleRelevant(item) {
    const title = (item.title || item.description || '').toLowerCase();
    const category = (item.category || item.categoryName || '').toLowerCase();
    return (
        VEHICLE_KEYWORDS.some(k => title.includes(k) || category.includes(k)) ||
        VEHICLE_CATEGORIES.some(c => category.includes(c.replace('-', ' ')))
    );
}

function normalizeLot(raw, capturedApiUrl) {
    const sellerName = raw.sellerName || raw.companyName || raw.auctioneer || raw.seller || '';
    const isAdesaLot = isAdesa(sellerName);

    const stateRaw = raw.state || raw.locationState || raw.stateAbbr || '';
    const state = normalizeState(stateRaw);

    const city = raw.city || raw.locationCity || '';
    const location = raw.location || (city && state ? `${city}, ${state}` : city || state || '');

    const lotId = raw.id || raw.lotId || raw.equipmentId || raw.listingId || '';
    const lotUrl = raw.url || raw.listingUrl || raw.lotUrl ||
        (lotId ? `${BASE_URL}/listing/${lotId}` : '');

    return {
        title: raw.title || raw.description || raw.equipmentDescription || '',
        year: raw.year || raw.modelYear || null,
        make: raw.make || raw.manufacturer || raw.makebrand || '',
        model: raw.model || raw.modelName || '',
        vin: raw.vin || raw.serialNumber || null,
        current_bid: parseFloat(raw.currentBid || raw.bidAmount || raw.currentPrice || 0),
        mileage: raw.mileage || raw.miles || raw.meterCount || null,
        state,
        city,
        location,
        auction_end_time: raw.auctionEndDate || raw.endTime || raw.auctionEnd || raw.closeTime || null,
        listing_url: lotUrl,
        source_site: SOURCE,
        source_type: isAdesaLot ? 'equipmentfacts_adesa' : 'equipmentfacts',
        agency_name: sellerName,
        auctioneer_name: sellerName,
        photo_url: raw.imageUrl || raw.photoUrl || raw.thumbnailUrl || '',
        lot_number: raw.lotNumber || raw.lotNum || '',
        scraped_at: new Date().toISOString(),
    };
}

// ── Captured API state ──────────────────────────────────────────────────────
const capturedApi = {
    apiBaseUrl: null,
    apiKey: null,
    authToken: null,
    requestHeaders: null,
    searchPayload: null,
    interceptedLots: [],
    detectedUrls: [],
};

function extractLotsFromJson(json) {
    if (!json || typeof json !== 'object') return [];
    // Sandhills Cloud API response shapes
    const candidates = [
        json.equipmentList,
        json.listings,
        json.lots,
        json.items,
        json.results,
        json.data?.listings,
        json.data?.lots,
        json.data?.items,
        json.data?.equipmentList,
        json.payload?.listings,
        json.payload?.lots,
        json.searchResults,
    ].filter(Array.isArray);
    if (candidates.length) return candidates[0];
    if (Array.isArray(json)) return json;
    return [];
}

await Actor.init();
const input = await Actor.getInput() ?? {};
const {
    maxPages = 15,
    minBid = 500,
    maxBid = 50000,
    includeRustStates = false,
} = input;

let totalFound = 0;
let totalPassed = 0;

function passes(item) {
    const state = normalizeState(item.state || item.locationState || '');
    if (!includeRustStates && HIGH_RUST_STATES.has(state)) return false;
    const bid = parseFloat(item.currentBid || item.bidAmount || item.currentPrice || 0);
    if (bid > 0 && (bid < minBid || bid > maxBid)) return false;
    const year = parseInt(item.year || item.modelYear || 0);
    if (year && (new Date().getFullYear() - year) > 15) return false;
    return true;
}

const crawler = new PlaywrightCrawler({
    maxRequestsPerCrawl: 5,
    requestHandlerTimeoutSecs: 240,
    headless: true,
    async requestHandler({ page, request, log }) {
        log.info(`Loading: ${request.url}`);

        // ── Capture ALL outbound XHR/fetch requests for API discovery ──
        page.on('request', (req) => {
            const url = req.url();
            const method = req.method();
            const headers = req.headers();

            // Sandhills Cloud API patterns
            const isSandhillsApi = (
                url.includes('api.sandhills.com') ||
                url.includes('api.equipmentfacts.com') ||
                url.includes('sandhillscloud.com') ||
                url.includes('equipmentfacts.com/api') ||
                url.includes('/api/v') ||
                url.includes('/Search') ||
                url.includes('/search') ||
                url.includes('/listings') ||
                url.includes('/equipment')
            );

            if (isSandhillsApi) {
                capturedApi.detectedUrls.push(`${method} ${url}`);
            }

            // Capture auth tokens / API keys
            if (!capturedApi.apiKey) {
                const apiKey = headers['x-api-key'] || headers['apikey'] || headers['api-key'];
                if (apiKey) {
                    capturedApi.apiKey = apiKey;
                    capturedApi.requestHeaders = { ...headers };
                    log.info(`[API KEY CAPTURED] ${apiKey} from ${url}`);
                }
            }
            if (!capturedApi.authToken) {
                const auth = headers['authorization'];
                if (auth) {
                    capturedApi.authToken = auth;
                    log.info(`[AUTH TOKEN CAPTURED] from ${url}`);
                }
            }

            // Capture search payload
            if (!capturedApi.searchPayload && (method === 'POST') && isSandhillsApi) {
                const postData = req.postData();
                if (postData) {
                    try {
                        capturedApi.searchPayload = JSON.parse(postData);
                        capturedApi.apiBaseUrl = url;
                        log.info(`[SEARCH PAYLOAD] captured from ${url}`);
                    } catch (_) {
                        capturedApi.searchPayload = postData;
                    }
                }
            }
        });

        // ── Capture JSON responses with listings ──
        page.on('response', async (resp) => {
            const url = resp.url();
            const ct = resp.headers()['content-type'] || '';
            if (!ct.includes('json')) return;

            // Track all JSON API URLs
            const isApiLike = (
                url.includes('api.') ||
                url.includes('/api/') ||
                url.includes('/Search') ||
                url.includes('/search') ||
                url.includes('/listings') ||
                url.includes('/equipment') ||
                url.includes('sandhills') ||
                url.includes('equipmentfacts')
            );
            if (!isApiLike) return;

            try {
                const body = await resp.json().catch(() => null);
                if (!body) return;

                const lots = extractLotsFromJson(body);
                if (lots.length > 0) {
                    log.info(`[JSON RESPONSE] ${url} → ${lots.length} items`);
                    if (!capturedApi.apiBaseUrl) capturedApi.apiBaseUrl = url;
                    for (const lot of lots) {
                        const id = lot.id || lot.lotId || lot.equipmentId || lot.listingId;
                        if (!id || capturedApi.interceptedLots.find(l =>
                            (l.id || l.lotId || l.equipmentId || l.listingId) === id
                        )) continue;
                        capturedApi.interceptedLots.push(lot);
                    }
                }
            } catch (_) {}
        });

        // ── Navigate to search page ──
        await page.goto(request.url, { waitUntil: 'networkidle', timeout: 60000 });
        await page.waitForTimeout(5000);

        // ── Try scrolling to trigger more data loads ──
        for (let i = 0; i < 3; i++) {
            await page.evaluate(() => window.scrollBy(0, 1000));
            await page.waitForTimeout(2000);
        }

        // ── Try DOM scraping as fallback if API not captured ──
        if (capturedApi.interceptedLots.length === 0) {
            log.info('No API lots captured, attempting DOM scrape...');
            const domLots = await page.evaluate(() => {
                const results = [];

                // Common Sandhills Cloud selectors
                const selectors = [
                    '.listing-card',
                    '.equipment-listing',
                    '.lot-card',
                    '.search-result',
                    '[data-lot-id]',
                    '[data-listing-id]',
                    '.inventory-item',
                    '.auction-item',
                    'article.card',
                    '.ef-listing',
                    '.ef-card',
                ];

                let cards = [];
                for (const sel of selectors) {
                    cards = Array.from(document.querySelectorAll(sel));
                    if (cards.length > 0) break;
                }

                for (const card of cards.slice(0, 100)) {
                    const getText = (sel) => {
                        const el = card.querySelector(sel);
                        return el ? el.textContent.trim() : '';
                    };
                    const getAttr = (sel, attr) => {
                        const el = card.querySelector(sel);
                        return el ? el.getAttribute(attr) : '';
                    };

                    const titleEl = card.querySelector('h2, h3, h4, .title, .listing-title, .equipment-title');
                    const title = titleEl ? titleEl.textContent.trim() : '';

                    const bidEl = card.querySelector('.bid, .current-bid, .price, .bid-amount, [class*="bid"]');
                    const bidText = bidEl ? bidEl.textContent.replace(/[^0-9.]/g, '') : '0';

                    const linkEl = card.querySelector('a[href]');
                    const url = linkEl ? linkEl.href : '';

                    const imgEl = card.querySelector('img');
                    const imageUrl = imgEl ? (imgEl.dataset.src || imgEl.src) : '';

                    const locationEl = card.querySelector('.location, .city, .state, [class*="location"]');
                    const locationText = locationEl ? locationEl.textContent.trim() : '';

                    const sellerEl = card.querySelector('.seller, .auctioneer, .company, [class*="seller"], [class*="auctioneer"]');
                    const sellerName = sellerEl ? sellerEl.textContent.trim() : '';

                    const endEl = card.querySelector('.end-time, .auction-end, .close-time, [class*="end"]');
                    const endTime = endEl ? endEl.textContent.trim() : '';

                    const lotId = card.dataset.lotId || card.dataset.listingId || card.dataset.id || '';

                    if (title || url) {
                        results.push({
                            title,
                            currentBid: parseFloat(bidText) || 0,
                            url,
                            imageUrl,
                            location: locationText,
                            sellerName,
                            endTime,
                            id: lotId,
                        });
                    }
                }
                return results;
            });

            if (domLots.length > 0) {
                log.info(`DOM scrape yielded ${domLots.length} items`);
                capturedApi.interceptedLots.push(...domLots);
            } else {
                log.warning('DOM scrape found no items — site may require JS or different selectors');
                // Log page title and first 500 chars of body for debugging
                const bodyText = await page.evaluate(() => document.body?.innerText?.slice(0, 500) || '');
                log.info(`Page body preview: ${bodyText}`);
            }
        }

        // ── Save intercepted lots ──
        const seenIds = new Set();
        for (const lot of capturedApi.interceptedLots) {
            const id = lot.id || lot.lotId || lot.equipmentId || lot.listingId || lot.url || lot.title;
            if (seenIds.has(id)) continue;
            seenIds.add(id);
            totalFound++;
            if (!isVehicleRelevant(lot)) continue;
            if (!passes(lot)) continue;
            totalPassed++;
            await Actor.pushData(normalizeLot(lot));
        }
        capturedApi.interceptedLots = []; // clear for next URL

        // ── If API was captured, paginate ──
        if (capturedApi.apiBaseUrl && (capturedApi.apiKey || capturedApi.authToken)) {
            await paginateApi(log, seenIds);
        }
    },
});

/**
 * Attempt direct API pagination using captured credentials
 */
async function paginateApi(log, seenIds) {
    const headers = {
        'accept': 'application/json',
        'content-type': 'application/json',
    };
    if (capturedApi.apiKey) headers['x-api-key'] = capturedApi.apiKey;
    if (capturedApi.authToken) headers['authorization'] = capturedApi.authToken;
    if (capturedApi.requestHeaders) {
        Object.assign(headers, {
            'user-agent': capturedApi.requestHeaders['user-agent'] || '',
            'origin': capturedApi.requestHeaders['origin'] || BASE_URL,
            'referer': capturedApi.requestHeaders['referer'] || `${BASE_URL}/equipmentsearch`,
        });
    }

    log.info(`Paginating API: ${capturedApi.apiBaseUrl}`);

    for (let page = 1; page <= maxPages; page++) {
        let url = capturedApi.apiBaseUrl;
        let body = null;
        let method = 'GET';

        if (capturedApi.searchPayload && typeof capturedApi.searchPayload === 'object') {
            method = 'POST';
            body = JSON.stringify({
                ...capturedApi.searchPayload,
                page,
                pageSize: capturedApi.searchPayload.pageSize || 50,
            });
        } else {
            // Try common Sandhills pagination query params
            const sep = url.includes('?') ? '&' : '?';
            url = `${url}${sep}page=${page}&pageSize=50`;
        }

        try {
            log.info(`API page ${page}: ${url}`);
            const resp = await fetch(url, { method, headers, body });
            if (!resp.ok) {
                log.warning(`API page ${page}: HTTP ${resp.status}`);
                break;
            }
            const json = await resp.json();
            const lots = extractLotsFromJson(json);
            if (!lots.length) { log.info(`API page ${page}: empty — done`); break; }

            log.info(`API page ${page}: ${lots.length} lots`);
            for (const lot of lots) {
                const id = lot.id || lot.lotId || lot.equipmentId || lot.listingId;
                if (id && seenIds.has(id)) continue;
                if (id) seenIds.add(id);
                totalFound++;
                if (!isVehicleRelevant(lot)) continue;
                if (!passes(lot)) continue;
                totalPassed++;
                await Actor.pushData(normalizeLot(lot));
            }
        } catch (err) {
            log.warning(`API page ${page} failed: ${err.message}`);
            break;
        }
        await new Promise(r => setTimeout(r, 1200));
    }
}

// Run all vehicle category search URLs
await crawler.run(SEARCH_URLS.map(url => ({ url })));

console.log(`[EQUIPMENTFACTS] Total found: ${totalFound} | Passed filters: ${totalPassed}`);
console.log(`[EQUIPMENTFACTS] API base URL: ${capturedApi.apiBaseUrl || 'NOT CAPTURED'}`);
console.log(`[EQUIPMENTFACTS] API key captured: ${!!capturedApi.apiKey}`);
console.log(`[EQUIPMENTFACTS] Auth token captured: ${!!capturedApi.authToken}`);
console.log(`[EQUIPMENTFACTS] Detected API URLs:`);
for (const u of [...new Set(capturedApi.detectedUrls)].slice(0, 20)) {
    console.log(`  ${u}`);
}

await Actor.exit();
