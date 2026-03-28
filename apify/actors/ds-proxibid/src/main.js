/**
 * ds-proxibid — Proxibid Vehicle Auction Scraper
 *
 * Proxibid.com: No bot protection, server-side rendered (SSR) after JS scroll trigger.
 * Uses Playwright to scroll-load the lazy-rendered lot grid, then parses article cards.
 *
 * Live recon findings (2026-03-17):
 * - Category URLs: /for-sale/cars-vehicles/pickup-trucks, /for-sale/cars-vehicles/cars
 * - Lot URL pattern: /Cars-Vehicles/Trucks/{Title}/lotInformation/{lotId}
 * - Card container: <article> elements
 * - Title: a[href*="/lotInformation/"] span[data-testid="body-primary"] (first)
 * - Location: span[data-testid="body-primary"] (second — "City, ST" format)
 * - Price: span[data-testid="body-primary"] (third — "$X,XXX.XX")
 * - Time left: span[data-testid="body-secondary"] (first)
 * - Auction house: a[href*="/auction-house/"]
 * - VIN often in title: "2008 GMC SIERRA K2500HD #1GTHK24K58E139687"
 */

import { Actor } from 'apify';
import { PlaywrightCrawler } from 'crawlee';

const SOURCE = 'proxibid';
const BASE = 'https://www.proxibid.com';

// Vehicle category pages to scrape (overridden when searchQuery is provided)

const TARGET_STATES = new Set([
    'AZ','CA','NV','CO','NM','UT','TX','FL','GA','SC','TN','NC','VA','WA','OR','HI',
]);

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

const MAKES = [
    'ford','chevrolet','chevy','dodge','ram','toyota','honda','nissan','jeep',
    'gmc','chrysler','hyundai','kia','subaru','mazda','volkswagen','vw',
    'bmw','mercedes','audi','lexus','acura','infiniti','cadillac','lincoln',
    'buick','pontiac','mitsubishi','volvo','tesla','rivian',
];
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

await Actor.init();

const input = await Actor.getInput() ?? {};
const {
    searchQuery = "",
    maxPages = 5,
    minBid = 500,
    maxBid = 50000,
    minYear = new Date().getFullYear() - 10,
} = input;

const CATEGORY_URLS = searchQuery
    ? [
        `${BASE}/for-sale/cars-vehicles/cars?q=${encodeURIComponent(searchQuery)}`,
        `${BASE}/for-sale/cars-vehicles/pickup-trucks?q=${encodeURIComponent(searchQuery)}`,
        `${BASE}/for-sale/cars-vehicles/trucks?q=${encodeURIComponent(searchQuery)}`,
    ]
    : [
        `${BASE}/for-sale/cars-vehicles/pickup-trucks`,
        `${BASE}/for-sale/cars-vehicles/cars`,
        `${BASE}/for-sale/cars-vehicles/trucks`,
    ];

let totalFound = 0;
let totalPassed = 0;
const seenLotIds = new Set();
const sampleLocations = [];

function normalize(text) {
    return String(text ?? '').replace(/\s+/g, ' ').trim();
}

function recordLocationSample(loc) {
    const n = normalize(loc);
    if (n && !sampleLocations.includes(n) && sampleLocations.length < 8) sampleLocations.push(n);
}

function parseState(locationText) {
    const loc = normalize(locationText).toUpperCase();
    // "City, ST" or "City, ST ZIPCODE"
    const m = loc.match(/,\s*([A-Z]{2})(?:\s+\d{5})?$/) || loc.match(/\b([A-Z]{2})\s*\d{5}$/);
    if (m && US_STATES.has(m[1])) return m[1];
    return null;
}

function parseYear(text) {
    const m = normalize(text).match(/\b(19[89]\d|20[012]\d)\b/);
    return m ? parseInt(m[1]) : null;
}

function parseMake(text) {
    const lower = normalize(text).toLowerCase();
    return MAKES.find(mk => new RegExp(`\\b${mk}\\b`).test(lower)) ?? null;
}

function parseBid(text) {
    const m = normalize(text).replace(/,/g, '').match(/\$?([\d]+(?:\.\d{2})?)/);
    return m ? parseFloat(m[1]) : 0;
}

function parseMileage(text) {
    const m = normalize(text).replace(/,/g, '').match(/(\d[\d,]*)\s*(?:miles?|mi\.?)\b/i);
    return m ? parseInt(m[1].replace(/,/g, ''), 10) : null;
}

function parseVin(text) {
    const m = normalize(text).match(/\b#?([A-HJ-NPR-Z0-9]{17})\b/i);
    return m ? m[1].toUpperCase() : null;
}

function hasConditionReject(text) {
    const lower = normalize(text).toLowerCase();
    return CONDITION_REJECT_PATTERNS.some((pattern) => pattern.test(lower));
}

function parseLotId(url) {
    const m = url.match(/\/lotInformation\/(\d+)/i);
    return m ? m[1] : null;
}

const crawler = new PlaywrightCrawler({
    maxRequestsPerCrawl: CATEGORY_URLS.length * maxPages * 50,
    maxConcurrency: 1,
    requestHandlerTimeoutSecs: 120,

    async requestHandler({ page, request, log }) {
        const label = request.userData.label ?? 'LIST';
        const url = request.url;

        if (label === 'LIST') {
            log.info(`[Proxibid] Loading list page: ${url}`);

            // Wait for Angular/React lot cards to render
            await page.waitForLoadState('networkidle').catch(() => {});
            await page.waitForTimeout(3000);

            // Scroll to trigger lazy load
            for (let i = 0; i < 4; i++) {
                await page.evaluate(() => window.scrollBy(0, 1200));
                await page.waitForTimeout(1500);
            }
            await page.waitForTimeout(2000);

            // Extract all lot links
            const lotLinks = await page.evaluate(() => {
                const links = [...document.querySelectorAll('a[href*="/lotInformation/"]')];
                const seen = new Set();
                return links
                    .map(a => a.href)
                    .filter(href => {
                        if (seen.has(href)) return false;
                        seen.add(href);
                        return true;
                    });
            });

            log.info(`[Proxibid] Found ${lotLinks.length} lot links on ${url}`);

            // Extract card data directly from list page (faster than visiting each detail)
            const cards = await page.evaluate(() => {
                const articles = [...document.querySelectorAll('article')];
                return articles.map(article => {
                    const lotLink = article.querySelector('a[href*="/lotInformation/"]');
                    const href = lotLink?.href ?? '';
                    const lotIdMatch = href.match(/\/lotInformation\/(\d+)/i);

                    // body-primary spans: [0]=title, [1]=location, [2]=price
                    const primarySpans = [...article.querySelectorAll('span[data-testid="body-primary"]')];
                    const title = primarySpans[0]?.innerText?.trim() ?? '';
                    const location = primarySpans[1]?.innerText?.trim() ?? '';
                    const priceText = primarySpans[2]?.innerText?.trim() ?? '';

                    const auctionHouseLink = article.querySelector('a[href*="/auction-house/"]');
                    const auctionHouse = auctionHouseLink?.innerText?.trim() ?? '';

                    const timeLeft = article.querySelector('span[data-testid="body-secondary"]')?.innerText?.trim() ?? '';
                    const imgSrc = article.querySelector('img')?.src ?? null;

                    return {
                        lotId: lotIdMatch ? lotIdMatch[1] : '',
                        title,
                        location,
                        priceText,
                        auctionHouse,
                        timeLeft,
                        listingUrl: href,
                        photoUrl: imgSrc,
                    };
                }).filter(c => c.lotId && c.title);
            });

            log.info(`[Proxibid] Extracted ${cards.length} cards from ${url}`);

            for (const card of cards) {
                totalFound++;
                recordLocationSample(card.location);

                const state = parseState(card.location);
                const year = parseYear(card.title);
                const make = parseMake(card.title);
                const bid = parseBid(card.priceText);
                const vin = parseVin(card.title);
                const mileage = parseMileage(card.title);

                if (seenLotIds.has(card.lotId)) continue;
                seenLotIds.add(card.lotId);

                if (hasConditionReject(card.title)) continue;
                if (!make) continue;
                if (!year || year < minYear) continue;
                if (bid > 0 && (bid < minBid || bid > maxBid)) continue;
                if (mileage !== null && mileage > 100000) continue;
                if (!state || !US_STATES.has(state)) continue;
                if (HIGH_RUST.has(state)) {
                    const currentYear = new Date().getFullYear();
                    if (!(year && year >= currentYear - 2)) continue;
                    console.log(`[BYPASS] Rust state ${state} allowed — vehicle is ${year} (≤2yr old)`);
                }

                totalPassed++;
                const titleParts = card.title.match(/^(\d{4})\s+(.+)/);
                const model = titleParts ? titleParts[2].replace(new RegExp(`^${make}\\s*`, 'i'), '').trim() : null;

                log.info(`[PASS] ${card.title} | $${bid} | ${state}`);

                await Actor.pushData({
                    title: card.title,
                    year,
                    make: make.charAt(0).toUpperCase() + make.slice(1),
                    model: model ?? null,
                    current_bid: bid,
                    state,
                    location: card.location,
                    listing_url: card.listingUrl,
                    photo_url: card.photoUrl,
                    auction_house: card.auctionHouse,
                    time_left: card.timeLeft,
                    vin: vin ?? null,
                    source_site: SOURCE,
                    scraped_at: new Date().toISOString(),
                });
            }

            // Pagination: increment page number in URL
            const pageNum = request.userData.page ?? 1;
            if (cards.length > 0 && pageNum < maxPages) {
                let nextUrl;
                if (url.match(/[?&]page=\d+/)) {
                    nextUrl = url.replace(/([?&])page=\d+/, `$1page=${pageNum + 1}`);
                } else {
                    nextUrl = url.includes('?')
                        ? `${url}&page=${pageNum + 1}`
                        : `${url}?page=${pageNum + 1}`;
                }
                await crawler.addRequests([{
                    url: nextUrl,
                    userData: { label: 'LIST', page: pageNum + 1 },
                }]);
            }
        }
    },
});

try {
    await crawler.run(CATEGORY_URLS.map(url => ({ url, userData: { label: 'LIST', page: 1 } })));
    console.log('[Proxibid] Sample locations:', sampleLocations);
    console.log(`[PROXIBID COMPLETE] Found: ${totalFound} | Passed filters: ${totalPassed}`);
} catch (err) {
    console.error(`[PROXIBID] Fatal error: ${err.message}`);
} finally {
    // Webhook notification to Railway ingest endpoint
    try {
        const dataset = await Actor.openDataset();
        const env = Actor.getEnv();
        await fetch('https://dealscan-insight-production.up.railway.app/api/ingest/apify', {
            method: 'POST',
            headers: {
                'X-Apify-Webhook-Secret': process.env.WEBHOOK_SECRET || '',
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                eventType: 'ACTOR.RUN.SUCCEEDED',
                eventData: {
                    actorId: env.actorId,
                    defaultDatasetId: dataset.id,
                },
            }),
            signal: AbortSignal.timeout(10000),
        });
        console.log('[PROXIBID] Webhook sent to Railway ingest');
    } catch (webhookErr) {
        console.warn(`[PROXIBID] Webhook failed (non-blocking): ${webhookErr.message}`);
    }
    await Actor.exit();
}
