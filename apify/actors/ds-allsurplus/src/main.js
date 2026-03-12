import { Actor } from 'apify';
import { CheerioCrawler } from 'crawlee';
const SOURCE = 'allsurplus';

const BASE = 'https://www.allsurplus.com';

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

// AllSurplus (Ritchie Bros.) API endpoints — try these first
const API_ENDPOINTS = [
    `${BASE}/api/search?q=vehicle&category=vehicles&status=active&limit=100`,
    `${BASE}/api/search?q=truck+suv+van&category=vehicles&status=active&limit=100`,
    `${BASE}/api/v1/lots?category=vehicles&status=active&per_page=100`,
    `${BASE}/api/lots?category=vehicle&status=open&limit=100`,
];

const WEB_SEARCH_URL = `${BASE}/auctions?category=vehicles`;

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
let usedApi = false;

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

async function tryApiFetch(log) {
    for (const endpoint of API_ENDPOINTS) {
        try {
            log.info(`[AllSurplus] Trying API: ${endpoint}`);
            const res = await fetch(endpoint, {
                headers: {
                    'Accept': 'application/json',
                    'User-Agent': 'Mozilla/5.0 (compatible; DealerScope/1.0)',
                },
                signal: AbortSignal.timeout(10000),
            });

            if (!res.ok) continue;

            const ct = res.headers.get('content-type') || '';
            if (!ct.includes('json')) continue;

            const data = await res.json();

            const items = Array.isArray(data) ? data :
                          data.lots ?? data.auctions ?? data.items ?? data.results ?? data.data ?? [];

            if (!Array.isArray(items) || items.length === 0) continue;

            log.info(`[AllSurplus] API returned ${items.length} items from ${endpoint}`);
            usedApi = true;

            for (const item of items) {
                totalFound++;
                const title = item.title || item.name || item.description || item.lot_title || '';
                const location = item.location || item.city_state || item.address || item.sale_location || '';
                const stateRaw = item.state || item.state_code || parseState(location);
                const state = stateRaw ? stateRaw.toUpperCase() : null;
                const bid = parseBid(item.current_bid || item.high_bid || item.current_price || item.price || 0);
                const lotNum = item.lot_number || item.lot_num || item.lot_id || item.id || '';
                const { year, make, model } = parseVehicleTitle(title);

                const listing = {
                    listing_id: String(item.id || item.lot_id || `allsurplus-api-${totalFound}`),
                    title,
                    current_bid: bid,
                    buy_now_price: parseBid(item.buy_now_price || item.buy_it_now || null) || null,
                    auction_end_date: parseDate(item.end_time || item.closes_at || item.auction_end || item.end_date || null),
                    state,
                    listing_url: item.url || item.listing_url || item.lot_url || `${BASE}/lots/${item.id}`,
                    image_url: item.photo_url || item.image_url || item.thumbnail || item.primary_image || null,
                    lot_number: String(lotNum),
                    mileage: item.mileage ? parseInt(item.mileage) : null,
                    vin: item.vin || null,
                    year,
                    make,
                    model,
                    source: SOURCE,
                    scraped_at: new Date().toISOString(),
                };

                if (applyFilters(listing, log)) {
                    totalAfterFilters++;
                    log.info(`[PASS] ${listing.title} | $${listing.current_bid} | ${listing.state}`);
                    allListings.push(listing);
                    await Actor.pushData(listing);
                }
            }

            return true;
        } catch (err) {
            log.debug(`[AllSurplus] API attempt failed: ${endpoint} — ${err.message}`);
        }
    }
    return false;
}

// Web crawler fallback
const crawler = new CheerioCrawler({
    maxRequestsPerCrawl: maxPages * 2 + 50,
    requestHandlerTimeoutSecs: 60,
    maxConcurrency: 2,
    minConcurrency: 1,

    async requestHandler({ $, request, enqueueLinks, log }) {
        const url = request.url;
        log.info(`[AllSurplus] Processing: ${url}`);

        if (request.label === 'DETAIL') {
            await handleDetailPage($, request, log);
            return;
        }

        // LIST page
        const listingLinks = [];

        // AllSurplus lot links
        $('a[href*="/lots/"], a[href*="/lot/"], a[href*="/auctions/"]').each((_, el) => {
            const href = $(el).attr('href');
            if (!href) return;
            const abs = href.startsWith('http') ? href : `${BASE}${href}`;
            if (abs.match(/\/(lots?|auctions?)\/[a-z0-9\-]+/i)) {
                listingLinks.push(abs);
            }
        });

        // Fallback: card/tile links
        if (listingLinks.length === 0) {
            $('.lot-card a, .auction-card a, .item-card a, [class*="lot-item"] a, [class*="auction-item"] a').each((_, el) => {
                const href = $(el).attr('href');
                if (!href) return;
                const abs = href.startsWith('http') ? href : `${BASE}${href}`;
                listingLinks.push(abs);
            });
        }

        const uniqueLinks = [...new Set(listingLinks)];
        log.info(`Found ${uniqueLinks.length} listings on page`);
        totalFound += uniqueLinks.length;

        if (uniqueLinks.length > 0) {
            await enqueueLinks({
                urls: uniqueLinks,
                label: 'DETAIL',
            });
        }

        // Pagination
        const currentPage = request.userData?.pageNum ?? 1;
        if (uniqueLinks.length > 0 && currentPage < maxPages) {
            const nextUrl = new URL(url);
            nextUrl.searchParams.set('page', currentPage + 1);
            await enqueueLinks({
                urls: [nextUrl.toString()],
                label: 'LIST',
                userData: { pageNum: currentPage + 1 },
            });
        }
    },
});

async function handleDetailPage($, request, log) {
    const title = $('h1, .lot-title, [class*="lot-title"], .item-title, [class*="item-title"]')
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
            if ($(el).text().match(/current\s*bid|high\s*bid/i)) {
                bidText = $(el).next().text().trim() ||
                          $(el).parent().next().text().trim();
            }
        });
    }
    const bid = parseBid(bidText);

    // Buy now
    let buyNowText = '';
    for (const sel of ['.buy-now-price', '[class*="buy-now"]', '[class*="buy_now"]', '[class*="buy-it-now"]']) {
        const t = $(sel).first().text().trim();
        if (t) { buyNowText = t; break; }
    }
    const buyNow = parseBid(buyNowText) || null;

    // Location
    let location = '';
    for (const sel of ['[class*="location"]', '.lot-location', '[class*="city"]', '.sale-location', '[class*="address"]']) {
        const t = $(sel).first().text().trim();
        if (t) { location = t; break; }
    }

    // End date
    let endText = '';
    for (const sel of ['[class*="end-time"]', '[class*="closes"]', '[data-end]', '.auction-end', '.close-date', '[class*="end-date"]']) {
        const el = $(sel).first();
        endText = el.attr('data-end') || el.attr('datetime') || el.text().trim();
        if (endText) break;
    }

    // Image
    const imgEl = $('img.lot-image, img.item-photo, [class*="main-image"] img, .gallery img, [class*="lot-photo"] img').first();
    const imageUrl = imgEl.attr('data-src') || imgEl.attr('src') || null;

    // Lot number
    const lotNumEl = $('[class*="lot-number"], [class*="lot-num"], [data-lot]').first();
    const lotNumber = lotNumEl.text().trim() || lotNumEl.attr('data-lot') || '';

    // ID from URL
    const idMatch = request.url.match(/\/lots?\/([a-z0-9\-]+)/i) ||
                    request.url.match(/\/auctions?\/([a-z0-9\-]+)/i) ||
                    request.url.match(/[Ll]ot[Ii]d=([a-z0-9\-]+)/i);
    const itemId = idMatch ? idMatch[1] : `allsurplus-${Date.now()}`;

    // Description for mileage/VIN
    const description = $('[class*="description"], #description, .lot-description, .item-description').text();
    const mileageMatch = description.match(/(\d[\d,]+)\s*(?:miles?|mi\.?)\b/i);
    const mileage = mileageMatch ? parseInt(mileageMatch[1].replace(/,/g, '')) : null;
    const vinMatch = description.match(/\bVIN[:\s#]*([A-HJ-NPR-Z0-9]{17})\b/i) ||
                     description.match(/\b([A-HJ-NPR-Z0-9]{17})\b/);
    const vin = vinMatch ? vinMatch[1] : null;

    const state = parseState(location);
    const { year, make, model } = parseVehicleTitle(title);

    const listing = {
        listing_id: itemId,
        title,
        current_bid: bid,
        buy_now_price: buyNow,
        auction_end_date: parseDate(endText),
        state,
        listing_url: request.url,
        image_url: imageUrl,
        lot_number: lotNumber,
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

// Try API first, fall back to web crawl
const log = { info: console.log, debug: () => {}, error: console.error };
const apiSuccess = await tryApiFetch(log);

if (!apiSuccess) {
    console.log('[AllSurplus] API not available — falling back to web crawl');
    await crawler.run([
        { url: WEB_SEARCH_URL, label: 'LIST', userData: { pageNum: 1 } },
    ]);
}

console.log(`[ALLSURPLUS COMPLETE] Used API: ${usedApi} | Found: ${totalFound} | Passed filters: ${totalAfterFilters}`);

await Actor.exit();
