import { Actor } from 'apify';
import { PlaywrightCrawler } from 'crawlee';

const SOURCE = 'govplanet';
const BASE = 'https://www.govplanet.com';
const VEHICLES_URL = `${BASE}/jsp/s/search.ips?ct=13`;

const HIGH_RUST = new Set([
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

const MAKES = new Set([
    'ford', 'chevrolet', 'chevy', 'dodge', 'ram', 'toyota', 'honda', 'nissan', 'jeep', 'gmc',
    'chrysler', 'hyundai', 'kia', 'subaru', 'mazda', 'volkswagen', 'vw', 'bmw', 'mercedes',
    'audi', 'lexus', 'acura', 'infiniti', 'cadillac', 'lincoln', 'buick', 'pontiac',
    'mitsubishi', 'volvo', 'tesla', 'saturn', 'isuzu', 'hummer', 'land rover', 'mini',
]);

const PASSENGER_KEYWORDS = [
    'passenger', 'sedan', 'coupe', 'hatchback', 'wagon', 'convertible', 'crossover', 'suv',
    'sport utility', 'crew cab', 'pickup', 'truck', 'car', '4x4', 'awd', 'minivan', 'van',
];

const COMMERCIAL_PATTERN = /\b(cargo van|cargo truck|cutaway|chassis cab|box truck|stake bed|dump truck|flatbed|refuse|crane truck|utility body|work van|sprinter cargo|step van|panel van|ambulance|fire truck|bucket truck|aerial lift|sewer|sweeper|plow truck|tractor|forklift|loader|backhoe|excavator|grader|boat|trailer|motorcycle|atv|utv|rv|camper)\b/i;

await Actor.init();

const input = await Actor.getInput() ?? {};
const {
    maxPages = 3,
    minBid = 500,
    maxBid = 35000,
} = input;

const seenListingUrls = new Set();
const enqueuedListingUrls = new Set();
const discoveredCategoryUrls = new Set();
const sampleLocations = [];

let totalFound = 0;
let totalPassed = 0;

function normalizeText(value) {
    return String(value ?? '').replace(/\s+/g, ' ').trim();
}

function recordLocationSample(locationText) {
    const normalized = normalizeText(locationText);
    if (!normalized || sampleLocations.includes(normalized) || sampleLocations.length >= 5) return;
    sampleLocations.push(normalized);
}

function toAbsoluteUrl(href) {
    if (!href) return '';
    try {
        return new URL(href, BASE).toString();
    } catch {
        return '';
    }
}

function parseBid(value) {
    if (typeof value === 'number') return value;
    const text = normalizeText(value).replace(/,/g, '');
    const match = text.match(/\$?\s*([\d]+(?:\.\d+)?)/);
    return match ? parseFloat(match[1]) : 0;
}

function parseDate(value) {
    const text = normalizeText(value)
        .replace(/^(closing time|close time|auction end|ends?|end date|time remaining)\s*:?\s*/i, '');
    if (!text) return null;

    const monthMatch = text.match(/([A-Z][a-z]{2,8}\s+\d{1,2},?\s+\d{4}(?:\s+\d{1,2}:\d{2}\s*[AP]M)?)\b/);
    const numericMatch = text.match(/(\d{1,2}\/\d{1,2}\/\d{4}(?:\s+\d{1,2}:\d{2}(?::\d{2})?\s*[AP]M?)?)/i);
    const candidate = monthMatch?.[1] ?? numericMatch?.[1] ?? text;
    const parsed = new Date(candidate);
    return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
}

const STATE_NAME_TO_ABBREV = {
    ALABAMA: 'AL', ALASKA: 'AK', ARIZONA: 'AZ', ARKANSAS: 'AR', CALIFORNIA: 'CA',
    COLORADO: 'CO', CONNECTICUT: 'CT', DELAWARE: 'DE', FLORIDA: 'FL', GEORGIA: 'GA',
    HAWAII: 'HI', IDAHO: 'ID', ILLINOIS: 'IL', INDIANA: 'IN', IOWA: 'IA',
    KANSAS: 'KS', KENTUCKY: 'KY', LOUISIANA: 'LA', MAINE: 'ME', MARYLAND: 'MD',
    MASSACHUSETTS: 'MA', MICHIGAN: 'MI', MINNESOTA: 'MN', MISSISSIPPI: 'MS', MISSOURI: 'MO',
    MONTANA: 'MT', NEBRASKA: 'NE', NEVADA: 'NV', 'NEW HAMPSHIRE': 'NH', 'NEW JERSEY': 'NJ',
    'NEW MEXICO': 'NM', 'NEW YORK': 'NY', 'NORTH CAROLINA': 'NC', 'NORTH DAKOTA': 'ND',
    OHIO: 'OH', OKLAHOMA: 'OK', OREGON: 'OR', PENNSYLVANIA: 'PA', 'RHODE ISLAND': 'RI',
    'SOUTH CAROLINA': 'SC', 'SOUTH DAKOTA': 'SD', TENNESSEE: 'TN', TEXAS: 'TX',
    UTAH: 'UT', VERMONT: 'VT', VIRGINIA: 'VA', WASHINGTON: 'WA', 'WEST VIRGINIA': 'WV',
    WISCONSIN: 'WI', WYOMING: 'WY', 'DISTRICT OF COLUMBIA': 'DC',
};

function extractState(value) {
    const text = normalizeText(value).toUpperCase();
    if (!text) return '';

    const match = text.match(/,\s*([A-Z]{2})(?:\s+\d{5})?\b/)
        ?? text.match(/\b([A-Z]{2})\s+\d{5}\b/)
        ?? text.match(/\b([A-Z]{2})\b$/);
    const abbrev = match?.[1] ?? '';
    if (US_STATES.has(abbrev)) return abbrev;

    for (const [name, code] of Object.entries(STATE_NAME_TO_ABBREV)) {
        if (text.includes(name)) return code;
    }
    return '';
}

function extractCity(value) {
    const text = normalizeText(value);
    const match = text.match(/^([^,]+),\s*[A-Z]{2}\b/);
    return match ? normalizeText(match[1]) : '';
}

function extractYear(text = '') {
    const match = normalizeText(text).match(/\b(19[89]\d|20[0-3]\d)\b/);
    return match ? parseInt(match[1], 10) : null;
}

function extractMake(title = '') {
    const lowerTitle = normalizeText(title).toLowerCase();
    for (const make of MAKES) {
        const pattern = new RegExp(`\\b${make.replace(/\s+/g, '\\s+')}\\b`, 'i');
        if (!pattern.test(lowerTitle)) continue;
        return make === 'chevy'
            ? 'Chevrolet'
            : make === 'vw'
                ? 'Volkswagen'
                : make.replace(/\b\w/g, (char) => char.toUpperCase());
    }
    return null;
}

function extractModel(title = '', make = '') {
    if (!make) return null;

    const normalizedTitle = normalizeText(title);
    const pattern = new RegExp(`\\b${make.replace(/\s+/g, '\\s+')}\\b`, 'i');
    const match = normalizedTitle.match(pattern);
    if (!match) return null;

    const afterMake = normalizedTitle.slice(match.index + match[0].length)
        .replace(/^[\s\-:]+/, '')
        .replace(/\b(4x4|awd|fwd|rwd|vin|odometer)\b.*$/i, '')
        .trim();
    const modelMatch = afterMake.match(/^([A-Za-z0-9][A-Za-z0-9\-]*(?:\s+[A-Za-z0-9][A-Za-z0-9\-]*)?)/);
    return modelMatch ? modelMatch[1] : null;
}

function isPassengerVehicle(title = '') {
    const normalizedTitle = normalizeText(title).toLowerCase();
    if (!normalizedTitle) return false;
    if (COMMERCIAL_PATTERN.test(normalizedTitle)) return false;

    return MAKES.has(normalizedTitle.split(' ')[1] ?? '')
        || [...MAKES].some((make) => normalizedTitle.includes(make))
        || PASSENGER_KEYWORDS.some((keyword) => normalizedTitle.includes(keyword));
}

function passesFilters({ title, year, bid, state }) {
    if (!title || !isPassengerVehicle(title)) return false;
    if (!state || !US_STATES.has(state)) return false;
    const currentYear = new Date().getFullYear();
    if (HIGH_RUST.has(state)) {
        if (!(year && year >= currentYear - 2)) return false;
        console.log(`[BYPASS] Rust state ${state} allowed — vehicle is ${year} (≤3yr old)`);
    }
    if (year && year < 1980) return false;
    if (year && (currentYear - year) > 12) return false;
    if (bid < minBid || bid > maxBid) return false;
    return true;
}

function buildRecord(detail, partial) {
    const title = normalizeText(detail.title || partial.title);
    const year = detail.year ?? extractYear(title);
    const make = detail.make || extractMake(title);
    const model = detail.model || extractModel(title, make || '');
    const currentBid = detail.current_bid || partial.current_bid || 0;
    const locationText = detail.location || `${partial.city ? `${partial.city}, ` : ''}${partial.state || ''}`;
    const state = detail.state || partial.state || extractState(locationText);
    const city = detail.city || partial.city || extractCity(locationText);

    return {
        title,
        year,
        make,
        model,
        current_bid: currentBid,
        state,
        city,
        auction_end_time: detail.auction_end_time || partial.auction_end_time || null,
        listing_url: partial.listing_url,
        photo_url: detail.photo_url || partial.photo_url || null,
        vin: detail.vin || null,
        mileage: detail.mileage || null,
        source_site: SOURCE,
        scraped_at: new Date().toISOString(),
    };
}

const crawler = new PlaywrightCrawler({
    maxRequestsPerCrawl: 30,
    maxConcurrency: 1,
    minConcurrency: 1,
    requestHandlerTimeoutSecs: 180,
    launchContext: {
        launchOptions: {
            args: ['--no-sandbox', '--disable-setuid-sandbox'],
        },
    },

    async requestHandler({ page, request, log }) {
        const label = request.userData.label || 'LIST';

        await page.waitForLoadState('domcontentloaded');
        await page.waitForTimeout(3000);

        if (label === 'DETAIL') {
            const partial = request.userData.partial || {};

            const rawDetail = await page.evaluate(() => {
                const findLabelValue = (labels) => {
                    const cells = [...document.querySelectorAll('th, td, dt, label, .label, [class*="label"], strong')];
                    for (const cell of cells) {
                        const text = (cell.textContent || '').trim().toLowerCase();
                        if (!labels.some((l) => text.includes(l))) continue;
                        const adj = cell.nextElementSibling;
                        if (adj?.textContent?.trim()) return adj.textContent.trim();
                        const parent = cell.parentElement;
                        const parentText = (parent?.textContent || '').trim();
                        if (parentText && parentText.toLowerCase() !== text) return parentText;
                    }
                    return '';
                };

                const bodyText = document.body?.innerText || '';
                const title = document.querySelector('h1, .itemTitle, [class*="hero-title"]')?.textContent?.trim()
                    || document.querySelector('meta[property="og:title"]')?.getAttribute('content') || '';

                const currentBidMatch = bodyText.match(/Current Bid[^$]*\$[\d,]+(?:\.\d+)?/i);
                const closingMatch = bodyText.match(/(Closing Time|Auction End|Ends)[^A-Z0-9]{0,8}[A-Za-z]{3,9}[^.|\n]+\d{4}(?:[^.|\n]+(?:AM|PM))?/i);
                const locationMatch = bodyText.match(/(Item Location|Located in|Location)[^A-Z0-9]{0,8}[^.|\n]+,\s*[A-Z]{2}(?:\s+\d{5})?/i);
                const vinMatch = bodyText.match(/\bVIN[:\s#-]*([A-HJ-NPR-Z0-9]{17})\b/i);
                const mileageMatch = bodyText.match(/(\d[\d,]+)\s*(miles?|mi\.?|odometer)\b/i);

                return {
                    title,
                    bodyText: bodyText.slice(0, 5000),
                    currentBidText: findLabelValue(['current bid']) || currentBidMatch?.[0] || '',
                    closingText: findLabelValue(['closing time', 'close time', 'auction end', 'ends']) || closingMatch?.[0] || '',
                    locationText: findLabelValue(['item location', 'located in', 'location']) || locationMatch?.[0] || '',
                    imageUrl: document.querySelector('meta[property="og:image"]')?.getAttribute('content')
                        || document.querySelector('img[src]')?.src || '',
                    vin: vinMatch?.[1] || null,
                    mileageStr: mileageMatch?.[1] || null,
                };
            });

            const detail = {
                title: rawDetail.title || partial.title,
                year: extractYear(rawDetail.title || partial.title || ''),
                make: extractMake(rawDetail.title || partial.title || ''),
                model: null,
                current_bid: parseBid(rawDetail.currentBidText),
                auction_end_time: parseDate(rawDetail.closingText),
                location: rawDetail.locationText,
                state: extractState(rawDetail.locationText),
                city: extractCity(rawDetail.locationText),
                photo_url: toAbsoluteUrl(rawDetail.imageUrl) || null,
                vin: rawDetail.vin || null,
                mileage: rawDetail.mileageStr ? parseInt(rawDetail.mileageStr.replace(/,/g, ''), 10) : null,
            };

            const record = buildRecord(detail, partial);
            totalFound += 1;

            if (!passesFilters({
                title: record.title,
                year: record.year,
                bid: record.current_bid,
                state: record.state,
            })) {
                return;
            }

            totalPassed += 1;
            await Actor.pushData(record);
            return;
        }

        log.info(`[GOVPLANET] Parsing search page ${request.url}`);

        // Extract category URLs (page 1 only)
        if (request.userData.pageNum === 1) {
            const categoryLinks = await page.evaluate(() => {
                return Array.from(document.querySelectorAll('a[href*="/jsp/s/search.ips?"]'))
                    .map((a) => ({ href: a.href, text: (a.textContent || '').trim() }));
            });

            const categoryRequests = [];
            for (const { href, text } of categoryLinks) {
                const url = href;
                if (!url || discoveredCategoryUrls.has(url)) continue;
                const haystack = `${text} ${url}`.toLowerCase();
                if (!haystack.includes('ct=13')) continue;
                if (!/(passenger|sedan|car|suv|sport utility|crossover|pickup|crew cab)/.test(haystack)) continue;
                if (COMMERCIAL_PATTERN.test(haystack)) continue;

                discoveredCategoryUrls.add(url);
                categoryRequests.push({
                    url,
                    uniqueKey: `govplanet-category:${url}`,
                    userData: {
                        label: 'LIST',
                        pageNum: 1,
                        category: text || 'discovered',
                        discoveredFromRoot: true,
                    },
                });
            }

            if (categoryRequests.length > 0) {
                await crawler.addRequests(categoryRequests);
                log.info(`[GOVPLANET] Discovered ${categoryRequests.length} passenger category URLs`);
            }
        }

        // Extract listing cards using multiple selectors
        const rawListings = await page.evaluate(() => {
            const SELECTORS = [
                '.sr_grid_tile', '.sr_item', '.sr_list_item', '.featured-item',
                '.lot-card', '.item-card', '.search-result-item', '.listing-item',
                '.product-card', '[data-testid="lot"]',
                '.searchResults .searchResult', '.searchResults li', '.searchResults article',
            ];

            let cards = [];
            let usedSelector = '';
            for (const sel of SELECTORS) {
                const found = document.querySelectorAll(sel);
                if (found.length > 0) {
                    cards = Array.from(found);
                    usedSelector = sel;
                    break;
                }
            }

            // Fallback: find all /for-sale/ links and climb to card parent
            if (cards.length === 0) {
                const links = document.querySelectorAll('a[href*="/for-sale/"]');
                const seen = new Set();
                for (const link of links) {
                    const parent = link.closest('li, article, [class*="item"], [class*="tile"], [class*="card"]') || link.parentElement;
                    if (parent && !seen.has(parent)) {
                        seen.add(parent);
                        cards.push(parent);
                    }
                }
                usedSelector = 'fallback-for-sale-links';
            }

            const results = [];
            const seenUrls = new Set();

            for (const card of cards) {
                const link = card.querySelector('a[href*="/for-sale/"]');
                if (!link) continue;
                const href = link.href;
                if (!href || seenUrls.has(href)) continue;
                seenUrls.add(href);

                const title = (link.textContent || '').trim()
                    || card.querySelector('h1, h2, h3, h4, [class*="title"]')?.textContent?.trim() || '';

                const priceEl = card.querySelector(
                    '.sr_price, .pdprice, .price, [class*="price"], [class*="Price"], [class*="bid"], [class*="Bid"]',
                );
                const locationEl = card.querySelector(
                    '.sr_location, .sr_current_location, .itemLocation, .location, [class*="location"], [class*="Location"]',
                );
                const timeEl = card.querySelector(
                    '.timeLeft, .timeRemaining, [class*="time"], [class*="Time"], [class*="close"], [class*="Close"]',
                );
                const imgEl = card.querySelector('img');

                results.push({
                    title,
                    bidText: priceEl?.textContent?.trim() || '',
                    locationText: locationEl?.textContent?.trim() || '',
                    endText: timeEl?.textContent?.trim() || '',
                    imageUrl: imgEl?.src || imgEl?.dataset?.src || '',
                    listingUrl: href,
                });
            }

            return { results, usedSelector, totalCards: cards.length };
        });

        log.info(`[GOVPLANET] Found ${rawListings.results.length} listing cards (selector: ${rawListings.usedSelector}, total card nodes: ${rawListings.totalCards}) on ${request.url}`);

        const detailRequests = [];
        for (const raw of rawListings.results) {
            const partial = {
                title: raw.title,
                current_bid: parseBid(raw.bidText),
                state: extractState(raw.locationText),
                city: extractCity(raw.locationText),
                auction_end_time: parseDate(raw.endText),
                listing_url: raw.listingUrl,
                photo_url: toAbsoluteUrl(raw.imageUrl) || null,
            };
            recordLocationSample(raw.locationText);

            if (!partial.listing_url || enqueuedListingUrls.has(partial.listing_url)) continue;
            enqueuedListingUrls.add(partial.listing_url);

            detailRequests.push({
                url: partial.listing_url,
                uniqueKey: `govplanet-detail:${partial.listing_url}`,
                userData: {
                    label: 'DETAIL',
                    partial,
                },
            });
        }

        if (detailRequests.length > 0) {
            await crawler.addRequests(detailRequests);
        }

        const currentPage = request.userData.pageNum || 1;
        if (currentPage >= maxPages) return;

        // Find next page URL
        const nextUrl = await page.evaluate((currentUrl) => {
            const nextLink = document.querySelector('a[rel="next"]')
                ?? [...document.querySelectorAll('a')].find((a) => /^\s*next\s*$/i.test(a.textContent || ''));
            if (nextLink?.href) return nextLink.href;

            try {
                const current = new URL(currentUrl);
                const currentStart = parseInt(current.searchParams.get('pstart') || '0', 10);
                for (const a of document.querySelectorAll('a[href*="pstart="]')) {
                    try {
                        const url = new URL(a.href);
                        const start = parseInt(url.searchParams.get('pstart') || '0', 10);
                        if (start > currentStart) return a.href;
                    } catch { /* skip */ }
                }
            } catch { /* skip */ }
            return '';
        }, request.url);

        if (!nextUrl) return;

        const nextPageKey = `govplanet-list:${request.userData.category || 'root'}:${nextUrl}`;
        if (seenListingUrls.has(nextPageKey)) return;
        seenListingUrls.add(nextPageKey);

        await crawler.addRequests([{
            url: nextUrl,
            uniqueKey: nextPageKey,
            userData: {
                label: 'LIST',
                pageNum: currentPage + 1,
                category: request.userData.category || 'vehicles',
            },
        }]);
    },
});

await crawler.run([{
    url: VEHICLES_URL,
    uniqueKey: 'govplanet-root-vehicles',
    userData: {
        label: 'LIST',
        pageNum: 1,
        category: 'vehicles',
    },
}]);

console.log('[GOVPLANET] Sample locations:', sampleLocations);
console.log(`[GOVPLANET] Found: ${totalFound} | Passed: ${totalPassed}`);
await Actor.exit();
