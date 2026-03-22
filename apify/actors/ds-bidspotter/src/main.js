import { Actor } from 'apify';
import { PlaywrightCrawler } from 'crawlee';

const SOURCE = 'bidspotter';
const BASE_URL = 'https://www.bidspotter.com';

// US target states for wholesale vehicle arbitrage
const TARGET_STATES = new Set([
    'AZ', 'CA', 'NV', 'CO', 'NM', 'UT', 'TX', 'FL', 'GA', 'SC', 'TN', 'NC', 'VA', 'WA', 'OR', 'HI',
    'ID', 'MT', 'WY', 'ND', 'SD', 'NE', 'KS', 'AL', 'LA', 'OK',
]);

// Canadian provinces — always reject
const CANADIAN_PROVINCES = new Set([
    'AB', 'BC', 'ON', 'QC', 'MB', 'SK', 'NS', 'NB', 'PE', 'NL', 'YT', 'NT', 'NU',
]);

// All valid US state codes (for validation)
const ALL_US_STATES = new Set([
    'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA', 'HI', 'ID', 'IL', 'IN', 'IA',
    'KS', 'KY', 'LA', 'ME', 'MD', 'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
    'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC', 'SD', 'TN', 'TX', 'UT', 'VT',
    'VA', 'WA', 'WV', 'WI', 'WY', 'DC',
]);

const VEHICLE_MAKES = [
    'ford', 'chevrolet', 'chevy', 'dodge', 'ram', 'toyota', 'honda', 'nissan', 'jeep', 'gmc',
    'chrysler', 'hyundai', 'kia', 'subaru', 'mazda', 'volkswagen', 'vw', 'bmw', 'mercedes',
    'audi', 'lexus', 'acura', 'infiniti', 'cadillac', 'lincoln', 'buick', 'pontiac',
    'mitsubishi', 'volvo', 'tesla', 'mini', 'saturn', 'scion', 'land rover', 'jaguar',
    'porsche', 'maserati', 'alfa romeo', 'fiat', 'genesis', 'rivian', 'lucid',
];

const VEHICLE_KEYWORDS = [
    'sedan', 'coupe', 'hatchback', 'wagon', 'convertible', 'suv', 'sport utility',
    'crossover', 'pickup', 'crew cab', 'extended cab', 'minivan', 'passenger van',
    '4x4', 'awd', 'fwd', 'rwd', 'passenger car', 'automobile',
];

// Exclude non-passenger / non-target vehicle lots
const EXCLUDED_PATTERN = /\b(forklift|tractor|loader|backhoe|excavator|grader|dozer|bulldozer|skid\s*steer|trencher|mower|generator|compressor|sprayer|sweeper|boat|marine|trailer|camper|rv|motorhome|jet\s*ski|snowmobile|motorcycle|atv|utv|golf\s*cart|bus|ambulance|fire\s*truck|dump\s*truck|flatbed|box\s*truck|cargo\s+van|step\s+van|cutaway|chassis\s+cab|stake\s*bed|semitrailer|furniture|desk|chair|cabinet|computer|electronics|tools|equipment|machinery|industrial)\b/i;

await Actor.init();

const input = await Actor.getInput() ?? {};
const {
    maxCatalogues = 30,
    minYear = 1990,
    targetStates = [...TARGET_STATES],
} = input;

const targetStateSet = new Set(targetStates.map((s) => String(s).toUpperCase()));
const seenListings = new Set();

let totalFound = 0;
let totalAfterFilters = 0;

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
        .replace(/^(ends?|closing|end\s*date|auction\s*end)\s*:?\s*/i, '')
        .replace(/\bat\b/i, ' ');
    if (!text) return null;
    const parsed = new Date(text);
    return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
}

function parseState(text) {
    const upper = normalizeText(text).toUpperCase();
    if (!upper) return null;

    // "City, ST" or "City, ST XXXXX"
    const match = upper.match(/,\s*([A-Z]{2})(?:\s+\d{5})?\b/)
        ?? upper.match(/\b([A-Z]{2})\s+\d{5}\b/)
        ?? upper.match(/\b([A-Z]{2})\b$/);
    const code = match?.[1];
    if (!code) return null;
    if (CANADIAN_PROVINCES.has(code)) return null; // US-ONLY: reject Canada
    return ALL_US_STATES.has(code) ? code : null;
}

function parseMileage(text) {
    const t = normalizeText(text);
    const match = t.match(/([\d,]+)\s*(?:mi(?:les?)?|km)/i);
    if (!match) return null;
    const miles = parseFloat(match[1].replace(/,/g, ''));
    // Convert km if needed
    if (/km/i.test(match[0])) return Math.round(miles * 0.621371);
    return miles;
}

function parseVehicleTitle(title) {
    const normalized = normalizeText(title);
    const lower = normalized.toLowerCase();

    const yearMatch = normalized.match(/\b(19[89]\d|20[0-3]\d)\b/);
    const year = yearMatch ? parseInt(yearMatch[1], 10) : null;

    let make = null;
    let model = null;

    for (const candidate of VEHICLE_MAKES) {
        const pattern = new RegExp(`\\b${candidate.replace(/\s+/g, '\\s+')}\\b`, 'i');
        const match = normalized.match(pattern);
        if (!match) continue;

        make = candidate === 'chevy' ? 'Chevrolet'
            : candidate === 'vw' ? 'Volkswagen'
            : candidate.replace(/\b\w/g, (c) => c.toUpperCase());

        const afterMake = normalized.slice(match.index + match[0].length)
            .replace(/^[\s\-:]+/, '')
            .replace(/\b(4x4|awd|fwd|rwd|vin|odometer|mileage)\b.*$/i, '')
            .trim();
        const modelMatch = afterMake.match(/^([A-Za-z0-9][A-Za-z0-9\-]*(?:\s+[A-Za-z0-9][A-Za-z0-9\-]*)?)/);
        model = modelMatch ? modelMatch[1] : null;
        break;
    }

    return { year, make, model, lower };
}

function isVehicleLot(title) {
    const { lower } = parseVehicleTitle(title);
    if (!lower) return false;
    if (EXCLUDED_PATTERN.test(lower)) return false;
    return VEHICLE_MAKES.some((m) => lower.includes(m))
        || VEHICLE_KEYWORDS.some((k) => lower.includes(k));
}

function applyFilters(listing, log) {
    if (!listing.make && !isVehicleLot(listing.title)) {
        log.debug(`[BS] Skip non-vehicle: ${listing.title}`);
        return false;
    }

    if (listing.state && CANADIAN_PROVINCES.has(listing.state)) {
        log.debug(`[BS] Skip Canadian province: ${listing.state}`);
        return false;
    }

    if (listing.state && !targetStateSet.has(listing.state)) {
        log.debug(`[BS] Skip out-of-target state ${listing.state}: ${listing.title}`);
        return false;
    }

    if (listing.year && listing.year < minYear) {
        log.debug(`[BS] Skip old year ${listing.year}: ${listing.title}`);
        return false;
    }

    if (!listing.make) {
        log.debug(`[BS] Skip no-make: ${listing.title}`);
        return false;
    }

    return true;
}

// Extract lot data from a BidSpotter lot detail page
async function extractLotDetail(page, log) {
    return page.evaluate(() => {
        const normalize = (v) => String(v ?? '').replace(/\s+/g, ' ').trim();

        const getText = (...selectors) => {
            for (const sel of selectors) {
                const el = document.querySelector(sel);
                const t = normalize(el?.textContent);
                if (t) return t;
            }
            return '';
        };

        const title = getText(
            'h1.lot-title', 'h1[class*="lot"]', '.lot-name h1',
            '[class*="LotTitle"]', '[class*="lot-title"]',
            'h1', 'h2',
        );

        // Try to get the closing date
        const closingEl = document.querySelector(
            '[class*="closing-date"] time, [class*="closingDate"] time, .lot-timer time, time[class*="end"]',
        );
        const closingDate = closingEl
            ? (closingEl.getAttribute('datetime') || normalize(closingEl.textContent))
            : getText('[class*="closing-date"]', '[class*="end-date"]', '.auction-end');

        // Current bid
        const currentBid = getText(
            '[class*="current-bid"] .amount', '[class*="currentBid"] .amount',
            '[class*="current-bid"]', '[class*="currentBid"]',
            '.bid-amount', '.current-amount',
        );

        // Location
        const location = getText(
            '[class*="location"]', '.auction-location', '.lot-location',
            '[class*="Location"]',
        );

        // Mileage
        const mileageEl = document.querySelector('[class*="odometer"], [class*="mileage"], [class*="Mileage"]');
        const mileage = normalize(mileageEl?.textContent) || '';

        // Image
        const img = document.querySelector('.lot-image img, [class*="lot-image"] img, .gallery img, .carousel img');
        const imageUrl = img?.getAttribute('src') || img?.getAttribute('data-src') || '';

        return { title, closingDate, currentBid, location, mileage, imageUrl };
    });
}

// Extract lot links from a catalogue page
async function extractLotLinks(page, baseUrl) {
    return page.evaluate((base) => {
        const links = [];
        const seen = new Set();
        const anchors = document.querySelectorAll('a[href*="/lot-"], a[href*="/lots/"]');
        for (const a of anchors) {
            const href = a.getAttribute('href');
            if (!href) continue;
            const url = new URL(href, base).toString();
            if (seen.has(url)) continue;
            seen.add(url);

            // Try to get card-level text
            let card = a;
            for (let i = 0; i < 8; i++) {
                if (!card.parentElement) break;
                card = card.parentElement;
                if (['li', 'article'].includes(card.tagName.toLowerCase())) break;
                if (card.tagName.toLowerCase() === 'div' && card.classList.toString().toLowerCase().includes('lot')) break;
            }
            links.push({
                url,
                cardText: String(card.textContent ?? '').replace(/\s+/g, ' ').trim().slice(0, 300),
            });
        }
        return links;
    }, baseUrl);
}

// Extract catalogue links from the main search-filter page
async function extractCatalogueLinks(page) {
    return page.evaluate(() => {
        const links = [];
        const seen = new Set();
        const anchors = document.querySelectorAll('a[href*="/auction-catalogues/"][href*="catalogue-id"]');
        for (const a of anchors) {
            const href = a.getAttribute('href');
            if (!href || href.includes('/search-filter?') || href.includes('CategoryCode=')) continue;
            const url = new URL(href, window.location.origin).toString();
            if (seen.has(url)) continue;
            seen.add(url);

            // Get location/state context from surrounding card
            let card = a;
            for (let i = 0; i < 10; i++) {
                if (!card.parentElement) break;
                card = card.parentElement;
                if (['article', 'li', 'section'].includes(card.tagName.toLowerCase())) break;
                if (card.tagName.toLowerCase() === 'div' && (
                    /state|location|address/i.test(card.getAttribute('class') || '')
                )) break;
            }
            const cardText = String(card.textContent ?? '').replace(/\s+/g, ' ').trim();
            links.push({ url, cardText });
        }
        return links;
    });
}

// Wait for page to hydrate
async function waitForPage(page) {
    await page.waitForLoadState('domcontentloaded', { timeout: 25000 }).catch(() => {});
    await page.waitForTimeout(1500);
    // Try to wait for some content
    await page.waitForSelector('a[href*="catalogue-id"], a[href*="/lot-"], h1', { timeout: 8000 }).catch(() => {});
}

const crawler = new PlaywrightCrawler({
    maxRequestsPerCrawl: 200,
    maxConcurrency: 3,
    navigationTimeoutSecs: 30,
    requestHandlerTimeoutSecs: 60,
    launchContext: {
        launchOptions: {
            args: [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
            ],
        },
    },

    async requestHandler({ page, request, enqueueLinks, log }) {
        const label = request.label ?? 'CATALOGUE_LIST';

        // ── LOT detail page ───────────────────────────────────────────────────
        if (label === 'LOT') {
            const url = page.url();
            log.info(`[BS] Lot: ${url}`);

            await waitForPage(page);
            const data = await extractLotDetail(page, log);

            if (!data.title) {
                log.warning(`[BS] No title on lot page: ${url}`);
                return;
            }

            totalFound += 1;

            const { year, make, model } = parseVehicleTitle(data.title);
            const state = parseState(data.location || request.userData?.location || '');
            const currentBid = parseBid(data.currentBid);
            const mileage = parseMileage(data.mileage);
            const auctionEndDate = parseDate(data.closingDate);

            const listingId = url.match(/\/lot-([^/?#]+)/)?.[1]
                ?? `bs-${Buffer.from(url).toString('base64').slice(0, 16)}`;

            const listing = {
                listing_id: listingId,
                title: normalizeText(data.title),
                year,
                make,
                model,
                mileage,
                current_bid: currentBid,
                auction_end_date: auctionEndDate,
                state,
                listing_url: url,
                image_url: data.imageUrl || null,
                source_site: SOURCE,
                scraped_at: new Date().toISOString(),
            };

            if (!applyFilters(listing, log)) return;

            if (seenListings.has(listing.listing_id)) return;
            seenListings.add(listing.listing_id);

            totalAfterFilters += 1;
            log.info(`[BS] ✓ ${listing.year} ${listing.make} ${listing.model} | $${listing.current_bid} | ${listing.state}`);
            await Actor.pushData(listing);
            return;
        }

        // ── Catalogue page — enumerate lots ───────────────────────────────────
        if (label === 'CATALOGUE') {
            const url = page.url();
            log.info(`[BS] Catalogue: ${url}`);

            await waitForPage(page);

            const lotLinks = await extractLotLinks(page, BASE_URL);
            log.info(`[BS] Catalogue has ${lotLinks.length} lot links`);

            for (const { url: lotUrl, cardText } of lotLinks) {
                // Fast pre-filter from card text
                const { year, make } = parseVehicleTitle(cardText);
                if (!make && !isVehicleLot(cardText)) {
                    log.debug(`[BS] Pre-filter non-vehicle: ${cardText.slice(0, 80)}`);
                    continue;
                }
                if (year && year < minYear) {
                    log.debug(`[BS] Pre-filter old year ${year}: ${cardText.slice(0, 60)}`);
                    continue;
                }

                const state = parseState(cardText);
                if (state && CANADIAN_PROVINCES.has(state)) continue;
                if (state && !targetStateSet.has(state)) {
                    log.debug(`[BS] Pre-filter state ${state}: ${cardText.slice(0, 60)}`);
                    continue;
                }
            }

            // Enqueue lots
            const validUrls = lotLinks
                .filter(({ cardText }) => {
                    const { make } = parseVehicleTitle(cardText);
                    return make || isVehicleLot(cardText);
                })
                .map(({ url: u }) => u);

            if (validUrls.length > 0) {
                await enqueueLinks({
                    urls: validUrls,
                    label: 'LOT',
                    userData: { catalogueUrl: url },
                });
            }

            // Pagination — try next page
            const nextPage = await page.evaluate(() => {
                const next = document.querySelector(
                    'a[aria-label="Next page"], a.next, [class*="pagination"] a[rel="next"]',
                );
                return next ? next.getAttribute('href') : null;
            });

            if (nextPage) {
                const nextUrl = new URL(nextPage, BASE_URL).toString();
                log.info(`[BS] Pagination → ${nextUrl}`);
                await enqueueLinks({ urls: [nextUrl], label: 'CATALOGUE' });
            }
            return;
        }

        // ── Catalogue list page ───────────────────────────────────────────────
        const pageNum = request.userData?.pageNum ?? 1;
        log.info(`[BS] Catalogue list page ${pageNum}: ${page.url()}`);

        await waitForPage(page);

        const catalogueLinks = await extractCatalogueLinks(page);
        log.info(`[BS] Found ${catalogueLinks.length} catalogue links`);

        if (!catalogueLinks.length && pageNum === 1) {
            log.warning('[BS] No catalogue links found — page may not have hydrated');
        }

        // Enqueue catalogues — filter out non-US by card text if possible
        const catUrls = catalogueLinks
            .filter(({ cardText }) => {
                const state = parseState(cardText);
                if (state && CANADIAN_PROVINCES.has(state)) return false;
                // If we can detect a state, check it's in target
                // If no state detected, include (let lot page decide)
                return true;
            })
            .slice(0, maxCatalogues)
            .map(({ url }) => url);

        if (catUrls.length > 0) {
            await enqueueLinks({ urls: catUrls, label: 'CATALOGUE' });
        }

        // Pagination for the catalogue list (BidSpotter uses page query param)
        const totalCatalogues = catalogueLinks.length;
        if (totalCatalogues >= 12 && pageNum * 12 < maxCatalogues) {
            const nextUrl = `${BASE_URL}/en-us/auction-catalogues/search-filter?categorytags=Automobiles%2c+Trucks+%26+Vans&country=US&page=${pageNum + 1}`;
            await enqueueLinks({
                urls: [nextUrl],
                label: 'CATALOGUE_LIST',
                userData: { pageNum: pageNum + 1 },
            });
        }
    },
});

const startUrl = `${BASE_URL}/en-us/auction-catalogues/search-filter?categorytags=Automobiles%2c+Trucks+%26+Vans&country=US`;
await crawler.run([{
    url: startUrl,
    label: 'CATALOGUE_LIST',
    userData: { pageNum: 1 },
}]);

console.log(`[BIDSPOTTER COMPLETE] Found: ${totalFound} | Passed filters: ${totalAfterFilters}`);
await Actor.exit();
