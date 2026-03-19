console.log('[BIDSPOTTER] Actor starting...');
import { Actor } from 'apify';
import { HttpCrawler, createHttpRouter } from 'crawlee';
import * as cheerio from 'cheerio';

const SOURCE = 'bidspotter';
const BASE = 'https://www.bidspotter.com';
const START_URL = `${BASE}/en-us/for-sale/automotive-and-vehicles`;

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

const MAKES = new Set([
    'ford', 'chevrolet', 'chevy', 'dodge', 'ram', 'toyota', 'honda', 'nissan', 'jeep', 'gmc',
    'chrysler', 'hyundai', 'kia', 'subaru', 'mazda', 'volkswagen', 'vw', 'bmw', 'mercedes',
    'audi', 'lexus', 'acura', 'infiniti', 'cadillac', 'lincoln', 'buick', 'pontiac',
    'mitsubishi', 'volvo', 'tesla', 'saturn', 'isuzu', 'hummer', 'land rover', 'mini',
]);

const COMMERCIAL_PATTERN = /\b(cargo van|cargo truck|cutaway|chassis cab|box truck|stake bed|dump truck|flatbed|refuse|crane truck|utility body|work van|sprinter cargo|step van|panel van|ambulance|fire truck|bucket truck|aerial lift|sewer|sweeper|plow truck|tractor|forklift|loader|backhoe|excavator|grader|boat|trailer|motorcycle|atv|utv|rv|camper)\b/i;

await Actor.init();

const input = await Actor.getInput() ?? {};
const {
    maxPages = 10,
    maxPrice = 50000,
    maxMileage = 50000,
} = input;

let totalFound = 0;
let totalPassed = 0;
const seenUrls = new Set();

function normalizeText(value) {
    return String(value ?? '').replace(/\s+/g, ' ').trim();
}

function parseBid(value) {
    const text = normalizeText(value).replace(/,/g, '');
    const match = text.match(/\$?\s*([\d]+(?:\.\d+)?)/);
    return match ? parseFloat(match[1]) : 0;
}

function parseDate(value) {
    const text = normalizeText(value)
        .replace(/^(closing time|close time|auction end|ends?|end date|time remaining)\s*:?\s*/i, '');
    if (!text) return null;
    const parsed = new Date(text);
    return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
}

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

function extractYear(text = '') {
    const match = normalizeText(text).match(/\b(19[89]\d|20[0-3]\d)\b/);
    return match ? parseInt(match[1], 10) : null;
}

function extractMake(title = '') {
    const lower = normalizeText(title).toLowerCase();
    for (const make of MAKES) {
        const pattern = new RegExp(`\\b${make.replace(/\s+/g, '\\s+')}\\b`, 'i');
        if (!pattern.test(lower)) continue;
        return make === 'chevy' ? 'Chevrolet' : make === 'vw' ? 'Volkswagen'
            : make.replace(/\b\w/g, (c) => c.toUpperCase());
    }
    return null;
}

function extractModel(title = '', make = '') {
    if (!make) return null;
    const pattern = new RegExp(`\\b${make.replace(/\s+/g, '\\s+')}\\b`, 'i');
    const match = normalizeText(title).match(pattern);
    if (!match) return null;
    const afterMake = normalizeText(title).slice(match.index + match[0].length)
        .replace(/^[\s\-:]+/, '').replace(/\b(4x4|awd|fwd|rwd|vin|odometer)\b.*$/i, '').trim();
    const modelMatch = afterMake.match(/^([A-Za-z0-9][A-Za-z0-9\-]*(?:\s+[A-Za-z0-9][A-Za-z0-9\-]*)?)/);
    return modelMatch ? modelMatch[1] : null;
}

function isPassengerVehicle(title = '') {
    const lower = normalizeText(title).toLowerCase();
    if (!lower) return false;
    if (COMMERCIAL_PATTERN.test(lower)) return false;
    return [...MAKES].some((make) => lower.includes(make))
        || /\b(passenger|sedan|coupe|hatchback|wagon|suv|sport utility|pickup|truck|crossover|minivan)\b/.test(lower);
}

function passesFilters({ title, bid, state, mileage }) {
    if (!title || !isPassengerVehicle(title)) return false;
    if (!state || !US_STATES.has(state)) return false;
    if (HIGH_RUST.has(state)) return false;
    if (bid > 0 && bid > maxPrice) return false;
    if (mileage && mileage > maxMileage) return false;
    return true;
}

const router = createHttpRouter();

router.addHandler('DETAIL', async ({ body, request, log }) => {
    const $ = cheerio.load(body);

    // Check for CAPTCHA/block page
    const bodyText = $.text();
    const titleText = $('title').text();
    if (titleText.toLowerCase().includes('just a moment') || $('form#challenge-form').length > 0) {
        log.warning(`[BIDSPOTTER] Cloudflare challenge on detail page: ${request.url}`);
        return;
    }

    const partial = request.userData.partial || {};

    const title = normalizeText(
        $('h1, .lot-title, .item-title, [class*="lotTitle"], [class*="itemTitle"]').first().text()
    ) || partial.title || '';

    const bidText = normalizeText(
        $('.current-bid, .bid-amount, [class*="currentBid"], [class*="bidAmount"], [class*="current-bid"], [data-testid="current-bid"]').first().text()
    );

    const endDateText = normalizeText(
        $('.auction-end, .closing-time, [class*="auctionEnd"], [class*="closingTime"], [class*="end-date"], [data-testid="end-date"]').first().text()
    );

    const locationText = normalizeText(
        $('.location, .item-location, [class*="location"], [class*="Location"]').first().text()
    ) || partial.location || '';

    const mileageMatch = bodyText.match(/(\d[\d,]+)\s*(miles?|mi\.?|odometer)\b/i);
    const mileage = mileageMatch ? parseInt(mileageMatch[1].replace(/,/g, ''), 10) : null;
    const vin = bodyText.match(/\bVIN[:\s#-]*([A-HJ-NPR-Z0-9]{17})\b/i)?.[1] || null;

    const photoUrl = $('meta[property="og:image"]').attr('content') || null;

    const currentBid = parseBid(bidText) || partial.current_bid || 0;
    const state = extractState(locationText) || partial.state || '';
    const finalTitle = title || partial.title || '';
    const make = extractMake(finalTitle);

    const record = {
        title: finalTitle,
        year: extractYear(finalTitle),
        make,
        model: extractModel(finalTitle, make || ''),
        current_bid: currentBid,
        auction_end_date: parseDate(endDateText) || partial.auction_end_date || null,
        state,
        location: locationText || partial.location || '',
        listing_url: partial.listing_url || request.url,
        photo_url: photoUrl,
        vin,
        mileage,
        source: SOURCE,
        scraped_at: new Date().toISOString(),
    };

    totalFound += 1;

    if (!passesFilters({ title: record.title, bid: record.current_bid, state: record.state, mileage: record.mileage })) {
        log.debug(`[BIDSPOTTER] Filtered: ${record.title} | state=${record.state} | bid=${record.current_bid}`);
        return;
    }

    totalPassed += 1;
    await Actor.pushData(record);
});

router.addDefaultHandler(async ({ body, request, log, crawler }) => {
    const $ = cheerio.load(body);

    // Check for CAPTCHA/block page
    const titleText = $('title').text();
    if (titleText.toLowerCase().includes('just a moment') || $('form#challenge-form').length > 0) {
        log.warning(`[BIDSPOTTER] Cloudflare/CAPTCHA detected on list page: ${request.url}`);
        log.info(`[BIDSPOTTER] Page title: ${titleText}`);
        log.info(`[BIDSPOTTER] HTML snippet: ${$('body').html()?.slice(0, 2000)}`);
        return;
    }

    const pageNum = request.userData.pageNum || 1;
    log.info(`[BIDSPOTTER] Parsing list page ${pageNum}: ${request.url}`);

    // Try multiple card selectors in priority order
    const cardSelectors = [
        '.lot-tile', '.lot-card', '.auction-item', '[data-testid="lot"]',
        '[class*="lot-tile"]', '[class*="lotTile"]', '[class*="lot-card"]', '[class*="lotCard"]',
        '[class*="auction-item"]', '[class*="auctionItem"]',
        'article', '.item-card', '[class*="item-card"]',
    ];

    let cards = null;
    let usedSelector = null;
    for (const sel of cardSelectors) {
        const found = $(sel);
        if (found.length > 0) {
            cards = found;
            usedSelector = sel;
            log.info(`[BIDSPOTTER] Found ${found.length} cards with selector: ${sel}`);
            break;
        }
    }

    if (!cards || cards.length === 0) {
        log.warning('[BIDSPOTTER] No listing cards found. Dumping HTML snippet for debugging.');
        log.info(`[BIDSPOTTER] HTML snippet: ${$('body').html()?.slice(0, 3000)}`);
        return;
    }

    const detailRequests = [];
    cards.each((i, el) => {
        const card = $(el);

        const linkEl = card.find('a[href*="/en-us/auction"], a[href*="/lot/"], a[href*="/item/"], a[href]').first();
        const href = linkEl.attr('href');
        if (!href) return;

        const listingUrl = new URL(href, BASE).toString();
        if (seenUrls.has(listingUrl)) return;
        seenUrls.add(listingUrl);

        const titleText2 = normalizeText(
            card.find('[class*="title"], [class*="name"], h2, h3, h4, a').first().text()
        );
        const bidText = normalizeText(
            card.find('[class*="price"], [class*="bid"], [class*="amount"]').first().text()
        );
        const endDateText = normalizeText(
            card.find('[class*="end"], [class*="close"], [class*="time"]').first().text()
        );
        const locationText2 = normalizeText(
            card.find('[class*="location"], [class*="state"], [class*="city"]').first().text()
        );

        const partial = {
            title: titleText2,
            current_bid: parseBid(bidText),
            auction_end_date: parseDate(endDateText),
            state: extractState(locationText2),
            location: locationText2,
            listing_url: listingUrl,
        };

        detailRequests.push({
            url: listingUrl,
            uniqueKey: `bidspotter-detail:${listingUrl}`,
            label: 'DETAIL',
            userData: { label: 'DETAIL', partial },
        });
    });

    if (detailRequests.length > 0) {
        await crawler.addRequests(detailRequests);
        log.info(`[BIDSPOTTER] Enqueued ${detailRequests.length} detail requests`);
    }

    // Pagination
    if (pageNum >= maxPages) return;

    const nextHref = $('a[rel="next"], [class*="next"]:not([class*="disabled"]) a, [aria-label="Next page"]').first().attr('href')
        || $('a').filter((i, el) => $(el).text().trim().toLowerCase() === 'next').first().attr('href');

    if (nextHref) {
        const nextUrl = new URL(nextHref, BASE).toString();
        if (!seenUrls.has(nextUrl)) {
            seenUrls.add(nextUrl);
            await crawler.addRequests([{
                url: nextUrl,
                uniqueKey: `bidspotter-list:p${pageNum + 1}:${nextUrl}`,
                userData: { label: 'LIST', pageNum: pageNum + 1 },
            }]);
        }
        return;
    }

    // Fallback: numbered page links
    $('a[href*="page="], a[href*="p="], [class*="pagination"] a').each((i, el) => {
        const href2 = $(el).attr('href');
        if (!href2) return;
        const url = new URL(href2, BASE).toString();
        if (seenUrls.has(url)) return;
        const num = parseInt($(el).text().trim(), 10);
        if (!isNaN(num) && num === pageNum + 1) {
            seenUrls.add(url);
            crawler.addRequests([{
                url,
                uniqueKey: `bidspotter-list:p${num}:${url}`,
                userData: { label: 'LIST', pageNum: num },
            }]);
        }
    });
});

// Use residential proxies to bypass Cloudflare/CAPTCHA on BidSpotter
const proxyConfiguration = await Actor.createProxyConfiguration({
    groups: ['RESIDENTIAL'],
    countryCode: 'US',
});

const crawler = new HttpCrawler({
    requestHandler: router,
    maxRequestsPerCrawl: maxPages * 50,
    maxConcurrency: 2,
    additionalMimeTypes: ['text/html'],
    proxyConfiguration,
    preNavigationHooks: [
        async (_crawlingContext, gotOptions) => {
            gotOptions.headers = {
                ...gotOptions.headers,
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Referer': 'https://www.google.com/',
                'Upgrade-Insecure-Requests': '1',
            };
        },
    ],
});

await crawler.run([{
    url: START_URL,
    uniqueKey: 'bidspotter-list:p1',
    userData: { label: 'LIST', pageNum: 1 },
}]);

console.log(`[BIDSPOTTER] Found: ${totalFound} | Passed filters: ${totalPassed}`);
await Actor.exit();
