/**
 * ds-hibid — HiBid Auction Platform Scraper
 *
 * STATUS: BLOCKED — Cloudflare Turnstile prevents Playwright from rendering lot pages.
 *
 * What was tried:
 * - PlaywrightCrawler with API traffic capture (XHR/fetch interception)
 * - Cloudflare Turnstile challenges are injected before Angular mounts, blocking all
 *   browser-based automation including headless Playwright.
 *
 * API investigation results (2026-03-13):
 * - hibid.com/graphql endpoint exists and returns JSON ({"version":"1.0.0.0","site":"WWW"})
 * - The site uses Apollo Client (GraphQL) — query shapes like `lotSearch` and `auctionSearch`
 *   are visible in the Apollo state bundle.
 * - GraphQL introspection is disabled; the exact query shapes are compiled into JS bundles.
 * - api.hibid.com redirects to hibid.com — no separate API subdomain accessible publicly.
 * - No public REST or RSS API found.
 *
 * Options to fix:
 * 1. Reverse-engineer the Apollo GraphQL bundle to find working lotSearch query shape,
 *    then POST to /graphql without triggering Turnstile (might work if /graphql has no challenge).
 * 2. Use a residential proxy + Playwright with turnstile-solving service.
 * 3. Use HiBid's official partner API (requires business relationship).
 *
 * Content note: HiBid hosts a broad range of auction content (estate, antiques, tools, coins).
 * Vehicles are a subset and searches need careful filtering.
 */

import { Actor } from 'apify';
import { PlaywrightCrawler } from 'crawlee';

// DISABLED: HiBid is a general auction site (coins, jewelry, estate sales).
// Vehicle lots are rare (<1%), location data missing from tiles, CAD currency mixing.
// Not worth the Apify compute cost. Disabled 2026-03-17.
await Actor.init();
console.log('[HIBID] Actor disabled - not a viable vehicle source');
await Actor.exit();

const SOURCE = 'hibid-bidcal';
const BASE_URL = 'https://hibid.com';
// Lots search = individual items (not auction events). Vehicle keywords filter for relevant lots.
// Vehicle category page — confirmed by Playwright recon (2026-03-18)
const SEARCH_URL = 'https://www.hibid.com/lots/700006/cars-and-vehicles';

const TARGET_STATES = new Set([
    'AZ', 'CA', 'NV', 'CO', 'NM', 'UT', 'TX', 'FL', 'GA', 'SC', 'TN', 'NC', 'VA', 'WA', 'OR', 'HI',
]);

const HIGH_RUST_STATES = new Set([
    'OH', 'MI', 'PA', 'NY', 'WI', 'MN', 'IL', 'IN', 'MO', 'IA',
    'ND', 'SD', 'NE', 'KS', 'WV', 'ME', 'NH', 'VT', 'MA', 'RI',
    'CT', 'NJ', 'MD', 'DE',
]);
const STATE_NAMES = new Map([
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
const US_STATES = new Set(STATE_NAMES.values());

const VEHICLE_KEYWORDS = ['car', 'truck', 'suv', 'van', 'pickup', 'sedan', 'coupe', 'wagon', 'vehicle', 'automobile', 'motor', '4wd', 'awd', 'hybrid'];
const VEHICLE_MAKES = ['ford', 'chevrolet', 'chevy', 'dodge', 'ram', 'toyota', 'honda', 'nissan', 'jeep', 'gmc', 'chrysler',
    'hyundai', 'kia', 'subaru', 'mazda', 'volkswagen', 'vw', 'bmw', 'mercedes', 'audi', 'lexus', 'acura', 'infiniti',
    'cadillac', 'lincoln', 'buick', 'pontiac', 'mitsubishi', 'volvo', 'tesla', 'rivian', 'lucid', 'genesis'];

await Actor.init();

const input = await Actor.getInput() ?? {};
const {
    maxPages = 6,
    minBid = 1000,
    maxMileage = 50000,
    minYear = 2022,
    targetStates = [...TARGET_STATES],
} = input;

const targetStateSet = new Set(targetStates.map((state) => state.toUpperCase()));
const effectiveMaxPages = Math.max(1, Math.min(maxPages, 6));
const fallbackMaxPages = Math.min(effectiveMaxPages, 3);
const seenListings = new Set();
const sampleLocations = [];

let totalFound = 0;
let totalAfterFilters = 0;
let totalFailedFilters = 0;
let apiModeUsed = false;

function normalizeText(value) {
    return String(value ?? '')
        .replace(/\u00a0/g, ' ')
        .replace(/[ \t]+/g, ' ')
        .replace(/\s*\n\s*/g, '\n')
        .trim();
}

function recordLocationSample(locationText) {
    const normalized = normalizeText(locationText);
    if (!normalized || sampleLocations.includes(normalized) || sampleLocations.length >= 5) return;
    sampleLocations.push(normalized);
}

function isVehicle(title) {
    const lower = normalizeText(title).toLowerCase();
    // Must match a known make, OR a vehicle keyword + a model year (2000-2030)
    // This prevents "car seats", "motor oil", "van accessories" etc from passing
    const hasMake = VEHICLE_MAKES.some((make) => lower.includes(make));
    const hasYear = /\b(200[0-9]|201[0-9]|202[0-9]|2030)\b/.test(lower);
    const hasKeyword = VEHICLE_KEYWORDS.some((kw) => {
        // Require word-boundary for short ambiguous keywords
        if (['car', 'van', 'motor'].includes(kw)) {
            return new RegExp(`\\b${kw}\\b`).test(lower) && hasYear;
        }
        return lower.includes(kw);
    });
    return hasMake || hasKeyword;
}

function parseVehicleTitle(title) {
    const normalizedTitle = normalizeText(title);
    const yearMatch = normalizedTitle.match(/\b(20\d{2}|19[89]\d)\b/);
    const year = yearMatch ? parseInt(yearMatch[1], 10) : null;

    let make = null;
    let model = null;
    const lower = normalizedTitle.toLowerCase();

    for (const candidateMake of VEHICLE_MAKES) {
        if (!lower.includes(candidateMake)) continue;

        make = candidateMake.charAt(0).toUpperCase() + candidateMake.slice(1);
        if (make === 'Chevy') make = 'Chevrolet';
        if (make === 'Vw') make = 'Volkswagen';

        const makeIndex = lower.indexOf(candidateMake);
        const afterMake = normalizedTitle.slice(makeIndex + candidateMake.length).trim();
        const modelMatch = afterMake.match(/^([A-Za-z0-9-]+(?:\s+[A-Za-z0-9-]+)?)/);
        if (modelMatch) model = modelMatch[1].trim();
        break;
    }

    return { year, make, model };
}

function parseState(locationText) {
    const normalized = normalizeText(locationText);
    if (!normalized) return null;

    const match = normalized.match(/,\s*([A-Z]{2})(?:\s+\d{5}(?:-\d{4})?)?\b/i)
        || normalized.match(/\b([A-Z]{2})\s*\d{5}(?:-\d{4})?/i)
        || normalized.match(/\b([A-Z]{2})\b$/i);
    const abbreviation = match ? match[1].toUpperCase() : null;
    if (abbreviation && US_STATES.has(abbreviation)) return abbreviation;

    const upper = normalized.toUpperCase();
    for (const [stateName, stateCode] of STATE_NAMES) {
        const pattern = new RegExp(`(?:,|\\b)\\s*${stateName}(?:\\s+\\d{5}(?:-\\d{4})?)?\\s*$`, 'i');
        if (pattern.test(upper)) return stateCode;
    }

    return null;
}

function parseBid(text) {
    const normalized = normalizeText(text);
    if (!normalized) return 0;

    const match = normalized.replace(/,/g, '').match(/[\d]+(?:\.\d+)?/);
    return match ? parseFloat(match[0]) : 0;
}

function parseDate(text) {
    const normalized = normalizeText(text);
    if (!normalized) return null;

    const parsed = new Date(normalized);
    return Number.isNaN(parsed.getTime()) ? normalized : parsed.toISOString();
}

function parseMileage(text) {
    const normalized = normalizeText(text);
    if (!normalized) return null;

    const match = normalized.match(/(\d[\d,]+)\s*(?:miles?|mi\.?)\b/i);
    return match ? parseInt(match[1].replace(/,/g, ''), 10) : null;
}

function parseVin(text) {
    const normalized = normalizeText(text);
    if (!normalized) return null;

    const match = normalized.match(/\bVIN[:\s#-]*([A-HJ-NPR-Z0-9]{17})\b/i)
        || normalized.match(/\b([A-HJ-NPR-Z0-9]{17})\b/);

    return match ? match[1] : null;
}

function toAbsoluteUrl(value) {
    const normalized = normalizeText(value);
    if (!normalized) return null;

    try {
        return new URL(normalized, BASE_URL).toString();
    } catch {
        return null;
    }
}

function pickFirst(objects, keys) {
    for (const object of objects) {
        if (!object || typeof object !== 'object') continue;
        for (const key of keys) {
            const value = object[key];
            if (Array.isArray(value) && value.length > 0) {
                return value;
            }
            if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
                if (normalizeText(value) !== '') {
                    return value;
                }
            }
            if (value instanceof Date) {
                return value;
            }
        }
    }
    return null;
}

function getNestedObjects(item) {
    const nestedObjects = [item];

    for (const key of ['lot', 'item', 'auction', 'listing', 'result', 'data', 'vehicle']) {
        const nested = item?.[key];
        if (nested && typeof nested === 'object' && !Array.isArray(nested)) {
            nestedObjects.push(nested);
        }
    }

    return nestedObjects;
}

function extractLocation(item) {
    const sources = getNestedObjects(item);
    const explicit = pickFirst(sources, [
        'location',
        'locationText',
        'auctionLocation',
        'saleLocation',
        'address',
        'cityState',
        'city_state',
        'auctionLocationText',
    ]);

    if (explicit) return normalizeText(explicit);

    const city = normalizeText(pickFirst(sources, ['city', 'auctionCity', 'saleCity']));
    const state = normalizeText(pickFirst(sources, ['state', 'stateCode', 'state_code', 'auctionState']));
    const zip = normalizeText(pickFirst(sources, ['zip', 'zipcode', 'postalCode']));

    return [city, state, zip].filter(Boolean).join(', ');
}

function extractImageUrl(item) {
    const sources = getNestedObjects(item);
    const direct = pickFirst(sources, [
        'photo_url',
        'photoUrl',
        'image_url',
        'imageUrl',
        'thumbnail',
        'thumbUrl',
        'primaryImage',
        'image',
    ]);
    if (direct) return toAbsoluteUrl(direct);

    const images = pickFirst(sources, ['images', 'photos', 'media']);
    if (Array.isArray(images)) {
        for (const image of images) {
            if (!image || typeof image !== 'object') continue;
            const candidate = pickFirst([image], ['url', 'src', 'image_url', 'imageUrl', 'thumbnail']);
            if (candidate) return toAbsoluteUrl(candidate);
        }
    }

    return null;
}

function extractListingUrl(item) {
    const sources = getNestedObjects(item);
    const direct = pickFirst(sources, [
        'listing_url',
        'listingUrl',
        'url',
        'href',
        'lotUrl',
        'itemUrl',
        'link',
        'canonicalUrl',
    ]);
    if (direct) return toAbsoluteUrl(direct);

    const lotId = normalizeText(pickFirst(sources, ['lotId', 'lot_id', 'itemId', 'item_id', 'id']));
    return lotId ? `${BASE_URL}/lot/${lotId}` : null;
}

function createListingId(item, listingUrl) {
    const sources = getNestedObjects(item);
    const id = normalizeText(pickFirst(sources, ['lotId', 'lot_id', 'itemId', 'item_id', 'id', 'auctionLotId']));
    if (id) return String(id);
    if (listingUrl) return `hibid-${Buffer.from(listingUrl).toString('base64').slice(0, 20)}`;
    return `hibid-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function buildListing(rawResult, sourceUrl) {
    const title = normalizeText(rawResult.title);
    const location = normalizeText(rawResult.location);
    recordLocationSample(location);
    const detailsText = [
        title,
        rawResult.description,
        rawResult.cardText,
        rawResult.location,
        rawResult.endText,
    ].map(normalizeText).filter(Boolean).join(' ');
    const state = parseState(rawResult.state) || parseState(location);
    const bid = parseBid(rawResult.bidText ?? rawResult.currentBid ?? rawResult.current_bid);
    const mileage = rawResult.mileage ?? parseMileage(detailsText);
    const vin = rawResult.vin ?? parseVin(detailsText);
    const listingUrl = toAbsoluteUrl(rawResult.listingUrl) || sourceUrl;
    const { year, make, model } = parseVehicleTitle(title);

    return {
        listing_id: rawResult.lotId || createListingId(rawResult.originalItem ?? rawResult, listingUrl),
        title,
        current_bid: bid,
        buy_now_price: null,
        auction_end_date: parseDate(rawResult.endText),
        state: state || null,
        listing_url: listingUrl,
        image_url: toAbsoluteUrl(rawResult.imageUrl) || null,
        mileage: mileage || null,
        vin: vin || null,
        year,
        make,
        model,
        source_site: SOURCE,
        scraped_at: new Date().toISOString(),
    };
}

function passesFilters(listing, log) {
    if (!listing.title || !isVehicle(listing.title)) {
        log.debug(`[SKIP] Not a vehicle: ${listing.title || 'unknown title'}`);
        totalFailedFilters++;
        return false;
    }
    if (listing.state && HIGH_RUST_STATES.has(listing.state) && listing.year != null) {
        if (listing.year >= 2023) {
            log.info(`[BYPASS] Rust state ${listing.state} allowed — vehicle is ${listing.year} (≤3yr old)`);
        } else {
            log.debug(`[SKIP] High-rust state: ${listing.state} - ${listing.title}`);
            totalFailedFilters++;
            return false;
        }
    }
    if (listing.state && !targetStateSet.has(listing.state)) {
        log.debug(`[SKIP] Out-of-target state: ${listing.state} - ${listing.title}`);
        totalFailedFilters++;
        return false;
    }
    if (listing.current_bid > 0 && listing.current_bid < minBid) {
        log.debug(`[SKIP] Bid too low: $${listing.current_bid} - ${listing.title}`);
        totalFailedFilters++;
        return false;
    }
    if (listing.year && listing.year < minYear) {
        log.debug(`[SKIP] Too old: ${listing.year} - ${listing.title}`);
        totalFailedFilters++;
        return false;
    }
    if (listing.mileage && listing.mileage > maxMileage) {
        log.debug(`[SKIP] Too many miles: ${listing.mileage} - ${listing.title}`);
        totalFailedFilters++;
        return false;
    }
    return true;
}

async function pushListing(rawResult, sourceUrl, log) {
    const listing = buildListing(rawResult, sourceUrl);
    if (!passesFilters(listing, log)) return false;

    const dedupeKey = listing.listing_url || listing.listing_id || `${listing.title}-${listing.state}-${listing.current_bid}`;
    if (seenListings.has(dedupeKey)) {
        log.debug(`[SKIP] Duplicate listing: ${dedupeKey}`);
        return false;
    }

    seenListings.add(dedupeKey);
    totalAfterFilters++;
    log.info(`[PASS] ${listing.title} | $${listing.current_bid} | ${listing.state}`);
    await Actor.pushData(listing);
    return true;
}

function safeJsonParse(value) {
    try {
        return JSON.parse(value);
    } catch {
        return null;
    }
}

function scoreItemArray(items) {
    if (!Array.isArray(items) || items.length === 0 || typeof items[0] !== 'object') return 0;

    let score = 0;
    for (const item of items.slice(0, 5)) {
        const keys = Object.keys(item).map((key) => key.toLowerCase());
        if (keys.some((key) => /title|name|item|lot/.test(key))) score += 3;
        if (keys.some((key) => /bid|price|current/.test(key))) score += 2;
        if (keys.some((key) => /state|location|city|address/.test(key))) score += 1;
        if (keys.some((key) => /end|close|time|date/.test(key))) score += 1;
    }

    return score;
}

function extractItemsFromPayload(payload) {
    const seen = new WeakSet();
    let best = { score: 0, items: [] };

    const visit = (value, depth) => {
        if (!value || depth > 5) return;

        if (Array.isArray(value)) {
            const score = scoreItemArray(value);
            if (score > best.score) {
                best = { score, items: value };
            }
            for (const entry of value.slice(0, 3)) {
                visit(entry, depth + 1);
            }
            return;
        }

        if (typeof value !== 'object') return;
        if (seen.has(value)) return;
        seen.add(value);

        for (const nested of Object.values(value)) {
            visit(nested, depth + 1);
        }
    };

    visit(payload, 0);
    return best.items;
}

function isRelevantApiUrl(url) {
    const lower = String(url).toLowerCase();
    return lower.includes('hibid')
        && (lower.includes('api')
            || lower.includes('search')
            || lower.includes('auction')
            || lower.includes('lot')
            || lower.includes('item')
            || lower.includes('vehicle'));
}

function normalizeHeaderEntries(entries) {
    const headers = {};
    for (const [key, value] of Object.entries(entries ?? {})) {
        if (!value) continue;
        headers[key.toLowerCase()] = value;
    }
    return headers;
}

function selectApiCapture(traffic) {
    const captures = [];

    for (const response of traffic.responses) {
        const payload = safeJsonParse(response.bodyText);
        if (!payload) continue;

        const items = extractItemsFromPayload(payload);
        if (!items.length) continue;

        const sampleTitles = items.slice(0, 5)
            .map((item) => normalizeText(pickFirst(getNestedObjects(item), ['title', 'name', 'lotTitle', 'lot_title', 'itemTitle', 'item_title', 'description'])))
            .filter(Boolean);
        const vehicleHits = sampleTitles.filter((title) => isVehicle(title)).length;
        const urlScore = isRelevantApiUrl(response.url) ? 4 : 0;
        const score = (items.length > 0 ? 3 : 0) + vehicleHits * 3 + urlScore;

        captures.push({
            score,
            payload,
            items,
            response,
        });
    }

    captures.sort((a, b) => b.score - a.score || b.items.length - a.items.length);
    return captures[0] || null;
}

function getPageSize(capture) {
    const requestInfo = capture.response.request ?? {};
    const requestUrl = requestInfo.url || capture.response.url;

    try {
        const parsedUrl = new URL(requestUrl);
        for (const key of ['limit', 'pageSize', 'page_size', 'per_page', 'perPage', 'rows', 'size', 'take']) {
            const value = parsedUrl.searchParams.get(key);
            if (value && Number(value) > 0) return Number(value);
        }
    } catch {
        // Ignore URL parsing failures.
    }

    const postData = requestInfo.postData;
    if (postData) {
        const parsed = safeJsonParse(postData);
        if (parsed && typeof parsed === 'object') {
            const size = findPaginationSize(parsed);
            if (size) return size;
        }
    }

    return Math.max(20, capture.items.length);
}

function findPaginationSize(value, depth = 0) {
    if (!value || depth > 4 || typeof value !== 'object') return null;

    for (const [key, entry] of Object.entries(value)) {
        const lower = key.toLowerCase();
        if (['limit', 'pagesize', 'page_size', 'perpage', 'per_page', 'size', 'rows', 'take'].includes(lower)) {
            const numeric = Number(entry);
            if (numeric > 0) return numeric;
        }
        if (entry && typeof entry === 'object') {
            const nested = findPaginationSize(entry, depth + 1);
            if (nested) return nested;
        }
    }

    return null;
}

function updateUrlPagination(url, pageNum, pageSize) {
    const parsed = new URL(url);
    let touched = false;

    for (const key of ['page', 'pageNum', 'page_num', 'pageNumber', 'page_number', 'currentPage']) {
        if (parsed.searchParams.has(key)) {
            parsed.searchParams.set(key, String(pageNum));
            touched = true;
        }
    }

    for (const key of ['offset', 'start', 'skip', 'from']) {
        if (parsed.searchParams.has(key)) {
            parsed.searchParams.set(key, String((pageNum - 1) * pageSize));
            touched = true;
        }
    }

    if (!touched) {
        parsed.searchParams.set('page', String(pageNum));
    }

    return parsed.toString();
}

function mutatePagination(value, pageNum, pageSize, depth = 0) {
    if (!value || depth > 5 || typeof value !== 'object') return false;

    let touched = false;

    for (const [key, entry] of Object.entries(value)) {
        const lower = key.toLowerCase();

        if (['page', 'pagenum', 'page_num', 'pagenumber', 'page_number', 'currentpage'].includes(lower)) {
            value[key] = pageNum;
            touched = true;
            continue;
        }

        if (['offset', 'start', 'skip', 'from'].includes(lower)) {
            value[key] = (pageNum - 1) * pageSize;
            touched = true;
            continue;
        }

        if (entry && typeof entry === 'object') {
            touched = mutatePagination(entry, pageNum, pageSize, depth + 1) || touched;
        }
    }

    return touched;
}

function updateBodyPagination(bodyText, pageNum, pageSize) {
    if (!bodyText) return bodyText;

    const jsonBody = safeJsonParse(bodyText);
    if (jsonBody && typeof jsonBody === 'object') {
        const clone = JSON.parse(JSON.stringify(jsonBody));
        const touched = mutatePagination(clone, pageNum, pageSize);
        if (!touched) {
            clone.page = pageNum;
        }
        return JSON.stringify(clone);
    }

    const params = new URLSearchParams(bodyText);
    let touched = false;

    for (const key of ['page', 'pageNum', 'page_num', 'pageNumber', 'page_number', 'currentPage']) {
        if (params.has(key)) {
            params.set(key, String(pageNum));
            touched = true;
        }
    }

    for (const key of ['offset', 'start', 'skip', 'from']) {
        if (params.has(key)) {
            params.set(key, String((pageNum - 1) * pageSize));
            touched = true;
        }
    }

    if (!touched) {
        params.set('page', String(pageNum));
    }

    return params.toString();
}

function buildFetchHeaders(requestHeaders, cookieHeader) {
    const headers = {
        accept: 'application/json, text/plain, */*',
        'user-agent': 'Mozilla/5.0 (compatible; DealerScope/1.0)',
    };

    for (const key of ['accept', 'content-type', 'origin', 'referer', 'authorization', 'x-requested-with']) {
        if (requestHeaders[key]) {
            headers[key] = requestHeaders[key];
        }
    }

    if (cookieHeader) {
        headers.cookie = cookieHeader;
    }

    return headers;
}

function normalizeApiItem(item) {
    const sources = getNestedObjects(item);
    const title = normalizeText(pickFirst(sources, ['title', 'name', 'lotTitle', 'lot_title', 'itemTitle', 'item_title', 'description']));
    const location = extractLocation(item);
    recordLocationSample(location);
    const state = parseState(pickFirst(sources, ['state', 'stateCode', 'state_code'])) || parseState(location);
    const listingUrl = extractListingUrl(item);
    const description = normalizeText(pickFirst(sources, ['description', 'subtitle', 'summary', 'notes']));
    const bidValue = pickFirst(sources, ['currentBid', 'current_bid', 'highBid', 'high_bid', 'bidAmount', 'currentPrice', 'price']);
    const endValue = pickFirst(sources, ['endTime', 'end_time', 'closeTime', 'close_time', 'endDate', 'end_date', 'closingDate', 'closesAt', 'closes_at']);
    const mileageValue = pickFirst(sources, ['mileage', 'odometer']);
    const vinValue = pickFirst(sources, ['vin', 'vehicleIdentificationNumber']);

    return {
        lotId: createListingId(item, listingUrl),
        title,
        bidText: bidValue,
        location,
        state,
        endText: endValue,
        listingUrl,
        imageUrl: extractImageUrl(item),
        mileage: mileageValue ? parseMileage(String(mileageValue)) ?? Number(mileageValue) : null,
        vin: normalizeText(vinValue) || null,
        description,
        cardText: `${title} ${location} ${description}`.trim(),
        originalItem: item,
    };
}

async function processApiCapture(capture, cookieHeader, log) {
    const pageSize = getPageSize(capture);
    const seenPageSignatures = new Set();

    for (let pageNum = 1; pageNum <= effectiveMaxPages; pageNum++) {
        let payload;
        let items;

        if (pageNum === 1) {
            payload = capture.payload;
            items = capture.items;
        } else {
            const requestInfo = capture.response.request ?? {};
            const method = (requestInfo.method || 'GET').toUpperCase();
            const headers = buildFetchHeaders(normalizeHeaderEntries(requestInfo.headers), cookieHeader);
            const url = updateUrlPagination(requestInfo.url || capture.response.url, pageNum, pageSize);
            const body = method === 'GET' ? undefined : updateBodyPagination(requestInfo.postData, pageNum, pageSize);

            try {
                const response = await fetch(url, {
                    method,
                    headers,
                    body,
                    signal: AbortSignal.timeout(15000),
                });
                if (!response.ok) {
                    log.debug(`[HiBid] API page ${pageNum} failed with status ${response.status}`);
                    break;
                }

                const text = await response.text();
                payload = safeJsonParse(text);
                items = extractItemsFromPayload(payload);
            } catch (error) {
                log.debug(`[HiBid] API page ${pageNum} request failed: ${error.message}`);
                break;
            }
        }

        if (!payload || !items.length) {
            log.info(`[HiBid] API page ${pageNum} returned no items`);
            break;
        }

        const pageSignature = JSON.stringify(items.slice(0, 5).map((item) => {
            const normalized = normalizeApiItem(item);
            return normalized.listingUrl || normalized.lotId || normalized.title;
        }));
        if (seenPageSignatures.has(pageSignature)) {
            log.info(`[HiBid] API page ${pageNum} repeated prior results, stopping pagination`);
            break;
        }
        seenPageSignatures.add(pageSignature);

        totalFound += items.length;
        log.info(`[HiBid] API page ${pageNum} returned ${items.length} items`);

        for (const item of items) {
            await pushListing(normalizeApiItem(item), SEARCH_URL, log);
            if (totalAfterFilters >= 100) return true;
        }
    }

    return totalAfterFilters > 0;
}

async function extractCardsFromPage(page) {
    return page.evaluate(() => {
        const normalizeText = (value) => String(value ?? '')
            .replace(/\u00a0/g, ' ')
            .replace(/[ \t]+/g, ' ')
            .replace(/\s*\n\s*/g, '\n')
            .trim();

        const textFrom = (root, selectors) => {
            for (const selector of selectors) {
                const node = root.querySelector(selector);
                const text = normalizeText(node?.textContent);
                if (text) return text;
            }
            return '';
        };

        const cards = Array.from(document.querySelectorAll('.auction-card, .lot-card, .item-card, [class*="card"], [class*="lot"]'));
        const anchors = Array.from(document.querySelectorAll('a[href*="/lot/"], a[href*="/item/"]'));
        const seen = new Set();
        const items = [];

        const candidates = cards.length > 0 ? cards : anchors.map((anchor) => anchor.closest('article, li, div') || anchor);

        for (const candidate of candidates) {
            const card = candidate;
            const anchor = card.querySelector('a[href*="/lot/"], a[href*="/item/"]') || (card.matches('a') ? card : null);
            const href = anchor?.href || '';
            const key = href || normalizeText(card.innerText);
            if (!key || seen.has(key)) continue;
            seen.add(key);

            const cardText = normalizeText(card.innerText);
            const title = textFrom(card, [
                'h1', 'h2', 'h3', 'h4',
                '[class*="title"]',
                '[class*="name"]',
            ]) || normalizeText(anchor?.textContent);
            if (!title) continue;

            const bidText = textFrom(card, [
                '[class*="current-bid"]',
                '[class*="high-bid"]',
                '[class*="bid"]',
                '[class*="price"]',
                '[class*="amount"]',
            ]);
            const endText = textFrom(card, [
                'time',
                '[datetime]',
                '[class*="end"]',
                '[class*="close"]',
                '[class*="time-left"]',
                '[class*="countdown"]',
            ]);
            const location = textFrom(card, [
                '[class*="location"]',
                '[class*="city"]',
                '[class*="state"]',
                '[class*="address"]',
                '[data-location]',
            ]);
            const img = card.querySelector('img');
            const imageUrl = img?.getAttribute('data-src') || img?.getAttribute('src') || null;
            const lotIdMatch = href.match(/\/lot\/(\d+)/i)
                || href.match(/\/item\/(\d+)/i)
                || href.match(/[?&](?:lotId|id)=(\d+)/i);

            items.push({
                lotId: lotIdMatch ? lotIdMatch[1] : '',
                title,
                bidText,
                endText,
                location,
                imageUrl,
                listingUrl: href,
                description: cardText,
                cardText,
            });
        }

        return items;
    });
}

const crawler = new PlaywrightCrawler({
    launchContext: {
        launchOptions: { headless: true },
    },
    maxRequestsPerCrawl: fallbackMaxPages + 3,
    navigationTimeoutSecs: 60,
    requestHandlerTimeoutSecs: 120,
    maxConcurrency: 2,
    minConcurrency: 1,
    preNavigationHooks: [
        async ({ page, request }) => {
            request.userData.apiTraffic = { responses: [] };

            page.on('response', (response) => {
                void (async () => {
                    try {
                        const requestInfo = response.request();
                        const url = response.url();
                        const resourceType = requestInfo.resourceType();
                        const contentType = (response.headers()['content-type'] || '').toLowerCase();

                        if (!['xhr', 'fetch'].includes(resourceType)) return;
                        if (!contentType.includes('json') && !isRelevantApiUrl(url)) return;

                        const bodyText = await response.text();
                        if (!bodyText || bodyText.length > 1_000_000) return;

                        request.userData.apiTraffic.responses.push({
                            url,
                            status: response.status(),
                            headers: response.headers(),
                            bodyText,
                            request: {
                                url: requestInfo.url(),
                                method: requestInfo.method(),
                                headers: requestInfo.headers(),
                                postData: requestInfo.postData(),
                            },
                        });
                    } catch {
                        // Ignore response parsing issues and keep crawling.
                    }
                })();
            });
        },
    ],

    async requestHandler({ page, request, enqueueLinks, log }) {
        const currentPage = request.userData?.pageNum ?? 1;
        log.info(`[HiBid] Processing search page ${currentPage}: ${request.url}`);

        await page.waitForSelector('body', { timeout: 30000 });
        await page.waitForLoadState('networkidle', { timeout: 20000 }).catch(() => {});
        // Wait for Angular to render lot cards — up to 15s
        await page.waitForSelector('a[href*="/lot/"], app-lot-card, .lot-card, [class*="lot"]', { timeout: 15000 }).catch(() => {});
        await page.waitForTimeout(2000);

        if (currentPage === 1 && !apiModeUsed) {
            const cookieHeader = (await page.context().cookies())
                .map((cookie) => `${cookie.name}=${cookie.value}`)
                .join('; ');
            const apiCapture = selectApiCapture(request.userData.apiTraffic ?? { responses: [] });

            if (apiCapture) {
                log.info(`[HiBid] Captured API endpoint: ${apiCapture.response.url}`);
                apiModeUsed = await processApiCapture(apiCapture, cookieHeader, log);
                if (apiModeUsed) {
                    return;
                }
                log.info('[HiBid] API capture did not yield usable results, falling back to card scraping');
            } else {
                log.info('[HiBid] No usable API response captured, falling back to card scraping');
            }
        }

        const results = await extractCardsFromPage(page);
        totalFound += results.length;
        log.info(`[HiBid] Found ${results.length} result cards on page ${currentPage}`);

        for (const result of results) {
            await pushListing(result, request.url, log);
            if (totalAfterFilters >= 100) return;
        }

        if (!apiModeUsed && results.length > 0 && currentPage < fallbackMaxPages) {
            const nextUrl = new URL(SEARCH_URL);
            nextUrl.searchParams.set('page', String(currentPage + 1));

            await enqueueLinks({
                urls: [nextUrl.toString()],
                label: 'LIST',
                userData: { pageNum: currentPage + 1 },
            });
        }
    },
});

await crawler.run([
    {
        url: SEARCH_URL,
        label: 'LIST',
        userData: { pageNum: 1 },
    },
]);

console.log('[HIBID] Sample locations:', sampleLocations);
console.log(`[HIBID COMPLETE] Found: ${totalFound} | Passed filters: ${totalAfterFilters} | Failed filters: ${totalFailedFilters}`);

await Actor.exit();
