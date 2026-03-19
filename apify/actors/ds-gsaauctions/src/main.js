import { Actor } from 'apify';
import { PlaywrightCrawler } from 'crawlee';

const SOURCE = 'gsaauctions';
const BASE_URL = 'https://www.gsaauctions.gov';
const LIST_BASE = `${BASE_URL}/auctions/auctions-list`;
const LIST_PARAMS = 'size=50&status=active&sort=auctionEndDateSoon,DESC&categoryDescription=Vehicles%2C+Trailers%2C+Cycles';

const TARGET_STATES = new Set([
    'AZ', 'CA', 'NV', 'CO', 'NM', 'UT', 'TX', 'FL', 'GA', 'SC', 'TN', 'NC', 'VA', 'WA', 'OR', 'HI',
]);

const HIGH_RUST_STATES = new Set([
    'OH', 'MI', 'PA', 'NY', 'WI', 'MN', 'IL', 'IN', 'MO', 'IA',
    'ND', 'SD', 'NE', 'KS', 'WV', 'ME', 'NH', 'VT', 'MA', 'RI',
    'CT', 'NJ', 'MD', 'DE',
]);

const ALL_STATES = new Set([
    'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA', 'HI', 'ID', 'IL', 'IN', 'IA',
    'KS', 'KY', 'LA', 'ME', 'MD', 'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
    'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC', 'SD', 'TN', 'TX', 'UT', 'VT',
    'VA', 'WA', 'WV', 'WI', 'WY', 'DC',
]);

const MAKES = [
    'ford', 'chevrolet', 'chevy', 'dodge', 'ram', 'toyota', 'honda', 'nissan', 'jeep', 'gmc',
    'chrysler', 'hyundai', 'kia', 'subaru', 'mazda', 'volkswagen', 'vw', 'bmw', 'mercedes',
    'audi', 'lexus', 'acura', 'infiniti', 'cadillac', 'lincoln', 'buick', 'pontiac',
    'mitsubishi', 'volvo', 'tesla', 'mini', 'saturn', 'scion',
];

const PASSENGER_KEYWORDS = [
    'sedan', 'coupe', 'hatchback', 'wagon', 'convertible', 'cabriolet', 'roadster',
    'pickup', 'crew cab', 'extended cab', 'suv', 'sport utility', 'crossover',
    'minivan', 'passenger van', 'passenger wagon', 'car', 'truck', '4x4', 'awd', 'fwd', 'rwd',
];

const EXCLUDED_TITLE_PATTERN = /\b(forklift|tractor|loader|backhoe|excavator|grader|dozer|bulldozer|skid\s*steer|trencher|mower|generator|compressor|sprayer|sweeper|boat|marine|trailer|camper|rv|motorhome|jet\s*ski|snowmobile|motorcycle|atv|utv|golf\s*cart|bus|ambulance|fire\s*truck|dump\s*truck|flatbed|box\s*truck|cargo\s+van|step\s+van|cutaway|chassis\s+cab|stake\s*bed|semitrailer|furniture|desk|chair|cabinet)\b/i;

await Actor.init();

const input = await Actor.getInput() ?? {};
const {
    maxPages = 15,
    minBid = 1000,
    maxMileage = 50000,
    minYear = 2022,
    targetStates = [...TARGET_STATES],
} = input;

const targetStateSet = new Set(targetStates.map((state) => String(state).toUpperCase()));
const seenListings = new Set();

let totalFound = 0;
let totalAfterFilters = 0;

function normalizeText(value) {
    return String(value ?? '').replace(/\s+/g, ' ').trim();
}

function parseBid(value) {
    const match = normalizeText(value).replace(/,/g, '').match(/\$?\s*([\d]+(?:\.\d+)?)/);
    return match ? parseFloat(match[1]) : 0;
}

function parseDate(value) {
    const text = normalizeText(value)
        .replace(/^(ends?|closing|close\s+time|auction\s+end|end\s+date)\s*:?\s*/i, '')
        .replace(/\bat\b/i, ' ');
    if (!text) return null;

    const monthMatch = text.match(/([A-Z][a-z]{2,8}\s+\d{1,2},?\s+\d{4}(?:\s+\d{1,2}:\d{2}\s*[AP]M)?)\b/);
    const numericMatch = text.match(/(\d{1,2}\/\d{1,2}\/\d{4}(?:\s+\d{1,2}:\d{2}(?::\d{2})?\s*[AP]M?)?)/i);
    const candidate = monthMatch?.[1] ?? numericMatch?.[1] ?? text;
    const parsed = new Date(candidate);
    return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
}

function parseState(value) {
    const text = normalizeText(value).toUpperCase();
    if (!text) return null;

    const match = text.match(/,\s*([A-Z]{2})(?:\s+\d{5})?\b/)
        ?? text.match(/\b([A-Z]{2})\s+\d{5}\b/)
        ?? text.match(/\b([A-Z]{2})\b$/);
    const state = match?.[1];
    return state && ALL_STATES.has(state) ? state : null;
}

function parseCity(value) {
    const text = normalizeText(value).replace(/^location\s*:?\s*/i, '');
    const match = text.match(/^([^,]+),\s*[A-Z]{2}\b/i);
    return match ? normalizeText(match[1]) : null;
}

function parseVehicleTitle(title) {
    const normalizedTitle = normalizeText(title);
    const lowerTitle = normalizedTitle.toLowerCase();

    const yearMatch = normalizedTitle.match(/\b(19[89]\d|20[0-3]\d)\b/);
    const year = yearMatch ? parseInt(yearMatch[1], 10) : null;

    let make = null;
    let model = null;

    for (const candidate of MAKES) {
        const pattern = new RegExp(`\\b${candidate.replace(/\s+/g, '\\s+')}\\b`, 'i');
        const match = normalizedTitle.match(pattern);
        if (!match) continue;

        const canonicalMake = candidate === 'chevy'
            ? 'Chevrolet'
            : candidate === 'vw'
                ? 'Volkswagen'
                : candidate.replace(/\b\w/g, (char) => char.toUpperCase());
        make = canonicalMake;

        const afterMake = normalizedTitle.slice(match.index + match[0].length)
            .replace(/^[\s\-:]+/, '')
            .replace(/\b(4x4|awd|fwd|rwd|vin|odometer)\b.*$/i, '')
            .trim();
        const modelMatch = afterMake.match(/^([A-Za-z0-9][A-Za-z0-9\-]*(?:\s+[A-Za-z0-9][A-Za-z0-9\-]*)?)/);
        model = modelMatch ? modelMatch[1] : null;
        break;
    }

    return { year, make, model, lowerTitle };
}

function isPassengerVehicle(title) {
    const { lowerTitle } = parseVehicleTitle(title);
    if (!lowerTitle) return false;
    if (EXCLUDED_TITLE_PATTERN.test(lowerTitle)) return false;

    return MAKES.some((make) => lowerTitle.includes(make))
        || PASSENGER_KEYWORDS.some((keyword) => lowerTitle.includes(keyword));
}

function buildListing(rawListing) {
    const title = normalizeText(rawListing.title);
    const bid = parseBid(rawListing.bidText);
    const auctionEndDate = parseDate(rawListing.endText);
    const state = parseState(rawListing.location);
    const city = parseCity(rawListing.location);
    const { year, make, model } = parseVehicleTitle(title);
    const listingId = rawListing.listingUrl.match(/\/preview\/(\d+)/)?.[1]
        ?? rawListing.listingUrl.match(/\/(\d+)(?:\?|$)/)?.[1]
        ?? `gsa-${Buffer.from(rawListing.listingUrl).toString('base64').slice(0, 16)}`;

    return {
        listing_id: listingId,
        title,
        current_bid: bid,
        buy_now_price: null,
        auction_end_date: auctionEndDate,
        state,
        city,
        listing_url: rawListing.listingUrl,
        image_url: rawListing.imageUrl || null,
        mileage: null,
        vin: null,
        year,
        make,
        model,
        source_site: SOURCE,
        scraped_at: new Date().toISOString(),
    };
}

function applyFilters(listing, log) {
    if (!isPassengerVehicle(listing.title)) {
        log.debug(`[GSA] Skipping non-passenger listing: ${listing.title}`);
        return false;
    }

    if (listing.state && HIGH_RUST_STATES.has(listing.state)) {
        log.debug(`[GSA] Skipping high-rust state ${listing.state}: ${listing.title}`);
        return false;
    }

    if (listing.state && targetStateSet.size > 0 && !targetStateSet.has(listing.state)) {
        log.debug(`[GSA] Skipping out-of-target state ${listing.state}: ${listing.title}`);
        return false;
    }

    if (listing.current_bid > 0 && listing.current_bid < minBid) {
        log.debug(`[GSA] Skipping low bid ${listing.current_bid}: ${listing.title}`);
        return false;
    }

    if (listing.year && listing.year < minYear) {
        log.debug(`[GSA] Skipping old model year ${listing.year}: ${listing.title}`);
        return false;
    }

    if (listing.mileage && listing.mileage > maxMileage) {
        log.debug(`[GSA] Skipping high mileage ${listing.mileage}: ${listing.title}`);
        return false;
    }

    return true;
}

// Wait for Angular SPA to finish rendering. The site requires networkidle +
// an extra fixed delay for the framework to hydrate the DOM.
async function waitForAngular(page) {
    await page.waitForLoadState('domcontentloaded', { timeout: 30000 }).catch(() => {});
    await page.waitForLoadState('networkidle', { timeout: 25000 }).catch(() => {});
    await page.waitForTimeout(500);
}

// Extract each preview link together with the location text from its card on the list page.
// Returns [{ url, locationText }] for each unique preview link found.
async function extractCardsWithLocation(page) {
    return page.evaluate((baseUrl) => {
        const normalize = (v) => String(v ?? '').replace(/\s+/g, ' ').trim();
        const results = [];
        const seen = new Set();
        const anchors = document.querySelectorAll('a[href*="/auctions/preview/"]');

        for (const a of anchors) {
            try {
                const href = a.getAttribute('href');
                if (!href) continue;
                const url = new URL(href, baseUrl).toString();
                if (seen.has(url)) continue;
                seen.add(url);

                // Walk up the DOM to find the card container that includes a "Location" label.
                let card = a;
                for (let i = 0; i < 12; i++) {
                    if (!card.parentElement) break;
                    card = card.parentElement;
                    if (['li', 'article', 'section'].includes(card.tagName.toLowerCase())) break;
                    if (card.tagName.toLowerCase() === 'div' && /location/i.test(card.innerText)) break;
                }

                const lines = normalize(card.innerText)
                    .split(/\n+/)
                    .map(normalize)
                    .filter(Boolean);

                const locIdx = lines.findIndex((l) => /^location$/i.test(l));
                const locationText = (locIdx >= 0 && locIdx < lines.length - 1) ? lines[locIdx + 1] : '';

                results.push({ url, locationText });
            } catch {
                // ignore malformed hrefs
            }
        }
        return results;
    }, BASE_URL);
}

// Extract lot metadata from a detail page (/auctions/preview/{id}).
// The page renders as labeled sections: a label line followed by a value line.
// Known labels: "Lot Name", "Location", "Closing Date", "Current Bid".
async function extractDetailData(page) {
    return page.evaluate(() => {
        const normalize = (v) => String(v ?? '').replace(/\s+/g, ' ').trim();

        // Try structured selectors first.
        const getText = (...selectors) => {
            for (const sel of selectors) {
                const el = document.querySelector(sel);
                const text = normalize(el?.textContent);
                if (text) return text;
            }
            return '';
        };

        // Parse the page as a flat list of lines; find value that follows a label.
        const lines = normalize(document.body.innerText)
            .split(/\n+/)
            .map(normalize)
            .filter(Boolean);

        const getValueAfterLabel = (pattern) => {
            const idx = lines.findIndex((line) => pattern.test(line));
            return (idx >= 0 && idx < lines.length - 1) ? lines[idx + 1] : '';
        };

        const title = getText('h1', '[class*="lot-title"]', '[class*="lotTitle"]', '[class*="lot-name"]')
            || getValueAfterLabel(/^lot\s*name$/i)
            || getText('h2', 'h3');

        const location = getValueAfterLabel(/^location$/i)
            || getText('[class*="location"]');

        const closingDate = getValueAfterLabel(/^closing\s*date$/i)
            || getText('time', '[class*="closing"]', '[class*="end-date"]');

        const currentBid = getValueAfterLabel(/^current\s*bid$/i)
            || getText('[class*="current-bid"]', '[class*="currentBid"]');

        const img = document.querySelector('[class*="lot"] img, [class*="photo"] img, main img');
        const imageUrl = img?.getAttribute('src') || img?.getAttribute('data-src') || '';

        return { title, location, closingDate, currentBid, imageUrl };
    });
}

const crawler = new PlaywrightCrawler({
    // One list page + up to maxPages-1 additional pages + detail pages.
    maxRequestsPerCrawl: maxPages + 500,
    maxConcurrency: 1,
    requestHandlerTimeoutSecs: 120,
    launchContext: {
        launchOptions: {
            args: [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
            ],
        },
    },

    async requestHandler({ page, request, enqueueLinks, log }) {
        const label = request.label ?? 'LIST';

        if (label === 'DETAIL') {
            const url = page.url();
            log.info(`[GSA] Detail page: ${url}`);

            await waitForAngular(page);

            const data = await extractDetailData(page);

            if (!data.title) {
                log.warning(`[GSA] No title extracted from detail page: ${url}`);
                return;
            }

            totalFound += 1;

            const rawListing = {
                title: data.title,
                bidText: data.currentBid,
                endText: data.closingDate,
                location: data.location,
                listingUrl: url,
                imageUrl: data.imageUrl,
            };

            const listing = buildListing(rawListing);

            if (!applyFilters(listing, log)) return;

            const dedupeKey = listing.listing_id;
            if (seenListings.has(dedupeKey)) return;
            seenListings.add(dedupeKey);

            totalAfterFilters += 1;
            log.info(`[GSA] Queuing: ${listing.title} | $${listing.current_bid} | ${listing.state}`);
            await Actor.pushData(listing);
            return;
        }

        // LIST page handler
        const pageNum = request.userData?.pageNum ?? 1;
        log.info(`[GSA] List page ${pageNum}: ${page.url()}`);

        await waitForAngular(page);

        // Wait up to 10s for at least one preview link to appear.
        await page.locator('a[href*="/auctions/preview/"]').first()
            .waitFor({ state: 'visible', timeout: 10000 })
            .catch(() => {});

        const cards = await extractCardsWithLocation(page);
        log.info(`[GSA] Page ${pageNum}: found ${cards.length} cards`);

        if (!cards.length) {
            if (pageNum === 1) {
                log.warning('[GSA] No preview links on first page — check URL and Angular rendering');
            }
            return;
        }

        // Pre-filter by state on the list page to avoid visiting every detail page.
        const filteredUrls = [];
        for (const { url, locationText } of cards) {
            const state = parseState(locationText);
            if (!state) {
                // Could not determine state — include to let detail page decide.
                filteredUrls.push(url);
                continue;
            }
            if (HIGH_RUST_STATES.has(state)) {
                log.debug(`[GSA] Pre-filter: skipping high-rust state ${state} (${locationText})`);
                continue;
            }
            if (targetStateSet.size > 0 && !targetStateSet.has(state)) {
                log.debug(`[GSA] Pre-filter: skipping out-of-target state ${state} (${locationText})`);
                continue;
            }
            filteredUrls.push(url);
        }

        log.info(`[GSA] Page ${pageNum}: ${filteredUrls.length}/${cards.length} cards pass state pre-filter`);

        if (filteredUrls.length) {
            await enqueueLinks({ urls: filteredUrls, label: 'DETAIL' });
        }

        if (pageNum < maxPages) {
            const nextUrl = `${LIST_BASE}?page=${pageNum + 1}&${LIST_PARAMS}`;
            await enqueueLinks({
                urls: [nextUrl],
                label: 'LIST',
                userData: { pageNum: pageNum + 1 },
            });
        }
    },
});

const startUrl = `${LIST_BASE}?page=1&${LIST_PARAMS}`;
await crawler.run([{ url: startUrl, label: 'LIST', userData: { pageNum: 1 } }]);

console.log(`[GSA COMPLETE] Found: ${totalFound} | Passed filters: ${totalAfterFilters}`);
await Actor.exit();
