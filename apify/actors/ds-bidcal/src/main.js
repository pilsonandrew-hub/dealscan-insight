import { Actor } from 'apify';
import { CheerioCrawler } from 'crawlee';

const WEBHOOK_URL = 'https://dealscan-insight-production.up.railway.app/api/ingest/apify';
const WEBHOOK_SECRET = 'sbEC0dNgb7Ohg3rDV';
const SOURCE = 'bidcal';

const BASE = 'https://bidcal.com';

const TARGET_STATES = new Set([
    'AZ','CA','NV','CO','NM','UT','TX','FL','GA','SC','TN','NC','VA','WA','OR','HI'
]);

const HIGH_RUST_STATES = new Set([
    'OH','MI','PA','NY','WI','MN','IL','IN','MO','IA',
    'ND','SD','NE','KS','WV','ME','NH','VT','MA','RI',
    'CT','NJ','MD','DE'
]);

const VEHICLE_KEYWORDS = ['car','truck','suv','van','pickup','sedan','coupe','wagon','vehicle','automobile','motor','4wd','awd','hybrid'];
const VEHICLE_MAKES = ['ford','chevrolet','chevy','dodge','ram','toyota','honda','nissan','jeep','gmc','chrysler',
    'hyundai','kia','subaru','mazda','volkswagen','vw','bmw','mercedes','audi','lexus','acura','infiniti',
    'cadillac','lincoln','buick','pontiac','mitsubishi','volvo','tesla','rivian','lucid','genesis'];

const SEARCH_URLS = [
    `${BASE}/auctions?type=vehicle`,
    `${BASE}/search?q=car+truck`,
    `${BASE}/search?q=suv+van+pickup`,
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

function isVehicle(title) {
    const lower = title.toLowerCase();
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

function applyFilters(listing, log) {
    if (!isVehicle(listing.title)) {
        log.debug(`[SKIP] Not a vehicle: ${listing.title}`);
        return false;
    }
    const state = listing.state;
    if (state && HIGH_RUST_STATES.has(state)) {
        log.debug(`[SKIP] High-rust state: ${state} — ${listing.title}`);
        return false;
    }
    if (state && !targetStateSet.has(state)) {
        log.debug(`[SKIP] Out-of-target state: ${state}`);
        return false;
    }
    if (listing.current_bid > 0 && listing.current_bid < minBid) {
        log.debug(`[SKIP] Bid too low: $${listing.current_bid}`);
        return false;
    }
    if (listing.current_bid > 0 && listing.current_bid > maxBid) {
        log.debug(`[SKIP] Bid too high: $${listing.current_bid}`);
        return false;
    }
    if (listing.year && listing.year < minYear) {
        log.debug(`[SKIP] Too old: ${listing.year}`);
        return false;
    }
    if (listing.mileage && listing.mileage > maxMileage) {
        log.debug(`[SKIP] Too many miles: ${listing.mileage}`);
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
        log.info(`[BidCal] Processing: ${url}`);

        if (request.label === 'DETAIL') {
            await handleDetailPage($, request, log);
            return;
        }

        // LIST page — BidCal aggregator listing cards
        const listingLinks = [];

        // BidCal auction listing links
        $('a[href*="/auction/"], a[href*="/lot/"], a[href*="/listing/"], a[href*="/item/"]').each((_, el) => {
            const href = $(el).attr('href');
            if (!href) return;
            const abs = href.startsWith('http') ? href : `${BASE}${href}`;
            if (abs.match(/\/(auction|lot|listing|item)\/[a-z0-9\-]+/i)) {
                listingLinks.push(abs);
            }
        });

        // Fallback: any card-style links with auction data
        if (listingLinks.length === 0) {
            $('.auction-card a, .listing-card a, .item-card a, [class*="auction-item"] a, [class*="result-item"] a').each((_, el) => {
                const href = $(el).attr('href');
                if (!href) return;
                const abs = href.startsWith('http') ? href : `${BASE}${href}`;
                if (!abs.includes('#')) listingLinks.push(abs);
            });
        }

        // BidCal may embed inline listing data in cards — extract directly from list
        $('[class*="auction-card"], [class*="listing-card"], [class*="item-row"], .result-item').each((_, card) => {
            const el = $(card);
            const title = el.find('h2, h3, h4, [class*="title"], [class*="name"]').first().text().trim();
            if (!title || !isVehicle(title)) return;

            const bidText = el.find('[class*="bid"], [class*="price"], [class*="amount"]').first().text().trim();
            const bid = parseBid(bidText);
            const locationText = el.find('[class*="location"], [class*="city"], [class*="address"]').first().text().trim();
            const state = parseState(locationText);
            const endText = el.find('[class*="end"], [class*="close"], [class*="date"], time').first().text().trim();
            const auctionHouse = el.find('[class*="auction-house"], [class*="company"], [class*="seller"]').first().text().trim();
            const linkEl = el.find('a').first();
            const href = linkEl.attr('href') || '';
            const listingUrl = href ? (href.startsWith('http') ? href : `${BASE}${href}`) : url;
            const imgEl = el.find('img').first();
            const imageUrl = imgEl.attr('data-src') || imgEl.attr('src') || null;

            const { year, make, model } = parseVehicleTitle(title);
            const listing = {
                listing_id: `bidcal-inline-${Buffer.from(listingUrl).toString('base64').slice(0, 16)}`,
                title,
                current_bid: bid,
                buy_now_price: null,
                auction_end_date: parseDate(endText),
                state,
                city: locationText.split(',')[0].trim() || null,
                listing_url: listingUrl,
                image_url: imageUrl,
                auction_house: auctionHouse || null,
                mileage: null,
                vin: null,
                year,
                make,
                model,
                source: SOURCE,
                scraped_at: new Date().toISOString(),
            };

            if (applyFilters(listing, log)) {
                totalAfterFilters++;
                log.info(`[PASS-INLINE] ${listing.title} | $${listing.current_bid} | ${listing.state}`);
                allListings.push(listing);
                Actor.pushData(listing);
            }
            totalFound++;
        });

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
            // Try next page link first
            const nextHref = $('a[rel="next"], a[aria-label*="Next"], [class*="pagination"] a[class*="next"]').attr('href');
            if (nextHref) {
                const nextAbs = nextHref.startsWith('http') ? nextHref : `${BASE}${nextHref}`;
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
    const title = $('h1, .lot-title, .listing-title, [class*="item-title"], [class*="lot-title"]')
        .first().text().trim() ||
        $('title').text().split('|')[0].trim();

    if (!title) {
        log.debug(`[SKIP] No title: ${request.url}`);
        return;
    }

    // Current bid
    let bidText = '';
    for (const sel of ['.current-bid', '[class*="current-bid"]', '[class*="high-bid"]',
                        '[class*="current-price"]', '.bid-amount', '[class*="bid-value"]']) {
        const t = $(sel).first().text().trim();
        if (t) { bidText = t; break; }
    }
    if (!bidText) {
        $('td, th, dt, label, span').each((_, el) => {
            if ($(el).text().match(/current\s*bid|high\s*bid|current\s*price/i)) {
                bidText = $(el).next().text().trim() ||
                          $(el).parent().next().text().trim();
            }
        });
    }
    const bid = parseBid(bidText);

    // Location / city / state
    let location = '';
    for (const sel of ['[class*="location"]', '.listing-location', '[class*="city"]',
                        '.auction-location', '[class*="address"]']) {
        const t = $(sel).first().text().trim();
        if (t) { location = t; break; }
    }

    // Auction house
    let auctionHouse = '';
    for (const sel of ['[class*="auction-house"]', '[class*="company"]', '[class*="seller"]', '.auctioneer']) {
        const t = $(sel).first().text().trim();
        if (t) { auctionHouse = t; break; }
    }

    // End date
    let endText = '';
    for (const sel of ['[class*="end-time"]', '[class*="closes"]', '[data-end]', '.auction-end',
                        '.close-date', 'time[datetime]']) {
        const el = $(sel).first();
        endText = el.attr('data-end') || el.attr('datetime') || el.text().trim();
        if (endText) break;
    }

    // Image
    const imgEl = $('img.listing-image, img.lot-photo, [class*="main-image"] img, .gallery img').first();
    const imageUrl = imgEl.attr('data-src') || imgEl.attr('src') || null;

    // ID from URL
    const idMatch = request.url.match(/\/(auction|lot|listing|item)\/([a-z0-9\-]+)/i);
    const itemId = idMatch ? `bidcal-${idMatch[2]}` : `bidcal-${Date.now()}`;

    // Description for mileage/VIN
    const description = $('[class*="description"], #description, .listing-description, .lot-description').text();
    const mileageMatch = description.match(/(\d[\d,]+)\s*(?:miles?|mi\.?)\b/i);
    const mileage = mileageMatch ? parseInt(mileageMatch[1].replace(/,/g, '')) : null;
    const vinMatch = description.match(/\bVIN[:\s#]*([A-HJ-NPR-Z0-9]{17})\b/i) ||
                     description.match(/\b([A-HJ-NPR-Z0-9]{17})\b/);
    const vin = vinMatch ? vinMatch[1] : null;

    const state = parseState(location);
    const city = location.split(',')[0].trim() || null;
    const { year, make, model } = parseVehicleTitle(title);

    const listing = {
        listing_id: itemId,
        title,
        current_bid: bid,
        buy_now_price: null,
        auction_end_date: parseDate(endText),
        state,
        city,
        listing_url: request.url,
        image_url: imageUrl,
        auction_house: auctionHouse || null,
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

async function sendWebhook(listings, log) {
    if (listings.length === 0) {
        log.info('[Webhook] No listings to send.');
        return;
    }

    const payload = { source: SOURCE, listings };

    try {
        log.info(`[Webhook] Sending ${listings.length} listings to ${WEBHOOK_URL}`);
        const response = await fetch(WEBHOOK_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Apify-Webhook-Secret': WEBHOOK_SECRET,
            },
            body: JSON.stringify(payload),
        });
        if (!response.ok) {
            const body = await response.text().catch(() => '');
            console.error(`[Webhook] Failed: HTTP ${response.status} — ${body}`);
        } else {
            console.log(`[Webhook] Success: HTTP ${response.status}`);
        }
    } catch (err) {
        console.error(`[Webhook] Error: ${err.message}`);
    }
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

console.log(`[BIDCAL COMPLETE] Found: ${totalFound} | Passed filters: ${totalAfterFilters}`);

await sendWebhook(allListings, log);

await Actor.exit();
