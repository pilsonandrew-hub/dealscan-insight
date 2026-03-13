import { Actor } from 'apify';
import { PlaywrightCrawler } from 'crawlee';

const SOURCE = 'hibid';
const SEARCH_URL = 'https://hibid.com/auctions?category=vehicle&sort=newest';

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

await Actor.init();

const input = await Actor.getInput() ?? {};
const {
    maxPages = 15,
    minBid = 1000,
    maxMileage = 50000,
    minYear = 2022,
    targetStates = [...TARGET_STATES],
} = input;

const targetStateSet = new Set(targetStates.map((state) => state.toUpperCase()));
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

function parseVehicleTitle(title) {
    const normalizedTitle = normalizeText(title);
    const yearMatch = normalizedTitle.match(/\b(20\d{2}|19[89]\d)\b/);
    const year = yearMatch ? parseInt(yearMatch[1], 10) : null;

    let make = null;
    let model = null;
    const lower = normalizedTitle.toLowerCase();

    for (const candidateMake of VEHICLE_MAKES) {
        if (!lower.includes(candidateMake)) continue;

        make = candidateMake.charAt(0).toUpperCase() + candidateMake.slice(1);
        if (make === 'Chevy') make = 'Chevrolet';
        if (make === 'Vw') make = 'Volkswagen';

        const makeIndex = lower.indexOf(candidateMake);
        const afterMake = normalizedTitle.slice(makeIndex + candidateMake.length).trim();
        const modelMatch = afterMake.match(/^([A-Za-z0-9-]+(?:\s+[A-Za-z0-9-]+)?)/);
        if (modelMatch) model = modelMatch[1].trim();
        break;
    }

    return { year, make, model };
}

function parseState(locationText) {
    const normalized = normalizeText(locationText);
    if (!normalized) return null;

    const match = normalized.match(/,\s*([A-Z]{2})\b/)
        || normalized.match(/\b([A-Z]{2})\s*\d{5}/)
        || normalized.match(/\b([A-Z]{2})\b$/);

    return match ? match[1].toUpperCase() : null;
}

function parseBid(text) {
    const normalized = normalizeText(text);
    if (!normalized) return 0;

    const match = normalized.replace(/,/g, '').match(/[\d]+(?:\.\d+)?/);
    return match ? parseFloat(match[0]) : 0;
}

function parseDate(text) {
    const normalized = normalizeText(text);
    if (!normalized) return null;

    const parsed = new Date(normalized);
    return Number.isNaN(parsed.getTime()) ? normalized : parsed.toISOString();
}

function parseMileage(text) {
    const normalized = normalizeText(text);
    if (!normalized) return null;

    const match = normalized.match(/(\d[\d,]+)\s*(?:miles?|mi\.?)\b/i);
    return match ? parseInt(match[1].replace(/,/g, ''), 10) : null;
}

function parseVin(text) {
    const normalized = normalizeText(text);
    if (!normalized) return null;

    const match = normalized.match(/\bVIN[:\s#-]*([A-HJ-NPR-Z0-9]{17})\b/i)
        || normalized.match(/\b([A-HJ-NPR-Z0-9]{17})\b/);

    return match ? match[1] : null;
}

async function processSearchResults(results, sourceUrl, log) {
    for (const result of results) {
        const title = normalizeText(result.title);
        if (!title || !isVehicle(title)) {
            continue;
        }

        const location = normalizeText(result.location);
        const state = parseState(location);
        const bid = parseBid(result.bidText);
        const detailsText = [title, result.description, result.cardText].map(normalizeText).filter(Boolean).join(' ');
        const mileage = result.mileage ?? parseMileage(detailsText);
        const vin = result.vin ?? parseVin(detailsText);
        const { year, make, model } = parseVehicleTitle(title);

        if (state && HIGH_RUST_STATES.has(state)) {
            log.debug(`[SKIP] High-rust state: ${state} - ${title}`);
            continue;
        }
        if (state && !targetStateSet.has(state)) {
            log.debug(`[SKIP] Out-of-target state: ${state} - ${title}`);
            continue;
        }
        if (bid > 0 && bid < minBid) {
            log.debug(`[SKIP] Bid too low: $${bid} - ${title}`);
            continue;
        }
        if (year && year < minYear) {
            log.debug(`[SKIP] Too old: ${year} - ${title}`);
            continue;
        }
        if (mileage && mileage > maxMileage) {
            log.debug(`[SKIP] Too many miles: ${mileage} - ${title}`);
            continue;
        }

        const listing = {
            listing_id: result.lotId || `hibid-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
            title,
            current_bid: bid,
            buy_now_price: null,
            auction_end_date: parseDate(result.endText),
            state: state || null,
            listing_url: result.listingUrl || sourceUrl,
            image_url: result.imageUrl || null,
            mileage: mileage || null,
            vin: vin || null,
            year,
            make,
            model,
            source_site: SOURCE,
            scraped_at: new Date().toISOString(),
        };

        totalAfterFilters++;
        log.info(`[PASS] ${listing.title} | $${listing.current_bid} | ${listing.state}`);
        await Actor.pushData(listing);
    }
}

const crawler = new PlaywrightCrawler({
    launchContext: {
        launchOptions: { headless: true },
    },
    maxRequestsPerCrawl: maxPages + 10,
    navigationTimeoutSecs: 60,
    requestHandlerTimeoutSecs: 120,
    maxConcurrency: 2,

    async requestHandler({ page, request, enqueueLinks, log }) {
        const currentPage = request.userData?.pageNum ?? 1;
        log.info(`[HiBid] Processing search page ${currentPage}: ${request.url}`);

        await page.waitForSelector('a[href*="/lot/"], a[href*="/item/"], [class*="lot"], [class*="item"], body', { timeout: 30000 });
        await page.waitForTimeout(2000);

        const results = await page.evaluate(() => {
            const normalizeText = (value) => String(value ?? '')
                .replace(/\u00a0/g, ' ')
                .replace(/[ \t]+/g, ' ')
                .replace(/\s*\n\s*/g, '\n')
                .trim();

            const textFrom = (root, selectors) => {
                for (const selector of selectors) {
                    const node = root.querySelector(selector);
                    const text = normalizeText(node?.textContent);
                    if (text) return text;
                }
                return '';
            };

            const anchors = Array.from(document.querySelectorAll('a[href*="/lot/"], a[href*="/item/"]'));
            const seen = new Set();
            const items = [];

            for (const anchor of anchors) {
                const href = anchor.href;
                if (!href || seen.has(href)) continue;
                seen.add(href);

                const card = anchor.closest('article, li, .lot-card, .item-card, .search-result, .search-card, .card, [class*="lot"], [class*="item"]')
                    || anchor.parentElement
                    || anchor;

                const cardText = normalizeText(card?.innerText);
                const title = textFrom(card, [
                    'h1', 'h2', 'h3', 'h4',
                    '[class*="title"]',
                    '[class*="name"]',
                ]) || normalizeText(anchor.textContent);

                const bidText = textFrom(card, [
                    '[class*="current-bid"]',
                    '[class*="high-bid"]',
                    '[class*="bid"]',
                    '[class*="price"]',
                    '[class*="amount"]',
                ]);

                const endText = textFrom(card, [
                    'time',
                    '[datetime]',
                    '[class*="end"]',
                    '[class*="close"]',
                    '[class*="time-left"]',
                    '[class*="countdown"]',
                ]);

                const location = textFrom(card, [
                    '[class*="location"]',
                    '[class*="city"]',
                    '[class*="state"]',
                    '[class*="address"]',
                    '[data-location]',
                ]);

                const img = card.querySelector('img');
                const imageUrl = img?.getAttribute('data-src') || img?.getAttribute('src') || null;

                const lotIdMatch = href.match(/\/lot\/(\d+)/i)
                    || href.match(/\/item\/(\d+)/i)
                    || href.match(/[?&](?:lotId|id)=(\d+)/i);

                items.push({
                    lotId: lotIdMatch ? lotIdMatch[1] : '',
                    title,
                    bidText,
                    endText,
                    location,
                    imageUrl,
                    listingUrl: href,
                    description: cardText,
                    cardText,
                });
            }

            return items;
        });

        log.info(`[HiBid] Found ${results.length} result rows on page ${currentPage}`);
        totalFound += results.length;

        await processSearchResults(results, request.url, log);

        if (results.length > 0 && currentPage < maxPages) {
            const nextUrl = new URL(SEARCH_URL);
            nextUrl.searchParams.set('page', String(currentPage + 1));

            await enqueueLinks({
                urls: [nextUrl.toString()],
                label: 'LIST',
                userData: { pageNum: currentPage + 1 },
            });
        }
    },
});

await crawler.run([
    {
        url: SEARCH_URL,
        label: 'LIST',
        userData: { pageNum: 1 },
    },
]);

console.log(`[HIBID COMPLETE] Found: ${totalFound} | Passed filters: ${totalAfterFilters}`);

await Actor.exit();
