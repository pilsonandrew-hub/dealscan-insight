/**
 * ds-usgovbid — USGovBid Impound Vehicle Auction Scraper
 *
 * STATUS: WORKING — Playwright (required for dynamic bid values)
 *
 * Architecture:
 *   USGovBid uses two layers:
 *   1. usgovbid.com/auctions/ — WordPress + The Events Calendar plugin
 *      → Public REST API: /wp-json/tribe/events/v1/events (returns auction events w/ venue/state)
 *   2. bid.auctionlistservices.com (ALS/Global Auction Platform) — individual lot pages
 *      → Lots are server-rendered in HTML (no AJAX auth required)
 *      → Bid values loaded dynamically but title/URL/image are in static HTML
 *
 * Strategy:
 *   1. Fetch upcoming auction events via WordPress REST API
 *   2. For each auction: crawl event page to find bid.auctionlistservices.com link
 *   3. Load auction catalog page in Playwright to get dynamic bid values
 *   4. Parse lot cards: title, current bid, end date, lot URL, photo
 *   5. Filter for vehicles, apply rust-state and bid-range filters
 *   6. Push normalized records to Apify dataset
 *
 * Note: USGovBid typically lists 1–5 active auctions with 20–200 lots each.
 * Vehicle lots are clearly labeled. Each auction covers a single government
 * agency (county sheriff, state surplus, etc.).
 */

import { Actor } from 'apify';
import { PlaywrightCrawler } from 'crawlee';

const SOURCE = 'usgovbid';
const WP_EVENTS_API = 'https://www.usgovbid.com/wp-json/tribe/events/v1/events?per_page=50&status=publish';
const BID_BASE = 'https://bid.auctionlistservices.com';

const HIGH_RUST_STATES = new Set([
    'OH', 'MI', 'PA', 'NY', 'WI', 'MN', 'IL', 'IN', 'MO', 'IA',
    'ND', 'SD', 'NE', 'KS', 'WV', 'ME', 'NH', 'VT', 'MA', 'RI',
    'CT', 'NJ', 'MD', 'DE',
]);

const US_STATES = new Set([
    'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA', 'HI', 'ID', 'IL', 'IN', 'IA',
    'KS', 'KY', 'LA', 'ME', 'MD', 'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
    'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC', 'SD', 'TN', 'TX', 'UT', 'VT',
    'VA', 'WA', 'WV', 'WI', 'WY', 'DC',
]);

const VEHICLE_KEYWORDS = [
    'car', 'truck', 'suv', 'van', 'pickup', 'sedan', 'coupe', 'wagon', 'vehicle',
    'automobile', '4wd', 'awd', 'hybrid', 'patrol', 'cruiser',
];

const VEHICLE_MAKES = new Set([
    'ford', 'chevrolet', 'chevy', 'dodge', 'ram', 'toyota', 'honda', 'nissan', 'jeep', 'gmc',
    'chrysler', 'hyundai', 'kia', 'subaru', 'mazda', 'volkswagen', 'vw', 'bmw', 'mercedes',
    'audi', 'lexus', 'acura', 'infiniti', 'cadillac', 'lincoln', 'buick', 'pontiac',
    'mitsubishi', 'volvo', 'tesla', 'saturn', 'isuzu', 'hummer', 'rivian', 'genesis',
    'land rover', 'mini', 'jaguar', 'porsche',
]);

const NON_VEHICLE_PATTERNS = /\b(motorcycle|atv|utv|boat|trailer|forklift|loader|backhoe|excavator|mower|tractor|jet ski|snowmobile|golf cart|bicycle|computer|furniture|equipment)\b/i;

await Actor.init();
const input = await Actor.getInput() ?? {};
const {
    maxAuctions = 10,
    maxLotsPerAuction = 500,
    minBid = 500,
    maxBid = 35000,
} = input;

let totalFound = 0;
let totalPassed = 0;

// ── Helpers ──────────────────────────────────────────────────────────────────

function normalizeText(v) {
    return String(v ?? '').replace(/\s+/g, ' ').trim();
}

function parseBid(v) {
    const text = normalizeText(v).replace(/,/g, '');
    const m = text.match(/\$?\s*([\d]+(?:\.\d+)?)/);
    return m ? parseFloat(m[1]) : 0;
}

function parseYear(title = '') {
    const m = normalizeText(title).match(/\b(19[89]\d|20[0-3]\d)\b/);
    return m ? parseInt(m[1], 10) : null;
}

function parseMake(title = '') {
    const lower = normalizeText(title).toLowerCase();
    for (const make of VEHICLE_MAKES) {
        if (new RegExp(`\\b${make.replace(/\s+/g, '\\s+')}\\b`).test(lower)) {
            if (make === 'chevy') return 'Chevrolet';
            if (make === 'vw') return 'Volkswagen';
            return make.replace(/\b\w/g, c => c.toUpperCase());
        }
    }
    return null;
}

function parseModel(title = '', make = '') {
    if (!make) return null;
    const t = normalizeText(title);
    const m = new RegExp(`\\b${make.replace(/\s+/g, '\\s+')}\\b`, 'i').exec(t);
    if (!m) return null;
    const afterMake = t.slice(m.index + m[0].length).replace(/^[\s\-:]+/, '');
    const mm = afterMake.match(/^([A-Za-z0-9][A-Za-z0-9\-]*(?:\s+[A-Za-z0-9][A-Za-z0-9\-]*)?)/);
    return mm ? mm[1] : null;
}

function isVehicle(title = '') {
    const lower = title.toLowerCase();
    if (NON_VEHICLE_PATTERNS.test(title)) return false;
    return VEHICLE_KEYWORDS.some(k => lower.includes(k)) ||
        [...VEHICLE_MAKES].some(m => new RegExp(`\\b${m}\\b`).test(lower));
}

function parseDate(v) {
    if (!v) return null;
    const text = normalizeText(v);
    const parsed = new Date(text);
    if (!isNaN(parsed.getTime())) return parsed.toISOString();
    return null;
}

/**
 * Parse lot cards from ALS (bid.auctionlistservices.com) auction catalog HTML.
 *
 * Card structure:
 *   <div class="card lot-list-item" id="lot-list-item-{uuid}" data-lot-id="{uuid}">
 *     <a href="/auctions/{id}/{ref}/lot-details/{uuid}">  ← lot URL + image
 *       <img class="lot-grid-image" src="...">
 *     </a>
 *     <div class="content lot-grid-content">
 *       <div class="meta lot-number">1A</div>
 *       <a class="header lot-grid-header" name="lot-title" href="...">TITLE</a>
 *       <div class="current-bid-value" data-current-bid="1234.0">1,234</div>
 *       ...
 *     </div>
 *   </div>
 */
function extractAuctionItems($, auctionEndDate) {
    const items = [];

    $('.lot-list-item').each((i, el) => {
        const $el = $(el);

        // Title
        const titleEl = $el.find('a[name="lot-title"], a.lot-grid-header').first();
        const title = normalizeText(titleEl.text() || titleEl.attr('title') || '');
        if (!title) return;

        // Lot URL — href is relative, prepend BID_BASE
        const href = titleEl.attr('href') || $el.find('a[href*="lot-details"]').first().attr('href') || '';
        const listing_url = href ? (href.startsWith('http') ? href : `${BID_BASE}${href}`) : '';

        // Current bid — prefer data-current-bid attribute (numeric, always present even if 0)
        const bidEl = $el.find('.current-bid-value').first();
        const bidAttr = bidEl.attr('data-current-bid');
        const current_bid = bidAttr !== undefined ? parseFloat(bidAttr) : parseBid(bidEl.text());

        // Photo
        const imgEl = $el.find('img.lot-grid-image').first();
        const photo_url = imgEl.attr('src') || imgEl.attr('data-zoom-src') || '';

        // Lot number
        const lot_num = normalizeText($el.find('.meta.lot-number').first().text());

        items.push({ title, listing_url, current_bid, auction_end_time: auctionEndDate, photo_url, lot_num });
    });

    return items;
}

// ── Fetch upcoming auctions from WP REST API ──────────────────────────────────

async function fetchUpcomingAuctions(log) {
    log.info(`Fetching upcoming auctions from WordPress Events API...`);
    const resp = await fetch(WP_EVENTS_API, {
        headers: { 'User-Agent': 'Mozilla/5.0 (compatible; DealerScope/1.0)' },
    });
    if (!resp.ok) {
        log.warning(`Events API returned ${resp.status}`);
        return [];
    }
    const data = await resp.json();
    const events = data.events || [];
    log.info(`Found ${events.length} upcoming auction event(s)`);

    return events.map(ev => {
        const venue = ev.venue || {};
        const state = (venue.stateprovince || '').toUpperCase();
        const city = venue.city || '';
        const location = [city, state].filter(Boolean).join(', ');

        // Try to extract bid.auctionlistservices.com URL from description
        const desc = ev.description || '';
        const bidMatch = desc.match(/href="(https?:\/\/bid\.auctionlistservices\.com[^"&]+)/);
        const auctionUrl = bidMatch
            ? bidMatch[1].replace(/&#038;/g, '&').replace(/&amp;/g, '&')
            : null;

        return {
            id: ev.id,
            title: normalizeText(ev.title?.replace(/<[^>]+>/g, '') || ''),
            state,
            location,
            city,
            end_date: ev.end_date || null,
            event_url: ev.url || '',
            bid_url: auctionUrl,
            photo_url: ev.image?.sizes?.medium?.url || ev.image?.url || '',
            seller: normalizeText(venue.venue || ''),
        };
    }).filter(Boolean);
}

// ── Main crawl ───────────────────────────────────────────────────────────────

const auctions = [];

const crawler = new PlaywrightCrawler({
    maxRequestsPerCrawl: 100,
    requestHandlerTimeoutSecs: 120,
    navigationTimeoutSecs: 60,
    browserPoolOptions: {
        useFingerprints: false,
    },
    async requestHandler({ page, request, log }) {
        const { auctionMeta } = request.userData;
        log.info(`Processing auction: ${auctionMeta.title} [${auctionMeta.state}] — ${request.url}`);

        // Wait for lot cards to render
        await page.waitForSelector('.lot-list-item', { timeout: 30000 }).catch(() => {
            log.warning(`No .lot-list-item found on ${request.url}`);
        });
        await page.waitForTimeout(2000);

        // Extract auction-level end date from the page header
        const auctionEndDate = await page.evaluate(() => {
            const saleDates = document.querySelectorAll('.sale-date');
            // Last .sale-date is usually the "ends from" date
            const last = saleDates[saleDates.length - 1];
            return last ? last.textContent.trim() : null;
        }).catch(() => null);

        const endDateIso = parseDate(auctionEndDate) || parseDate(auctionMeta.end_date);

        // Parse all lot pages (ALS shows ~60 lots per page; handle pagination)
        let allLots = [];
        let pageNum = 1;

        while (allLots.length < maxLotsPerAuction) {
            const html = await page.content();
            const cheerio = await import('cheerio');
            const $ = cheerio.load(html);
            const pageLots = extractAuctionItems($, endDateIso);
            log.info(`Page ${pageNum}: ${pageLots.length} lots parsed`);

            if (!pageLots.length) break;
            allLots = allLots.concat(pageLots);

            // Check for next page link
            const nextHref = await page.$eval(
                'a.item[data-page].next, .pagination a[rel="next"], a.next-page',
                el => el.href
            ).catch(() => null);

            if (!nextHref) break;
            await page.goto(nextHref, { waitUntil: 'domcontentloaded' });
            await page.waitForSelector('.lot-list-item', { timeout: 20000 }).catch(() => {});
            await page.waitForTimeout(1000);
            pageNum++;
        }

        log.info(`Auction ${auctionMeta.title}: ${allLots.length} lots total`);

        // ── Filter and push ──────────────────────────────────────────────────
        for (const lot of allLots) {
            totalFound++;
            const { title, listing_url, current_bid, auction_end_time, photo_url } = lot;

            if (!isVehicle(title)) continue;

            const state = auctionMeta.state;
            const year = parseYear(title);
            const currentYear = new Date().getFullYear();
            if (state && HIGH_RUST_STATES.has(state)) {
                if (!(year && year >= currentYear - 2)) continue;
                console.log(`[BYPASS] Rust state ${state} allowed — vehicle is ${year} (≤3yr old)`);
            }

            if (current_bid > 0 && (current_bid < minBid || current_bid > maxBid)) continue;

            if (year && (currentYear - year) > 12) continue;

            const make = parseMake(title);
            const model = parseModel(title, make);

            const record = {
                title,
                make: make || '',
                model: model || '',
                year,
                current_bid,
                state,
                location: auctionMeta.location || '',
                city: auctionMeta.city || '',
                auction_end_time: auction_end_time || auctionMeta.end_date || null,
                listing_url: listing_url || auctionMeta.event_url || '',
                photo_url: photo_url || auctionMeta.photo_url || '',
                agency_name: auctionMeta.seller || auctionMeta.title || '',
                source_site: SOURCE,
                scraped_at: new Date().toISOString(),
            };

            totalPassed++;
            await Actor.pushData(record);
        }
    },

    failedRequestHandler({ request, log, error }) {
        log.error(`Request ${request.url} failed: ${error.message}`);
    },
});

// ── Orchestrate ──────────────────────────────────────────────────────────────

let events = [];
try {
    events = await fetchUpcomingAuctions(console);
} catch (err) {
    console.error(`Failed to fetch events: ${err.message}`);
}

if (!events.length) {
    console.warn('[USGOVBID] No upcoming auctions found via Events API');
    await Actor.exit();
}

// Build request list — for each auction, find the ALS bid URL
const requests = [];
for (const auction of events.slice(0, maxAuctions)) {
    let bidUrl = auction.bid_url;

    if (!bidUrl) {
        console.log(`No direct bid URL for ${auction.title} — will crawl event page`);
        requests.push({
            url: auction.event_url,
            userData: { auctionMeta: auction, needsRedirect: true },
        });
        continue;
    }

    requests.push({
        url: bidUrl,
        userData: { auctionMeta: auction },
    });
}

// Pre-pass: resolve event pages → ALS bid URL
if (requests.some(r => r.userData.needsRedirect)) {
    const redirectCrawler = new PlaywrightCrawler({
        maxRequestsPerCrawl: 20,
        requestHandlerTimeoutSecs: 60,
        async requestHandler({ page, request, log }) {
            const { auctionMeta } = request.userData;
            log.info(`Resolving bid URL from event page: ${request.url}`);

            // Find bid.auctionlistservices.com link (current platform)
            const bidLink = await page.$eval(
                'a[href*="bid.auctionlistservices.com"]',
                el => el.href
            ).catch(() => null);

            if (bidLink) {
                auctionMeta.bid_url = bidLink;
                auctions.push({ url: bidLink, userData: { auctionMeta } });
                log.info(`Found bid URL: ${bidLink}`);
            } else {
                log.warning(`No bid.auctionlistservices.com link found on ${request.url}`);
                // Log all external links for debugging
                const links = await page.$$eval('a[href^="http"]', els =>
                    els.map(el => el.href).filter(h => !h.includes('usgovbid.com'))
                ).catch(() => []);
                log.info(`External links: ${links.slice(0, 10).join(', ')}`);
            }
        },
    });

    const redirectRequests = requests.filter(r => r.userData.needsRedirect);
    if (redirectRequests.length) {
        await redirectCrawler.run(redirectRequests.map(r => ({ url: r.url, userData: r.userData })));
    }
}

const mainRequests = [
    ...requests.filter(r => !r.userData.needsRedirect),
    ...auctions,
];

if (!mainRequests.length) {
    console.warn('[USGOVBID] No bid URLs resolved — check event page structure');
    await Actor.exit();
}

await crawler.run(mainRequests);

console.log(`[USGOVBID] Scrape complete. Found: ${totalFound} | Passed filters: ${totalPassed}`);
console.log(`[USGOVBID] Auctions processed: ${mainRequests.length}`);

await Actor.exit();
