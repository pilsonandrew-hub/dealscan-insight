/**
 * ds-equipmentfacts — EquipmentFacts.com Auction Scraper (Sandhills Cloud Platform)
 *
 * Strategy:
 * EquipmentFacts is a Sandhills Cloud platform serving live auction listings for trucks,
 * RVs, and heavy equipment. Key auctioneers: various truck/commercial vehicle auctions.
 *
 * Approach:
 * 1. Load the equipmentsearch page in Playwright, capturing XHR/fetch traffic
 * 2. Intercept the Sandhills API calls (api.sandhills.com or similar)
 * 3. Filter for Trucks/Autos categories
 * 4. Paginate via captured API key/endpoint
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
const WEBHOOK_SECRET = process.env.WEBHOOK_SECRET || '';
const CURRENT_YEAR = new Date().getFullYear();
const DEFAULT_MAX_MILEAGE = 50000;

if (!WEBHOOK_SECRET) {
    console.warn('[EQUIPMENTFACTS] WARNING: WEBHOOK_SECRET env var not set');
}

// Vehicle/truck relevant categories on EquipmentFacts
const VEHICLE_CATEGORIES = [
    'trucks-trailers',
    'automobiles',
    'rvs-motorhomes',
    'vans',
];

// EquipmentFacts (Sandhills Cloud) search URLs for vehicle/truck categories
// URL pattern: /listings/upcoming-auctions/[slug]/[catid]  OR  /listings/search?q=...
// Kept to 3 URLs so Playwright runs complete within the 300s timeout
const SEARCH_URLS = [
    `${BASE_URL}/listings/upcoming-auctions/box-trucks/16004`,
    `${BASE_URL}/listings/search?q=pickup+truck&ListingType=Upcoming+Auctions`,
    `${BASE_URL}/listings/search?q=truck&ListingType=Upcoming+Auctions`,
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
const CONDITION_REJECT_PATTERNS = [
    /\bsalvage\b/i,
    /\bflood\b/i,
    /\bframe[\s-]+damage\b/i,
    /\bcrash(?:ed)?\b/i,
    /\bcollision[\s-]+damage\b/i,
    /\bfire[\s-]+damage\b/i,
    /\bhail[\s-]+damage\b/i,
    /\bwont\s+start\b/i,
    /\bwon'?t\s+start\b/i,
    /\bdoes\s+not\s+start\b/i,
    /\bno[\s-]start\b/i,
    /\binop(?:erable)?\b/i,
    /\bparts[\s-]+only\b/i,
    /\bfor\s+parts\b/i,
    /\bproject\s+(?:car|vehicle|truck)\b/i,
    /\brebuilt\s+title\b/i,
    /\bstructural[\s-]+damage\b/i,
    /\bblown\s+engine\b/i,
    /\bbad\s+engine\b/i,
    /\bno\s+title\b/i,
];

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

const MAKE_NORMALIZATION = new Map([
    ['CHEVROLET', 'Chevrolet'],
    ['CHEVY', 'Chevrolet'],
    ['FORD', 'Ford'],
    ['GMC', 'GMC'],
    ['DODGE', 'Dodge'],
    ['RAM', 'Ram'],
    ['TOYOTA', 'Toyota'],
    ['HONDA', 'Honda'],
    ['NISSAN', 'Nissan'],
    ['JEEP', 'Jeep'],
    ['INTERNATIONAL', 'International'],
]);

const TITLE_MODEL_STOP_WORDS = new Set([
    'CARGO', 'STRAIGHT', 'BOX', 'TRUCK', 'TRUCKS', 'CUTAWAY', 'CUBE',
    'PICKUP', 'UTILITY', 'SPORT', 'SUV', 'VAN', 'VANS', 'SEDAN', 'COUPE',
]);

function normalizeText(value) {
    return String(value ?? '').replace(/\s+/g, ' ').trim();
}

function titleCaseToken(value) {
    const token = String(value ?? '').trim();
    if (!token) return '';
    if (/^\d/.test(token)) return token;
    return token.charAt(0).toUpperCase() + token.slice(1).toLowerCase();
}

function parseVehicleIdentityFromTitle(title) {
    const normalized = normalizeText(title).toUpperCase();
    const match = normalized.match(/\b((?:19|20)\d{2})\s+([A-Z]+)\s+(.+?)$/);
    if (!match) return {};

    const year = parseInt(match[1], 10);
    const make = MAKE_NORMALIZATION.get(match[2]);
    if (!Number.isFinite(year) || !make) return {};

    const modelTokens = match[3]
        .replace(/[()/]/g, ' ')
        .replace(/[-/]/g, ' ')
        .split(/\s+/)
        .filter(Boolean);
    const model = [];
    for (const token of modelTokens) {
        if (TITLE_MODEL_STOP_WORDS.has(token)) break;
        model.push(titleCaseToken(token));
        if (model.length >= 3) break;
    }

    return {
        year,
        make,
        model: model.join(' ').trim(),
    };
}

function withTitleVehicleIdentity(item) {
    const parsed = parseVehicleIdentityFromTitle(item.title || item.description || item.equipmentDescription || '');
    return {
        ...item,
        year: item.year ?? item.modelYear ?? parsed.year ?? null,
        make: item.make || item.manufacturer || item.makebrand || parsed.make || '',
        model: item.model || item.modelName || parsed.model || '',
    };
}

function normalizeState(stateRaw) {
    if (!stateRaw) return '';
    const s = stateRaw.trim().toUpperCase();
    if (s.length === 2) return s;
    return STATE_ABBR.get(s) || s;
}

function isVehicleRelevant(item) {
    const title = (item.title || item.description || '').toLowerCase();
    const category = (item.category || item.categoryName || '').toLowerCase();
    if (CONDITION_REJECT_PATTERNS.some((pattern) => pattern.test(title))) return false;
    return (
        VEHICLE_KEYWORDS.some(k => title.includes(k) || category.includes(k)) ||
        VEHICLE_CATEGORIES.some(c => category.includes(c.replace('-', ' ')))
    );
}

function normalizeLot(raw, capturedApiUrl) {
    raw = withTitleVehicleIdentity(raw);
    const sellerName = raw.sellerName || raw.companyName || raw.auctioneer || raw.seller || '';

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
        source_type: 'equipmentfacts',
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
    // Sandhills Cloud / EquipmentFacts AJAX API response shapes
    // /ajax/listings/* returns shapes observed: {listings:[...]}, {results:[...]}, plain arrays
    const candidates = [
        json.equipmentList,
        json.listings,
        json.lots,
        json.items,
        json.results,
        json.SearchResults,
        json.searchResults,
        json.data?.listings,
        json.data?.lots,
        json.data?.items,
        json.data?.equipmentList,
        json.data?.results,
        json.payload?.listings,
        json.payload?.lots,
        json.payload?.results,
        json.ResultList,
        json.resultList,
        json.ListingList,
        json.listingList,
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
    minYear = CURRENT_YEAR - 4,
    maxMileage = DEFAULT_MAX_MILEAGE,
    webhookUrl = 'https://dealscan-insight-production.up.railway.app/api/ingest/apify',
    includeRustStates = false,
    searchQuery = '',
} = input;
const searchQueryLower = searchQuery ? searchQuery.toLowerCase() : '';
const MIN_YEAR = Number(minYear) || CURRENT_YEAR - 4;
const MAX_MILEAGE = Number(maxMileage) || DEFAULT_MAX_MILEAGE;

let totalFound = 0;
let totalPassed = 0;
let totalFailed = 0;
const proofCounters = {
    rows_excluded_search_filter: 0,
    rows_excluded_non_vehicle: 0,
    rows_excluded_missing_required_data: 0,
    rows_excluded_age_mileage_prefilter: 0,
    rows_excluded_policy_prefilter: 0,
    rows_excluded_rust_state: 0,
    rows_excluded_bid_range: 0,
    rows_excluded_zero_pricing_signal: 0,
};
const proofSamples = {
    search_filter_rejected_samples: [],
    non_vehicle_rejected_samples: [],
    missing_required_data_rejected_samples: [],
    prefilter_age_mileage_rejected_samples: [],
    prefilter_policy_rejected_samples: [],
    rust_state_rejected_samples: [],
    bid_range_rejected_samples: [],
    zero_pricing_rejected_samples: [],
};

function sampleForProof(item, reason, extra = {}) {
    item = withTitleVehicleIdentity(item);
    return {
        title: String(item.title || item.description || item.equipmentDescription || '').slice(0, 120),
        year: item.year ?? item.modelYear ?? null,
        make: item.make || item.manufacturer || item.makebrand || null,
        model: item.model || item.modelName || null,
        state: normalizeState(item.state || item.locationState || item.stateAbbr || ''),
        mileage: item.mileage ?? item.miles ?? item.meterCount ?? null,
        current_bid: item.currentBid ?? item.bidAmount ?? item.currentPrice ?? null,
        listing_url: item.url || item.listingUrl || item.lotUrl || null,
        reason,
        ...extra,
    };
}

function rejectForProof(counterKey, sampleKey, item, reason, extra = {}) {
    totalFailed++;
    proofCounters[counterKey] += 1;
    const samples = proofSamples[sampleKey];
    if (samples && samples.length < 5) {
        samples.push(sampleForProof(item, reason, extra));
    }
}

function passes(item) {
    item = withTitleVehicleIdentity(item);
    const conditionText = [
        item.title,
        item.description,
        item.equipmentDescription,
        item.longDescription,
    ].filter(Boolean).join(' ').toLowerCase();
    if (CONDITION_REJECT_PATTERNS.some((pattern) => pattern.test(conditionText))) {
        rejectForProof(
            'rows_excluded_policy_prefilter',
            'prefilter_policy_rejected_samples',
            item,
            'condition_reject_pattern',
        );
        return false;
    }
    const state = normalizeState(item.state || item.locationState || '');
    const yearValue = item.year ?? item.modelYear ?? null;
    const year = yearValue == null || yearValue === '' ? null : parseInt(yearValue, 10);
    const hasYear = Number.isFinite(year);
    if (!includeRustStates && HIGH_RUST_STATES.has(state) && hasYear) {
        if (year < 2023) {
            rejectForProof(
                'rows_excluded_rust_state',
                'rust_state_rejected_samples',
                item,
                'rust_state_age_reject',
            );
            return false;
        }
        console.log(`[BYPASS] Rust state ${state} allowed — vehicle is ${year} (≤3yr old)`);
    }
    const mileageValue = item.mileage ?? item.miles ?? item.meterCount ?? null;
    const mileage = mileageValue == null || mileageValue === ''
        ? null
        : parseInt(String(mileageValue).replace(/,/g, ''), 10);
    if (mileage !== null && mileage > MAX_MILEAGE) {
        rejectForProof(
            'rows_excluded_age_mileage_prefilter',
            'prefilter_age_mileage_rejected_samples',
            item,
            'mileage_over_50k',
            { max_mileage: MAX_MILEAGE },
        );
        return false;
    }
    if (!year || year < MIN_YEAR || year > CURRENT_YEAR + 1) {
        rejectForProof(
            'rows_excluded_age_mileage_prefilter',
            'prefilter_age_mileage_rejected_samples',
            item,
            !year ? 'missing_model_year' : year > CURRENT_YEAR + 1 ? 'future_model_year' : 'model_year_reject',
            { min_year: MIN_YEAR },
        );
        return false;
    }
    const bid = parseFloat(item.currentBid || item.bidAmount || item.currentPrice || 0);
    if (bid <= 0) {
        rejectForProof(
            'rows_excluded_zero_pricing_signal',
            'zero_pricing_rejected_samples',
            item,
            'missing_current_bid',
        );
        return false;
    }
    if (bid < minBid || bid > maxBid) {
        rejectForProof(
            'rows_excluded_bid_range',
            'bid_range_rejected_samples',
            item,
            'bid_out_of_range',
            { min_bid: minBid, max_bid: maxBid },
        );
        return false;
    }
    return true;
}

const crawler = new PlaywrightCrawler({
    maxRequestsPerCrawl: 6,
    requestHandlerTimeoutSecs: 90,
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
                    log.info(`[API KEY CAPTURED] ${apiKey.slice(0, 8)}*** from ${url}`);
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

            // Track all JSON API URLs — broad to avoid missing Sandhills Cloud endpoints
            // Key pattern: /ajax/listings/* is the equipmentfacts.com search/facet API
            const isApiLike = (
                url.includes('/ajax/') ||
                url.includes('api.') ||
                url.includes('/api/') ||
                url.includes('/Api/') ||
                url.includes('/Search') ||
                url.includes('/search') ||
                url.includes('/listings') ||
                url.includes('/Listings') ||
                url.includes('/equipment') ||
                url.includes('/Equipment') ||
                url.includes('/Result') ||
                url.includes('/result') ||
                url.includes('sandhills') ||
                url.includes('equipmentfacts') ||
                url.includes('cloudfront') ||
                url.includes('amazonaws')
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
        await page.waitForTimeout(3000);

        // ── Try AJAX HTML listing endpoint (same cookie jar, bypasses bot detection) ──
        // Pattern observed: /ajax/listings/getfacet/?... for facets (JSON)
        // Listings HTML: /ajax/listings/?<same-params> returns HTML fragment
        if (capturedApi.interceptedLots.length === 0) {
            const ajaxResult = await page.evaluate(async (pageUrl) => {
                try {
                    const u = new URL(pageUrl);
                    const params = new URLSearchParams(u.search);
                    // Derive path from page path: /listings/search → /ajax/listings/
                    // or /listings/upcoming-auctions/box-trucks/16004 → /ajax/listings/?Category=16004
                    let ajaxPath;
                    if (u.pathname.includes('/listings/search') || u.pathname.includes('/listings/upcoming-auctions/') || u.pathname.includes('/listings/')) {
                        ajaxPath = '/ajax/listings/';
                        // For category pages, extract category ID from path
                        const catMatch = u.pathname.match(/\/(\d+)\/?$/);
                        if (catMatch) params.set('Category', catMatch[1]);
                        params.set('lang', 'en-US');
                        params.set('sort', '1');
                    } else {
                        return { html: null, error: 'unknown URL pattern' };
                    }
                    const ajaxUrl = ajaxPath + '?' + params.toString();
                    const resp = await fetch(ajaxUrl, {
                        headers: {
                            'Accept': 'text/html, */*; q=0.01',
                            'X-Requested-With': 'XMLHttpRequest',
                        },
                        credentials: 'include',
                    });
                    const html = await resp.text();
                    return { html: html.slice(0, 5000), status: resp.status, url: resp.url };
                } catch (e) {
                    return { html: null, error: e.message };
                }
            }, request.url);

            log.info(`[AJAX] ${request.url} → status=${ajaxResult.status} url=${ajaxResult.url} error=${ajaxResult.error || 'none'}`);
            if (ajaxResult.html) {
                log.info(`[AJAX HTML preview] ${ajaxResult.html.slice(0, 800)}`);
            }

            // Parse the AJAX HTML response for listing items
            if (ajaxResult.html && ajaxResult.status === 200) {
                const htmlLots = await page.evaluate((html) => {
                    const parser = new DOMParser();
                    const doc = parser.parseFromString(html, 'text/html');
                    const results = [];

                    // Try to find listing items in the HTML fragment
                    const selectors = [
                        'a[href*="/listing/"]',
                        '.listing-card',
                        '.result-item',
                        '.search-result-item',
                        '[class*="listing"]',
                        '[class*="result"]',
                        'article',
                        'li[data-id]',
                        'div[data-id]',
                    ];

                    let cards = [];
                    for (const sel of selectors) {
                        cards = Array.from(doc.querySelectorAll(sel));
                        if (cards.length > 0 && cards[0].textContent.trim().length > 10) break;
                    }

                    for (const card of cards.slice(0, 100)) {
                        const titleEl = card.querySelector('h2, h3, h4, .title, [class*="title"]') || card;
                        const title = titleEl.textContent.trim().slice(0, 200);
                        const linkEl = card.tagName === 'A' ? card : card.querySelector('a[href]');
                        const url = linkEl ? (linkEl.href || linkEl.getAttribute('href') || '') : '';
                        const imgEl = card.querySelector('img');
                        const imageUrl = imgEl ? (imgEl.src || imgEl.getAttribute('data-src') || '') : '';
                        const bidEl = card.querySelector('[class*="bid"], [class*="price"], [class*="amount"]');
                        const bidText = bidEl ? bidEl.textContent.replace(/[^0-9.]/g, '') : '0';
                        const locEl = card.querySelector('[class*="location"], [class*="city"], [class*="state"]');
                        const location = locEl ? locEl.textContent.trim() : '';

                        if (title.length > 3) {
                            results.push({ title, url, imageUrl, currentBid: parseFloat(bidText) || 0, location, id: url || title });
                        }
                    }
                    return { count: cards.length, lots: results, selectorUsed: selectors.find((s) => doc.querySelectorAll(s).length > 0) || 'none' };
                }, ajaxResult.html);

                log.info(`[AJAX PARSE] selector="${htmlLots.selectorUsed}" cards=${htmlLots.count} lots=${htmlLots.lots.length}`);
                if (htmlLots.lots.length > 0) {
                    capturedApi.interceptedLots.push(...htmlLots.lots);
                }
            }
        }

        // ── Fallback: DOM scrape from the live page ──
        if (capturedApi.interceptedLots.length === 0) {
            log.info('AJAX approach yielded nothing, attempting live DOM scrape...');

            // Log all unique classes in the page to identify listing card selectors
            const pageClasses = await page.evaluate(() => {
                const allClasses = new Set();
                document.querySelectorAll('[class]').forEach(el => {
                    el.className.toString().split(/\s+/).forEach(c => {
                        if (c && !c.startsWith('Mui') && !c.startsWith('css-') && c.length > 3 && c.length < 40) allClasses.add(c);
                    });
                });
                return [...allClasses].slice(0, 50).join(' | ');
            });
            log.info(`[PAGE CLASSES] ${pageClasses}`);

            const domLots = await page.evaluate(() => {
                const results = [];
                // Look for any anchor links to listings (the most reliable marker)
                const listingLinks = Array.from(document.querySelectorAll('a[href]'))
                    .filter(a => a.href && a.href.includes('/listing/'));

                for (const link of listingLinks.slice(0, 100)) {
                    const card = link.closest('article, [class*="card"], [class*="item"], li, div') || link;
                    const titleEl = card.querySelector('h2, h3, h4, [class*="title"]') || link;
                    const title = titleEl.textContent.trim().slice(0, 200);
                    const bidEl = card.querySelector('[class*="bid"], [class*="price"]');
                    const bidText = bidEl ? bidEl.textContent.replace(/[^0-9.]/g, '') : '0';
                    const imgEl = card.querySelector('img');
                    if (title.length > 3) {
                        results.push({ title, url: link.href, currentBid: parseFloat(bidText) || 0,
                            imageUrl: imgEl ? imgEl.src : '', id: link.href });
                    }
                }
                return results;
            });

            if (domLots.length > 0) {
                log.info(`DOM scrape yielded ${domLots.length} items`);
                capturedApi.interceptedLots.push(...domLots);
            } else {
                log.warning('DOM scrape found no items');
                const bodyHtml = await page.evaluate(() =>
                    document.body?.innerHTML?.slice(0, 1500) || '');
                log.info(`[PAGE HTML] ${bodyHtml}`);
            }
        }

        // ── Save intercepted lots ──
        const seenIds = new Set();
        for (const lot of capturedApi.interceptedLots) {
            const id = lot.id || lot.lotId || lot.equipmentId || lot.listingId || lot.url || lot.title;
            if (seenIds.has(id)) continue;
            seenIds.add(id);
            totalFound++;
            if (!isVehicleRelevant(lot)) {
                rejectForProof(
                    'rows_excluded_non_vehicle',
                    'non_vehicle_rejected_samples',
                    lot,
                    'non_vehicle_or_policy_title_reject',
                );
                continue;
            }
            if (!passes(lot)) continue;
            const normalized = normalizeLot(lot);
            if (searchQueryLower && !normalized.title.toLowerCase().includes(searchQueryLower)) {
                rejectForProof(
                    'rows_excluded_search_filter',
                    'search_filter_rejected_samples',
                    normalized,
                    'search_query_reject',
                    { search_query: searchQuery },
                );
                continue;
            }
            totalPassed++;
            await Actor.pushData(normalized);
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
                if (!isVehicleRelevant(lot)) {
                    rejectForProof(
                        'rows_excluded_non_vehicle',
                        'non_vehicle_rejected_samples',
                        lot,
                        'non_vehicle_or_policy_title_reject',
                    );
                    continue;
                }
                if (!passes(lot)) continue;
                const normalized = normalizeLot(lot);
                if (searchQueryLower && !normalized.title.toLowerCase().includes(searchQueryLower)) {
                    rejectForProof(
                        'rows_excluded_search_filter',
                        'search_filter_rejected_samples',
                        normalized,
                        'search_query_reject',
                        { search_query: searchQuery },
                    );
                    continue;
                }
                totalPassed++;
                await Actor.pushData(normalized);
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

console.log(`[EQUIPMENTFACTS] Total found: ${totalFound} | Passed filters: ${totalPassed} | Failed filters: ${totalFailed}`);
console.log(`[EQUIPMENTFACTS] Auth initialized`);
console.log(`[EQUIPMENTFACTS] Detected API URLs:`);
for (const u of [...new Set(capturedApi.detectedUrls)].slice(0, 20)) {
    console.log(`  ${u}`);
}

const env = Actor.getEnv();
const accountedRows = Object.values(proofCounters).reduce((sum, value) => sum + value, 0);
const proof = {
    record_type: 'source_quality_proof',
    source: SOURCE,
    source_site: SOURCE,
    actor_run_id: env.actorRunId || null,
    run_id: env.actorRunId || null,
    actor_id: env.actorId || null,
    found_rows_total: totalFound,
    prefilter_passed_rows_total: totalPassed,
    pushed_rows_total: totalPassed,
    failed_rows_total: totalFailed,
    max_pages: maxPages,
    min_year: MIN_YEAR,
    max_mileage: MAX_MILEAGE,
    rows_excluded_unaccounted_after_prefilter: Math.max(0, totalFound - totalPassed - accountedRows),
    ...proofCounters,
    ...proofSamples,
    detected_api_urls: [...new Set(capturedApi.detectedUrls)].slice(0, 20),
    scraped_at: new Date().toISOString(),
};
await Actor.pushData(proof);

if (WEBHOOK_SECRET) {
    try {
        const res = await fetch(webhookUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'x-apify-webhook-secret': WEBHOOK_SECRET,
            },
            body: JSON.stringify({
                source: SOURCE,
                runId: env.actorRunId,
                actorId: env.actorId,
                datasetId: env.defaultDatasetId,
                itemCount: totalPassed + 1,
            }),
        });
        console.log(`[EQUIPMENTFACTS] Webhook → ${res.status}`);
    } catch (err) {
        console.warn(`[EQUIPMENTFACTS] Webhook failed: ${err.message}`);
    }
} else {
    console.warn('[EQUIPMENTFACTS] WEBHOOK_SECRET missing; proof row was pushed to dataset but not delivered to webhook');
}

await Actor.exit();
