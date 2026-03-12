import { Actor } from 'apify';
import { PlaywrightCrawler } from 'crawlee';

const SOURCE = 'hibid';

const TARGET_STATES = new Set([
    'AZ','CA','NV','CO','NM','UT','TX','FL','GA','SC','TN','NC','VA','WA','OR','HI'
]);

const HIGH_RUST_STATES = new Set([
    'OH','MI','PA','NY','WI','MN','IL','IN','MO','IA',
    'ND','SD','NE','KS','WV','ME','NH','VT','MA','RI',
    'CT','NJ','MD','DE'
]);

const VEHICLE_KEYWORDS = ['car','truck','suv','van','pickup','sedan','coupe','wagon','vehicle','automobile','motor','4wd','awd','hybrid'];
const VEHICLE_MAKES = ['ford','chevrolet','chevy','dodge','ram','toyota','honda','nissan','jeep','gmc','chrysler',
    'hyundai','kia','subaru','mazda','volkswagen','vw','bmw','mercedes','audi','lexus','acura','infiniti',
    'cadillac','lincoln','buick','pontiac','mitsubishi','volvo','tesla','rivian','lucid','genesis'];

// HiBid paginates its vehicle search catalog
const SEARCH_URLS = [
    'https://hibid.com/catalog/auctions?category=20',   // Vehicles & Transportation
    'https://hibid.com/catalog/auctions?keywords=vehicle&category=20',
];

await Actor.init();

const input = await Actor.getInput() ?? {};
const {
    maxPages = 15,
    minBid = 1000,
    maxMileage = 50000,
    minYear = 2022,
    targetStates = [...TARGET_STATES],
} = input;

const targetStateSet = new Set(targetStates.map(s => s.toUpperCase()));
const allListings = [];
let totalFound = 0;
let totalAfterFilters = 0;

function isVehicle(title) {
    const lower = title.toLowerCase();
    return VEHICLE_KEYWORDS.some(kw => lower.includes(kw)) ||
           VEHICLE_MAKES.some(make => lower.includes(make));
}

function parseVehicleTitle(title) {
    const yearMatch = title.match(/\b(20\d{2}|19[89]\d)\b/);
    const year = yearMatch ? parseInt(yearMatch[1]) : null;

    let make = null;
    let model = null;
    const lower = title.toLowerCase();

    for (const m of VEHICLE_MAKES) {
        if (lower.includes(m)) {
            make = m.charAt(0).toUpperCase() + m.slice(1);
            if (make === 'Chevy') make = 'Chevrolet';
            if (make === 'Vw') make = 'Volkswagen';
            // Try to extract model after make
            const makeIdx = lower.indexOf(m);
            const afterMake = title.slice(makeIdx + m.length).trim();
            const modelMatch = afterMake.match(/^([A-Za-z0-9\-]+(?:\s+[A-Za-z0-9\-]+)?)/);
            if (modelMatch) model = modelMatch[1].trim();
            break;
        }
    }

    return { year, make, model };
}

function parseState(locationText) {
    if (!locationText) return null;
    // "City, ST 12345" or "City, ST" or just "ST"
    const match = locationText.match(/,\s*([A-Z]{2})\b/) ||
                  locationText.match(/\b([A-Z]{2})\s*\d{5}/) ||
                  locationText.match(/\b([A-Z]{2})\b/);
    return match ? match[1].toUpperCase() : null;
}

function parseBid(text) {
    if (!text) return 0;
    const match = text.replace(/,/g, '').match(/[\d]+\.?\d*/);
    return match ? parseFloat(match[0]) : 0;
}

function parseDate(text) {
    if (!text) return null;
    try {
        const d = new Date(text);
        if (!isNaN(d.getTime())) return d.toISOString();
    } catch {}
    return null;
}

const crawler = new PlaywrightCrawler({
    launchContext: {
        launchOptions: { headless: true },
    },
    maxRequestsPerCrawl: maxPages * 5 + 100,
    navigationTimeoutSecs: 60,
    requestHandlerTimeoutSecs: 120,
    maxConcurrency: 2,

    async requestHandler({ page, request, enqueueLinks, log }) {
        const url = request.url;
        log.info(`[HiBid] Processing: ${url}`);

        if (request.label === 'AUCTION') {
            await handleAuctionPage(page, request, log, enqueueLinks);
            return;
        }

        if (request.label === 'LOT') {
            await handleLotPage(page, request, log);
            return;
        }

        // LIST page — HiBid auction catalog
        // Wait for Angular to render
        await page.waitForSelector('.auction-card, [class*="auction"], .catalog-item, body', { timeout: 30000 });
        // Extra wait for Angular SPA hydration
        await page.waitForTimeout(2000);

        const auctionLinks = await page.evaluate(() => {
            const links = new Set();
            // HiBid auction cards link to individual auction pages
            document.querySelectorAll('a[href*="/catalog/"]').forEach(a => {
                const href = a.href;
                if (href && href.match(/\/catalog\/\d+/)) links.add(href);
            });
            document.querySelectorAll('a[href*="/auctions/"]').forEach(a => {
                const href = a.href;
                if (href && href.match(/\/auctions?\/\d+/)) links.add(href);
            });
            // Fallback: any card links
            document.querySelectorAll('.auction-card a, [class*="auction-item"] a, .catalog-tile a').forEach(a => {
                if (a.href && !a.href.includes('#')) links.add(a.href);
            });
            return [...links].slice(0, 50);
        });

        log.info(`Found ${auctionLinks.length} auction links`);
        totalFound += auctionLinks.length;

        if (auctionLinks.length > 0) {
            await enqueueLinks({
                urls: auctionLinks,
                label: 'AUCTION',
            });
        }

        // Pagination — HiBid uses ?page=N or similar
        const currentPage = request.userData?.pageNum ?? 1;
        if (auctionLinks.length > 0 && currentPage < maxPages) {
            const nextUrl = new URL(url);
            nextUrl.searchParams.set('page', currentPage + 1);
            await enqueueLinks({
                urls: [nextUrl.toString()],
                label: 'LIST',
                userData: { pageNum: currentPage + 1 },
            });
        }
    },
});

async function handleAuctionPage(page, request, log, enqueueLinks) {
    await page.waitForSelector('body', { timeout: 30000 });
    await page.waitForTimeout(2000);

    // Check auction location/state early to filter out high-rust states
    const auctionMeta = await page.evaluate(() => {
        const locEl = document.querySelector('[class*="location"], .auction-location, [data-location]');
        const location = locEl ? locEl.textContent.trim() : '';
        const titleEl = document.querySelector('h1, .auction-title, [class*="auction-title"]');
        const title = titleEl ? titleEl.textContent.trim() : '';
        return { location, title };
    });

    const state = parseState(auctionMeta.location);
    if (state && HIGH_RUST_STATES.has(state)) {
        log.debug(`Skipping high-rust state auction: ${state}`);
        return;
    }

    // Extract individual lot links from auction page
    const lotLinks = await page.evaluate(() => {
        const links = new Set();
        document.querySelectorAll('a[href*="/lot/"], a[href*="/item/"]').forEach(a => {
            if (a.href) links.add(a.href);
        });
        // Also grab lot cards that may have relative links
        document.querySelectorAll('.lot-card a, [class*="lot-item"] a, .catalog-lot a').forEach(a => {
            if (a.href && !a.href.includes('#')) links.add(a.href);
        });
        return [...links].slice(0, 100);
    });

    log.info(`Auction ${request.url}: found ${lotLinks.length} lots`);

    if (lotLinks.length > 0) {
        await enqueueLinks({
            urls: lotLinks,
            label: 'LOT',
            userData: { auctionLocation: auctionMeta.location },
        });
    } else {
        // Some auctions embed lots on the same page — extract inline
        await extractInlineLots(page, request, log, auctionMeta.location);
    }

    // Handle lot pagination within an auction
    const nextLotPage = await page.$('[class*="pagination"] a[aria-label*="Next"], .next-page, [rel="next"]');
    if (nextLotPage) {
        const href = await nextLotPage.getAttribute('href');
        if (href) {
            await enqueueLinks({
                urls: [new URL(href, request.url).toString()],
                label: 'AUCTION',
                userData: { auctionLocation: auctionMeta.location },
            });
        }
    }
}

async function extractInlineLots(page, request, log, auctionLocation) {
    const lots = await page.evaluate((auctionUrl) => {
        const items = [];
        const cards = document.querySelectorAll('.lot-card, [class*="lot-item"], .catalog-lot, [class*="item-card"]');
        cards.forEach(card => {
            try {
                const titleEl = card.querySelector('h3, h4, [class*="title"], [class*="name"]');
                const bidEl = card.querySelector('[class*="bid"], [class*="price"], [class*="amount"]');
                const endEl = card.querySelector('[class*="end"], [class*="close"], [class*="date"]');
                const imgEl = card.querySelector('img');
                const linkEl = card.querySelector('a') || (card.tagName === 'A' ? card : null);

                items.push({
                    title: titleEl ? titleEl.textContent.trim() : '',
                    bidText: bidEl ? bidEl.textContent.trim() : '',
                    endText: endEl ? endEl.textContent.trim() : '',
                    imageUrl: imgEl ? (imgEl.getAttribute('data-src') || imgEl.src) : null,
                    listingUrl: linkEl ? linkEl.href : auctionUrl,
                    lotId: card.getAttribute('data-lot-id') || card.getAttribute('data-id') || '',
                });
            } catch {}
        });
        return items;
    }, request.url);

    processExtractedLots(lots, auctionLocation, request.url, log);
}

async function handleLotPage(page, request, log) {
    await page.waitForSelector('body', { timeout: 30000 });
    await page.waitForTimeout(1500);

    const auctionLocation = request.userData?.auctionLocation ?? '';

    const data = await page.evaluate(() => {
        const getText = (sel) => {
            const el = document.querySelector(sel);
            return el ? el.textContent.trim() : '';
        };

        // Lot/item title
        const title = getText('h1, .lot-title, [class*="lot-title"], .item-title') ||
                      document.title.split('|')[0].trim();

        // Current bid
        const bidSelectors = [
            '[class*="current-bid"]', '[class*="high-bid"]', '.bid-amount',
            '[class*="bid-value"]', '[data-bind*="currentBid"]', '#current-bid'
        ];
        let bidText = '';
        for (const sel of bidSelectors) {
            const el = document.querySelector(sel);
            if (el) { bidText = el.textContent; break; }
        }

        // End date
        const endSelectors = [
            '[class*="end-time"]', '[class*="closes"]', '[class*="auction-end"]',
            '[data-countdown]', '.countdown', '[class*="time-left"]'
        ];
        let endText = '';
        for (const sel of endSelectors) {
            const el = document.querySelector(sel);
            if (el) {
                endText = el.getAttribute('data-end') ||
                          el.getAttribute('datetime') ||
                          el.textContent.trim();
                break;
            }
        }

        // Location
        const locSelectors = [
            '[class*="location"]', '[class*="city"]', '.auction-location',
            '[data-location]', '[class*="address"]'
        ];
        let location = '';
        for (const sel of locSelectors) {
            const el = document.querySelector(sel);
            if (el) { location = el.textContent.trim(); break; }
        }

        // Image
        const imgEl = document.querySelector(
            '.lot-image img, [class*="main-image"] img, .gallery-main img, ' +
            '[class*="lot-photo"] img, img[class*="primary"]'
        );
        const imageUrl = imgEl ? (imgEl.getAttribute('data-src') || imgEl.src) : null;

        // Lot/item ID from URL or page
        const idMatch = window.location.href.match(/\/lot\/(\d+)/) ||
                        window.location.href.match(/lotId=(\d+)/i) ||
                        window.location.href.match(/\/item\/(\d+)/);
        const lotId = idMatch ? idMatch[1] : '';

        // Mileage from description
        const descEl = document.querySelector('[class*="description"], .lot-description, #description');
        const description = descEl ? descEl.textContent : '';
        const mileageMatch = description.match(/(\d[\d,]+)\s*(?:miles?|mi\.?)\b/i);
        const mileage = mileageMatch ? parseInt(mileageMatch[1].replace(/,/g, '')) : null;

        // VIN
        const vinMatch = description.match(/\bVIN[:\s#]*([A-HJ-NPR-Z0-9]{17})\b/i) ||
                         description.match(/\b([A-HJ-NPR-Z0-9]{17})\b/);
        const vin = vinMatch ? vinMatch[1] : null;

        return { title, bidText, endText, location, imageUrl, lotId, mileage, vin };
    });

    const location = data.location || auctionLocation;
    const state = parseState(location);
    const bid = parseBid(data.bidText);
    const { year, make, model } = parseVehicleTitle(data.title);

    // Filters
    if (!isVehicle(data.title)) {
        log.debug(`[SKIP] Not a vehicle: ${data.title}`);
        return;
    }
    if (state && HIGH_RUST_STATES.has(state)) {
        log.debug(`[SKIP] High-rust state: ${state} — ${data.title}`);
        return;
    }
    if (state && !targetStateSet.has(state)) {
        log.debug(`[SKIP] Out-of-target state: ${state}`);
        return;
    }
    if (bid > 0 && bid < minBid) {
        log.debug(`[SKIP] Bid too low: $${bid} — ${data.title}`);
        return;
    }
    if (year && year < minYear) {
        log.debug(`[SKIP] Too old: ${year} — ${data.title}`);
        return;
    }
    if (data.mileage && data.mileage > maxMileage) {
        log.debug(`[SKIP] Too many miles: ${data.mileage} — ${data.title}`);
        return;
    }

    const listing = {
        listing_id: data.lotId || `hibid-${Date.now()}-${Math.random().toString(36).slice(2,7)}`,
        title: data.title,
        current_bid: bid,
        buy_now_price: null,
        auction_end_date: parseDate(data.endText),
        state: state || null,
        listing_url: request.url,
        image_url: data.imageUrl || null,
        mileage: data.mileage || null,
        vin: data.vin || null,
        year,
        make,
        model,
        scraped_at: new Date().toISOString(),
    };

    totalAfterFilters++;
    log.info(`[PASS] ${listing.title} | $${listing.current_bid} | ${listing.state}`);
    allListings.push(listing);
    await Actor.pushData(listing);
}

function processExtractedLots(lots, auctionLocation, sourceUrl, log) {
    for (const lot of lots) {
        if (!isVehicle(lot.title)) continue;

        const state = parseState(lot.location || auctionLocation);
        const bid = parseBid(lot.bidText);
        const { year, make, model } = parseVehicleTitle(lot.title);

        if (state && HIGH_RUST_STATES.has(state)) continue;
        if (state && !targetStateSet.has(state)) continue;
        if (bid > 0 && bid < minBid) continue;
        if (year && year < minYear) continue;

        const listing = {
            listing_id: lot.lotId || `hibid-inline-${Date.now()}-${Math.random().toString(36).slice(2,7)}`,
            title: lot.title,
            current_bid: bid,
            buy_now_price: null,
            auction_end_date: parseDate(lot.endText),
            state: state || null,
            listing_url: lot.listingUrl || sourceUrl,
            image_url: lot.imageUrl || null,
            mileage: null,
            vin: null,
            year,
            make,
            model,
            scraped_at: new Date().toISOString(),
        };

        totalAfterFilters++;
        log.info(`[PASS-INLINE] ${listing.title} | $${listing.current_bid} | ${listing.state}`);
        allListings.push(listing);
        Actor.pushData(listing);
    }
}

// Start crawl
await crawler.run(
    SEARCH_URLS.map((url, i) => ({
        url,
        label: 'LIST',
        userData: { pageNum: 1 },
        uniqueKey: `list-start-${i}`,
    }))
);

const log = crawler.log ?? console;
console.log(`[HIBID COMPLETE] Found: ${totalFound} | Passed filters: ${totalAfterFilters}`);

await Actor.exit();
