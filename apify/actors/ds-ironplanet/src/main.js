import { Actor } from 'apify';
import { PlaywrightCrawler } from 'crawlee';

// IronPlanet trucks & trailers category (ct=3)
// Search results API: /jsp/s/search.ips?mode=6&ct=3&format=json
// Pagination via pstart=60, pstart=120, etc. (60 items per page)
// NOTE: mode=6 JSON API requires a valid browser session (cookies) — we use Playwright
// to load the first page, which sets session cookies, then call the JSON API via page.evaluate/fetch.

const SOURCE = 'ironplanet';
const BASE = 'https://www.ironplanet.com';
const SEARCH_URL = `${BASE}/jsp/s/search.ips?ct=3`;
const WEBHOOK_SECRET = process.env.WEBHOOK_SECRET || '';

if (!WEBHOOK_SECRET) {
    console.warn('[IRONPLANET] WARNING: WEBHOOK_SECRET env var not set');
}

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

// State code from IronPlanet locationCode field (e.g. "USA-CA", "CAN-AB")
function extractStateFromCode(locationCode) {
    if (!locationCode) return '';
    const match = locationCode.match(/^USA-([A-Z]{2})$/);
    return match ? match[1] : '';
}

// Extract state from locationString (plain text like "California" or "Texas, USA")
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

function extractStateFromName(locationString) {
    if (!locationString) return '';
    const upper = locationString.toUpperCase().trim();
    // Direct two-letter match
    const twoLetter = upper.match(/\b([A-Z]{2})\b/);
    if (twoLetter && US_STATES.has(twoLetter[1])) return twoLetter[1];
    // Full state name
    for (const [name, code] of Object.entries(STATE_NAME_TO_ABBREV)) {
        if (upper.includes(name)) return code;
    }
    return '';
}

function extractYear(text = '') {
    const match = String(text).match(/\b(19[89]\d|20[0-3]\d)\b/);
    return match ? parseInt(match[1], 10) : null;
}

function parseMileage(meterString = '') {
    // e.g. "38,655 mi" or "171,828 mi" or "" (hours/etc)
    const match = String(meterString).replace(/,/g, '').match(/(\d+)\s*(mi|mile)/i);
    return match ? parseInt(match[1], 10) : null;
}

function parsePriceString(priceString = '') {
    // priceString is HTML like: <span class="price"><span itemprop="price">US $19,000</span></span>
    const match = String(priceString).replace(/,/g, '').match(/\$\s*([\d]+(?:\.\d+)?)/);
    return match ? parseFloat(match[1]) : 0;
}

function passesFilters({ state, mileage, year, currentBid, maxMileage, maxAgeYears, minBid, maxBid }) {
    // Must be USA
    if (!state || !US_STATES.has(state)) return false;
    // Skip high-rust states — bypass for <=2yr old vehicles
    if (HIGH_RUST.has(state)) {
        const currentYear = new Date().getFullYear();
        if (!(year !== null && year >= currentYear - 2)) return false;
        console.log(`[BYPASS] Rust state ${state} allowed — vehicle is ${year} (≤2yr old)`);
    }
    // Mileage filter (if available)
    if (mileage !== null && mileage > maxMileage) return false;
    // Age filter (if year available)
    if (year === null || (new Date().getFullYear() - year) > maxAgeYears) return false;
    // Price filter (if price available — 0 means TBD/not set, skip price filter for those)
    if (currentBid > 0 && (currentBid < minBid || currentBid > maxBid)) return false;
    return true;
}

await Actor.init();

const input = await Actor.getInput() ?? {};
const {
    maxPages = 4,
    maxMileage = 100000,
    maxAgeYears = 10,
    minBid = 0,
    maxBid = 150000,
    maxItems = 0, // 0 = unlimited
} = input;

let totalScraped = 0;
let totalPushed = 0;

const crawler = new PlaywrightCrawler({
    maxRequestsPerCrawl: maxPages + 5,
    maxConcurrency: 1,
    minConcurrency: 1,
    requestHandlerTimeoutSecs: 120,
    launchContext: {
        launchOptions: {
            args: ['--no-sandbox', '--disable-setuid-sandbox'],
        },
    },

    async requestHandler({ page, request, log }) {
        const pageNum = request.userData.pageNum || 1;
        const pstart = (pageNum - 1) * 60;

        log.info(`[IRONPLANET] Loading page ${pageNum} (pstart=${pstart}): ${request.url}`);

        // Wait for the page to load (domcontentloaded avoids networkidle timeout)
        await page.waitForLoadState('domcontentloaded');
        await page.waitForTimeout(2000);

        // Fetch JSON data via in-page fetch (uses the session cookies Playwright established)
        const apiUrl = `${BASE}/jsp/s/search.ips?mode=6&ct=3&format=json${pstart > 0 ? `&pstart=${pstart}` : ''}`;
        log.info(`[IRONPLANET] Fetching API: ${apiUrl}`);

        const apiData = await page.evaluate(async (url) => {
            try {
                const res = await fetch(url, { credentials: 'include' });
                if (!res.ok) return { error: `HTTP ${res.status}`, items: [], total: 0 };
                const json = await res.json();
                return json.jsonData || { items: [], total: 0 };
            } catch (e) {
                return { error: e.message, items: [], total: 0 };
            }
        }, apiUrl);

        if (apiData.error) {
            log.error(`[IRONPLANET] API error: ${apiData.error}`);
            return;
        }

        const total = apiData.total || 0;
        const items = apiData.items || [];
        log.info(`[IRONPLANET] Page ${pageNum}: ${items.length} items (total=${total})`);

        for (const item of items) {
            totalScraped++;

            const state = extractStateFromCode(item.locationCode) || extractStateFromName(item.locationString);
            const mileage = parseMileage(item.meterString);
            const year = extractYear(item.description);
            const currentBid = parsePriceString(item.priceString);

            if (!passesFilters({ state, mileage, year, currentBid, maxMileage, maxAgeYears, minBid, maxBid })) {
                continue;
            }

            const listingUrl = item.itemPageUri ? `${BASE}${item.itemPageUri.split('?')[0]}` : '';
            const endDate = item.aucEndDate ? new Date(item.aucEndDate).toISOString() : null;

            await Actor.pushData({
                title: item.description || '',
                year,
                current_bid: currentBid,
                state,
                city: item.locationString || '',
                location: item.locationString || '',
                auction_end_time: endDate,
                listing_url: listingUrl,
                photo_url: item.photo || item.photoBigger || null,
                mileage,
                source_site: SOURCE,
                equip_id: item.equipId || '',
                scraped_at: new Date().toISOString(),
            });
            totalPushed++;

            if (maxItems > 0 && totalPushed >= maxItems) {
                log.info(`[IRONPLANET] Reached maxItems=${maxItems}, stopping.`);
                return;
            }
        }

        log.info(`[IRONPLANET] Page ${pageNum}: pushed ${totalPushed} total so far`);

        // Enqueue next page if more results exist
        const totalPages = Math.ceil(total / 60);
        if (pageNum < maxPages && pageNum < totalPages) {
            const nextPageNum = pageNum + 1;
            const nextPstart = nextPageNum * 60 - 60;
            const nextUrl = `${SEARCH_URL}&pstart=${nextPstart}`;
            await crawler.addRequests([{
                url: nextUrl,
                uniqueKey: `ironplanet-page-${nextPageNum}`,
                userData: { pageNum: nextPageNum },
            }]);
        }
    },

    failedRequestHandler({ request, log }) {
        log.error(`[IRONPLANET] Request failed: ${request.url}`);
    },
});

await crawler.run([{
    url: SEARCH_URL,
    uniqueKey: 'ironplanet-page-1',
    userData: { pageNum: 1 },
}]);

console.log(`[IRONPLANET] Done. Scraped: ${totalScraped} | Pushed: ${totalPushed}`);
await Actor.exit();
