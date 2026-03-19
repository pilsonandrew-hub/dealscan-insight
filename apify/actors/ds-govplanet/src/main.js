import { Actor } from 'apify';
import { CheerioCrawler } from 'crawlee';

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
const REQUEST_DELAY_MS = 2500;

await Actor.init();

const input = await Actor.getInput() ?? {};
const {
    maxPages = 10,
    minBid = 500,
    maxBid = 35000,
} = input;

const seenListingUrls = new Set();
const enqueuedListingUrls = new Set();
const discoveredCategoryUrls = new Set();
const sampleLocations = [];

let totalFound = 0;
let totalPassed = 0;
let lastRequestStartedAt = 0;

function normalizeText(value) {
    return String(value ?? '').replace(/\s+/g, ' ').trim();
}

function recordLocationSample(locationText) {
    const normalized = normalizeText(locationText);
    if (!normalized || sampleLocations.includes(normalized) || sampleLocations.length >= 5) return;
    sampleLocations.push(normalized);
}

async function throttleRequests() {
    const waitMs = lastRequestStartedAt ? Math.max(0, REQUEST_DELAY_MS - (Date.now() - lastRequestStartedAt)) : 0;
    if (waitMs > 0) {
        await new Promise((resolve) => setTimeout(resolve, waitMs));
    }
    lastRequestStartedAt = Date.now();
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

function extractState(value) {
    const text = normalizeText(value).toUpperCase();
    if (!text) return '';

    const match = text.match(/,\s*([A-Z]{2})(?:\s+\d{5})?\b/)
        ?? text.match(/\b([A-Z]{2})\s+\d{5}\b/)
        ?? text.match(/\b([A-Z]{2})\b$/);
    const state = match?.[1] ?? '';
    return US_STATES.has(state) ? state : '';
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
    if (HIGH_RUST.has(state)) return false;
    if (year && year < 1980) return false;
    if (year && (new Date().getFullYear() - year) > 12) return false;
    if (bid < minBid || bid > maxBid) return false;
    return true;
}

function findLabelValue($, labels) {
    for (const selector of ['th', 'td', 'dt', 'label', '.label', '[class*="label"]', 'strong']) {
        const nodes = $(selector).toArray();
        for (const node of nodes) {
            const text = normalizeText($(node).text()).toLowerCase();
            if (!text) continue;
            if (!labels.some((label) => text.includes(label))) continue;

            const adjacent = normalizeText($(node).next('td, dd, div, span').first().text());
            if (adjacent) return adjacent;

            const parentText = normalizeText($(node).parent().text());
            if (parentText && parentText.toLowerCase() !== text) return parentText;
        }
    }
    return '';
}

function extractCategoryRequests($) {
    const requests = [];

    $('a[href*="/jsp/s/search.ips?"]').each((_, element) => {
        const href = $(element).attr('href');
        const url = toAbsoluteUrl(href);
        if (!url || discoveredCategoryUrls.has(url)) return;

        const text = normalizeText($(element).text());
        const haystack = `${text} ${url}`.toLowerCase();
        if (!haystack.includes('ct=13')) return;
        if (!/(passenger|sedan|car|suv|sport utility|crossover|pickup|crew cab)/.test(haystack)) return;
        if (COMMERCIAL_PATTERN.test(haystack)) return;

        discoveredCategoryUrls.add(url);
        requests.push({
            url,
            uniqueKey: `govplanet-category:${url}`,
            userData: {
                label: 'LIST',
                pageNum: 1,
                category: text || 'discovered',
                discoveredFromRoot: true,
            },
        });
    });

    return requests;
}

function extractSearchListings($) {
    const listings = [];
    const seenUrlsOnPage = new Set();

    const cards = $('.sr_list_item, .featured-item, .searchResults .featured-item, .searchResults .searchResult, .searchResults li, .searchResults article');
    const cardNodes = cards.length ? cards.toArray() : $('a[href*="/for-sale/"]').toArray().map((link) => $(link).closest('li, article, .sr_list_item, .featured-item').get(0)).filter(Boolean);

    for (const node of cardNodes) {
        const card = $(node);
        const link = card.find('.itemTitle a[href*="/for-sale/"], a[href*="/for-sale/"]').first();
        const listingUrl = toAbsoluteUrl(link.attr('href'));
        if (!listingUrl || seenUrlsOnPage.has(listingUrl)) continue;
        seenUrlsOnPage.add(listingUrl);

        const title = normalizeText(link.text())
            || normalizeText(card.find('h1, h2, h3, h4, [class*="title"]').first().text());
        if (!title) continue;

        const bidText = normalizeText(
            card.find('.sr_price, .pdprice, .price, [class*="price"], [class*="Price"], [class*="bid"], [class*="Bid"]').first().text(),
        );
        const locationText = normalizeText(
            card.find('.sr_location, .sr_current_location, .itemLocation, .location, [class*="location"], [class*="Location"]').first().text(),
        ) || normalizeText(card.text());
        recordLocationSample(locationText);
        const endText = normalizeText(
            card.find('.timeLeft, .timeRemaining, [class*="time"], [class*="Time"], [class*="close"], [class*="Close"]').first().text(),
        );
        const imageUrl = toAbsoluteUrl(
            card.find('img').first().attr('src')
            || card.find('img').first().attr('data-src')
            || '',
        );

        listings.push({
            title,
            current_bid: parseBid(bidText),
            state: extractState(locationText),
            city: extractCity(locationText),
            auction_end_time: parseDate(endText),
            listing_url: listingUrl,
            photo_url: imageUrl || null,
        });
    }

    return listings;
}

function findNextPageUrl($, currentUrl) {
    const explicitNext = $('a[rel="next"], a:contains("Next"), a:contains("next")').first().attr('href');
    if (explicitNext) return toAbsoluteUrl(explicitNext);

    const current = new URL(currentUrl);
    const currentStart = parseInt(current.searchParams.get('pstart') || '0', 10);
    let nextUrl = '';

    $('a[href*="pstart="]').each((_, element) => {
        if (nextUrl) return;
        const href = $(element).attr('href');
        const absolute = toAbsoluteUrl(href);
        if (!absolute) return;

        const candidate = new URL(absolute);
        const start = parseInt(candidate.searchParams.get('pstart') || '0', 10);
        if (start > currentStart) {
            nextUrl = absolute;
        }
    });

    return nextUrl;
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

const crawler = new CheerioCrawler({
    maxRequestsPerCrawl: maxPages * 250,
    maxConcurrency: 1,
    minConcurrency: 1,
    requestHandlerTimeoutSecs: 180,

    async requestHandler({ $, request, log }) {
        await throttleRequests();
        const label = request.userData.label || 'LIST';

        if (label === 'DETAIL') {
            const partial = request.userData.partial || {};
            const bodyText = normalizeText($('body').text());
            const title = normalizeText(
                $('h1, .itemTitle, [class*="hero-title"], meta[property="og:title"]').first().text()
                || $('meta[property="og:title"]').attr('content'),
            ) || partial.title;

            const currentBidText = findLabelValue($, ['current bid']) || bodyText.match(/Current Bid[^$]*\$[\d,]+(?:\.\d+)?/i)?.[0] || '';
            const closingText = findLabelValue($, ['closing time', 'close time', 'auction end', 'ends'])
                || bodyText.match(/(Closing Time|Auction End|Ends)[^A-Z0-9]{0,8}[A-Za-z]{3,9}[^.|\n]+\d{4}(?:[^.|\n]+(?:AM|PM))?/i)?.[0]
                || '';
            const locationText = findLabelValue($, ['item location', 'located in', 'location'])
                || bodyText.match(/(Item Location|Located in|Location)[^A-Z0-9]{0,8}[^.|\n]+,\s*[A-Z]{2}(?:\s+\d{5})?/i)?.[0]
                || '';
            const vin = bodyText.match(/\bVIN[:\s#-]*([A-HJ-NPR-Z0-9]{17})\b/i)?.[1] || null;
            const mileageMatch = bodyText.match(/(\d[\d,]+)\s*(miles?|mi\.?|odometer)\b/i);
            const imageUrl = toAbsoluteUrl(
                $('meta[property="og:image"]').attr('content')
                || $('img[src]').first().attr('src')
                || $('img[data-src]').first().attr('data-src')
                || '',
            );

            const detail = {
                title,
                year: extractYear(title),
                make: extractMake(title),
                model: null,
                current_bid: parseBid(currentBidText),
                auction_end_time: parseDate(closingText),
                location: locationText,
                state: extractState(locationText),
                city: extractCity(locationText),
                photo_url: imageUrl || null,
                vin,
                mileage: mileageMatch ? parseInt(mileageMatch[1].replace(/,/g, ''), 10) : null,
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

        if (request.userData.pageNum === 1) {
            const categoryRequests = extractCategoryRequests($);
            if (categoryRequests.length > 0) {
                await crawler.addRequests(categoryRequests);
                log.info(`[GOVPLANET] Discovered ${categoryRequests.length} passenger category URLs`);
            }
        }

        const listings = extractSearchListings($);
        log.info(`[GOVPLANET] Found ${listings.length} listing cards on ${request.url}`);

        const detailRequests = [];
        for (const partial of listings) {
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

        const nextUrl = findNextPageUrl($, request.url);
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
