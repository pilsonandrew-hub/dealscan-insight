/**
 * ds-usgovbid — USGovBid Impound Vehicle Auction Scraper
 *
 * STATUS: WORKING — Playwright (required for AJAX item loading)
 *
 * Architecture:
 *   USGovBid uses two layers:
 *   1. usgovbid.com/auctions/ — WordPress + The Events Calendar plugin
 *      → Public REST API: /wp-json/tribe/events/v1/events (returns auction events w/ venue/state)
 *   2. bid.usgovbid.com (Maxanet platform) — individual lot pages
 *      → Items loaded via AJAX: POST /Public/Auction/GetAuctionItems
 *      → Requires session cookie + CSRF token captured from page load
 *
 * Strategy:
 *   1. Fetch upcoming auction events via WordPress REST API
 *   2. For each auction: load AuctionItems page in Playwright to get session/CSRF
 *   3. POST to GetAuctionItems AJAX endpoint to retrieve lot HTML
 *   4. Parse lot cards: title, current bid, end date, lot URL, photo
 *   5. Filter for vehicles, apply rust-state and bid-range filters
 *   6. Push normalized records to Apify dataset
 *
 * Note: USGovBid typically lists 3–10 active auctions with 20–200 lots each.
 * Vehicle lots are clearly labeled ("Vehicles" category). Each auction covers
 * a single government agency (county sheriff, state surplus, etc.).
 */

import { Actor } from 'apify';
import { PlaywrightCrawler } from 'crawlee';

const SOURCE = 'usgovbid';
const WP_EVENTS_API = 'https://www.usgovbid.com/wp-json/tribe/events/v1/events?per_page=50&status=publish';
const BID_BASE = 'https://bid.usgovbid.com';

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
    maxLotsPerAuction = 200,
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

function extractAuctionItems($) {
    const items = [];
    // Maxanet grid view: each lot is in .ibox-content or auction-item-card
    // Look for lot cards with title, bid, end date, image
    $('[id^="catelog_time_"], .auction-item-card, .ibox-content').each((i, el) => {
        const $el = $(el);

        // Title — usually in an h4, h3, or .public-item-font-color link
        const titleEl = $el.find('.public-item-font-color, h4 a, h3 a, .catelog-desc h2, .item-title').first();
        const title = normalizeText(titleEl.text() || titleEl.attr('title') || '');
        if (!title) return;

        // Lot URL
        const href = titleEl.attr('href') || $el.find('a[href*="AuctionItemId"]').first().attr('href') || '';
        const listing_url = href ? (href.startsWith('http') ? href : `${BID_BASE}${href}`) : '';

        // Current bid
        const bidText = $el.find('.min_bid_amount_text_quantity, .current-bid, [class*="current_bid"], [class*="CurrentBid"], .min-bid-text').first().text();
        const current_bid = parseBid(bidText);

        // End date — stored in data-enddate on .remain-time or .local-date-time spans
        const endEl = $el.find('.remain-time, [data-enddate], .bid-content-date[data-auc-date]').first();
        const endRaw = endEl.attr('data-enddate') || endEl.attr('data-auc-date') || '';
        const auction_end_time = parseDate(endRaw) || parseDate($el.find('[data-auc-date]').last().attr('data-auc-date'));

        // Photo
        const imgEl = $el.find('img[src*="maxanet"], img[src*="amazonaws"], img[src*="prod.maxanet"], .carousel-item img').first();
        const photo_url = imgEl.attr('src') || imgEl.attr('data-src') || '';

        // Lot number from title or catelog id
        const lotNum = $el.attr('id')?.match(/catelog_time_(\w+)/)?.[1] || '';

        items.push({ title, listing_url, current_bid, auction_end_time, photo_url, lot_num: lotNum });
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

        // Extract bid.usgovbid.com URL from description
        const desc = ev.description || '';
        const bidMatch = desc.match(/href="(https?:\/\/bid\.usgovbid\.com[^"&]+)/);
        const auctionUrl = bidMatch
            ? bidMatch[1].replace(/&#038;/g, '&').replace(/&amp;/g, '&')
            : null;

        // Also try the event's own page for the bid URL
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
    maxRequestsPerCrawl: 50,
    requestHandlerTimeoutSecs: 120,
    navigationTimeoutSecs: 60,
    browserPoolOptions: {
        useFingerprints: false,
    },
    async requestHandler({ page, request, log }) {
        const { auctionMeta } = request.userData;

        // ── Step 1: Load the AuctionItems page to get session & CSRF ──────────
        log.info(`Processing auction: ${auctionMeta.title} [${auctionMeta.state}] — ${request.url}`);
        await page.waitForTimeout(2000);

        // Extract hidden field values for AJAX call
        const auctionId = await page.$eval('#hdn_AuctionId', el => el.value).catch(() => null);
        const aucId = await page.$eval('#hdn_AucId', el => el.value).catch(() => null);
        const csrfToken = await page.$eval('#__RequestVerificationToken', el => el.value).catch(() => null);

        if (!auctionId) {
            log.warning(`Could not extract AuctionId from ${request.url} — trying DOM parse`);
        }

        // ── Step 2: Trigger AJAX to load all lots ────────────────────────────
        let allLots = [];
        let page_num = 1;
        const PAGE_SIZE = 100;

        while (allLots.length < maxLotsPerAuction) {
            log.info(`Fetching lots page ${page_num} for auction ${auctionId || 'unknown'}...`);

            let lotsHtml = null;
            try {
                // Use page.evaluate to call the AJAX endpoint from within browser context (avoids CORS)
                lotsHtml = await page.evaluate(async ({ auctionId, pageNum, pageSize, csrf }) => {
                    const formData = new URLSearchParams({
                        AuctionId: auctionId,
                        pageNumber: String(pageNum),
                        itemsPerPage: String(pageSize),
                        viewType: '2',
                        Categoryfilter: '',
                        ShowFilter: 'all',
                        SortBy: 'ordernumber_asc',
                        SearchFilter: '',
                        pageSize: String(pageSize),
                        __RequestVerificationToken: csrf || '',
                    });
                    const resp = await fetch('/Public/Auction/GetAuctionItems', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                        body: formData.toString(),
                        credentials: 'include',
                    });
                    if (!resp.ok) return null;
                    return await resp.text();
                }, { auctionId, pageNum: page_num, pageSize: PAGE_SIZE, csrf: csrfToken });
            } catch (err) {
                log.warning(`GetAuctionItems AJAX failed: ${err.message}`);
                break;
            }

            if (!lotsHtml || lotsHtml.includes('No Data Found') || lotsHtml.length < 100) {
                log.info(`No more lots on page ${page_num}`);
                break;
            }

            // Parse lots from HTML response
            const cheerio = await import('cheerio');
            const $ = cheerio.load(lotsHtml);
            const pageLots = extractAuctionItems($);
            log.info(`Page ${page_num}: ${pageLots.length} lots parsed`);

            if (!pageLots.length) break;
            allLots = allLots.concat(pageLots);

            // Check if there are more pages
            const hasNextPage = lotsHtml.includes('next-page') || lotsHtml.includes('page-next') ||
                (pageLots.length === PAGE_SIZE);
            if (!hasNextPage) break;
            page_num++;
            await page.waitForTimeout(1000);
        }

        log.info(`Auction ${auctionMeta.title}: ${allLots.length} lots total`);

        // ── Step 3: Filter and push ──────────────────────────────────────────
        for (const lot of allLots) {
            totalFound++;
            const { title, listing_url, current_bid, auction_end_time, photo_url } = lot;

            // Vehicle filter
            if (!isVehicle(title)) continue;

            // State filter
            const state = auctionMeta.state;
            if (state && HIGH_RUST_STATES.has(state)) continue;

            // Bid filter
            if (current_bid > 0 && (current_bid < minBid || current_bid > maxBid)) continue;

            // Age filter
            const year = parseYear(title);
            if (year && (new Date().getFullYear() - year) > 12) continue;

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

// Fetch auction list from WP Events API
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

// Build request list — for each auction that has a bid URL, crawl the lots page
const requests = [];
for (const auction of events.slice(0, maxAuctions)) {
    let bidUrl = auction.bid_url;

    if (!bidUrl) {
        // Fall back: crawl event page to find bid.usgovbid.com link
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

// Handle event pages that need redirect to bid URL
if (requests.some(r => r.userData.needsRedirect)) {
    // Use a pre-pass crawler to resolve event page → bid URL
    const redirectCrawler = new PlaywrightCrawler({
        maxRequestsPerCrawl: 20,
        requestHandlerTimeoutSecs: 60,
        async requestHandler({ page, request, log }) {
            const { auctionMeta } = request.userData;
            log.info(`Resolving bid URL from event page: ${request.url}`);

            // Find the bid.usgovbid.com link
            const bidLink = await page.$eval(
                'a[href*="bid.usgovbid.com"]',
                el => el.href
            ).catch(() => null);

            if (bidLink) {
                auctionMeta.bid_url = bidLink;
                auctions.push({ url: bidLink, userData: { auctionMeta } });
                log.info(`Found bid URL: ${bidLink}`);
            } else {
                log.warning(`No bid.usgovbid.com link found on ${request.url}`);
            }
        },
    });

    const redirectRequests = requests.filter(r => r.userData.needsRedirect);
    if (redirectRequests.length) {
        await redirectCrawler.run(redirectRequests.map(r => ({ url: r.url, userData: r.userData })));
    }
}

// Build final request list for main crawler
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
