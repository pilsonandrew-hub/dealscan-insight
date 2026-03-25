/**
 * ds-bidspotter scraper — HTTP-based rewrite (no Playwright)
 *
 * Key findings from 2026-03-22 investigation:
 * - BidSpotter pages are SERVER-SIDE RENDERED and fully accessible via plain HTTP
 * - The old Playwright actor got 123 UK equipment items (all filtered out) due to:
 *   1. No country filtering (UK auctions pass the Automobiles category)
 *   2. No state detection from auctionCity
 *   3. 49-minute runs with max 170 requests before stopping
 * - US vehicle auctions exist (machin7 TX: Ford F-150s, RAMs; bscroyal FL: Govt Fleet)
 * - Some BSC-hosted US pages return 202 AWS WAF challenge (need Playwright+proxy to unlock)
 *   BUT most lot pages and non-BSC-hosted catalogue pages ARE accessible via HTTP
 * - Key data extracted from dataLayer: auctionCountry, auctionCity, lotName, lotEndsFrom, openingPrice
 *
 * Strategy:
 * 1. Crawl search-filter pages to get catalogue URLs (pagination up to maxPages)
 * 2. For each catalogue, fetch via HTTP and check dataLayer for auctionCountry == 'United States'
 * 3. If US, enumerate lots (60/page) and extract vehicle lot data from each lot page
 * 4. Parse state from auctionCity using city→state lookup table
 * 5. Use HttpCrawler (fast, no Playwright overhead) with proper UA rotation
 */

import { Actor } from 'apify';
import { HttpCrawler } from 'crawlee';

const SOURCE = 'bidspotter';
const BASE_URL = 'https://www.bidspotter.com';

// US target states for wholesale vehicle arbitrage
const TARGET_STATES = new Set([
    'AZ', 'CA', 'NV', 'CO', 'NM', 'UT', 'TX', 'FL', 'GA', 'SC', 'TN', 'NC', 'VA', 'WA', 'OR', 'HI',
    'ID', 'MT', 'WY', 'ND', 'SD', 'NE', 'KS', 'AL', 'LA', 'OK',
]);

// Canadian provinces — always reject
const CANADIAN_PROVINCES = new Set([
    'AB', 'BC', 'ON', 'QC', 'MB', 'SK', 'NS', 'NB', 'PE', 'NL', 'YT', 'NT', 'NU',
]);

// All valid US state codes
const ALL_US_STATES = new Set([
    'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA', 'HI', 'ID', 'IL', 'IN', 'IA',
    'KS', 'KY', 'LA', 'ME', 'MD', 'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
    'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC', 'SD', 'TN', 'TX', 'UT', 'VT',
    'VA', 'WA', 'WV', 'WI', 'WY', 'DC',
]);

// City → State mapping for BidSpotter auction cities (extend as needed)
const CITY_TO_STATE = {
    // Texas
    'odessa': 'TX', 'dallas': 'TX', 'houston': 'TX', 'austin': 'TX', 'san antonio': 'TX',
    'fort worth': 'TX', 'el paso': 'TX', 'arlington': 'TX', 'corpus christi': 'TX',
    'lubbock': 'TX', 'plano': 'TX', 'laredo': 'TX', 'irving': 'TX', 'garland': 'TX',
    // Florida
    'tampa': 'FL', 'miami': 'FL', 'orlando': 'FL', 'jacksonville': 'FL', 'fort lauderdale': 'FL',
    'tallahassee': 'FL', 'st. petersburg': 'FL', 'hialeah': 'FL', 'panama city': 'FL',
    'pensacola': 'FL', 'gainesville': 'FL', 'clearwater': 'FL', 'cape coral': 'FL',
    // Georgia
    'atlanta': 'GA', 'savannah': 'GA', 'augusta': 'GA', 'macon': 'GA', 'columbus': 'GA',
    // South Carolina
    'charleston': 'SC', 'columbia': 'SC', 'greenville': 'SC', 'ladson': 'SC', 'spartanburg': 'SC',
    // North Carolina
    'charlotte': 'NC', 'raleigh': 'NC', 'greensboro': 'NC', 'durham': 'NC', 'winston-salem': 'NC',
    // Tennessee
    'nashville': 'TN', 'memphis': 'TN', 'knoxville': 'TN', 'chattanooga': 'TN',
    // Virginia
    'richmond': 'VA', 'virginia beach': 'VA', 'norfolk': 'VA', 'chesapeake': 'VA',
    // California
    'los angeles': 'CA', 'san francisco': 'CA', 'san diego': 'CA', 'sacramento': 'CA',
    'fresno': 'CA', 'long beach': 'CA', 'oakland': 'CA', 'bakersfield': 'CA',
    'anaheim': 'CA', 'santa ana': 'CA', 'riverside': 'CA', 'stockton': 'CA',
    'chula vista': 'CA', 'irvine': 'CA', 'fremont': 'CA', 'modesto': 'CA',
    'santa clara': 'CA', 'fontana': 'CA', 'oxnard': 'CA',
    // Nevada
    'las vegas': 'NV', 'henderson': 'NV', 'reno': 'NV', 'north las vegas': 'NV',
    // Arizona
    'phoenix': 'AZ', 'tucson': 'AZ', 'mesa': 'AZ', 'chandler': 'AZ', 'scottsdale': 'AZ',
    'tempe': 'AZ', 'gilbert': 'AZ', 'glendale': 'AZ', 'peoria': 'AZ',
    // Washington
    'seattle': 'WA', 'spokane': 'WA', 'tacoma': 'WA', 'bellevue': 'WA', 'kent': 'WA',
    'renton': 'WA', 'kirkland': 'WA', 'redmond': 'WA', 'vancouver': 'WA',
    // Oregon
    'portland': 'OR', 'salem': 'OR', 'eugene': 'OR', 'gresham': 'OR',
    // Colorado
    'denver': 'CO', 'colorado springs': 'CO', 'aurora': 'CO', 'fort collins': 'CO',
    // New Mexico
    'albuquerque': 'NM', 'santa fe': 'NM', 'las cruces': 'NM',
    // Alabama
    'birmingham': 'AL', 'montgomery': 'AL', 'huntsville': 'AL', 'mobile': 'AL',
    // Louisiana
    'new orleans': 'LA', 'baton rouge': 'LA', 'shreveport': 'LA', 'lafayette': 'LA',
    // Oklahoma
    'oklahoma city': 'OK', 'tulsa': 'OK', 'norman': 'OK', 'broken arrow': 'OK',
    // Kansas
    'wichita': 'KS', 'overland park': 'KS', 'kansas city': 'KS',
    // Nebraska
    'omaha': 'NE', 'lincoln': 'NE',
    // South Dakota
    'sioux falls': 'SD', 'rapid city': 'SD',
    // Utah
    'salt lake city': 'UT', 'provo': 'UT', 'west valley city': 'UT',
    // Idaho
    'boise': 'ID', 'nampa': 'ID', 'meridian': 'ID',
    // Hawaii
    'honolulu': 'HI',
    // DC
    'washington': 'DC', 'washington, d.c.': 'DC',
    // Other key cities
    'swedesboro': 'NJ',
};

const VEHICLE_MAKES = [
    'ford', 'chevrolet', 'chevy', 'dodge', 'ram', 'toyota', 'honda', 'nissan', 'jeep', 'gmc',
    'chrysler', 'hyundai', 'kia', 'subaru', 'mazda', 'volkswagen', 'vw', 'bmw', 'mercedes',
    'audi', 'lexus', 'acura', 'infiniti', 'cadillac', 'lincoln', 'buick', 'pontiac',
    'mitsubishi', 'volvo', 'tesla', 'mini', 'saturn', 'scion', 'land rover', 'jaguar',
    'porsche', 'maserati', 'alfa romeo', 'fiat', 'genesis', 'rivian', 'lucid',
    'international', 'kenworth', 'peterbilt', 'mack', 'freightliner', 'western star', 'sterling',
];

const VEHICLE_KEYWORDS = [
    'sedan', 'coupe', 'hatchback', 'wagon', 'convertible', 'suv', 'sport utility',
    'crossover', 'pickup', 'crew cab', 'extended cab', 'minivan', 'passenger van',
    '4x4', 'awd', 'fwd', 'rwd', 'passenger car', 'automobile',
    'f-150', 'f-250', 'f-350', 'f-450', 'silverado', 'sierra', 'ranger', 'explorer',
    'expedition', 'tahoe', 'suburban', 'escalade', 'navigator', 'wrangler', 'cherokee',
];

// Exclude non-passenger / non-target vehicle lots
const EXCLUDED_PATTERN = /\b(forklift|tractor(?!\s+truck)|loader|backhoe|excavator|grader|dozer|bulldozer|skid\s*steer|trencher|mower|generator|compressor|sprayer|sweeper|boat|marine|camper|rv|motorhome|jet\s*ski|snowmobile|motorcycle|atv|utv|golf\s*cart|ambulance|fire\s*truck|flatbed(?!\s+car)|box\s*truck|cargo\s+van|step\s+van|cutaway|chassis\s+cab|stake\s*bed|semitrailer|furniture|desk|chair|cabinet|computer|electronics|tools(?!\s+truck)|industrial|forklift|scissor\s*lift|telehandler|dumper|tipper|sweeper|baler|combine|harvester|sprayer)\b/i;

await Actor.init();

const input = await Actor.getInput() ?? {};
const {
    maxCatalogues = 50,
    maxPages = 10,
    minYear = 1990,
    targetStates = [...TARGET_STATES],
} = input;

const targetStateSet = new Set(targetStates.map((s) => String(s).toUpperCase()));
const seenListings = new Set();

let totalFound = 0;
let totalAfterFilters = 0;

function normalizeText(value) {
    return String(value ?? '').replace(/\s+/g, ' ').trim();
}

function parseBid(value) {
    const text = normalizeText(value).replace(/,/g, '');
    const match = text.match(/\$?\s*([\d]+(?:\.\d+)?)/);
    return match ? parseFloat(match[1]) : 0;
}

function parseDate(value) {
    const text = normalizeText(value)
        .replace(/^(ends?|closing|end\s*date|auction\s*end)\s*:?\s*/i, '')
        .replace(/\bat\b/i, ' ');
    if (!text) return null;
    const parsed = new Date(text);
    return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
}

/**
 * Parse state code from BidSpotter auctionCity field.
 * BidSpotter gives city names like "Odessa", "Tampa", "Ladson", etc.
 * We look up in our city→state table, or try to extract from the text.
 */
function parseStateFromCity(cityText) {
    if (!cityText) return null;
    const text = normalizeText(cityText);
    const upper = text.toUpperCase();
    const lower = text.toLowerCase();

    // Check if city text has a state code already (e.g. "Tampa, FL" or "Tampa FL")
    const stateInText = text.match(/,\s*([A-Z]{2})\b/)
        ?? text.match(/\b([A-Z]{2})\s*(?:\d{5})?\s*$/)
        ?? text.match(/\s([A-Z]{2})\s*$/);
    if (stateInText) {
        const code = stateInText[1];
        if (ALL_US_STATES.has(code) && !CANADIAN_PROVINCES.has(code)) return code;
    }

    // City lookup table
    for (const [city, state] of Object.entries(CITY_TO_STATE)) {
        if (lower.includes(city)) return state;
    }

    return null;
}

function parseState(text) {
    const upper = normalizeText(text).toUpperCase();
    if (!upper) return null;

    const match = upper.match(/,\s*([A-Z]{2})(?:\s+\d{5})?\b/)
        ?? upper.match(/\b([A-Z]{2})\s+\d{5}\b/)
        ?? upper.match(/\b([A-Z]{2})\b$/);
    const code = match?.[1];
    if (!code) return null;
    if (CANADIAN_PROVINCES.has(code)) return null;
    return ALL_US_STATES.has(code) ? code : null;
}

function parseMileage(text) {
    const t = normalizeText(text);
    const match = t.match(/([\d,]+)\s*(?:mi(?:les?)?|km)/i);
    if (!match) return null;
    const miles = parseFloat(match[1].replace(/,/g, ''));
    if (/km/i.test(match[0])) return Math.round(miles * 0.621371);
    return miles;
}

function parseVehicleTitle(title) {
    const normalized = normalizeText(title);
    const lower = normalized.toLowerCase();

    const yearMatch = normalized.match(/\b(19[89]\d|20[0-3]\d)\b/);
    const year = yearMatch ? parseInt(yearMatch[1], 10) : null;

    let make = null;
    let model = null;

    for (const candidate of VEHICLE_MAKES) {
        const pattern = new RegExp(`\\b${candidate.replace(/\s+/g, '\\s+')}\\b`, 'i');
        const match = normalized.match(pattern);
        if (!match) continue;

        make = candidate === 'chevy' ? 'Chevrolet'
            : candidate === 'vw' ? 'Volkswagen'
            : candidate.replace(/\b\w/g, (c) => c.toUpperCase());

        const afterMake = normalized.slice(match.index + match[0].length)
            .replace(/^[\s\-:]+/, '')
            .replace(/\b(4x4|awd|fwd|rwd|vin|odometer|mileage)\b.*$/i, '')
            .trim();
        const modelMatch = afterMake.match(/^([A-Za-z0-9][A-Za-z0-9\-]*(?:\s+[A-Za-z0-9][A-Za-z0-9\-]*)?)/);
        model = modelMatch ? modelMatch[1] : null;
        break;
    }

    return { year, make, model, lower };
}

function isVehicleLot(title) {
    const { lower } = parseVehicleTitle(title);
    if (!lower) return false;
    if (EXCLUDED_PATTERN.test(lower)) return false;
    return VEHICLE_MAKES.some((m) => lower.includes(m))
        || VEHICLE_KEYWORDS.some((k) => lower.includes(k));
}

function applyFilters(listing, log) {
    // Must have a make or be clearly a vehicle
    if (!listing.make && !isVehicleLot(listing.title)) {
        log.debug(`[BS] Skip non-vehicle: ${listing.title}`);
        return false;
    }

    // Must have a make
    if (!listing.make) {
        log.debug(`[BS] Skip no-make: ${listing.title}`);
        return false;
    }

    // Exclude Canadian provinces
    if (listing.state && CANADIAN_PROVINCES.has(listing.state)) {
        log.debug(`[BS] Skip Canadian: ${listing.state}`);
        return false;
    }

    // Must be in target state (if state known)
    // If state is null but auction is in US, we include it (let it through with null state)
    if (listing.state && !targetStateSet.has(listing.state)) {
        log.debug(`[BS] Skip out-of-target state ${listing.state}: ${listing.title}`);
        return false;
    }

    // Year filter
    if (listing.year && listing.year < minYear) {
        log.debug(`[BS] Skip old year ${listing.year}: ${listing.title}`);
        return false;
    }

    return true;
}

/**
 * Extract dataLayer values from BidSpotter HTML pages.
 * BidSpotter uses window.dataLayer.push({...}) with JSON-like data (with trailing commas).
 */
function extractDataLayer(html) {
    const match = html.match(/window\.dataLayer\.push\(\s*(\{[\s\S]*?\})\s*\)\s*;/);
    if (!match) return {};
    
    const raw = match[1];
    const result = {};
    
    // Extract individual key-value pairs with regex (handles trailing commas)
    const pairs = raw.matchAll(/"([^"]+)"\s*:\s*"([^"]*)"/g);
    for (const [, key, value] of pairs) {
        result[key] = value;
    }
    
    return result;
}

/**
 * Extract catalogue links from search-filter page HTML.
 * Pattern: href="/en-us/auction-catalogues/{seller}/catalogue-id-{id}"
 */
function extractCatalogueLinks(html) {
    const links = new Set();
    const matches = html.matchAll(/href="(\/en-us\/auction-catalogues\/[^"?]+\/catalogue-id-[^"?]+)"/g);
    for (const [, href] of matches) {
        links.add(href);
    }
    return [...links];
}

/**
 * Extract lot links from a catalogue page HTML.
 * BidSpotter lot URLs: /en-us/auction-catalogues/{seller}/catalogue-id-{id}/lot-{uuid}
 */
function extractLotLinks(html) {
    const links = new Set();
    // Generic lot link pattern - handles any seller prefix
    const matches = html.matchAll(/href="(\/en-us\/auction-catalogues\/[^"?]+\/lot-[^"?]+)"/g);
    for (const [, href] of matches) {
        // Exclude search-filter and other non-lot pages
        if (!href.includes('/search-filter') && !href.includes('?')) {
            links.add(href);
        }
    }
    return [...links];
}

/**
 * Extract lot titles from catalogue page cards (for pre-filtering).
 * Pattern: class="lot-title">Title text</
 */
function extractLotCards(html) {
    const cards = [];
    const titleMatches = html.matchAll(/class="lot-title"[^>]*>([^<]+)</g);
    for (const [, title] of titleMatches) {
        cards.push(normalizeText(title));
    }
    return cards;
}

/**
 * Extract image URL from lot page.
 */
function extractImageUrl(html) {
    // CDN image pattern
    const cdnMatch = html.match(/https:\/\/cdn\.globalauctionplatform\.com\/[^"'\s]+\.(?:jpg|jpeg|png|webp)/i);
    if (cdnMatch) return cdnMatch[0].replace(/\?.*$/, '');
    return null;
}

/**
 * Extract mileage from lot description/title HTML.
 */
function extractMileage(html) {
    const match = html.match(/([\d,]+)\s*(?:mi(?:les?)?|km)(?:\s|,|\.|<)/i);
    if (!match) return null;
    const miles = parseFloat(match[1].replace(/,/g, ''));
    if (/km/i.test(match[0])) return Math.round(miles * 0.621371);
    return miles;
}

function isBlockedResponse(statusCode, html) {
    if (statusCode === 403 || statusCode === 429 || statusCode === 503) return true;
    if (!html) return true;
    const lower = html.toLowerCase();
    return lower.includes('awswaf')
        || lower.includes('access denied')
        || lower.includes('request blocked')
        || lower.includes('forbidden')
        || html.length < 800;
}

function extractCatalogueBidByIndex(html) {
    const bids = [];
    const hrefMatches = [...html.matchAll(/href="(\/en-us\/auction-catalogues\/[^"?]+\/lot-[^"?]+)"/g)];

    for (const match of hrefMatches) {
        const index = match.index ?? 0;
        const windowStart = Math.max(0, index - 900);
        const windowEnd = Math.min(html.length, index + 1800);
        const chunk = html.slice(windowStart, windowEnd);

        const bidMatch = chunk.match(/(?:current\s*bid|opening\s*bid|starting\s*bid|bid(?:ding)?(?:\s*price)?|hammer\s*price)[^$]{0,80}\$\s*([\d,]+(?:\.\d{2})?)/i)
            ?? chunk.match(/\$\s*([\d,]+(?:\.\d{2})?)/);
        bids.push(bidMatch ? parseBid(bidMatch[1] || bidMatch[0]) : 0);
    }

    return bids;
}

function buildDetailHeaders(userAgent) {
    return {
        ...BROWSER_HEADERS,
        'User-Agent': userAgent,
    };
}

function buildFallbackListing(request, detailData = {}) {
    const fallback = request.userData?.fallbackListing || {};
    const url = request.url;
    const listingId = url.match(/\/lot-([^/?#]+)/)?.[1]
        ?? `bs-${Buffer.from(url).toString('base64').slice(0, 16)}`;

    const finalTitle = normalizeText(
        detailData.lotName
        || fallback.title
        || request.userData?.cardTitle
        || ''
    );
    const parsed = parseVehicleTitle(finalTitle);
    const cardBid = Number(request.userData?.cardBid || fallback.current_bid || 0);
    const detailBid = parseBid(detailData.openingPrice || detailData.currentBid || '0');

    return {
        listing_id: listingId,
        title: finalTitle,
        year: parsed.year ?? fallback.year ?? null,
        make: parsed.make ?? fallback.make ?? null,
        model: parsed.model ?? fallback.model ?? null,
        mileage: extractMileage(request.userData?.cardHtml || '') || fallback.mileage || null,
        current_bid: detailBid || cardBid || 0,
        auction_end_date: parseDate(detailData.lotEndsFrom || request.userData?.auctionEndDate || ''),
        state: detailData.auctionCity
            ? (parseStateFromCity(detailData.auctionCity) ?? parseState(detailData.auctionCity) ?? fallback.state ?? null)
            : (fallback.state ?? null),
        listing_url: url,
        image_url: detailData.imageUrl || fallback.image_url || null,
        source_site: SOURCE,
        scraped_at: new Date().toISOString(),
    };
}

async function enqueueDetailRetry(crawler, request, attempt, log) {
    const nextAttempt = attempt + 1;
    if (nextAttempt >= DETAIL_UA_ROTATION.length) return false;

    const retryUrl = request.url;
    await crawler.requestQueue.addRequest({
        url: retryUrl,
        uniqueKey: `${retryUrl}::retry-${nextAttempt}`,
        label: 'LOT',
        headers: buildDetailHeaders(DETAIL_UA_ROTATION[nextAttempt]),
        userData: {
            ...request.userData,
            detailAttempt: nextAttempt,
        },
    });
    log.warning(`[BS] Retrying blocked lot with UA ${nextAttempt + 1}/${DETAIL_UA_ROTATION.length}: ${retryUrl}`);
    return true;
}

// Request headers to mimic a real browser
const BROWSER_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
};

const DETAIL_UA_ROTATION = [
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
];

let cataloguesProcessed = 0;
let cataloguesSkippedNonUS = 0;
let cataloguesSkippedWAF = 0;

const proxyConfiguration = await Actor.createProxyConfiguration({
    useApifyProxy: true,
    countryCode: 'US',
});

const crawler = new HttpCrawler({
    maxRequestsPerCrawl: 2000,
    maxConcurrency: 5,
    requestHandlerTimeoutSecs: 30,
    navigationTimeoutSecs: 20,
    additionalMimeTypes: ['text/html'],
    proxyConfiguration,
    
    // Retry on failures
    maxRequestRetries: 1,
    
    async requestHandler({ request, response, body, log }) {
        const html = body.toString();
        const label = request.label ?? 'CATALOGUE_LIST';
        const detailAttempt = request.userData?.detailAttempt ?? 0;
        const responseStatus = response?.statusCode ?? response?.status ?? 200;
        
        // Skip WAF challenge pages (202 or empty body)
        if (label !== 'LOT' && (!html || html.length < 1000)) {
            if (label === 'CATALOGUE') {
                cataloguesSkippedWAF++;
                log.warning(`[BS] WAF/empty page blocked: ${request.url}`);
            }
            return;
        }

        // ── LOT detail page ───────────────────────────────────────────────────
        if (label === 'LOT') {
            const url = request.url;
            
            const blocked = isBlockedResponse(responseStatus, html);
            if (blocked) {
                const retried = await enqueueDetailRetry(crawler, request, detailAttempt, log);
                if (retried) return;

                const fallbackListing = buildFallbackListing(request, {});
                if (!applyFilters(fallbackListing, log)) return;
                if (seenListings.has(fallbackListing.listing_id)) return;
                seenListings.add(fallbackListing.listing_id);

                totalFound += 1;
                totalAfterFilters += 1;
                log.warning(`[BS] Lot detail blocked, keeping fallback listing at $0: ${fallbackListing.title}`);
                await Actor.pushData({
                    ...fallbackListing,
                    current_bid: 0,
                });
                return;
            }

            const data = extractDataLayer(html);
            const title = normalizeText(data.lotName || '');
            
            if (!title) {
                // Try h1 fallback
                const h1Match = html.match(/<h1[^>]*>([^<]+)<\/h1>/);
                if (!h1Match) {
                    log.warning(`[BS] No title found: ${url}`);
                    return;
                }
            }
            
            const finalTitle = title || html.match(/<h1[^>]*>([^<]+)<\/h1>/)?.[1] || '';
            if (!finalTitle) return;

            totalFound += 1;

            const { year, make, model } = parseVehicleTitle(finalTitle);
            
            // Get state: try auctionCity from dataLayer first, then userData
            const auctionCity = data.auctionCity || request.userData?.auctionCity || '';
            const auctionCountry = data.auctionCountry || request.userData?.auctionCountry || '';
            
            let state = null;
            if (auctionCountry === 'United States' || auctionCountry === 'US') {
                state = parseStateFromCity(auctionCity)
                    ?? parseState(auctionCity)
                    ?? request.userData?.state
                    ?? null;
            }
            
            // Opening price as current bid proxy
            const openingPrice = parseBid(data.openingPrice || '0');
            const auctionEndDate = parseDate(data.lotEndsFrom || '');
            const mileage = extractMileage(html);
            const imageUrl = extractImageUrl(html);

            const listing = buildFallbackListing(request, {
                lotName: finalTitle,
                openingPrice,
                lotEndsFrom: auctionEndDate,
                auctionCity,
                imageUrl: imageUrl || null,
            });
            listing.year = year ?? listing.year;
            listing.make = make ?? listing.make;
            listing.model = model ?? listing.model;
            listing.mileage = mileage ?? listing.mileage;
            listing.state = state ?? listing.state;
            listing.current_bid = openingPrice || listing.current_bid || 0;
            listing.auction_end_date = auctionEndDate || listing.auction_end_date;
            listing.image_url = imageUrl || listing.image_url || null;

            if (!applyFilters(listing, log)) return;

            if (seenListings.has(listing.listing_id)) return;
            seenListings.add(listing.listing_id);

            totalAfterFilters += 1;
            log.info(`[BS] ✓ ${listing.year} ${listing.make} ${listing.model} | $${listing.current_bid} | ${listing.state || 'US'} | ${finalTitle.slice(0, 50)}`);
            await Actor.pushData(listing);
            return;
        }

        // ── Catalogue page — enumerate lots ───────────────────────────────────
        if (label === 'CATALOGUE') {
            const url = request.url;
            
            // Check for WAF challenge
            if (html.includes('awswaf.com') && html.length < 5000) {
                cataloguesSkippedWAF++;
                log.warning(`[BS] WAF challenge on catalogue: ${url}`);
                return;
            }

            // Extract catalogue metadata from dataLayer
            const data = extractDataLayer(html);
            const auctionCountry = data.auctionCountry || '';
            const auctionCity = data.auctionCity || '';
            const catalogueName = data.catalogueName || '';

            // CRITICAL FILTER: Only process US auctions
            if (auctionCountry && auctionCountry !== 'United States') {
                cataloguesSkippedNonUS++;
                log.info(`[BS] Skip non-US catalogue: ${auctionCountry} | ${catalogueName}`);
                return;
            }

            cataloguesProcessed++;
            log.info(`[BS] Catalogue: ${catalogueName || url} | ${auctionCity}`);

            // Get state from city
            const state = parseStateFromCity(auctionCity) ?? parseState(auctionCity);

            // Extract lot links
            const lotLinks = extractLotLinks(html);
            log.info(`[BS] Catalogue has ${lotLinks.length} lot links`);

            // Extract card-level titles for pre-filtering
            const cardTitles = extractLotCards(html);
            const cardBids = extractCatalogueBidByIndex(html);

            for (let i = 0; i < lotLinks.length; i++) {
                const lotUrl = `${BASE_URL}${lotLinks[i]}`;
                const cardTitle = cardTitles[i] || '';
                const cardBid = cardBids[i] || 0;
                
                // Pre-filter from card text
                const { year: cardYear, make: cardMake } = parseVehicleTitle(cardTitle);
                if (cardTitle && !cardMake && !isVehicleLot(cardTitle)) {
                    log.debug(`[BS] Pre-filter non-vehicle: ${cardTitle.slice(0, 60)}`);
                    continue;
                }
                if (cardYear && cardYear < minYear) {
                    log.debug(`[BS] Pre-filter old year ${cardYear}: ${cardTitle.slice(0, 60)}`);
                    continue;
                }

                await crawler.requestQueue.addRequest({
                    url: lotUrl,
                    uniqueKey: lotLinks[i],
                    label: 'LOT',
                    headers: buildDetailHeaders(DETAIL_UA_ROTATION[0]),
                    userData: { 
                        auctionCity,
                        auctionCountry,
                        state,
                        catalogueName,
                        detailAttempt: 0,
                        cardTitle,
                        cardBid,
                        fallbackListing: {
                            title: cardTitle,
                            year: cardYear,
                            make: cardMake,
                            model: parseVehicleTitle(cardTitle).model,
                            current_bid: cardBid,
                            state,
                            listing_url: lotUrl,
                        },
                    },
                });
            }

            // Pagination
            const pageMatch = url.match(/[?&]page=(\d+)/);
            const currentPage = pageMatch ? parseInt(pageMatch[1]) : 1;
            if (lotLinks.length >= 58) {
                // Likely more pages
                const nextPage = currentPage + 1;
                const baseUrl = url.replace(/[?&]page=\d+/, '');
                const sep = baseUrl.includes('?') ? '&' : '?';
                const nextUrl = `${baseUrl}${sep}page=${nextPage}`;
                await crawler.requestQueue.addRequest({
                    url: nextUrl,
                    label: 'CATALOGUE',
                    headers: BROWSER_HEADERS,
                    userData: { auctionCity, auctionCountry, state, catalogueName },
                });
            }
            return;
        }

        // ── Catalogue list page ───────────────────────────────────────────────
        const pageNum = request.userData?.pageNum ?? 1;
        log.info(`[BS] Catalogue list page ${pageNum}: ${request.url}`);

        const catalogueLinks = extractCatalogueLinks(html);
        log.info(`[BS] Found ${catalogueLinks.length} catalogue links`);

        if (!catalogueLinks.length && pageNum === 1) {
            log.warning('[BS] No catalogue links found on list page');
            return;
        }

        // Enqueue catalogues (up to maxCatalogues)
        let enqueued = 0;
        for (const catPath of catalogueLinks) {
            if (enqueued >= maxCatalogues) break;
            const catUrl = `${BASE_URL}${catPath}`;
            await crawler.requestQueue.addRequest({
                url: catUrl,
                label: 'CATALOGUE',
                headers: BROWSER_HEADERS,
            });
            enqueued++;
        }

        // Paginate catalogue list
        if (catalogueLinks.length >= 55 && pageNum < maxPages) {
            const nextUrl = `${BASE_URL}/en-us/auction-catalogues/search-filter?categorytags=Automobiles%2c+Trucks+%26+Vans&country=US&page=${pageNum + 1}`;
            await crawler.requestQueue.addRequest({
                url: nextUrl,
                label: 'CATALOGUE_LIST',
                headers: BROWSER_HEADERS,
                userData: { pageNum: pageNum + 1 },
            });
        }
    },

    async failedRequestHandler({ request, log }) {
        log.error(`[BS] Request failed after retries: ${request.url}`);
    },
});

const startUrl = `${BASE_URL}/en-us/auction-catalogues/search-filter?categorytags=Automobiles%2c+Trucks+%26+Vans&country=US`;
await crawler.run([{
    url: startUrl,
    label: 'CATALOGUE_LIST',
    headers: BROWSER_HEADERS,
    userData: { pageNum: 1 },
}]);

console.log(`[BIDSPOTTER COMPLETE] Found: ${totalFound} | Passed filters: ${totalAfterFilters}`);
console.log(`[BIDSPOTTER STATS] Catalogues processed: ${cataloguesProcessed} | Skipped non-US: ${cataloguesSkippedNonUS} | Skipped WAF: ${cataloguesSkippedWAF}`);
await Actor.exit();
# deploy Tue Mar 24 23:57:03 PDT 2026
# Wed Mar 25 00:01:36 PDT 2026
