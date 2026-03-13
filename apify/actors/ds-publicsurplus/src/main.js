import { Actor } from 'apify';
import { PlaywrightCrawler } from 'crawlee';

const HIGH_RUST_STATES = new Set([
    'OH', 'MI', 'PA', 'NY', 'WI', 'MN', 'IL', 'IN', 'MO', 'IA',
    'ND', 'SD', 'NE', 'KS', 'WV', 'ME', 'NH', 'VT', 'MA', 'RI',
    'CT', 'NJ', 'MD', 'DE',
]);

const DEFAULT_TARGET_STATES = ['AZ', 'CA', 'NV', 'CO', 'NM', 'UT', 'TX', 'FL', 'GA', 'SC', 'TN', 'NC', 'VA', 'WA', 'OR', 'HI'];

// catid=4 = Motor Pool on PublicSurplus
const BASE_URL = 'https://www.publicsurplus.com/sms/all,wa/browse/cataucs?catid=4&page={PAGE}';

await Actor.init();

const input = await Actor.getInput() ?? {};
const {
    maxPages = 10,
    minBid = 500,
    maxBid = 35000,
    targetStates = DEFAULT_TARGET_STATES,
} = input;

const targetStateSet = new Set(targetStates.map((state) => state.toUpperCase()));
const effectiveMaxPages = Math.min(maxPages, 3);
let totalFound = 0;
let totalAfterFilters = 0;

function normalizeText(value) {
    return String(value ?? '')
        .replace(/\u00a0/g, ' ')
        .replace(/[ \t]+/g, ' ')
        .replace(/\s*\n\s*/g, '\n')
        .trim();
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

async function processInlineListings(listings, sourceUrl, log) {
    for (const listing of listings) {
        const title = normalizeText(listing.title);
        const bid = parseMoney(listing.currentBid);
        const location = normalizeText(listing.location);
        const state = parseState(location) || 'WA';

        if (!title) {
            log.debug(`[SKIP] Missing title on ${sourceUrl}`);
            continue;
        }
        if (HIGH_RUST_STATES.has(state)) {
            log.debug(`[SKIP] High-rust state: ${state} - ${title}`);
            continue;
        }
        if (!targetStateSet.has(state)) {
            log.debug(`[SKIP] Out-of-target state: ${state} - ${title}`);
            continue;
        }
        if (bid < minBid || bid > maxBid) {
            log.debug(`[SKIP] Out-of-range bid $${bid} - ${title}`);
            continue;
        }

        const vehicle = {
            title,
            current_bid: bid,
            buyer_premium: 0.10,
            doc_fee: 50,
            auction_end_time: parseAuctionDate(listing.endDate),
            location,
            state,
            listing_url: listing.listingUrl || sourceUrl,
            item_number: normalizeText(listing.itemNumber),
            photo_url: listing.photoUrl || null,
            description: null,
            agency_name: normalizeText(listing.agencyName),
            source_site: 'publicsurplus',
            scraped_at: new Date().toISOString(),
        };

        totalAfterFilters++;
        log.info(`[PASS] ${vehicle.title} | $${vehicle.current_bid} | ${vehicle.state}`);
        await Actor.pushData(vehicle);
    }
}

const crawler = new PlaywrightCrawler({
    launchContext: {
        launchOptions: {
            headless: true,
        },
    },
    maxRequestsPerCrawl: effectiveMaxPages + 5,

    async requestHandler({ page, request, enqueueLinks, log }) {
        const currentPage = request.userData?.pageNum ?? 1;
        log.info(`Processing index page ${currentPage}: ${request.url}`);

        await page.waitForSelector('#auctionTableView tbody tr[id$="catList"], a[href*="/auction/view?auc="], body', { timeout: 30000 });

        const listings = await page.evaluate(() => {
            const normalizeText = (value) => String(value ?? '')
                .replace(/\u00a0/g, ' ')
                .replace(/[ \t]+/g, ' ')
                .replace(/\s*\n\s*/g, '\n')
                .trim();

            const rows = Array.from(document.querySelectorAll('#auctionTableView tbody tr[id$="catList"]'));

            return rows.map((row) => {
                const titleLink = row.querySelector('td.text-start a[href*="/auction/view?auc="]');
                if (!titleLink) return null;

                const photo = row.querySelector('img');
                const cells = Array.from(row.querySelectorAll('td')).map((cell) => normalizeText(cell.textContent));

                return {
                    itemNumber: normalizeText(row.querySelector('td:first-child')?.textContent),
                    title: normalizeText(titleLink.textContent),
                    currentBid: normalizeText(row.querySelector('td[id^="val_"]')?.textContent),
                    location: normalizeText(row.querySelector('td.text-success.fw-bold')?.textContent),
                    endDate: normalizeText(row.querySelector('.auction-time_left span, [id^="timeLeftValue"]')?.textContent),
                    listingUrl: titleLink.href,
                    photoUrl: photo?.getAttribute('src') || photo?.getAttribute('data-src') || null,
                    agencyName: cells.find((cell) => /county|city|school|district|port|state|police|public works|transport/i.test(cell)) || '',
                };
            }).filter(Boolean);
        });

        log.info(`Found ${listings.length} listing rows on page ${currentPage}`);
        totalFound += listings.length;

        await processInlineListings(listings, request.url, log);

        if (listings.length > 0 && currentPage < effectiveMaxPages) {
            const nextPageUrl = BASE_URL.replace('{PAGE}', String(currentPage + 1));
            await enqueueLinks({
                urls: [nextPageUrl],
                label: 'LIST',
                userData: { pageNum: currentPage + 1 },
            });
        }
    },
});

const startUrl = BASE_URL.replace('{PAGE}', '1');
await crawler.run([
    { url: startUrl, label: 'LIST', userData: { pageNum: 1 } },
]);

console.log(`[PUBLICSURPLUS COMPLETE] Found: ${totalFound} | Passed filters: ${totalAfterFilters}`);

await Actor.exit();
