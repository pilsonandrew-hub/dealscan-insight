import { Actor } from 'apify';
import { PlaywrightCrawler } from 'crawlee';

const SOURCE = 'bidspotter';
const BASE = 'https://www.bidspotter.com';
const START_URL = `${BASE}/en-us/for-sale/automotive-and-vehicles`;
const STEALTH_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36';

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

const crawler = new PlaywrightCrawler({
    maxRequestsPerCrawl: maxPages * 50,
    maxConcurrency: 1,

    launchContext: {
        launchOptions: {
            headless: true,
            args: [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-blink-features=AutomationControlled',
            ],
        },
    },

    preNavigationHooks: [
        async ({ page }) => {
            await page.setExtraHTTPHeaders({
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache',
                'Sec-CH-UA': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                'Sec-CH-UA-Mobile': '?0',
                'Sec-CH-UA-Platform': '"Windows"',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Upgrade-Insecure-Requests': '1',
            });
            await page.setExtraHTTPHeaders({ 'User-Agent': STEALTH_UA });
        },
    ],

    async requestHandler({ page, request, log, enqueueLinks }) {
        const label = request.userData.label || 'LIST';

        // Override navigator.webdriver to evade detection
        await page.addInitScript(() => {
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        });

        // Wait past Cloudflare challenge / initial load
        await page.waitForLoadState('networkidle').catch(() => {});
        await new Promise((r) => setTimeout(r, 3000));

        // Check if still on Cloudflare waiting room
        const pageTitle = await page.title();
        if (pageTitle.toLowerCase().includes('just a moment') || pageTitle.toLowerCase().includes('checking')) {
            log.warning(`[BIDSPOTTER] Cloudflare challenge detected on ${request.url}, waiting 10s...`);
            await new Promise((r) => setTimeout(r, 10000));
            await page.waitForLoadState('networkidle').catch(() => {});
        }

        if (label === 'DETAIL') {
            const partial = request.userData.partial || {};

            const title = normalizeText(await page.$eval(
                'h1, .lot-title, .item-title, [class*="lotTitle"], [class*="itemTitle"]',
                (el) => el.textContent,
            ).catch(() => partial.title || ''));

            const bidText = normalizeText(await page.$eval(
                '.current-bid, .bid-amount, [class*="currentBid"], [class*="bidAmount"], [class*="current-bid"], [data-testid="current-bid"]',
                (el) => el.textContent,
            ).catch(() => ''));

            const endDateText = normalizeText(await page.$eval(
                '.auction-end, .closing-time, [class*="auctionEnd"], [class*="closingTime"], [class*="end-date"], [data-testid="end-date"]',
                (el) => el.textContent,
            ).catch(() => ''));

            const locationText = normalizeText(await page.$eval(
                '.location, .item-location, [class*="location"], [class*="Location"]',
                (el) => el.textContent,
            ).catch(() => partial.location || ''));

            const bodyText = await page.evaluate(() => document.body.innerText);
            const mileageMatch = bodyText.match(/(\d[\d,]+)\s*(miles?|mi\.?|odometer)\b/i);
            const mileage = mileageMatch ? parseInt(mileageMatch[1].replace(/,/g, ''), 10) : null;
            const vin = bodyText.match(/\bVIN[:\s#-]*([A-HJ-NPR-Z0-9]{17})\b/i)?.[1] || null;

            const photoUrl = await page.$eval(
                'meta[property="og:image"]', (el) => el.content,
            ).catch(() => null);

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
                photo_url: photoUrl || null,
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
            return;
        }

        // LIST page
        const pageNum = request.userData.pageNum || 1;
        log.info(`[BIDSPOTTER] Parsing list page ${pageNum}: ${request.url}`);

        // Try multiple selectors for lot cards
        const lotSelectors = [
            '.lot-tile', '.lot-card', '.auction-item', '[data-testid="lot"]',
            '[class*="lot-tile"]', '[class*="lotTile"]', '[class*="lot-card"]', '[class*="lotCard"]',
            '[class*="auction-item"]', '[class*="auctionItem"]',
        ];

        let cards = [];
        for (const selector of lotSelectors) {
            const found = await page.$$(selector);
            if (found.length > 0) {
                log.info(`[BIDSPOTTER] Found ${found.length} cards with selector: ${selector}`);
                cards = found;
                break;
            }
        }

        // Fallback: find divs containing both a link and a price-like element
        if (cards.length === 0) {
            log.warning('[BIDSPOTTER] No cards found with primary selectors, trying fallback div scan');
            cards = await page.$$('div:has(a):has([class*="price"]), div:has(a):has([class*="bid"])');
        }

        if (cards.length === 0) {
            log.warning(`[BIDSPOTTER] No listing cards found on page ${pageNum}. Dumping HTML snippet for debugging.`);
            const snippet = await page.evaluate(() => document.body.innerHTML.slice(0, 2000));
            log.info(`[BIDSPOTTER] HTML snippet: ${snippet}`);
        }

        for (const card of cards) {
            const linkEl = await card.$('a[href*="/en-us/auction"], a[href*="/lot/"], a[href*="/item/"], a[href]');
            const listingUrl = linkEl
                ? new URL(await linkEl.getAttribute('href'), BASE).toString()
                : null;

            if (!listingUrl || seenUrls.has(listingUrl)) continue;
            seenUrls.add(listingUrl);

            const titleText = normalizeText(await card.$eval(
                '[class*="title"], [class*="name"], h2, h3, h4, a',
                (el) => el.textContent,
            ).catch(() => ''));

            const bidText = normalizeText(await card.$eval(
                '[class*="price"], [class*="bid"], [class*="amount"]',
                (el) => el.textContent,
            ).catch(() => ''));

            const endDateText = normalizeText(await card.$eval(
                '[class*="end"], [class*="close"], [class*="time"]',
                (el) => el.textContent,
            ).catch(() => ''));

            const locationText = normalizeText(await card.$eval(
                '[class*="location"], [class*="state"], [class*="city"]',
                (el) => el.textContent,
            ).catch(() => ''));

            const partial = {
                title: titleText,
                current_bid: parseBid(bidText),
                auction_end_date: parseDate(endDateText),
                state: extractState(locationText),
                location: locationText,
                listing_url: listingUrl,
            };

            await crawler.addRequests([{
                url: listingUrl,
                uniqueKey: `bidspotter-detail:${listingUrl}`,
                userData: { label: 'DETAIL', partial },
            }]);
        }

        // Pagination
        if (pageNum >= maxPages) return;

        // Try to find Next button
        const nextEl = await page.$('a[rel="next"], a:has-text("Next"), button:has-text("Next"), [aria-label="Next page"], [class*="next"]:not([class*="disabled"])');
        if (nextEl) {
            const nextHref = await nextEl.getAttribute('href');
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
            } else {
                // Button-based pagination — click it
                await nextEl.click();
                await page.waitForLoadState('networkidle').catch(() => {});
                await new Promise((r) => setTimeout(r, 2000));
                const newUrl = page.url();
                if (!seenUrls.has(newUrl) && newUrl !== request.url) {
                    seenUrls.add(newUrl);
                    await crawler.addRequests([{
                        url: newUrl,
                        uniqueKey: `bidspotter-list:p${pageNum + 1}:${newUrl}`,
                        userData: { label: 'LIST', pageNum: pageNum + 1 },
                    }]);
                }
            }
            return;
        }

        // Fallback: page number links
        const pageLinks = await page.$$('a[href*="page="], a[href*="p="], [class*="pagination"] a');
        for (const link of pageLinks) {
            const href = await link.getAttribute('href');
            if (!href) continue;
            const url = new URL(href, BASE).toString();
            if (seenUrls.has(url)) continue;
            const text = normalizeText(await link.textContent());
            const num = parseInt(text, 10);
            if (!isNaN(num) && num === pageNum + 1) {
                seenUrls.add(url);
                await crawler.addRequests([{
                    url,
                    uniqueKey: `bidspotter-list:p${num}:${url}`,
                    userData: { label: 'LIST', pageNum: num },
                }]);
                break;
            }
        }
    },
});

await crawler.run([{
    url: START_URL,
    uniqueKey: 'bidspotter-list:p1',
    userData: { label: 'LIST', pageNum: 1 },
}]);

console.log(`[BIDSPOTTER] Found: ${totalFound} | Passed filters: ${totalPassed}`);
await Actor.exit();
