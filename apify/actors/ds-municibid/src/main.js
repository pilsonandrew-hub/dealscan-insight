import { Actor } from 'apify';
import { CheerioCrawler } from 'crawlee';

const SOURCE = 'municibid';

const BASE = 'https://www.municibid.com';

const TARGET_STATES = new Set([
    'AZ','CA','NV','CO','NM','UT','TX','FL','GA','SC','TN','NC','VA','WA','OR','HI'
]);

const HIGH_RUST_STATES = new Set([
    'OH','MI','PA','NY','WI','MN','IL','IN','MO','IA',
    'ND','SD','NE','KS','WV','ME','NH','VT','MA','RI',
    'CT','NJ','MD','DE'
]);

const VEHICLE_KEYWORDS = ['car','truck','suv','van','pickup','sedan','coupe','wagon','vehicle','automobile','motor','4wd','awd'];
const VEHICLE_MAKES = ['ford','chevrolet','chevy','dodge','ram','toyota','honda','nissan','jeep','gmc','chrysler',
    'hyundai','kia','subaru','mazda','volkswagen','vw','bmw','mercedes','audi','lexus','acura','infiniti',
    'cadillac','lincoln','buick','pontiac','mitsubishi','volvo','tesla'];

// Municibid known vehicle category/search endpoints (try API first, then web)
const API_ENDPOINTS = [
    `${BASE}/api/v1/auctions?category=vehicle&status=open&per_page=100`,
    `${BASE}/api/v1/items?category=vehicles&status=active&limit=100`,
    `${BASE}/search.json?q=vehicle&category=vehicles`,
    `${BASE}/auctions.json?category=vehicle`,
];

// Municibid vehicle browse/search pages. Use current-looking endpoints first.
const WEB_SEARCH_URLS = [
    `${BASE}/auctions/vehicles`,
    `${BASE}/auctions?q=vehicle`,
    `${BASE}/Browse/C160883/Automotive?ViewStyle=list&StatusFilter=active_only&SortFilterOptions=1`,
];

const LISTING_SELECTORS = [
    '.auction-row a[href*="/auction/"]',
    '.auction-item a[href*="/auction/"]',
    '.lot-card a[href*="/auction/"]',
    '.listing-item a[href*="/auction/"]',
    'a[href*="/auction/"]',
    '.row.browse-item a[href*="/Listing/Details/"]',
    'a[href*="/Listing/Details/"]',
];

await Actor.init();

const input = await Actor.getInput() ?? {};
const {
    maxPages = 20,
    minBid = 1000,
    maxMileage = 50000,
    minYear = 2022,
    targetStates = [...TARGET_STATES],
} = input;

const targetStateSet = new Set(targetStates.map(s => s.toUpperCase()));
const allListings = [];
let totalFound = 0;
let totalAfterFilters = 0;

function normalizeText(value) {
    return String(value ?? '')
        .replace(/\u00a0/g, ' ')
        .replace(/[ \t]+/g, ' ')
        .replace(/\s*\n\s*/g, '\n')
        .trim();
}

function toAbsoluteUrl(href) {
    if (!href) return '';
    return href.startsWith('http') ? href : `${BASE}${href}`;
}

function isListingDetailUrl(url) {
    return /\/auction\/[^/?#]+/i.test(url) || /\/Listing\/Details\/\d+/i.test(url);
}

function extractLabelValue(lines, label) {
    const normalizedLabel = label.toLowerCase();
    const index = lines.findIndex((line) => {
        const lower = line.toLowerCase();
        return lower === normalizedLabel || lower.startsWith(`${normalizedLabel}:`);
    });

    if (index === -1) return '';

    const inlineValue = lines[index].slice(label.length).replace(/^[:\s-]+/, '').trim();
    if (inlineValue) return inlineValue;

    return lines[index + 1] ?? '';
}

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

// Try API endpoints first
let usedApi = false;

async function tryApiFetch(log) {
    for (const endpoint of API_ENDPOINTS) {
        try {
            log.info(`[Municibid] Trying API: ${endpoint}`);
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

            // Normalize whatever the API returns
            const items = Array.isArray(data) ? data :
                          data.auctions ?? data.items ?? data.results ?? data.data ?? [];

            if (!Array.isArray(items) || items.length === 0) continue;

            log.info(`[Municibid] API returned ${items.length} items from ${endpoint}`);
            usedApi = true;

            for (const item of items) {
                totalFound++;
                const title = item.title || item.name || item.description || '';
                const location = item.location || item.city_state || item.address || '';
                const stateRaw = item.state || item.state_code || parseState(location);
                const state = stateRaw ? stateRaw.toUpperCase() : null;
                const bid = parseBid(item.current_bid || item.high_bid || item.price || 0);
                const { year, make, model } = parseVehicleTitle(title);

                const listing = {
                    listing_id: String(item.id || item.auction_id || `municibid-api-${totalFound}`),
                    title,
                    current_bid: bid,
                    buy_now_price: parseBid(item.buy_now_price || item.buy_it_now || null) || null,
                    auction_end_date: parseDate(item.end_time || item.closes_at || item.auction_end || null),
                    state,
                    listing_url: item.url || item.listing_url || `${BASE}/auctions/${item.id}`,
                    image_url: item.photo_url || item.image_url || item.thumbnail || null,
                    mileage: item.mileage ? parseInt(item.mileage) : null,
                    vin: item.vin || null,
                    year,
                    make,
                    model,
                    scraped_at: new Date().toISOString(),
                };

                if (applyFilters(listing, log)) {
                    totalAfterFilters++;
                    log.info(`[PASS] ${listing.title} | $${listing.current_bid} | ${listing.state}`);
                    allListings.push(listing);
                    await Actor.pushData(listing);
                }
            }

            return true; // API worked
        } catch (err) {
            log.debug(`[Municibid] API attempt failed: ${endpoint} — ${err.message}`);
        }
    }
    return false;
}

// Web crawler fallback
const crawler = new CheerioCrawler({
    maxRequestsPerCrawl: maxPages * 2 + 50,
    requestHandlerTimeoutSecs: 60,
    maxConcurrency: 2,
    // Rate limit: ~1 req/sec
    minConcurrency: 1,

    async requestHandler({ $, request, enqueueLinks, log }) {
        const url = request.url;
        log.info(`[Municibid] Processing: ${url}`);

        if (request.label === 'DETAIL') {
            await handleDetailPage($, request, log);
            return;
        }

        // LIST page
        const listingLinks = [];

        for (const selector of LISTING_SELECTORS) {
            $(selector).each((_, el) => {
                const href = $(el).attr('href');
                const abs = toAbsoluteUrl(href);
                if (isListingDetailUrl(abs)) listingLinks.push(abs);
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
        if (currentPage < maxPages) {
            const nextHref = $('a[rel="next"], .pagination a[aria-label*="Next"], .PagedList-skipToNext a').attr('href');
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
    const lines = bodyText.split('\n').map((line) => line.trim()).filter(Boolean);

    const title = normalizeText($('h1.titleTextForItem, h1.text-truncate.text-card, h1').first().text()) ||
        normalizeText($('meta[property="og:title"]').attr('content')).replace(/\s+Online Government Auctions.*$/i, '') ||
        $('title').text().split('|')[0].trim();

    if (!title) {
        log.debug(`[SKIP] No title: ${request.url}`);
        return;
    }

    const bidText = normalizeText($('.containerBid, .awe-rt-BuyBox').first().text()) ||
        extractLabelValue(lines, 'Current Highest Bid') ||
        extractLabelValue(lines, 'Current Price');
    const bid = parseBid(bidText);

    const buyNow = null;

    const headerText = normalizeText($('.listing-data-div').first().text());
    const locationMatch = headerText.match(/Listing\s+#\s*\d+\s*[•|]\s*([^•\n]+?)\s*[•|]\s*([^•\n+]+)/i);
    const location = normalizeText(locationMatch?.[1]) || extractLabelValue(lines, 'Item Location');
    const seller = normalizeText(locationMatch?.[2]);

    const endText = normalizeText($('.auctiontimeEndingText').first().text()) ||
        extractLabelValue(lines, 'End Date');

    const imageUrl = $('meta[property="og:image"]').attr('content') ||
        $('img[src*="/listing/"], img[src*="/thumb"], .listing-data-div img').first().attr('src') ||
        null;

    const idMatch = request.url.match(/\/Details\/(\d+)/i);
    const itemId = idMatch ? idMatch[1] : `municibid-${Date.now()}`;

    const descriptionStart = lines.findIndex((line) => line.toLowerCase() === 'item description');
    const descriptionEnd = lines.findIndex((line) => {
        const lower = line.toLowerCase();
        return lower.includes('seller’s terms & conditions') || lower.includes("seller's terms & conditions");
    });
    const description = descriptionStart === -1
        ? ''
        : lines
            .slice(descriptionStart + 1, descriptionEnd === -1 ? descriptionStart + 14 : descriptionEnd)
            .join(' ')
            .trim();

    const mileageText = extractLabelValue(lines, 'Miles') || description;
    const mileageMatch = mileageText.match(/(\d[\d,]+)\s*(?:miles?|mi\.?)?\b/i);
    const mileage = mileageMatch ? parseInt(mileageMatch[1].replace(/,/g, '')) : null;
    const vinSource = extractLabelValue(lines, 'VIN') || description;
    const vinMatch = vinSource.match(/\bVIN[:\s#]*([A-HJ-NPR-Z0-9]{17})\b/i) ||
                     vinSource.match(/\b([A-HJ-NPR-Z0-9]{17})\b/);
    const vin = vinMatch ? vinMatch[1] : null;

    const state = parseState(location);
    const year = parseInt(extractLabelValue(lines, 'Year'), 10) || parseVehicleTitle(title).year;
    const make = extractLabelValue(lines, 'Make') || parseVehicleTitle(title).make;
    const model = extractLabelValue(lines, 'Model') || parseVehicleTitle(title).model;

    const listing = {
        listing_id: itemId,
        title,
        current_bid: bid,
        buy_now_price: buyNow,
        auction_end_date: parseDate(extractLabelValue(lines, 'End Date')) || endText || null,
        state,
        listing_url: request.url,
        image_url: imageUrl,
        mileage,
        vin,
        year,
        make,
        model,
        seller: seller || null,
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
    console.log('[Municibid] API not available — falling back to web crawl');
    await crawler.run(
        WEB_SEARCH_URLS.map((url, i) => ({
            url,
            label: 'LIST',
            userData: { pageNum: 1 },
            uniqueKey: `list-start-${i}`,
        }))
    );
}

console.log(`[MUNICIBID COMPLETE] Used API: ${usedApi} | Found: ${totalFound} | Passed filters: ${totalAfterFilters}`);

await Actor.exit();
