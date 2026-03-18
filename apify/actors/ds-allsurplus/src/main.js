/**
 * ds-allsurplus — AllSurplus (Ritchie Bros.) Scraper
 *
 * STATUS: OPERATIONAL — Playwright-based with vehicle-targeted search strategy.
 *
 * Architecture notes (2026-03-18):
 * - AllSurplus is an Angular SPA backed by maestro.lqdt1.com/search/list API.
 * - The maestro API requires session auth (401 without tokens) — cannot call directly.
 * - URL query params (?q=truck, ?categories=*^18) are set by the JS app but DO NOT
 *   filter server-side at page load; the browser JS reads them and fires API calls.
 * - Category IDs discovered: Transportation=18, Automobiles/Cars(753), SUV(638),
 *   Pickup Trucks(667), Electric/Hybrid(60), Vehicles-Misc(82), Classic Cars(19).
 * - Strategy: use make-specific search URLs (e.g., /en/search?q=ford) which heavily
 *   bias results toward vehicles, then apply strict isVehicle() + isJunk() filters.
 * - Playwright must wait for Angular to hydrate (4-6 seconds) before scraping results.
 *
 * Vehicle category URLs (for Playwright navigation — categories are applied by JS):
 *   https://www.allsurplus.com/en/search?q=ford
 *   https://www.allsurplus.com/en/search?q=toyota
 *   https://www.allsurplus.com/en/search?q=honda
 *   https://www.allsurplus.com/en/search?q=chevrolet
 *   https://www.allsurplus.com/en/search?q=dodge+ram
 *   https://www.allsurplus.com/en/search?q=nissan
 *   https://www.allsurplus.com/en/search?q=jeep
 *   https://www.allsurplus.com/en/search?q=hyundai+kia
 */

import { Actor } from 'apify';
import { PlaywrightCrawler } from 'crawlee';

const SOURCE = 'allsurplus';
const BASE = 'https://www.allsurplus.com';

const TARGET_STATES = new Set([
    'AZ','CA','NV','CO','NM','UT','TX','FL','GA','SC','TN','NC','VA','WA','OR','HI'
]);

const HIGH_RUST_STATES = new Set([
    'OH','MI','PA','NY','WI','MN','IL','IN','MO','IA',
    'ND','SD','NE','KS','WV','ME','NH','VT','MA','RI',
    'CT','NJ','MD','DE'
]);

// Vehicle-specific keywords (passenger vehicles)
const VEHICLE_KEYWORDS = [
    'car','sedan','coupe','hatchback','convertible','cabriolet',
    'suv','crossover','4wd','awd','4x4',
    'pickup','pickup truck',
    'minivan','minivan','van',
    'hybrid','electric vehicle','ev',
    'automobile','motor vehicle',
];

// Vehicle makes (passenger vehicles + light trucks only)
const VEHICLE_MAKES = [
    'ford','chevrolet','chevy','dodge','ram','jeep','chrysler','lincoln','buick','cadillac','pontiac','gmc',
    'toyota','honda','nissan','subaru','mazda','mitsubishi','lexus','acura','infiniti','scion',
    'hyundai','kia','genesis',
    'volkswagen','vw','audi','bmw','mercedes','mercedes-benz','porsche','volvo',
    'tesla','rivian','lucid','polestar',
    'land rover','range rover','jaguar','mini',
    'fiat','alfa romeo','maserati',
];

// Junk patterns — if title matches any of these, skip regardless of vehicle keywords
const JUNK_PATTERNS = [
    /chromatograph/i, /spectrometer/i, /centrifuge/i, /autoclave/i,
    /excavator/i, /bulldozer/i, /dozer/i, /loader/i, /backhoe/i,
    /forklift/i, /scissor\s*lift/i, /boom\s*lift/i, /aerial\s*lift/i,
    /skid\s*steer/i, /motor\s*grader/i, /compactor/i,
    /generator/i, /compressor/i, /pump\s*unit/i,
    /dump\s*truck/i, /garbage\s+truck/i, /box\s*truck/i, /semi\s*truck/i,
    /tractor\s*trailer/i, /semi-tractor/i, /flatbed\s*truck/i,
    /fire\s*truck/i, /ambulance/i, /sweeper/i, /street\s*sweeper/i,
    /boat|marine\s*vessel/i, /aircraft|airplane|helicopter/i,
    /motorcycle|motorbike/i,
    /golf\s*cart/i, /atv|utv|all.terrain/i,
    /pallet\s*jack/i, /forklift/i,
    /server|router|switch|rack\s*mount/i,
    /auction\s*lot\s+\d+\s*pcs/i, /^\d+\s*pcs/i,
];

// Make-specific vehicle search URLs — these strongly bias results toward passenger vehicles
// The Angular SPA will render vehicle results for make-specific searches
const VEHICLE_SEARCH_URLS = [
    `${BASE}/en/search?q=ford+mustang+f150+explorer+escape`,
    `${BASE}/en/search?q=toyota+camry+rav4+highlander+tacoma`,
    `${BASE}/en/search?q=honda+civic+accord+cr-v+pilot`,
    `${BASE}/en/search?q=chevrolet+silverado+malibu+equinox+tahoe`,
    `${BASE}/en/search?q=dodge+charger+challenger+durango+ram`,
    `${BASE}/en/search?q=jeep+wrangler+grand+cherokee+compass`,
    `${BASE}/en/search?q=nissan+altima+sentra+rogue+pathfinder`,
    `${BASE}/en/search?q=hyundai+sonata+elantra+tucson+santa`,
    `${BASE}/en/search?q=kia+optima+sorento+sportage+telluride`,
    `${BASE}/en/search?q=bmw+mercedes+audi+lexus+cadillac`,
    `${BASE}/en/search?q=tesla+model+electric+hybrid+vehicle`,
    // Direct category navigation — JS will apply Transportation filter if stored in state
    `${BASE}/en/search?categories=*%5E18`,
];

await Actor.init();

const input = await Actor.getInput() ?? {};
const {
    maxPages = 15,
    minBid = 3000,
    maxBid = 35000,
    maxMileage = 50000,
    minYear = 2020,
    targetStates = [...TARGET_STATES],
    searchUrls = VEHICLE_SEARCH_URLS,
} = input;

const targetStateSet = new Set(targetStates.map(s => s.toUpperCase()));
const allListings = [];
const seenUrls = new Set();
let totalFound = 0;
let totalAfterFilters = 0;

function isVehicle(title) {
    const lower = title.toLowerCase();
    // Must match a make OR a vehicle keyword
    const makeMatch = VEHICLE_MAKES.some(make => {
        const idx = lower.indexOf(make);
        if (idx === -1) return false;
        // Make sure it's a word boundary, not part of another word
        const before = idx === 0 ? ' ' : lower[idx - 1];
        const after = idx + make.length >= lower.length ? ' ' : lower[idx + make.length];
        return /[\s,.\-(\/]/.test(before) || idx === 0;
    });
    if (!makeMatch) {
        return VEHICLE_KEYWORDS.some(kw => lower.includes(kw));
    }
    return true;
}

function isJunk(title) {
    return JUNK_PATTERNS.some(pat => pat.test(title));
}

function parseVehicleTitle(title) {
    const yearMatch = title.match(/\b(20[12]\d|19[89]\d)\b/);
    const year = yearMatch ? parseInt(yearMatch[1]) : null;

    let make = null;
    let model = null;
    const lower = title.toLowerCase();

    for (const m of VEHICLE_MAKES) {
        const idx = lower.indexOf(m);
        if (idx === -1) continue;
        // Word boundary check
        const before = idx === 0 ? ' ' : lower[idx - 1];
        if (idx > 0 && !/[\s,.\-(\/]/.test(before)) continue;

        make = m.charAt(0).toUpperCase() + m.slice(1);
        // Normalize aliases
        const aliases = { chevy: 'Chevrolet', vw: 'Volkswagen', ram: 'Ram' };
        make = aliases[m] || make;

        const afterMake = title.slice(idx + m.length).trim();
        const modelMatch = afterMake.match(/^([A-Za-z0-9\-]+(?:\s+[A-Za-z0-9\-]+)?)/);
        if (modelMatch) model = modelMatch[1].trim();
        break;
    }

    return { year, make, model };
}

function parseState(text) {
    if (!text) return null;
    const match = text.match(/,\s*([A-Z]{2})\b/) ||
                  text.match(/\b([A-Z]{2})\s*\d{5}/) ||
                  text.match(/\b([A-Z]{2})\b/);
    if (!match) return null;
    const candidate = match[1].toUpperCase();
    // Sanity: known 2-letter state codes only
    const validStates = new Set(['AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA','HI','ID','IL','IN',
        'IA','KS','KY','LA','ME','MD','MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ','NM','NY',
        'NC','ND','OH','OK','OR','PA','RI','SC','SD','TN','TX','UT','VT','VA','WA','WV','WI','WY','DC']);
    return validStates.has(candidate) ? candidate : null;
}

function parseBid(text) {
    if (!text) return 0;
    const match = String(text).replace(/,/g, '').match(/[\d]+\.?\d*/);
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

function normalizeText(text) {
    return String(text || '').replace(/\s+/g, ' ').trim();
}

function applyFilters(listing, log) {
    const title = listing.title || '';

    if (!isVehicle(title)) {
        log.debug(`[SKIP-NOT-VEHICLE] ${title.slice(0, 60)}`);
        return false;
    }
    if (isJunk(title)) {
        log.debug(`[SKIP-JUNK] ${title.slice(0, 60)}`);
        return false;
    }

    const state = listing.state;
    if (state && HIGH_RUST_STATES.has(state)) {
        log.debug(`[SKIP-RUST] ${state}: ${title.slice(0, 60)}`);
        return false;
    }
    if (state && !targetStateSet.has(state)) {
        log.debug(`[SKIP-STATE] ${state}: ${title.slice(0, 60)}`);
        return false;
    }
    if (listing.current_bid > 0 && listing.current_bid < minBid) {
        log.debug(`[SKIP-BID-LOW] $${listing.current_bid}`);
        return false;
    }
    if (listing.current_bid > 0 && listing.current_bid > maxBid) {
        log.debug(`[SKIP-BID-HIGH] $${listing.current_bid}`);
        return false;
    }
    if (listing.year && listing.year < minYear) {
        log.debug(`[SKIP-OLD] ${listing.year}`);
        return false;
    }
    if (listing.mileage && listing.mileage > maxMileage) {
        log.debug(`[SKIP-MILES] ${listing.mileage}`);
        return false;
    }
    return true;
}

// Web crawler using make-specific search URLs
const crawler = new PlaywrightCrawler({
    maxRequestsPerCrawl: maxPages * 3 + 50,
    requestHandlerTimeoutSecs: 90,
    maxConcurrency: 2,
    minConcurrency: 1,
    launchContext: {
        launchOptions: {
            headless: true,
        },
    },

    async requestHandler({ page, request, enqueueLinks, log }) {
        const url = request.url;
        log.info(`[AllSurplus] Processing: ${url} (label=${request.label})`);

        if (request.label === 'DETAIL') {
            await handleDetailPage(page, request, log);
            return;
        }

        // Wait for Angular to hydrate and render search results
        await page.waitForLoadState('domcontentloaded');
        // Wait for the search results to populate (Angular SPA needs time)
        await page.waitForTimeout(6000);

        // Try waiting for asset links to appear
        try {
            await page.waitForSelector('a[href*="/en/asset/"]', { timeout: 10000 });
        } catch {
            log.warning(`[AllSurplus] No asset links appeared on: ${url}`);
        }

        const listings = await page.evaluate(() => {
            const normalize = (value) => String(value ?? '').replace(/\s+/g, ' ').trim();
            const toAbsolute = (href) => {
                if (!href) return null;
                try { return new URL(href, window.location.origin).toString(); }
                catch { return null; }
            };

            // AllSurplus uses /en/asset/{eventId}/{assetId} URL pattern
            const anchors = Array.from(document.querySelectorAll('a[href*="/en/asset/"]')).filter((anchor) => {
                const href = anchor.getAttribute('href') || '';
                return /\/en\/asset\/\d+\/\d+/.test(href);
            });

            const deduped = new Map();
            for (const anchor of anchors) {
                const listingUrl = toAbsolute(anchor.href || anchor.getAttribute('href'));
                if (!listingUrl || deduped.has(listingUrl)) continue;

                const card = anchor.closest(
                    'article, li, .card, .search-result, [class*="search-result"], [class*="SearchResult"], [class*="asset-card"], [class*="lot-card"]'
                ) || anchor.closest('[id^="asset-"]') || anchor.parentElement?.parentElement || anchor.parentElement || anchor;

                // Get title from various element types
                const titleNodes = Array.from(card.querySelectorAll(
                    'h1, h2, h3, h4, .card-title, [class*="title"], [data-testid*="title"], [class*="assetTitle"], [class*="asset-title"]'
                )).map((node) => normalize(node.textContent)).filter(Boolean);
                const title = titleNodes.find((value) => value.length > 4) || normalize(anchor.textContent);
                if (!title || title === 'Online Auction') continue;

                const cardText = normalize(card.textContent);
                const bidMatch = cardText.match(/(?:current\s*bid|bid)\s*[:$]?\s*\$?([\d,]+(?:\.\d+)?)/i);
                const locationMatch = cardText.match(/([A-Za-z .'-]+,\s*[A-Z]{2})(?:\s+\d{5})?/);
                const timerMatch = cardText.match(/(?:ends?|closes?|closing)\s*[:\-]?\s*([A-Za-z0-9,:/ \-]+(?:AM|PM|UTC|PDT|PST|EDT|EST)?)/i);
                const img = card.querySelector('img[src], img[data-src], img[loading]');

                deduped.set(listingUrl, {
                    title,
                    listingUrl,
                    currentBid: bidMatch?.[1] ?? '',
                    location: locationMatch?.[1] ?? '',
                    endDate: timerMatch?.[1] ?? '',
                    imageUrl: img?.getAttribute('src') || img?.getAttribute('data-src') || null,
                });
            }

            return Array.from(deduped.values());
        });

        log.info(`[AllSurplus] Found ${listings.length} asset links on page`);

        const newDetailUrls = [];
        for (const item of listings) {
            const listingUrl = item.listingUrl;
            if (!listingUrl || seenUrls.has(listingUrl)) continue;
            seenUrls.add(listingUrl);
            totalFound++;
            newDetailUrls.push(listingUrl);
        }

        if (newDetailUrls.length > 0) {
            await enqueueLinks({
                urls: newDetailUrls,
                label: 'DETAIL',
            });
        }

        // Pagination — AllSurplus uses ?page=N
        const currentPage = request.userData?.pageNum ?? 1;
        if (listings.length > 5 && currentPage < maxPages) {
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

async function handleDetailPage(page, request, log) {
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(3000);

    const data = await page.evaluate(() => {
        const normalize = (value) => String(value ?? '').replace(/\s+/g, ' ').trim();
        const text = normalize(document.body?.innerText || '');

        const findLabelValue = (...patterns) => {
            for (const pattern of patterns) {
                const match = text.match(pattern);
                if (match?.[1]) return normalize(match[1]);
            }
            return '';
        };

        const titleEl = document.querySelector(
            'h1, [data-testid*="title"], .card-title, [class*="assetTitle"], [class*="asset-title"], [class*="title"]'
        );
        const title = normalize(titleEl?.textContent || document.title.split('|')[0].split('-')[0]);

        const img = document.querySelector('img[src*="allsurplus"], img[class*="main"], .main-image img, [class*="gallery"] img');
        const lotNumber = findLabelValue(/lot\s*#?\s*[:\-]?\s*([A-Za-z0-9\-]+)/i);

        // Try to find structured data fields
        const location = findLabelValue(
            /location\s*[:\-]\s*([A-Za-z0-9 .,'-]+,\s*[A-Z]{2}(?:\s+\d{5})?)/i,
            /([A-Za-z .'-]+,\s*[A-Z]{2})(?:\s+\d{5})?/i
        );

        return {
            title,
            bidText: findLabelValue(
                /current\s*bid\s*[:\-]?\s*\$?([\d,]+(?:\.\d+)?)/i,
                /high\s*bid\s*[:\-]?\s*\$?([\d,]+(?:\.\d+)?)/i,
                /\$\s*([\d,]+(?:\.\d+)?)/i
            ),
            buyNowText: findLabelValue(/buy(?:\s+it)?\s*now\s*[:\-]?\s*\$?([\d,]+(?:\.\d+)?)/i),
            location,
            endText: findLabelValue(
                /(?:auction\s+)?(?:end|ends|close|closes)\s*[:\-]?\s*([A-Za-z0-9,:/ \-]+(?:AM|PM|UTC|PDT|PST)?)/i
            ),
            imageUrl: img?.getAttribute('src') || img?.getAttribute('data-src') || null,
            lotNumber,
            bodyText: text.slice(0, 5000),
        };
    });

    const title = data.title;
    if (!title) {
        log.debug(`[SKIP-NOTITLE] ${request.url}`);
        return;
    }

    // ID from URL pattern /en/asset/{eventId}/{assetId}
    const idMatch = request.url.match(/\/en\/asset\/(\d+\/\d+)/i) ||
                    request.url.match(/\/lots?\/([a-z0-9\-]+)/i) ||
                    request.url.match(/[Ll]ot[Ii]d=([a-z0-9\-]+)/i);
    const itemId = idMatch ? idMatch[1].replace('/', '-') : `allsurplus-${Date.now()}`;

    const description = normalizeText(data.bodyText);
    const mileageMatch = description.match(/(\d[\d,]+)\s*(?:miles?|mi\.?|odometer)\b/i);
    const mileage = mileageMatch ? parseInt(mileageMatch[1].replace(/,/g, '')) : null;
    const vinMatch = description.match(/\bVIN[:\s#]*([A-HJ-NPR-Z0-9]{17})\b/i) ||
                     description.match(/\b([A-HJ-NPR-Z0-9]{17})\b/);
    const vin = vinMatch ? vinMatch[1] : null;

    const bid = parseBid(data.bidText);
    const buyNow = parseBid(data.buyNowText) || null;
    const state = parseState(data.location);
    const { year, make, model } = parseVehicleTitle(title);

    // Extract title_status
    let titleStatus = '';
    const tsMatch = description.match(/(?:title\s+status|title\s+type)\s*[:\-]?\s*([A-Za-z ]+?)(?:\.|,|\n|$)/i);
    if (tsMatch) titleStatus = normalizeText(tsMatch[1]);
    // Check for salvage indicators
    if (/salvage|rebuilt\s+title|branded\s+title|lemon|flood/i.test(description)) {
        titleStatus = titleStatus || 'salvage';
    }

    const listing = {
        listing_id: itemId,
        title,
        title_status: titleStatus,
        current_bid: bid,
        buy_now_price: buyNow,
        auction_end_date: parseDate(data.endText),
        auction_end_time: parseDate(data.endText),
        state,
        location: data.location || (state ? state : ''),
        listing_url: request.url,
        image_url: data.imageUrl,
        photo_url: data.imageUrl,
        lot_number: data.lotNumber,
        mileage,
        vin,
        year,
        make,
        model,
        source: SOURCE,
        source_site: SOURCE,
        scraped_at: new Date().toISOString(),
    };

    if (!applyFilters(listing, log)) return;

    totalAfterFilters++;
    allListings.push(listing);
    log.info(`[PASS] ${listing.year || '?'} ${listing.make || '?'} ${listing.model || '?'} | $${listing.current_bid} | ${listing.state || '?'} | ${title.slice(0, 50)}`);
    await Actor.pushData(listing);
}

// Run Playwright crawler with make-specific search URLs
console.log('[AllSurplus] Starting vehicle-targeted scrape with make-specific URLs');
console.log(`[AllSurplus] Target URLs: ${searchUrls.length} searches`);

await crawler.run(
    searchUrls.map((url, index) => ({
        url,
        label: 'LIST',
        userData: { pageNum: 1 },
        uniqueKey: `allsurplus-search-${index}`,
    }))
);

console.log(`[ALLSURPLUS COMPLETE] Found: ${totalFound} detail links | Passed filters: ${totalAfterFilters}`);

await Actor.exit();
