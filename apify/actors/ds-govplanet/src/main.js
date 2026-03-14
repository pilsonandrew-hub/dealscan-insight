/**
 * ds-govplanet — GovPlanet Automotive Scraper
 *
 * GovPlanet (govplanet.com) is a Ritchie Bros government surplus auction site.
 * It is JS-rendered (React/Next.js) but scrapeable — no Cloudflare/403.
 *
 * Strategy:
 *   1. Load each category URL with PlaywrightCrawler
 *   2. Intercept ALL JSON responses looking for lot/vehicle arrays
 *   3. Capture the search API URL and paginate via direct API calls
 *      (page.goto on API URL — avoids CORS, response still intercepted)
 *   4. Filter and push results
 *
 * Category URLs:
 *   https://www.govplanet.com/Passenger+Vehicles
 *   https://www.govplanet.com/Trucks
 *   https://www.govplanet.com/en/govplanet-trucks  (variation)
 */

import { Actor } from 'apify';
import { PlaywrightCrawler } from 'crawlee';

/* ── Constants ──────────────────────────────────────────────── */

const SOURCE = 'govplanet';
const BASE   = 'https://www.govplanet.com';

const CATEGORY_URLS = [
    `${BASE}/Passenger+Vehicles`,
    `${BASE}/Trucks`,
];

// Fallback URL variations to try if category pages yield nothing
const FALLBACK_URLS = [
    `${BASE}/en/govplanet-trucks`,
    `${BASE}/en/passenger-vehicles`,
    `${BASE}/for-sale/Trucks`,
    `${BASE}/for-sale/Passenger+Vehicles`,
];

const HIGH_RUST = new Set([
    'OH','MI','PA','NY','WI','MN','IL','IN','MO','IA',
    'ND','SD','NE','KS','WV','ME','NH','VT','MA','RI',
    'CT','NJ','MD','DE',
]);

const US_STATES = new Set([
    'AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA','HI','ID','IL','IN','IA',
    'KS','KY','LA','ME','MD','MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ',
    'NM','NY','NC','ND','OH','OK','OR','PA','RI','SC','SD','TN','TX','UT','VT',
    'VA','WA','WV','WI','WY','DC',
]);

const COMMERCIAL_PATTERN = /\b(cargo van|cargo truck|cutaway|chassis cab|box truck|stake bed|dump truck|flatbed|refuse|crane truck|utility body|work van|transit connect cargo|sprinter cargo|step van|panel van|ambulance|fire truck|bucket truck|aerial lift|sewer|sweeper|plow truck)\b/i;

const MAKES = new Set([
    'ford','chevrolet','chevy','dodge','ram','toyota','honda','nissan','jeep','gmc',
    'chrysler','hyundai','kia','subaru','mazda','volkswagen','vw','bmw','mercedes',
    'audi','lexus','acura','infiniti','cadillac','lincoln','buick','pontiac',
    'mitsubishi','volvo','tesla','saturn','isuzu','hummer','land rover','mini',
]);

/* ── Actor boot ─────────────────────────────────────────────── */

await Actor.init();

const input = await Actor.getInput() ?? {};
const {
    maxPages = 10,
    minBid   = 500,
    maxBid   = 35000,
} = input;

const CURRENT_YEAR = new Date().getFullYear();
let totalFound = 0;
let totalPassed = 0;

/* ── Helpers ─────────────────────────────────────────────────── */

function parseBid(raw) {
    if (typeof raw === 'number') return raw;
    const s = String(raw ?? '').replace(/,/g, '').replace(/\$/g, '');
    const m = s.match(/[\d.]+/);
    return m ? parseFloat(m[0]) : 0;
}

function extractYear(text = '') {
    const m = String(text).match(/\b(19[89]\d|20[0-3]\d)\b/);
    return m ? parseInt(m[1], 10) : null;
}

function extractState(text = '') {
    // "City, ST" or "City, ST 12345" or standalone "TX"
    const m = String(text).match(/,\s*([A-Z]{2})\s*(?:\d{5})?(?:\s|$)/)
           || String(text).match(/\b([A-Z]{2})\b\s*\d{5}/)
           || String(text).match(/\b([A-Z]{2})\b\s*$/);
    return m ? m[1].toUpperCase() : '';
}

function extractCity(location = '') {
    const m = String(location).match(/^([^,]+),/);
    return m ? m[1].trim() : '';
}

function extractMake(title = '') {
    const lower = title.toLowerCase();
    for (const mk of MAKES) {
        if (new RegExp(`\\b${mk.replace(/ /g,'\\s+')}\\b`).test(lower)) {
            const canonical = { chevy: 'Chevrolet', vw: 'Volkswagen' };
            return canonical[mk] ?? (mk.charAt(0).toUpperCase() + mk.slice(1));
        }
    }
    return null;
}

function extractModel(title = '', make = '') {
    if (!make) return null;
    const lowerTitle = title.toLowerCase();
    const lowerMake  = make.toLowerCase();
    const idx = lowerTitle.indexOf(lowerMake);
    if (idx === -1) return null;
    const after = title.slice(idx + make.length).trim();
    // Strip leading year
    const clean = after.replace(/^(19|20)\d{2}\s+/, '').trim();
    // Take first 1-2 words; strip trailing color names
    const COLOR_STRIP = /\b(black|white|silver|gray|grey|red|blue|green|yellow|orange|brown|beige|tan|gold|maroon|charcoal|navy|cream|burgundy|pearl)\b.*/i;
    const word_match = clean.match(/^([A-Za-z0-9][-A-Za-z0-9]*(?:\s+[A-Za-z0-9][-A-Za-z0-9]*)?)/);
    return word_match ? word_match[1].replace(COLOR_STRIP, '').trim() : null;
}

/**
 * Walk a JSON object/array looking for arrays that look like lot lists.
 * Returns the best candidate array found.
 */
function findLotsArray(json) {
    if (!json || typeof json !== 'object') return [];

    // Direct well-known keys
    const KEYS = [
        'items','lots','results','data','listings','assets','records',
        'vehicles','auctions','searchResults','auctionItems','content',
        'hits','documents','products',
    ];

    for (const key of KEYS) {
        const val = json[key];
        if (Array.isArray(val) && val.length > 0 && isLotArray(val)) return val;
    }

    // One level deep in data/response/payload wrappers
    const WRAPPERS = ['data','response','payload','result','body'];
    for (const wrap of WRAPPERS) {
        if (json[wrap] && typeof json[wrap] === 'object') {
            for (const key of KEYS) {
                const val = json[wrap][key];
                if (Array.isArray(val) && val.length > 0 && isLotArray(val)) return val;
            }
        }
    }

    // Root array
    if (Array.isArray(json) && json.length > 0 && isLotArray(json)) return json;

    return [];
}

/** Heuristic: does this array look like lot/listing objects? */
function isLotArray(arr) {
    if (!arr.length) return false;
    const sample = arr[0];
    if (typeof sample !== 'object' || !sample) return false;
    // Must have at least one field that suggests it's a lot/listing
    const keys = Object.keys(sample).join(' ').toLowerCase();
    return /lot|item|title|name|bid|price|auction|listing|vehicle|make|model|year/.test(keys);
}

/**
 * Normalize a raw lot object into our output schema.
 * GovPlanet/Ritchie Bros lots tend to have fields like:
 *   lotId, title, makeModel, year, currentBidAmount, location, stateCode,
 *   lotDetailUrl, primaryImageUrl, vin, meterHours, meterReading
 */
function normalizeLot(lot) {
    // Title
    const title = lot.title || lot.name || lot.description
               || [lot.year, lot.make, lot.model].filter(Boolean).join(' ')
               || '';

    // Year
    const year = lot.year
              ?? lot.modelYear
              ?? extractYear(lot.title || lot.name || '');

    // Make / Model
    const make  = lot.make  || lot.manufacturerName || lot.manufacturer || extractMake(title);
    const model = lot.model || lot.modelName        || extractModel(title, make || '');

    // Bid
    const bid = parseBid(
        lot.currentBidAmount  ?? lot.currentBid ?? lot.current_bid
     ?? lot.price             ?? lot.amount     ?? lot.bidAmount
     ?? lot.startingBid       ?? 0
    );

    // Location / State
    const locationRaw = lot.location || lot.city || lot.address || lot.saleLocation || '';
    const stateRaw    = lot.stateCode || lot.state || lot.stateAbbr || lot.province || '';
    const state       = (stateRaw || extractState(locationRaw)).toUpperCase().slice(0, 2);
    const city        = lot.city || lot.cityName || extractCity(locationRaw);

    // URL
    let listingUrl = lot.lotDetailUrl || lot.url || lot.lotUrl || lot.detailUrl || lot.link || '';
    if (listingUrl && !listingUrl.startsWith('http')) {
        listingUrl = `${BASE}${listingUrl.startsWith('/') ? '' : '/'}${listingUrl}`;
    }

    // Photo
    const photo = lot.primaryImageUrl || lot.imageUrl || lot.photoUrl
               || lot.image           || lot.thumbnailUrl
               || (Array.isArray(lot.images) ? lot.images[0]?.url ?? lot.images[0] : '')
               || '';

    // VIN / Mileage
    const vin     = lot.vin || lot.vinNumber || lot.serialNumber || '';
    const mileage = parseBid(
        lot.meterReading ?? lot.mileage ?? lot.odometer
     ?? lot.meterHours   ?? lot.hours   ?? null
    ) || null;

    return { title, year, make, model, bid, state, city, listingUrl, photo, vin, mileage };
}

function passesFilters({ title, year, bid, state, mileage }) {
    // US states only
    if (!US_STATES.has(state)) return false;
    // No high-rust states
    if (HIGH_RUST.has(state)) return false;
    // Year >= 2014 (no older than 12 years)
    if (year && (CURRENT_YEAR - year) > 12) return false;
    if (year && year < 1980) return false; // sanity: reject parse errors
    // Bid range
    if (bid < minBid || bid > maxBid) return false;
    // No commercial vehicles
    if (COMMERCIAL_PATTERN.test(title)) return false;
    return true;
}

/* ── Main crawl ──────────────────────────────────────────────── */

const crawler = new PlaywrightCrawler({
    // One session per category — we handle pagination inside the handler
    maxRequestsPerCrawl: CATEGORY_URLS.length + 5,
    requestHandlerTimeoutSecs: 300,
    launchContext: {
        launchOptions: {
            args: [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
            ],
        },
    },

    async requestHandler({ page, request, log }) {
        const startUrl = request.url;
        log.info(`[GOVPLANET] Loading: ${startUrl}`);

        // ── Intercept setup ────────────────────────────────────
        const capturedApiUrls = [];  // API URLs that returned lots
        const allLots = [];

        function registerPageIntercept(pg, tag) {
            pg.on('response', async (response) => {
                const url = response.url();
                const ct  = (response.headers()['content-type'] || '').toLowerCase();

                // Only JSON
                if (!ct.includes('json')) return;

                // Skip noise: analytics, tracking, config, fonts, auth
                if (/analytics|tracking|segment|gtm|amplitude|hotjar|mixpanel|sentry|rollbar|logrocket/.test(url)) return;
                if (/\/auth\/|\/oauth\/|\/config$|\/health$|\/favicon/.test(url)) return;

                try {
                    const body = await response.json().catch(() => null);
                    if (!body) return;

                    const lots = findLotsArray(body);
                    if (lots.length > 0) {
                        log.info(`[${tag}] Intercepted ${lots.length} lots from: ${url}`);
                        allLots.push(...lots);
                        if (!capturedApiUrls.includes(url)) {
                            capturedApiUrls.push(url);
                        }
                    }
                } catch (_) { /* ignore parse errors */ }
            });
        }

        registerPageIntercept(page, 'P1');

        // ── Navigate to category ───────────────────────────────
        await page.goto(startUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });

        // Wait for JS to fire API calls (GovPlanet is React/Next.js)
        await page.waitForTimeout(8000);

        // If no lots yet, wait for network to settle
        if (allLots.length === 0) {
            log.info('[GOVPLANET] No lots on first load — waiting for dynamic content...');
            await page.waitForTimeout(5000);
        }

        // ── Fallback: try alternate category URLs ──────────────
        if (allLots.length === 0 && startUrl === CATEGORY_URLS[0]) {
            log.info('[GOVPLANET] Trying fallback URLs...');
            for (const fallbackUrl of FALLBACK_URLS) {
                await page.goto(fallbackUrl, { waitUntil: 'domcontentloaded', timeout: 30000 })
                    .catch(() => {});
                await page.waitForTimeout(5000);
                if (allLots.length > 0) {
                    log.info(`[GOVPLANET] Got lots from fallback: ${fallbackUrl}`);
                    break;
                }
            }
        }

        // ── DOM fallback: scrape visible lot cards ─────────────
        if (allLots.length === 0) {
            log.info('[GOVPLANET] API intercept empty — attempting DOM scrape');
            const domLots = await page.evaluate(() => {
                const results = [];
                // GovPlanet uses card patterns like .lot-card, [data-lot-id], etc.
                const CARD_SELECTORS = [
                    '[data-lot-id]',
                    '[class*="lot-card"]',
                    '[class*="LotCard"]',
                    '[class*="item-card"]',
                    '[class*="ItemCard"]',
                    '[class*="listing-card"]',
                    '[class*="ListingCard"]',
                    '[class*="search-result"]',
                    'article[class*="lot"]',
                    'li[class*="lot"]',
                ];
                let cards = [];
                for (const sel of CARD_SELECTORS) {
                    const found = document.querySelectorAll(sel);
                    if (found.length > 0) { cards = Array.from(found); break; }
                }

                for (const card of cards) {
                    const titleEl  = card.querySelector('h2, h3, h4, [class*="title"], [class*="Title"]');
                    const priceEl  = card.querySelector('[class*="bid"], [class*="Bid"], [class*="price"], [class*="Price"]');
                    const locEl    = card.querySelector('[class*="location"], [class*="Location"]');
                    const linkEl   = card.querySelector('a[href]');
                    const imgEl    = card.querySelector('img');

                    const title = titleEl?.textContent?.trim() || '';
                    const priceText = priceEl?.textContent?.replace(/[^0-9.]/g, '') || '0';
                    const location  = locEl?.textContent?.trim() || '';
                    const href      = linkEl?.href || '';
                    const img       = imgEl?.src || imgEl?.dataset?.src || '';
                    const lotId     = card.dataset?.lotId || card.dataset?.id || '';

                    if (title || priceText !== '0') {
                        results.push({
                            title,
                            currentBidAmount: parseFloat(priceText) || 0,
                            location,
                            lotDetailUrl: href,
                            primaryImageUrl: img,
                            lotId,
                        });
                    }
                }
                return results;
            });

            if (domLots.length > 0) {
                log.info(`[GOVPLANET] DOM scrape found ${domLots.length} lots`);
                allLots.push(...domLots);
            } else {
                log.warning('[GOVPLANET] DOM scrape also empty — page may require login or different URL');
            }
        }

        log.info(`[GOVPLANET] Page 1 total intercepted: ${allLots.length} lots`);

        // ── Pagination ─────────────────────────────────────────
        // Detect the search API URL and paginate by modifying page/offset params
        const searchApiBase = capturedApiUrls.find(u =>
            /search|listing|lot|inventory|result|browse/i.test(u)
        ) || capturedApiUrls[0];

        if (searchApiBase && maxPages > 1) {
            log.info(`[GOVPLANET] Paginating from: ${searchApiBase}`);

            for (let pageNum = 2; pageNum <= maxPages; pageNum++) {
                const pageLots = [];

                // Register per-page intercept
                const onResponse = async (response) => {
                    const url = response.url();
                    const ct  = (response.headers()['content-type'] || '').toLowerCase();
                    if (!ct.includes('json')) return;
                    try {
                        const body = await response.json().catch(() => null);
                        if (!body) return;
                        const lots = findLotsArray(body);
                        if (lots.length > 0) {
                            log.info(`[P${pageNum}] ${lots.length} lots from: ${url}`);
                            pageLots.push(...lots);
                        }
                    } catch (_) { /* ignore */ }
                };
                page.on('response', onResponse);

                // Build paged URL — try common pagination param patterns
                const nextUrl = buildPagedUrl(searchApiBase, pageNum);
                log.info(`[GOVPLANET] Fetching page ${pageNum}: ${nextUrl}`);
                await page.goto(nextUrl, { waitUntil: 'domcontentloaded', timeout: 45000 })
                    .catch(() => {});
                await page.waitForTimeout(4000);

                page.off('response', onResponse);

                if (pageLots.length === 0) {
                    log.info(`[GOVPLANET] Page ${pageNum}: 0 lots — stopping pagination`);
                    break;
                }

                allLots.push(...pageLots);
                await page.waitForTimeout(1000);
            }
        } else if (capturedApiUrls.length === 0 && maxPages > 1) {
            // No API URL captured — try paginating via category URL query param
            log.info('[GOVPLANET] No API URL — paginating via category URL with ?page=N');
            for (let pageNum = 2; pageNum <= maxPages; pageNum++) {
                const pageLots = [];

                const onResponse = async (response) => {
                    const url = response.url();
                    const ct  = (response.headers()['content-type'] || '').toLowerCase();
                    if (!ct.includes('json')) return;
                    try {
                        const body = await response.json().catch(() => null);
                        if (!body) return;
                        const lots = findLotsArray(body);
                        if (lots.length > 0) pageLots.push(...lots);
                    } catch (_) { /* ignore */ }
                };
                page.on('response', onResponse);

                const sep = startUrl.includes('?') ? '&' : '?';
                const nextUrl = `${startUrl}${sep}page=${pageNum}`;
                await page.goto(nextUrl, { waitUntil: 'domcontentloaded', timeout: 45000 })
                    .catch(() => {});
                await page.waitForTimeout(5000);

                page.off('response', onResponse);

                if (pageLots.length === 0) {
                    log.info(`[GOVPLANET] Category page ${pageNum}: 0 lots — stopping`);
                    break;
                }

                allLots.push(...pageLots);
                await page.waitForTimeout(1000);
            }
        }

        // ── Filter & push ──────────────────────────────────────
        const seen = new Set();
        for (const raw of allLots) {
            const { title, year, make, model, bid, state, city, listingUrl, photo, vin, mileage } = normalizeLot(raw);

            // Dedup by listing URL or title+bid
            const key = listingUrl || `${title}::${bid}`;
            if (seen.has(key)) continue;
            seen.add(key);

            totalFound++;

            if (!passesFilters({ title, year, bid, state, mileage })) continue;

            totalPassed++;
            await Actor.pushData({
                title,
                year,
                make,
                model,
                current_bid:  bid,
                state,
                city,
                listing_url:  listingUrl,
                photo_url:    photo,
                vin,
                mileage,
                source_site:  SOURCE,
                scraped_at:   new Date().toISOString(),
            });
        }

        log.info(`[GOVPLANET] Category done — Found: ${totalFound} | Passed: ${totalPassed}`);
    },
});

/* ── URL pagination helper ───────────────────────────────────── */

function buildPagedUrl(base, pageNum) {
    try {
        const u = new URL(base);
        // Try common page/offset params in priority order
        if (u.searchParams.has('page')) {
            u.searchParams.set('page', pageNum);
        } else if (u.searchParams.has('p')) {
            u.searchParams.set('p', pageNum);
        } else if (u.searchParams.has('offset')) {
            const size = parseInt(u.searchParams.get('size') || u.searchParams.get('limit') || '24', 10);
            u.searchParams.set('offset', (pageNum - 1) * size);
        } else if (u.searchParams.has('start')) {
            const size = parseInt(u.searchParams.get('rows') || u.searchParams.get('size') || '24', 10);
            u.searchParams.set('start', (pageNum - 1) * size);
        } else if (u.searchParams.has('from')) {
            const size = parseInt(u.searchParams.get('size') || '24', 10);
            u.searchParams.set('from', (pageNum - 1) * size);
        } else {
            // Default: append page param
            u.searchParams.set('page', pageNum);
        }
        return u.toString();
    } catch (_) {
        // Not a full URL (relative path or malformed) — append page param
        const sep = base.includes('?') ? '&' : '?';
        return `${base}${sep}page=${pageNum}`;
    }
}

/* ── Run ─────────────────────────────────────────────────────── */

await crawler.run(CATEGORY_URLS.map(url => ({ url })));

console.log(`[GOVPLANET] Found: ${totalFound} | Passed: ${totalPassed}`);
await Actor.exit();
