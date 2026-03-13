import { Actor } from 'apify';
import { PlaywrightCrawler } from 'crawlee';

const TARGET_STATES = new Set([
    'AZ', 'CA', 'NV', 'CO', 'NM', 'UT', 'TX', 'FL', 'GA', 'SC', 'TN', 'NC', 'VA', 'WA', 'OR', 'HI',
]);

const HIGH_RUST_STATES = new Set([
    'OH', 'MI', 'PA', 'NY', 'WI', 'MN', 'IL', 'IN', 'MO', 'IA',
    'ND', 'SD', 'NE', 'KS', 'WV', 'ME', 'NH', 'VT', 'MA', 'RI',
    'CT', 'NJ', 'MD', 'DE',
]);

const VEHICLE_KEYWORDS = ['car', 'truck', 'suv', 'van', 'pickup', 'sedan', 'coupe', 'wagon', 'vehicle', 'automobile', 'motor', '4wd', 'awd', 'hybrid'];
const VEHICLE_MAKES = ['ford', 'chevrolet', 'chevy', 'dodge', 'ram', 'toyota', 'honda', 'nissan', 'jeep', 'gmc', 'chrysler',
    'hyundai', 'kia', 'subaru', 'mazda', 'volkswagen', 'vw', 'bmw', 'mercedes', 'audi', 'lexus', 'acura', 'infiniti',
    'cadillac', 'lincoln', 'buick', 'pontiac', 'mitsubishi', 'volvo', 'tesla', 'rivian', 'lucid', 'genesis'];

const BASE_URL = 'https://www.publicsurplus.com';
const BASE_LIST_URL = `${BASE_URL}/sms/all,wa/browse/cataucs?catid=4&page={PAGE}`;

await Actor.init();

const input = await Actor.getInput() ?? {};
const {
    maxPages = 3,
    minBid = 500,
    maxBid = 35000,
    targetStates = [...TARGET_STATES],
} = input;

const targetStateSet = new Set(targetStates.map((state) => state.toUpperCase()));
const effectiveMaxPages = Math.max(1, Math.min(maxPages, 3));
const seenListings = new Set();

let totalFound = 0;
let totalAfterFilters = 0;

function normalizeText(value) {
    return String(value ?? '')
        .replace(/\u00a0/g, ' ')
        .replace(/[ \t]+/g, ' ')
        .replace(/\s*\n\s*/g, '\n')
        .trim();
}

function isVehicle(title) {
    const lower = normalizeText(title).toLowerCase();
    return VEHICLE_KEYWORDS.some((keyword) => lower.includes(keyword))
        || VEHICLE_MAKES.some((make) => lower.includes(make));
}

function parseMoney(value) {
    const match = normalizeText(value).match(/\$?([\d,]+(?:\.\d+)?)/);
    return match ? parseFloat(match[1].replace(/,/g, '')) : 0;
}

function parseAuctionDate(value) {
    const normalized = normalizeText(value);
    if (!normalized) return null;

    const parsed = new Date(normalized);
    return Number.isNaN(parsed.getTime()) ? normalized : parsed.toISOString();
}

function parseState(location) {
    const normalized = normalizeText(location);
    if (!normalized) return null;

    const match = normalized.match(/,\s*([A-Z]{2})\b/)
        || normalized.match(/\b([A-Z]{2})\s*\d{5}/)
        || normalized.match(/\b([A-Z]{2})\b$/);

    return match ? match[1].toUpperCase() : null;
}

async function pushListing(listing, sourceUrl, log) {
    const title = normalizeText(listing.title);
    const currentBid = parseMoney(listing.currentBid);
    const location = normalizeText(listing.location);
    const state = parseState(location) || 'WA';

    if (!title) {
        log.debug(`[SKIP] Missing title on ${sourceUrl}`);
        return false;
    }
    if (!isVehicle(title)) {
        log.debug(`[SKIP] Not a vehicle: ${title}`);
        return false;
    }
    if (HIGH_RUST_STATES.has(state)) {
        log.debug(`[SKIP] High-rust state: ${state} - ${title}`);
        return false;
    }
    if (!targetStateSet.has(state)) {
        log.debug(`[SKIP] Out-of-target state: ${state} - ${title}`);
        return false;
    }
    if (currentBid < minBid || currentBid > maxBid) {
        log.debug(`[SKIP] Out-of-range bid $${currentBid} - ${title}`);
        return false;
    }

    const listingUrl = normalizeText(listing.listingUrl) || sourceUrl;
    const dedupeKey = listingUrl || `${title}-${state}-${currentBid}`;
    if (seenListings.has(dedupeKey)) {
        return false;
    }
    seenListings.add(dedupeKey);

    const vehicle = {
        title,
        current_bid: currentBid,
        buyer_premium: 0.10,
        doc_fee: 50,
        auction_end_time: parseAuctionDate(listing.endDate),
        location,
        state,
        listing_url: listingUrl,
        item_number: normalizeText(listing.itemNumber),
        photo_url: normalizeText(listing.photoUrl) || null,
        description: null,
        agency_name: normalizeText(listing.agencyName),
        source_site: 'publicsurplus',
        scraped_at: new Date().toISOString(),
    };

    totalAfterFilters++;
    log.info(`[PASS] ${vehicle.title} | $${vehicle.current_bid} | ${vehicle.state}`);
    await Actor.pushData(vehicle);
    return true;
}

const crawler = new PlaywrightCrawler({
    launchContext: {
        launchOptions: {
            headless: true,
        },
    },
    maxRequestsPerCrawl: effectiveMaxPages + 2,
    navigationTimeoutSecs: 60,
    requestHandlerTimeoutSecs: 90,
    maxConcurrency: 2,
    minConcurrency: 1,

    async requestHandler({ page, request, enqueueLinks, log }) {
        const currentPage = request.userData?.pageNum ?? 1;
        log.info(`[PublicSurplus] Processing index page ${currentPage}: ${request.url}`);

        await page.waitForSelector('#auctionTableView, table.auction-list, table, body', { timeout: 30000 });
        await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});
        await page.waitForTimeout(1500);

        const listings = await page.evaluate(() => {
            const normalizeText = (value) => String(value ?? '')
                .replace(/\u00a0/g, ' ')
                .replace(/[ \t]+/g, ' ')
                .replace(/\s*\n\s*/g, '\n')
                .trim();

            const tableSelectors = ['#auctionTableView tr', 'table.auction-list tr', 'table tr'];
            const rows = [];
            const seen = new Set();

            const findFromCells = (cells, matcher) => cells.find((cell) => matcher(cell)) || '';

            for (const selector of tableSelectors) {
                for (const row of Array.from(document.querySelectorAll(selector))) {
                    const titleLink = row.querySelector('a[href*="/auction/view?auc="], a[href*="view?auc="]');
                    if (!titleLink) continue;

                    const href = titleLink.getAttribute('href') || '';
                    const listingUrl = href ? new URL(href, window.location.href).toString() : '';
                    const dedupeKey = listingUrl || normalizeText(titleLink.textContent);
                    if (!dedupeKey || seen.has(dedupeKey)) continue;
                    seen.add(dedupeKey);

                    const cells = Array.from(row.querySelectorAll('td')).map((cell) => normalizeText(cell.textContent));
                    const photo = row.querySelector('img');
                    const title = normalizeText(titleLink.textContent);
                    const currentBid = normalizeText(row.querySelector('td[id^="val_"]')?.textContent)
                        || findFromCells(cells, (cell) => /\$\s*\d/.test(cell));
                    const location = normalizeText(row.querySelector('td.text-success.fw-bold, .text-success, [class*="location"]')?.textContent)
                        || findFromCells(cells, (cell) => /,\s*[A-Z]{2}\b/.test(cell) || /\bWA\b/.test(cell));
                    const endDate = normalizeText(row.querySelector('.auction-time_left span, [id^="timeLeftValue"], time')?.textContent)
                        || findFromCells(cells, (cell) => /\d{1,2}\/\d{1,2}\/\d{2,4}/.test(cell) || /\b(?:AM|PM)\b/i.test(cell) || /days|hrs|mins/i.test(cell));
                    const agencyName = findFromCells(cells, (cell) => /county|city|school|district|port|state|police|public works|transport/i.test(cell));
                    const itemNumber = normalizeText(row.querySelector('td:first-child')?.textContent) || cells[0] || '';

                    rows.push({
                        itemNumber,
                        title,
                        currentBid,
                        location,
                        endDate,
                        listingUrl,
                        photoUrl: photo?.getAttribute('src') || photo?.getAttribute('data-src') || '',
                        agencyName,
                    });
                }

                if (rows.length > 0) break;
            }

            return rows;
        });

        totalFound += listings.length;
        log.info(`[PublicSurplus] Found ${listings.length} listing rows on page ${currentPage}`);

        for (const listing of listings) {
            await pushListing(listing, request.url, log);
        }

        if (listings.length > 0 && currentPage < effectiveMaxPages) {
            const nextPageUrl = BASE_LIST_URL.replace('{PAGE}', String(currentPage + 1));
            await enqueueLinks({
                urls: [nextPageUrl],
                label: 'LIST',
                userData: { pageNum: currentPage + 1 },
            });
        }
    },
});

const startUrl = BASE_LIST_URL.replace('{PAGE}', '1');
await crawler.run([
    { url: startUrl, label: 'LIST', userData: { pageNum: 1 } },
]);

console.log(`[PUBLICSURPLUS COMPLETE] Found: ${totalFound} | Passed filters: ${totalAfterFilters}`);

await Actor.exit();
