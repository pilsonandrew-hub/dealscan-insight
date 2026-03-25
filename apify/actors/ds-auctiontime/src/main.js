/**
 * ds-auctiontime — AuctionTime (Sandhills Publishing) Scraper
 *
 * STATUS: BLOCKED + NOT_RELEVANT
 *
 * Bot protection (2026-03-13):
 * - All URLs return HTTP 403 Forbidden — Distil Networks (now Imperva) protection is active.
 * - No content returned to inspect for API patterns.
 * - No public REST or RSS API found.
 *
 * Content relevance:
 * - AuctionTime is a Sandhills Publishing platform primarily focused on AGRICULTURAL
 *   and CONSTRUCTION equipment (tractors, combines, harvesters, plows, grain carts, etc.).
 * - Passenger vehicle and consumer truck listings are a very small minority.
 * - NOT a viable source for the DealerScope passenger vehicle arbitrage use case.
 *
 * Recommendation: DEPRIORITIZE. Even if bot protection were bypassed, the vehicle-to-noise
 * ratio would be too low to justify the effort.
 */

import { Actor } from 'apify';
import { CheerioCrawler } from 'crawlee';

const SOURCE = 'auctiontime';

const BASE = 'https://www.auctiontime.com';

const TARGET_STATES = new Set([
    'AZ','CA','NV','CO','NM','UT','TX','FL','GA','SC','TN','NC','VA','WA','OR','HI'
]);

const HIGH_RUST_STATES = new Set([
    'OH','MI','PA','NY','WI','MN','IL','IN','MO','IA',
    'ND','SD','NE','KS','WV','ME','NH','VT','MA','RI',
    'CT','NJ','MD','DE'
]);

// AuctionTime (Sandhills) focuses on trucks, trailers, and commercial vehicles
const TRUCK_KEYWORDS = ['truck','pickup','semi','tractor','flatbed','dump','box truck','utility truck',
    'service truck','crew cab','extended cab','regular cab','4x4','diesel','f-150','f-250','f-350',
    'silverado','sierra','ram 1500','ram 2500','ram 3500','tundra','tacoma','ranger','colorado','canyon'];
const TRAILER_KEYWORDS = ['trailer','flatbed trailer','utility trailer','cargo trailer','enclosed trailer',
    'dump trailer','equipment trailer','gooseneck','lowboy'];
const VEHICLE_KEYWORDS = ['car','suv','van','vehicle','automobile','4wd','awd','hybrid',
    ...TRUCK_KEYWORDS, ...TRAILER_KEYWORDS];
const VEHICLE_MAKES = ['ford','chevrolet','chevy','dodge','ram','toyota','honda','nissan','jeep','gmc','chrysler',
    'hyundai','kia','subaru','mazda','volkswagen','vw','bmw','mercedes','audi','lexus','acura','infiniti',
    'cadillac','lincoln','buick','pontiac','mitsubishi','volvo','tesla','freightliner','kenworth','peterbilt',
    'mack','international','navistar','isuzu','hino','mitsubishi fuso'];

// Exclude farm equipment / non-vehicle categories
const EXCLUDE_KEYWORDS = ['tractor farm','combine','harvester','planter','cultivator','plow','tillage',
    'grain cart','hay baler','sprayer farm','corn head','header','auger','irrigation'];

const SEARCH_URLS = [
    `${BASE}/listings/pickup-trucks`,
    `${BASE}/listings/search?q=truck`,
    `${BASE}/listings/search?q=trailer`,
    `${BASE}/listings/pickup-trucks?sort=newest`,
];

const LISTING_SELECTORS = [
    '.listing-card a',
    '.result-item a',
    'a.listing-link',
    '.vehicle-card a',
    'a[href*="/listing/for-sale/"]',
    'a[href*="/listing/upcoming-auctions/"]',
    'a[href*="/listing/auction-results/"]',
];

await Actor.init();

const input = await Actor.getInput() ?? {};
const {
    maxPages = 20,
    minBid = 3000,
    maxBid = 35000,
    maxMileage = 50000,
    minYear = 2022,
    targetStates = [...TARGET_STATES],
} = input;

const targetStateSet = new Set(targetStates.map(s => s.toUpperCase()));
const allListings = [];
let totalFound = 0;
let totalAfterFilters = 0;
let totalFailedFilters = 0;

function toAbsoluteUrl(href) {
    if (!href) return '';
    return href.startsWith('http') ? href : `${BASE}${href}`;
}

function isDetailListingUrl(url) {
    try {
        const { pathname } = new URL(url);
        if (!pathname.startsWith('/listing/')) return false;
        return /\/for-sale\//i.test(pathname) || /\/\d+\/?$/i.test(pathname);
    } catch {
        return false;
    }
}

function isCommercialVehicle(title) {
    const lower = title.toLowerCase();
    // Reject farm equipment
    if (EXCLUDE_KEYWORDS.some(kw => lower.includes(kw))) return false;
    return VEHICLE_KEYWORDS.some(kw => lower.includes(kw)) ||
           VEHICLE_MAKES.some(make => lower.includes(make));
}

function parseVehicleTitle(title) {
    const yearMatch = title.match(/\b(20\d{2}|19[89]\d)\b/);
    const year = yearMatch ? parseInt(yearMatch[1]) : null;

    let make = null;
    let model = null;
    const lower = title.toLowerCase();

    for (const m of VEHICLE_MAKES) {
        if (lower.includes(m)) {
            make = m.charAt(0).toUpperCase() + m.slice(1);
            if (make === 'Chevy') make = 'Chevrolet';
            if (make === 'Vw') make = 'Volkswagen';
            const makeIdx = lower.indexOf(m);
            const afterMake = title.slice(makeIdx + m.length).trim();
            const modelMatch = afterMake.match(/^([A-Za-z0-9\-]+(?:\s+[A-Za-z0-9\-]+)?)/);
            if (modelMatch) model = modelMatch[1].trim();
            break;
        }
    }

    return { year, make, model };
}

function parseState(text) {
    if (!text) return null;
    const match = text.match(/,\s*([A-Z]{2})\b/) ||
                  text.match(/\b([A-Z]{2})\s*\d{5}/) ||
                  text.match(/\b([A-Z]{2})\b/);
    return match ? match[1].toUpperCase() : null;
}

function parseBid(text) {
    if (!text) return 0;
    const match = String(text).replace(/,/g, '').match(/[\d]+\.?\d*/);
    return match ? parseFloat(match[0]) : 0;
}

function parseDate(text) {
    if (!text) return null;
    try {
        const d = new Date(text);
        if (!isNaN(d.getTime())) return d.toISOString();
    } catch {}
    return null;
}

function parseMileage(text) {
    if (!text) return null;
    const match = text.replace(/,/g, '').match(/(\d+)\s*(?:miles?|mi\.?|hrs?|hours?)/i);
    if (match) return parseInt(match[1]);
    return null;
}

function normalizeText(text) {
    return String(text || '').replace(/\s+/g, ' ').trim();
}

function readLabelFromBody(bodyText, labelRegex) {
    const match = bodyText.match(new RegExp(`${labelRegex.source}\\s*([^\\n]+)`, labelRegex.flags));
    return match ? normalizeText(match[1]) : '';
}

function applyFilters(listing, log) {
    if (!isCommercialVehicle(listing.title)) {
        log.debug(`[SKIP] Not a commercial vehicle: ${listing.title}`);
        totalFailedFilters++;
        return false;
    }
    const state = listing.state;
    if (state && HIGH_RUST_STATES.has(state)) {
        const currentYear = new Date().getFullYear();
        const bypassYear = currentYear - 2; // vehicles newer than 2 years bypass rust filter
        if (listing.year != null && listing.year >= bypassYear) {
            log.info(`[BYPASS] Rust state ${state} allowed — vehicle is ${listing.year} (≤2yr old, bypass >= ${bypassYear})`);
        } else {
            // null year OR old vehicle in rust state — reject
            log.debug(`[SKIP] High-rust state: ${state} — ${listing.title}`);
            totalFailedFilters++;
            return false;
        }
    }
    if (state && !targetStateSet.has(state)) {
        log.debug(`[SKIP] Out-of-target state: ${state}`);
        totalFailedFilters++;
        return false;
    }
    if (listing.current_bid > 0 && listing.current_bid < minBid) {
        log.debug(`[SKIP] Bid too low: $${listing.current_bid}`);
        totalFailedFilters++;
        return false;
    }
    if (listing.current_bid > 0 && listing.current_bid > maxBid) {
        log.debug(`[SKIP] Bid too high: $${listing.current_bid}`);
        totalFailedFilters++;
        return false;
    }
    if (listing.year && listing.year < minYear) {
        log.debug(`[SKIP] Too old: ${listing.year}`);
        totalFailedFilters++;
        return false;
    }
    if (listing.mileage && listing.mileage > maxMileage) {
        log.debug(`[SKIP] Too many miles: ${listing.mileage}`);
        totalFailedFilters++;
        return false;
    }
    return true;
}

const crawler = new CheerioCrawler({
    maxRequestsPerCrawl: maxPages * 3 + 50,
    requestHandlerTimeoutSecs: 60,
    maxConcurrency: 2,
    minConcurrency: 1,

    async requestHandler({ $, request, enqueueLinks, log }) {
        const url = request.url;
        log.info(`[AuctionTime] Processing: ${url}`);

        if (request.label === 'DETAIL') {
            await handleDetailPage($, request, log);
            return;
        }

        // LIST page — AuctionTime lot links follow Sandhills listing patterns.
        const listingLinks = [];

        for (const selector of LISTING_SELECTORS) {
            $(selector).each((_, el) => {
                const href = $(el).attr('href');
                const abs = toAbsoluteUrl(href);
                if (!abs || abs.includes('#') || abs === url) return;
                if (isDetailListingUrl(abs)) listingLinks.push(abs);
            });
        }

        const uniqueLinks = [...new Set(listingLinks)];
        log.info(`Found ${uniqueLinks.length} detail links on page`);
        totalFound += uniqueLinks.length;

        if (uniqueLinks.length > 0) {
            await enqueueLinks({
                urls: uniqueLinks,
                label: 'DETAIL',
            });
        }

        // Pagination
        const currentPage = request.userData?.pageNum ?? 1;
        if (currentPage < maxPages) {
            const nextHref = $('a[rel="next"], [class*="pagination"] a[class*="next"], a[aria-label*="Next"]').attr('href');
            if (nextHref) {
                const nextAbs = toAbsoluteUrl(nextHref);
                await enqueueLinks({
                    urls: [nextAbs],
                    label: 'LIST',
                    userData: { pageNum: currentPage + 1 },
                });
            } else if (uniqueLinks.length > 0) {
                const nextUrl = new URL(url);
                nextUrl.searchParams.set('page', currentPage + 1);
                await enqueueLinks({
                    urls: [nextUrl.toString()],
                    label: 'LIST',
                    userData: { pageNum: currentPage + 1 },
                });
            }
        }
    },
});

async function handleDetailPage($, request, log) {
    const bodyText = normalizeText($('body').text());
    const title = $('h1').first().text().trim() ||
        $('meta[property="og:title"]').attr('content') ||
        $('title').text().split('|')[0].trim();

    if (!title) {
        log.debug(`[SKIP] No title: ${request.url}`);
        return;
    }

    // Current bid
    let bidText = '';
    for (const sel of ['.current-bid', '[class*="current-bid"]', '[class*="high-bid"]',
                        '[class*="current-price"]', '.bid-amount', '[class*="bid-value"]',
                        '[class*="asking-price"]']) {
        const t = $(sel).first().text().trim();
        if (t) { bidText = t; break; }
    }
    if (!bidText) {
        bidText = readLabelFromBody(bodyText, /current\s*bid:|high\s*bid:|asking\s*price:|reserve\s*price:/i);
    }
    const bid = parseBid(bidText);

    // Location
    let location = '';
    for (const sel of ['[class*="location"]', '.listing-location', '[class*="city"]',
                        '.equipment-location', '[class*="address"]', '[class*="state"]']) {
        const t = $(sel).first().text().trim();
        if (t) { location = t; break; }
    }
    if (!location) {
        location = readLabelFromBody(bodyText, /machine\s*location:|location:/i);
    }

    // End date
    let endText = '';
    for (const sel of ['[class*="end-time"]', '[class*="closes"]', '[data-end]',
                        '.auction-end', '.close-date', '[class*="end-date"]', 'time[datetime]']) {
        const el = $(sel).first();
        endText = el.attr('data-end') || el.attr('datetime') || el.text().trim();
        if (endText) break;
    }
    if (!endText) {
        endText = readLabelFromBody(bodyText, /auction\s*date:|closing\s*date:|ends?:/i);
    }

    // Image
    const imgEl = $('img.listing-image, img.equipment-photo, [class*="main-image"] img, .gallery img, [class*="primary-photo"] img').first();
    const imageUrl = $('meta[property="og:image"]').attr('content') || imgEl.attr('data-src') || imgEl.attr('src') || null;

    // Mileage / hours from specs table or description
    let mileage = null;
    const specsText = normalizeText($('[class*="specs"], [class*="details"], .listing-details, table').text());
    const descText = normalizeText($('[class*="description"], #description, .listing-description').text());
    const combinedText = `${specsText} ${descText} ${bodyText}`;

    const mileageMatch = combinedText.match(/(\d[\d,]+)\s*(?:miles?|mi\.?)\b/i);
    if (mileageMatch) mileage = parseInt(mileageMatch[1].replace(/,/g, ''));

    // VIN
    const vinMatch = combinedText.match(/\bVIN[:\s#]*([A-HJ-NPR-Z0-9]{17})\b/i) ||
                     combinedText.match(/\b([A-HJ-NPR-Z0-9]{17})\b/);
    const vin = vinMatch ? vinMatch[1] : null;

    // ID from URL
    const idMatch = request.url.match(/\/listings\/[a-z\-]+\/([a-z0-9\-]+)$/i) ||
                    request.url.match(/\/listings\/(\d+)/) ||
                    request.url.match(/\/(?:listing|item|lot)\/([a-z0-9\-]+)/i);
    const itemId = idMatch ? `auctiontime-${idMatch[1]}` : `auctiontime-${Date.now()}`;

    const state = parseState(location);
    const { year, make, model } = parseVehicleTitle(title);

    const listing = {
        listing_id: itemId,
        title,
        current_bid: bid,
        buy_now_price: null,
        auction_end_date: parseDate(endText),
        state,
        listing_url: request.url,
        image_url: imageUrl,
        mileage,
        vin,
        year,
        make,
        model,
        source: SOURCE,
        scraped_at: new Date().toISOString(),
    };

    if (!applyFilters(listing, log)) return;

    totalAfterFilters++;
    log.info(`[PASS] ${listing.title} | $${listing.current_bid} | ${listing.state}`);
    allListings.push(listing);
    await Actor.pushData(listing);
}

const log = { info: console.log, debug: () => {}, error: console.error };

await crawler.run(
    SEARCH_URLS.map((url, i) => ({
        url,
        label: 'LIST',
        userData: { pageNum: 1 },
        uniqueKey: `list-start-${i}`,
    }))
);

console.log(`[AUCTIONTIME COMPLETE] Found: ${totalFound} | Passed filters: ${totalAfterFilters} | Failed filters: ${totalFailedFilters}`);

await Actor.exit();
