/**
 * PublicSurplus scraper with VIN extraction.
 *
 * VIN extraction strategy:
 * 1. TX titles already embed VIN (regex extracted in parseTXSurplusTitle)
 * 2. Standard listings: regex VIN scan over title + description
 * 3. Fallback: visit detail page and regex over full page text
 *    - Capped at MAX_DETAIL_PAGES (200) per run, ~1 req/sec
 */

import { Actor } from 'apify';
import { PlaywrightCrawler } from 'crawlee';

const MAX_DETAIL_PAGES = 200;

const TARGET_STATES = new Set([
    'AZ', 'CA', 'NV', 'CO', 'NM', 'UT', 'TX', 'FL', 'GA', 'SC', 'TN', 'NC', 'VA', 'WA', 'OR', 'HI',
]);

const HIGH_RUST_STATES = new Set([
    'OH', 'MI', 'PA', 'NY', 'WI', 'MN', 'IL', 'IN', 'MO', 'IA',
    'ND', 'SD', 'NE', 'KS', 'WV', 'ME', 'NH', 'VT', 'MA', 'RI',
    'CT', 'NJ', 'MD', 'DE',
]);

const VEHICLE_KEYWORDS = ['car', 'truck', 'suv', 'van', 'pickup', 'sedan', 'coupe', 'wagon', 'vehicle', 'automobile', 'motor', '4wd', 'awd', 'hybrid'];
const VEHICLE_MAKES = ['ford', 'chevrolet', 'chevy', 'dodge', 'ram', 'toyota', 'honda', 'nissan', 'jeep', 'gmc', 'chrysler',
    'hyundai', 'kia', 'subaru', 'mazda', 'volkswagen', 'vw', 'bmw', 'mercedes', 'audi', 'lexus', 'acura', 'infiniti',
    'cadillac', 'lincoln', 'buick', 'pontiac', 'mitsubishi', 'volvo', 'tesla', 'saturn', 'isuzu', 'hummer',
    'rivian', 'lucid', 'genesis'];
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

const BASE_URL = 'https://www.publicsurplus.com';
// 'all' = nationwide search across all agencies (not just WA)
const BASE_LIST_URL_TEMPLATE = `${BASE_URL}/sms/all/browse/cataucs?catid=4&page={PAGE}`;

// Texas General Land Office surplus — mobile site with JS pagination
const TX_SURPLUS_BASE = 'https://m.publicsurplus.com/sms/state,tx/list/current?orgid=871876';
const TX_SURPLUS_DETAIL_BASE = 'https://m.publicsurplus.com';

// VIN pattern: 17 alphanumeric chars, no I/O/Q
const VIN_PATTERN = /\b([A-HJ-NPR-Z0-9]{17})\b/i;

await Actor.init();

const input = await Actor.getInput() ?? {};
const {
    maxPages = 5,
    minBid = 500,
    maxBid = 35000,
    targetStates = [...TARGET_STATES],
    maxTXPages = 10,
    searchQuery = "",
} = input;

const BASE_LIST_URL = searchQuery
    ? `${BASE_LIST_URL_TEMPLATE}&kw=${encodeURIComponent(searchQuery)}`
    : BASE_LIST_URL_TEMPLATE;

const targetStateSet = new Set(targetStates.map((state) => state.toUpperCase()));
const effectiveMaxPages = Math.max(1, Math.min(maxPages, 3));
const seenListings = new Set();

let totalFound = 0;
let totalAfterFilters = 0;

function normalizeText(value) {
    return String(value ?? '')
        .replace(/\u00a0/g, ' ')
        .replace(/[ \t]+/g, ' ')
        .replace(/\s*\n\s*/g, '\n')
        .trim();
}

function isVehicle(title) {
    const lower = normalizeText(title).toLowerCase();
    if (CONDITION_REJECT_PATTERNS.some((pattern) => pattern.test(lower))) return false;
    return VEHICLE_KEYWORDS.some((keyword) => lower.includes(keyword))
        || VEHICLE_MAKES.some((make) => lower.includes(make));
}

function parseMoney(value) {
    const match = normalizeText(value).match(/\$?([\d,]+(?:\.\d+)?)/);
    return match ? parseFloat(match[1].replace(/,/g, '')) : 0;
}

function parseTitleStatus(text = '') {
    const normalized = normalizeText(text).toLowerCase();
    const damageKeywords = [
        ['frame damage', 'frame damage'],
        ['salvage', 'salvage'],
        ['rebuilt', 'rebuilt'],
        ['flood', 'flood'],
        ['lemon', 'lemon'],
    ];

    for (const [keyword, label] of damageKeywords) {
        if (normalized.includes(keyword)) return label;
    }

    if (normalized.includes('clean title')) return 'clean';
    if (normalized.includes('title')) return 'clean';

    return 'unknown';
}

// Canonical make list for normalization (lower-case keys → display name)
const MAKE_CANONICAL = {
    'ford': 'Ford', 'chevrolet': 'Chevrolet', 'chevy': 'Chevrolet',
    'toyota': 'Toyota', 'honda': 'Honda', 'nissan': 'Nissan',
    'dodge': 'Dodge', 'ram': 'RAM', 'jeep': 'Jeep', 'gmc': 'GMC',
    'chrysler': 'Chrysler', 'hyundai': 'Hyundai', 'kia': 'Kia',
    'subaru': 'Subaru', 'mazda': 'Mazda', 'bmw': 'BMW',
    'mercedes': 'Mercedes', 'audi': 'Audi', 'lexus': 'Lexus',
    'acura': 'Acura', 'infiniti': 'Infiniti', 'cadillac': 'Cadillac',
    'lincoln': 'Lincoln', 'buick': 'Buick', 'pontiac': 'Pontiac',
    'mitsubishi': 'Mitsubishi', 'volvo': 'Volvo', 'tesla': 'Tesla',
    'saturn': 'Saturn', 'isuzu': 'Isuzu', 'hummer': 'Hummer',
    'volkswagen': 'Volkswagen', 'vw': 'Volkswagen',
    'rivian': 'Rivian', 'lucid': 'Lucid', 'genesis': 'Genesis',
};

/**
 * Parse a PublicSurplus auction title into year/make/model.
 * Handles formats like:
 *   "2. 2017 Ford Explorer"
 *   "6. Two (2) 2005 CHEVY TAHOES"
 *   "ADOT - CF57 - 2013 FORD F250 P/U 3/4 TON"
 *   "(APD-184) 2019 Dodge Charger"
 */
function parseVehicleTitle(rawTitle) {
    let title = normalizeText(rawTitle);

    // 1. Strip leading number/dot: "2. " or "12. "
    title = title.replace(/^\d+\.\s*/, '');

    // 2. Strip agency prefix patterns:
    //    "ADOT - CF57 - "  (AGENCY - CODE - )
    //    "(APD-184) "       (parens code)
    title = title.replace(/^[A-Z0-9 ]{2,10}\s*-\s*[A-Z0-9 ]{2,10}\s*-\s*/i, '');
    title = title.replace(/^\([^)]{1,20}\)\s*/i, '');
    title = normalizeText(title);

    // 3. Extract year 1990–2026
    const yearMatch = title.match(/\b(199\d|200\d|201\d|202[0-6])\b/);
    const year = yearMatch ? parseInt(yearMatch[1], 10) : null;

    // 4 & 5. Extract make and model
    let make = null;
    let model = null;
    const lowerTitle = title.toLowerCase();

    for (const lowerMake of Object.keys(MAKE_CANONICAL)) {
        const idx = lowerTitle.indexOf(lowerMake);
        if (idx === -1) continue;
        // Ensure word boundary before and after to avoid partial matches (e.g. "ford" in "afford")
        const before = idx === 0 || /\W/.test(lowerTitle[idx - 1]);
        const after = idx + lowerMake.length >= lowerTitle.length || /\W/.test(lowerTitle[idx + lowerMake.length]);
        if (!before || !after) continue;

        make = MAKE_CANONICAL[lowerMake];
        const afterMake = title.slice(idx + lowerMake.length).trim();
        // Strip trailing color words from model
        const COLOR_WORDS = /\b(black|white|silver|gray|grey|red|blue|green|yellow|orange|brown|beige|tan|gold|maroon|purple|pink|copper|charcoal|navy|cream|ivory|burgundy|champagne|bronze)\b.*/i;
        const rawModel = afterMake.match(/^([A-Za-z0-9/-]+(?:\s+[A-Za-z0-9/-]+)?)/);
        if (rawModel) model = rawModel[1].trim().replace(COLOR_WORDS, '').trim();
        break;
    }

    return { year, make, model };
}

/**
 * Parse Texas surplus title format:
 * "2015 FORD F150 EXT CAB SB 4X4 1FTFX1EF7FKD99057"
 * Returns { year, make, model, vin }
 */
function parseTXSurplusTitle(rawTitle) {
    const title = normalizeText(rawTitle);

    // Extract VIN (17-char alphanumeric, no I/O/Q) — usually the last token
    const vinMatch = title.match(VIN_PATTERN);
    const vin = vinMatch ? vinMatch[1].toUpperCase() : null;

    // Strip VIN from title before parsing year/make/model
    const titleWithoutVin = vin ? title.replace(vin, '').trim() : title;

    const { year, make, model } = parseVehicleTitle(titleWithoutVin);

    return { year, make, model, vin };
}

function parseAuctionDate(value) {
    const normalized = normalizeText(value);
    if (!normalized) return null;

    const parsed = new Date(normalized);
    return Number.isNaN(parsed.getTime()) ? normalized : parsed.toISOString();
}

function parseState(location) {
    const normalized = normalizeText(location);
    if (!normalized) return null;

    const match = normalized.match(/,\s*([A-Z]{2})\b/)
        || normalized.match(/\b([A-Z]{2})\s*\d{5}/)
        || normalized.match(/\b([A-Z]{2})\b$/);

    return match ? match[1].toUpperCase() : null;
}

function parseMileage(text = '') {
    const match = normalizeText(text).replace(/,/g, '').match(/\b(\d{1,3}(?:\d{3})+|\d+)\s*(?:miles?|mi\.?)\b/i);
    return match ? parseInt(match[1], 10) : null;
}

// Queue of passing standard listings that need VIN detail-page scraping
const vinQueue = [];
let detailPageCount = 0;

/**
 * Extract VIN via regex from combined title + description text.
 * Returns null if not found.
 */
function extractVinFromText(text) {
    const match = String(text || '').match(VIN_PATTERN);
    return match ? match[1].toUpperCase() : null;
}

async function pushListing(listing, sourceUrl, log) {
    const title = normalizeText(listing.title);
    const description = normalizeText(listing.description);
    const currentBid = parseMoney(listing.currentBid);
    const location = normalizeText(listing.location);
    const state = parseState(location) || null;
    const mileage = parseMileage([title, description].filter(Boolean).join(' '));

    if (!title) {
        log.debug(`[SKIP] Missing title on ${sourceUrl}`);
        return false;
    }
    if (CONDITION_REJECT_PATTERNS.some((pattern) => pattern.test(`${title} ${description}`.toLowerCase()))) {
        log.debug(`[SKIP] Condition reject: ${title}`);
        return false;
    }
    if (!isVehicle(title)) {
        log.debug(`[SKIP] Not a vehicle: ${title}`);
        return false;
    }
    const { year, make, model } = parseVehicleTitle(title);

    if (HIGH_RUST_STATES.has(state)) {
        const currentYear = new Date().getFullYear();
        if (year && year >= currentYear - 2) {
            log.info(`[BYPASS] Rust state ${state} allowed — vehicle is ${year} (≤3yr old)`);
        } else {
            log.debug(`[SKIP] High-rust state: ${state} - ${title}`);
            return false;
        }
    }
    if (!targetStateSet.has(state)) {
        log.debug(`[SKIP] Out-of-target state: ${state} - ${title}`);
        return false;
    }
    if (currentBid < minBid || currentBid > maxBid) {
        log.debug(`[SKIP] Out-of-range bid $${currentBid} - ${title}`);
        return false;
    }
    const currentYear = new Date().getFullYear();
    const age = currentYear - year;
    if (!year || age > 10 || age < 0) {
        log.debug(`[SKIP] Too old or unknown year: ${year} - ${title}`);
        return false;
    }
    if (mileage !== null && mileage > 100000) {
        log.debug(`[SKIP] Too many miles: ${mileage} - ${title}`);
        return false;
    }

    const listingUrl = normalizeText(listing.listingUrl) || sourceUrl;
    const dedupeKey = listingUrl || `${title}-${state}-${currentBid}`;
    if (seenListings.has(dedupeKey)) {
        return false;
    }
    seenListings.add(dedupeKey);

    // Try extracting VIN from title + description text first
    const vinFromText = extractVinFromText([title, description].join(' '));

    const vehicle = {
        title,
        year,
        make,
        model,
        vin: vinFromText || null,
        current_bid: currentBid,
        buyer_premium: 0.10,
        doc_fee: 50,
        auction_end_time: parseAuctionDate(listing.endDate),
        location,
        state,
        mileage,
        listing_url: listingUrl,
        item_number: normalizeText(listing.itemNumber),
        photo_url: normalizeText(listing.photoUrl) || null,
        description: description || null,
        title_status: parseTitleStatus([title, description].filter(Boolean).join(' ')),
        agency_name: normalizeText(listing.agencyName),
        source_site: 'publicsurplus',
        scraped_at: new Date().toISOString(),
    };

    totalAfterFilters++;
    log.info(`[PASS] ${vehicle.title} | $${vehicle.current_bid} | ${vehicle.state} | VIN: ${vehicle.vin || 'pending'}`);

    // If no VIN found yet and we have a detail URL, queue for detail page scrape
    if (!vehicle.vin && listingUrl && detailPageCount < MAX_DETAIL_PAGES) {
        vinQueue.push(vehicle);
    } else {
        await Actor.pushData(vehicle);
    }
    return true;
}

/**
 * Push a Texas State Surplus listing. Bypasses state/rust filters since we
 * explicitly target TX and the data is pre-parsed.
 */
async function pushTXListing(listing, sourceUrl, log) {
    const title = normalizeText(listing.title);
    const currentBid = parseMoney(listing.currentBid);

    if (!title) {
        log.debug(`[TX][SKIP] Missing title on ${sourceUrl}`);
        return false;
    }
    if (CONDITION_REJECT_PATTERNS.some((pattern) => pattern.test(title.toLowerCase()))) {
        log.debug(`[TX][SKIP] Condition reject: ${title}`);
        return false;
    }
    if (!isVehicle(title)) {
        log.debug(`[TX][SKIP] Not a vehicle: ${title}`);
        return false;
    }
    if (currentBid !== 0 && (currentBid < minBid || currentBid > maxBid)) {
        log.debug(`[TX][SKIP] Out-of-range bid $${currentBid} - ${title}`);
        return false;
    }

    const listingUrl = normalizeText(listing.listingUrl) || sourceUrl;
    const dedupeKey = listingUrl || `${title}-TX-${currentBid}`;
    if (seenListings.has(dedupeKey)) {
        return false;
    }
    seenListings.add(dedupeKey);

    const { year, make, model, vin } = parseTXSurplusTitle(title);
    const mileage = parseMileage(title);
    const currentYear = new Date().getFullYear();
    const age = currentYear - year;
    if (!year || age > 10 || age < 0) {
        log.debug(`[TX][SKIP] Too old or unknown year: ${year} - ${title}`);
        return false;
    }
    if (mileage !== null && mileage > 100000) {
        log.debug(`[TX][SKIP] Too many miles: ${mileage} - ${title}`);
        return false;
    }

    const vehicle = {
        title,
        year,
        make,
        model,
        vin: vin || null,
        current_bid: currentBid,
        buyer_premium: 0.10,
        doc_fee: 50,
        auction_end_time: normalizeText(listing.timeLeft) || null,
        location: 'Texas',
        location_state: 'TX',
        state: 'TX',
        listing_url: listingUrl,
        item_number: normalizeText(listing.itemNumber) || null,
        photo_url: normalizeText(listing.photoUrl) || null,
        description: null,
        title_status: parseTitleStatus(title),
        agency_name: 'Texas General Land Office',
        auction_source: 'Texas State Surplus',
        source_site: 'publicsurplus_tx',
        mileage,
        scraped_at: new Date().toISOString(),
    };

    totalAfterFilters++;
    log.info(`[TX][PASS] ${vehicle.title} | $${vehicle.current_bid} | VIN: ${vehicle.vin}`);
    await Actor.pushData(vehicle);
    return true;
}

const crawler = new PlaywrightCrawler({
    launchContext: {
        launchOptions: {
            headless: true,
        },
    },
    maxRequestsPerCrawl: effectiveMaxPages + maxTXPages + MAX_DETAIL_PAGES + 5,
    navigationTimeoutSecs: 60,
    requestHandlerTimeoutSecs: 120,
    maxConcurrency: 2,
    minConcurrency: 1,

    async requestHandler({ page, request, enqueueLinks, log }) {
        // ── PublicSurplus detail page — extract VIN ────────────────────────────
        if (request.label === 'DETAIL_VIN') {
            const vehicle = request.userData.vehicle;
            try {
                await page.waitForLoadState('domcontentloaded', { timeout: 20000 }).catch(() => {});
                await page.waitForTimeout(1000);
                const bodyText = await page.evaluate(() => document.body.innerText || document.body.textContent || '');
                const vin = extractVinFromText(bodyText);
                if (vin) {
                    vehicle.vin = vin;
                    log.info(`[VIN DETAIL] Found VIN ${vin} for: ${vehicle.title}`);
                }
            } catch (err) {
                log.warning(`[VIN DETAIL] Failed for ${request.url}: ${err.message}`);
            }
            await Actor.pushData(vehicle);
            return;
        }
        // ── Texas State Surplus (mobile site) ──────────────────────────────────
        if (request.label === 'TX_LIST') {
            const currentPage = request.userData?.pageNum ?? 1;
            log.info(`[TX Surplus] Processing page ${currentPage}: ${request.url}`);

            await page.waitForLoadState('networkidle', { timeout: 20000 }).catch(() => {});
            await page.waitForTimeout(1500);

            const txListings = await page.evaluate((detailBase) => {
                const normalizeText = (value) => String(value ?? '')
                    .replace(/\u00a0/g, ' ')
                    .replace(/[ \t]+/g, ' ')
                    .replace(/\s*\n\s*/g, '\n')
                    .trim();

                const results = [];
                const seen = new Set();

                // Mobile site uses anchor tags linking to auction/view?auc=
                const lotLinks = Array.from(document.querySelectorAll('a[href*="auction/view?auc="]'));

                for (const link of lotLinks) {
                    const href = link.getAttribute('href') || '';
                    const listingUrl = href.startsWith('http') ? href : `${detailBase}${href}`;
                    if (seen.has(listingUrl)) continue;
                    seen.add(listingUrl);

                    // Title is the text content of the link
                    const title = normalizeText(link.textContent);

                    // Walk up to find the parent row/card container for price + time
                    const container = link.closest('tr, .lot-row, .auction-row, li, div[class*="lot"], div[class*="item"]') || link.parentElement;
                    const containerText = container ? normalizeText(container.textContent) : '';

                    // Extract current bid — look for $ pattern
                    const bidMatch = containerText.match(/\$\s*([\d,]+(?:\.\d+)?)/);
                    const currentBid = bidMatch ? bidMatch[0] : '0';

                    // Extract time left — "Xd Xh" or "X days" pattern
                    const timeMatch = containerText.match(/(\d+\s*d[ay]*\s*\d*\s*h(?:r|ours?)?|\d+\s*h(?:rs?|ours?)\s*\d*\s*m(?:in)?|Ended|Closed)/i);
                    const timeLeft = timeMatch ? timeMatch[0] : '';

                    // Photo
                    const img = container ? container.querySelector('img') : null;
                    const photoUrl = img ? (img.getAttribute('src') || img.getAttribute('data-src') || '') : '';

                    // Item number from URL auc param
                    const aucMatch = href.match(/auc=(\d+)/);
                    const itemNumber = aucMatch ? aucMatch[1] : '';

                    if (title) {
                        results.push({ title, currentBid, timeLeft, listingUrl, photoUrl, itemNumber });
                    }
                }

                return results;
            }, TX_SURPLUS_DETAIL_BASE);

            totalFound += txListings.length;
            log.info(`[TX Surplus] Found ${txListings.length} listings on page ${currentPage}`);

            for (const listing of txListings) {
                await pushTXListing(listing, request.url, log);
            }

            // Pagination: try clicking "Next" link (javascript:srchPage('N'))
            // or look for a link with text "Next" / ">>"
            if (txListings.length > 0 && currentPage < maxTXPages) {
                try {
                    // Try to find "Next" pagination link
                    const nextLink = await page.$('a[href*="srchPage"][href*="N"], a:text("Next"), a:text(">>"), a:has-text("Next Page")');
                    if (nextLink) {
                        const nextHref = await nextLink.getAttribute('href');
                        log.info(`[TX Surplus] Found Next link: ${nextHref}`);

                        if (nextHref && nextHref.includes('javascript')) {
                            // Click JS pagination link and wait for navigation/reload
                            await Promise.all([
                                page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {}),
                                nextLink.click(),
                            ]);
                            await page.waitForTimeout(2000);
                            const newUrl = page.url();
                            log.info(`[TX Surplus] Navigated to: ${newUrl}`);
                            await enqueueLinks({
                                urls: [newUrl],
                                label: 'TX_LIST',
                                userData: { pageNum: currentPage + 1 },
                            });
                        } else if (nextHref) {
                            const absUrl = nextHref.startsWith('http') ? nextHref : `${TX_SURPLUS_DETAIL_BASE}${nextHref}`;
                            await enqueueLinks({
                                urls: [absUrl],
                                label: 'TX_LIST',
                                userData: { pageNum: currentPage + 1 },
                            });
                        }
                    } else {
                        log.info(`[TX Surplus] No Next link found — end of results at page ${currentPage}`);
                    }
                } catch (err) {
                    log.warning(`[TX Surplus] Pagination error on page ${currentPage}: ${err.message}`);
                }
            }

            return;
        }

        // ── Standard PublicSurplus (desktop site) ──────────────────────────────
        const currentPage = request.userData?.pageNum ?? 1;
        log.info(`[PublicSurplus] Processing index page ${currentPage}: ${request.url}`);

        await page.waitForSelector('#auctionTableView, table.auction-list, table, body', { timeout: 30000 });
        await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});
        await page.waitForTimeout(1500);

        const listings = await page.evaluate(() => {
            const normalizeText = (value) => String(value ?? '')
                .replace(/\u00a0/g, ' ')
                .replace(/[ \t]+/g, ' ')
                .replace(/\s*\n\s*/g, '\n')
                .trim();

            const tableSelectors = ['#auctionTableView tr', 'table.auction-list tr', 'table tr'];
            const rows = [];
            const seen = new Set();

            const findFromCells = (cells, matcher) => cells.find((cell) => matcher(cell)) || '';

            for (const selector of tableSelectors) {
                for (const row of Array.from(document.querySelectorAll(selector))) {
                    const titleLink = row.querySelector('a[href*="/auction/view?auc="], a[href*="view?auc="]');
                    if (!titleLink) continue;

                    const href = titleLink.getAttribute('href') || '';
                    const listingUrl = href ? new URL(href, window.location.href).toString() : '';
                    const dedupeKey = listingUrl || normalizeText(titleLink.textContent);
                    if (!dedupeKey || seen.has(dedupeKey)) continue;
                    seen.add(dedupeKey);

                    const cells = Array.from(row.querySelectorAll('td')).map((cell) => normalizeText(cell.textContent));
                    const photo = row.querySelector('img');
                    const title = normalizeText(titleLink.textContent);
                    const currentBid = normalizeText(row.querySelector('td[id^="val_"]')?.textContent)
                        || findFromCells(cells, (cell) => /\$\s*\d/.test(cell));
                    const location = normalizeText(row.querySelector('td.text-success.fw-bold, .text-success, [class*="location"]')?.textContent)
                        || findFromCells(cells, (cell) => /,\s*[A-Z]{2}\b/.test(cell) || /\bWA\b/.test(cell));
                    const endDate = normalizeText(row.querySelector('.auction-time_left span, [id^="timeLeftValue"], time')?.textContent)
                        || findFromCells(cells, (cell) => /\d{1,2}\/\d{1,2}\/\d{2,4}/.test(cell) || /\b(?:AM|PM)\b/i.test(cell) || /days|hrs|mins/i.test(cell));
                    const agencyName = findFromCells(cells, (cell) => /county|city|school|district|port|state|police|public works|transport/i.test(cell));
                    const itemNumber = normalizeText(row.querySelector('td:first-child')?.textContent) || cells[0] || '';

                    rows.push({
                        itemNumber,
                        title,
                        currentBid,
                        location,
                        endDate,
                        listingUrl,
                        photoUrl: photo?.getAttribute('src') || photo?.getAttribute('data-src') || '',
                        agencyName,
                    });
                }

                if (rows.length > 0) break;
            }

            return rows;
        });

        totalFound += listings.length;
        log.info(`[PublicSurplus] Found ${listings.length} listing rows on page ${currentPage}`);

        for (const listing of listings) {
            await pushListing(listing, request.url, log);
        }

        if (listings.length > 0 && currentPage < effectiveMaxPages) {
            const nextPageUrl = BASE_LIST_URL.replace('{PAGE}', String(currentPage + 1));
            await enqueueLinks({
                urls: [nextPageUrl],
                label: 'LIST',
                userData: { pageNum: currentPage + 1 },
            });
        }
    },
});

const startUrl = BASE_LIST_URL.replace('{PAGE}', '1');
await crawler.run([
    { url: startUrl, label: 'LIST', userData: { pageNum: 1 } },
    { url: TX_SURPLUS_BASE, label: 'TX_LIST', userData: { pageNum: 1 } },
]);

// ── VIN enrichment: visit detail pages for listings without a VIN ──────────
if (vinQueue.length > 0) {
    console.log(`[PUBLICSURPLUS] Enriching VINs: ${vinQueue.length} detail pages to visit`);
    const detailRequests = vinQueue.map((vehicle) => ({
        url: vehicle.listing_url,
        label: 'DETAIL_VIN',
        userData: { vehicle },
    }));
    await crawler.run(detailRequests);
} else {
    console.log('[PUBLICSURPLUS] No VIN detail pages needed (all VINs found inline or no passing lots)');
}

console.log(`[PUBLICSURPLUS COMPLETE] Found: ${totalFound} | Passed filters: ${totalAfterFilters}`);

await Actor.exit();
