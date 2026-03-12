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
    `${BASE}/listings/trucks`,
    `${BASE}/listings/trailers`,
    `${BASE}/listings/trucks?sort=newest`,
    `${BASE}/listings/trailers?sort=newest`,
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

function applyFilters(listing, log) {
    if (!isCommercialVehicle(listing.title)) {
        log.debug(`[SKIP] Not a commercial vehicle: ${listing.title}`);
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
        log.info(`[AuctionTime] Processing: ${url}`);

        if (request.label === 'DETAIL') {
            await handleDetailPage($, request, log);
            return;
        }

        // LIST page — AuctionTime listing grid
        const listingLinks = [];

        // AuctionTime listing links
        $('a[href*="/listings/"]').each((_, el) => {
            const href = $(el).attr('href');
            if (!href) return;
            const abs = href.startsWith('http') ? href : `${BASE}${href}`;
            // Avoid re-queuing list pages — match individual listing IDs (numeric or slug after category)
            if (abs.match(/\/listings\/[a-z\-]+\/[a-z0-9\-]+$/i) ||
                abs.match(/\/listings\/\d+/) ||
                abs.match(/\/(listing|item|lot)\/[a-z0-9\-]+/i)) {
                listingLinks.push(abs);
            }
        });

        // Fallback: card links
        if (listingLinks.length === 0) {
            $('.listing-card a, .item-card a, [class*="listing-item"] a, [class*="result-card"] a, .equipment-card a').each((_, el) => {
                const href = $(el).attr('href');
                if (!href) return;
                const abs = href.startsWith('http') ? href : `${BASE}${href}`;
                if (!abs.includes('#') && abs !== url) listingLinks.push(abs);
            });
        }

        // Try to extract inline listing data from cards (AuctionTime renders some data in list)
        $('[class*="listing-card"], [class*="item-card"], [class*="equipment-item"], [class*="result-item"]').each((_, card) => {
            const el = $(card);
            const title = el.find('h2, h3, h4, [class*="title"], [class*="name"]').first().text().trim();
            if (!title || !isCommercialVehicle(title)) return;

            const bidText = el.find('[class*="bid"], [class*="price"], [class*="amount"]').first().text().trim();
            const bid = parseBid(bidText);
            const locationText = el.find('[class*="location"], [class*="city"], [class*="state"]').first().text().trim();
            const state = parseState(locationText);
            const endText = el.find('[class*="end"], [class*="close"], [class*="date"], time').first().text().trim();
            const mileageText = el.find('[class*="mileage"], [class*="miles"], [class*="odometer"], [class*="hours"]').first().text().trim();
            const mileage = parseMileage(mileageText);
            const linkEl = el.find('a').first();
            const href = linkEl.attr('href') || '';
            const listingUrl = href ? (href.startsWith('http') ? href : `${BASE}${href}`) : url;
            const imgEl = el.find('img').first();
            const imageUrl = imgEl.attr('data-src') || imgEl.attr('src') || null;

            const { year, make, model } = parseVehicleTitle(title);
            const listing = {
                listing_id: `auctiontime-inline-${Buffer.from(listingUrl).toString('base64').slice(0, 16)}`,
                title,
                current_bid: bid,
                buy_now_price: null,
                auction_end_date: parseDate(endText),
                state,
                listing_url: listingUrl,
                image_url: imageUrl,
                mileage,
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
            const nextHref = $('a[rel="next"], [class*="pagination"] a[class*="next"], a[aria-label*="Next"]').attr('href');
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
    const title = $('h1, .listing-title, [class*="listing-title"], [class*="item-title"], .equipment-title')
        .first().text().trim() ||
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
        $('td, th, dt, label, span, div').each((_, el) => {
            if ($(el).text().match(/current\s*bid|high\s*bid|asking\s*price|reserve\s*price/i)) {
                bidText = $(el).next().text().trim() ||
                          $(el).parent().next().text().trim();
            }
        });
    }
    const bid = parseBid(bidText);

    // Location
    let location = '';
    for (const sel of ['[class*="location"]', '.listing-location', '[class*="city"]',
                        '.equipment-location', '[class*="address"]', '[class*="state"]']) {
        const t = $(sel).first().text().trim();
        if (t) { location = t; break; }
    }

    // End date
    let endText = '';
    for (const sel of ['[class*="end-time"]', '[class*="closes"]', '[data-end]',
                        '.auction-end', '.close-date', '[class*="end-date"]', 'time[datetime]']) {
        const el = $(sel).first();
        endText = el.attr('data-end') || el.attr('datetime') || el.text().trim();
        if (endText) break;
    }

    // Image
    const imgEl = $('img.listing-image, img.equipment-photo, [class*="main-image"] img, .gallery img, [class*="primary-photo"] img').first();
    const imageUrl = imgEl.attr('data-src') || imgEl.attr('src') || null;

    // Mileage / hours from specs table or description
    let mileage = null;
    const specsText = $('[class*="specs"], [class*="details"], .listing-details, table').text();
    const descText = $('[class*="description"], #description, .listing-description').text();
    const combinedText = specsText + ' ' + descText;

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

console.log(`[AUCTIONTIME COMPLETE] Found: ${totalFound} | Passed filters: ${totalAfterFilters}`);

await Actor.exit();
