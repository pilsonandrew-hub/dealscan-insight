import { Actor } from 'apify';
import { PlaywrightCrawler } from 'crawlee';

const SOURCE = 'gsaauctions';
const START_URL = 'https://gsaauctions.gov/auctions/auctions-list?category=vehicles';

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
    maxPages = 20,
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
    const match = text.match(/^([^,]+),\s*[A-Z]{2}\b/);
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

    return {
        year,
        make,
        model,
        lowerTitle,
    };
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

async function waitForListings(page, log) {
    await page.waitForLoadState('domcontentloaded', { timeout: 30000 }).catch(() => {});
    await page.waitForLoadState('networkidle', { timeout: 20000 }).catch(() => {});

    const selectors = [
        'a[href*="/auctions/preview/"]',
        'a[href*="/auctions/listing/"]',
        'a[href*="/auctions/item/"]',
        '[data-testid*="auction"] a[href]',
    ];

    for (const selector of selectors) {
        const found = await page.locator(selector).first().waitFor({ state: 'visible', timeout: 6000 })
            .then(() => true)
            .catch(() => false);
        if (found) return;
    }

    log.warning('[GSA] Listing selector did not become visible before timeout');
}

async function extractPageListings(page) {
    return page.evaluate(() => {
        const normalize = (value) => String(value ?? '').replace(/\s+/g, ' ').trim();
        const toAbsoluteUrl = (href) => {
            try {
                return new URL(href, window.location.origin).toString();
            } catch {
                return '';
            }
        };

        const anchors = Array.from(document.querySelectorAll(
            'a[href*="/auctions/preview/"], a[href*="/auctions/listing/"], a[href*="/auctions/item/"]',
        ));

        const seenUrls = new Set();
        const records = [];

        for (const anchor of anchors) {
            const href = anchor.getAttribute('href');
            if (!href) continue;

            const listingUrl = toAbsoluteUrl(href);
            if (!listingUrl || seenUrls.has(listingUrl)) continue;
            seenUrls.add(listingUrl);

            const card = anchor.closest('article, li, section, [class*="card"], [class*="Card"], [class*="tile"], [class*="Tile"], [data-testid*="auction"], [data-testid*="listing"]')
                ?? anchor.parentElement;
            if (!card) continue;

            const title = normalize(anchor.textContent)
                || normalize(card.querySelector('h1, h2, h3, h4, [class*="title"], [class*="Title"]')?.textContent);
            if (!title) continue;

            const lines = String(card.innerText ?? '')
                .split(/\n+/)
                .map((line) => normalize(line))
                .filter(Boolean);

            const bidText = lines.find((line) => /(current bid|high bid)\b/i.test(line))
                ?? lines.find((line) => /\$\s*[\d,]/.test(line))
                ?? '';
            const endText = Array.from(card.querySelectorAll('time'))
                .map((node) => node.getAttribute('datetime') || node.textContent || '')
                .map((line) => normalize(line))
                .find(Boolean)
                ?? lines.find((line) => /\b(end|ends|closing|close time|auction end)\b/i.test(line))
                ?? '';
            const location = lines.find((line) => /\b(location|pickup)\b/i.test(line))
                ?? lines.find((line) => /,\s*[A-Z]{2}(?:\s+\d{5})?\b/.test(line))
                ?? lines.find((line) => /\b[A-Z]{2}\s+\d{5}\b/.test(line))
                ?? '';

            const image = card.querySelector('img');
            const imageUrl = image?.getAttribute('src')
                || image?.getAttribute('data-src')
                || image?.getAttribute('data-original')
                || image?.getAttribute('srcset')?.split(',')[0]?.trim().split(' ')[0]
                || '';

            records.push({
                title,
                bidText,
                endText,
                location,
                listingUrl,
                imageUrl: imageUrl ? toAbsoluteUrl(imageUrl) : '',
            });
        }

        return records;
    });
}

async function getNextControl(page) {
    const candidates = [
        page.getByRole('button', { name: /next/i }),
        page.getByRole('link', { name: /next/i }),
        page.locator('[aria-label*="next" i]'),
        page.locator('button:has-text("Next"), a:has-text("Next")'),
    ];

    for (const candidate of candidates) {
        const count = await candidate.count().catch(() => 0);
        if (!count) continue;

        const control = candidate.first();
        const visible = await control.isVisible().catch(() => false);
        if (!visible) continue;

        const disabled = await control.evaluate((node) => {
            const element = /** @type {HTMLElement} */ (node);
            return element.hasAttribute('disabled')
                || element.getAttribute('aria-disabled') === 'true'
                || element.classList.contains('disabled');
        }).catch(() => false);
        if (!disabled) return control;
    }

    return null;
}

const crawler = new PlaywrightCrawler({
    maxRequestsPerCrawl: 1,
    maxConcurrency: 1,
    requestHandlerTimeoutSecs: 300,
    launchContext: {
        launchOptions: {
            args: [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
            ],
        },
    },

    async requestHandler({ page, log }) {
        log.info(`[GSA] Loading ${START_URL}`);
        await waitForListings(page, log);

        let previousSignature = null;

        for (let pageNumber = 1; pageNumber <= maxPages; pageNumber += 1) {
            const rawListings = await extractPageListings(page);
            const signature = rawListings.map((listing) => listing.listingUrl).slice(0, 10).join('|');

            log.info(`[GSA] Page ${pageNumber}: extracted ${rawListings.length} cards`);

            if (!rawListings.length) {
                if (pageNumber === 1) {
                    log.warning('[GSA] No auction cards found on the first hydrated page');
                }
                break;
            }

            if (signature && signature === previousSignature) {
                log.info('[GSA] Page signature repeated after pagination, stopping');
                break;
            }
            previousSignature = signature;

            for (const rawListing of rawListings) {
                const dedupeKey = rawListing.listingUrl;
                if (!dedupeKey || seenListings.has(dedupeKey)) continue;
                seenListings.add(dedupeKey);

                totalFound += 1;
                const listing = buildListing(rawListing);

                if (!applyFilters(listing, log)) continue;

                totalAfterFilters += 1;
                await Actor.pushData(listing);
            }

            if (pageNumber >= maxPages) break;

            const nextControl = await getNextControl(page);
            if (!nextControl) {
                log.info('[GSA] No enabled next-page control found');
                break;
            }

            const firstListingUrl = rawListings[0]?.listingUrl || null;
            await Promise.all([
                page.waitForFunction((previousUrl) => {
                    const nextAnchor = document.querySelector(
                        'a[href*="/auctions/preview/"], a[href*="/auctions/listing/"], a[href*="/auctions/item/"]',
                    );
                    return !previousUrl || !nextAnchor || nextAnchor.href !== previousUrl;
                }, firstListingUrl, { timeout: 20000 }).catch(() => {}),
                nextControl.click(),
            ]);

            await waitForListings(page, log);
        }
    },
});

await crawler.run([{ url: START_URL }]);

console.log(`[GSA COMPLETE] Found: ${totalFound} | Passed filters: ${totalAfterFilters}`);
await Actor.exit();
