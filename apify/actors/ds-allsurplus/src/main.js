import { Actor } from 'apify';
import { PlaywrightCrawler } from 'crawlee';
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

const WEB_SEARCH_URLS = [
    `${BASE}/search#q=truck&t=all&s=vehicle`,
    `${BASE}/search?q=truck+suv+car`,
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

function normalizeText(text) {
    return String(text || '').replace(/\s+/g, ' ').trim();
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
const crawler = new PlaywrightCrawler({
    maxRequestsPerCrawl: maxPages * 2 + 50,
    requestHandlerTimeoutSecs: 60,
    maxConcurrency: 2,
    minConcurrency: 1,
    launchContext: {
        launchOptions: {
            headless: true,
        },
    },

    async requestHandler({ page, request, enqueueLinks, log }) {
        const url = request.url;
        log.info(`[AllSurplus] Processing: ${url}`);

        if (request.label === 'DETAIL') {
            await handleDetailPage(page, request, log);
            return;
        }

        await page.waitForLoadState('domcontentloaded');
        await page.waitForTimeout(4000);

        const listings = await page.evaluate(() => {
            const normalize = (value) => String(value ?? '').replace(/\s+/g, ' ').trim();
            const toAbsolute = (href) => {
                if (!href) return null;
                try {
                    return new URL(href, window.location.origin).toString();
                } catch {
                    return null;
                }
            };

            const anchors = Array.from(document.querySelectorAll('a[href]')).filter((anchor) => {
                const href = anchor.getAttribute('href') || '';
                return /\/(en\/asset\/\d+\/\d+|asset\/|lot\/|lots\/|listing\/)/i.test(href);
            });

            const deduped = new Map();
            for (const anchor of anchors) {
                const listingUrl = toAbsolute(anchor.href || anchor.getAttribute('href'));
                if (!listingUrl || deduped.has(listingUrl)) continue;

                const card = anchor.closest(
                    '[id^="asset-"], article, li, .card, .search-result, .result, [data-testid*="search"], [class*="search-result"], [class*="SearchResult"]'
                ) || anchor.parentElement || anchor;

                const textNodes = Array.from(card.querySelectorAll('h1, h2, h3, h4, .card-title, [class*="title"], [data-testid*="title"]'))
                    .map((node) => normalize(node.textContent))
                    .filter(Boolean);
                const title = textNodes.find((value) => value.length > 4) || normalize(anchor.textContent);
                if (!title) continue;

                const cardText = normalize(card.textContent);
                const bidMatch = cardText.match(/(?:current\s*bid|bid)\s*[:$]?\s*\$?([\d,]+(?:\.\d+)?)/i);
                const locationMatch = cardText.match(/([A-Za-z .'-]+,\s*[A-Z]{2})(?:\s+\d{5})?/);
                const timerMatch = cardText.match(/(?:ends?|closes?)\s*[:\-]?\s*([A-Za-z0-9,:/ \-]+(?:AM|PM|UTC)?)/i);
                const lotMatch = cardText.match(/lot#?\s*[:\-]?\s*([A-Za-z0-9-]+)/i);
                const img = card.querySelector('img');

                deduped.set(listingUrl, {
                    title,
                    listingUrl,
                    currentBid: bidMatch?.[1] ?? '',
                    location: locationMatch?.[1] ?? '',
                    endDate: timerMatch?.[1] ?? '',
                    lotNumber: lotMatch?.[1] ?? '',
                    imageUrl: img?.getAttribute('src') || img?.getAttribute('data-src') || null,
                });
            }

            return Array.from(deduped.values());
        });

        const inlineListings = [];
        for (const item of listings) {
            const title = normalizeText(item.title);
            if (!title || !isVehicle(title)) continue;

            const { year, make, model } = parseVehicleTitle(title);
            const listing = {
                listing_id: normalizeText(item.lotNumber) || `allsurplus-inline-${Buffer.from(item.listingUrl).toString('base64').slice(0, 16)}`,
                title,
                current_bid: parseBid(item.currentBid),
                buy_now_price: null,
                auction_end_date: parseDate(item.endDate),
                state: parseState(item.location),
                listing_url: item.listingUrl,
                image_url: item.imageUrl,
                lot_number: normalizeText(item.lotNumber),
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
                inlineListings.push(listing);
            }
            totalFound++;
        }
        for (const listing of inlineListings) {
            await Actor.pushData(listing);
        }

        const uniqueLinks = [...new Set(listings.map((item) => item.listingUrl).filter(Boolean))];
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

async function handleDetailPage(page, request, log) {
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(2000);

    const data = await page.evaluate(() => {
        const normalize = (value) => String(value ?? '').replace(/\s+/g, ' ').trim();
        const text = normalize(document.body?.innerText || '');
        const findLabelValue = (...patterns) => {
            for (const pattern of patterns) {
                const match = text.match(pattern);
                if (match?.[1]) return normalize(match[1]);
            }
            return '';
        };

        const title = normalize(
            document.querySelector('h1, [data-testid*="title"], .card-title, [class*="title"]')?.textContent ||
            document.title.split('|')[0]
        );
        const image = document.querySelector('img[src], img[data-src]');
        const lotNumber = findLabelValue(/lot#?\s*[:\-]?\s*([A-Za-z0-9-]+)/i);

        return {
            title,
            bidText: findLabelValue(/current\s*bid\s*[:\-]?\s*\$?([\d,]+(?:\.\d+)?)/i, /high\s*bid\s*[:\-]?\s*\$?([\d,]+(?:\.\d+)?)/i),
            buyNowText: findLabelValue(/buy(?:\s+it)?\s*now\s*[:\-]?\s*\$?([\d,]+(?:\.\d+)?)/i),
            location: findLabelValue(/location\s*[:\-]?\s*([A-Za-z0-9 .,'-]+,\s*[A-Z]{2}(?:\s+\d{5})?)/i, /([A-Za-z .'-]+,\s*[A-Z]{2})(?:\s+\d{5})?/i),
            endText: findLabelValue(/(?:auction\s+)?(?:end|ends|close|closes)\s*[:\-]?\s*([A-Za-z0-9,:/ \-]+(?:AM|PM|UTC)?)/i),
            imageUrl: image?.getAttribute('src') || image?.getAttribute('data-src') || null,
            lotNumber,
            bodyText: text,
        };
    });

    const title = data.title;

    if (!title) {
        log.debug(`[SKIP] No title: ${request.url}`);
        return;
    }

    // ID from URL
    const idMatch = request.url.match(/\/lots?\/([a-z0-9\-]+)/i) ||
                    request.url.match(/\/auctions?\/([a-z0-9\-]+)/i) ||
                    request.url.match(/\/en\/asset\/(\d+\/\d+)/i) ||
                    request.url.match(/[Ll]ot[Ii]d=([a-z0-9\-]+)/i);
    const itemId = idMatch ? idMatch[1] : `allsurplus-${Date.now()}`;

    // Description for mileage/VIN
    const description = normalizeText(data.bodyText);
    const mileageMatch = description.match(/(\d[\d,]+)\s*(?:miles?|mi\.?)\b/i);
    const mileage = mileageMatch ? parseInt(mileageMatch[1].replace(/,/g, '')) : null;
    const vinMatch = description.match(/\bVIN[:\s#]*([A-HJ-NPR-Z0-9]{17})\b/i) ||
                     description.match(/\b([A-HJ-NPR-Z0-9]{17})\b/);
    const vin = vinMatch ? vinMatch[1] : null;

    const bid = parseBid(data.bidText);
    const buyNow = parseBid(data.buyNowText) || null;
    const state = parseState(data.location);
    const { year, make, model } = parseVehicleTitle(title);

    const listing = {
        listing_id: itemId,
        title,
        current_bid: bid,
        buy_now_price: buyNow,
        auction_end_date: parseDate(data.endText),
        state,
        listing_url: request.url,
        image_url: data.imageUrl,
        lot_number: data.lotNumber,
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
    await crawler.run(
        WEB_SEARCH_URLS.map((url, index) => ({
            url,
            label: 'LIST',
            userData: { pageNum: 1 },
            uniqueKey: `allsurplus-search-${index}`,
        }))
    );
}

console.log(`[ALLSURPLUS COMPLETE] Used API: ${usedApi} | Found: ${totalFound} | Passed filters: ${totalAfterFilters}`);

await Actor.exit();
