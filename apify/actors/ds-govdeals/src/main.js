/**
 * GovDeals Apify Actor — Click-Navigation + API-Intercept approach
 *
 * GovDeals is a Liquidity Services Angular SPA. All direct search URLs route
 * to the home page — the Angular router ignores URL params from old CFM paths.
 *
 * Correct approach:
 * 1. Load homepage, wait for Angular to boot
 * 2. Intercept ALL JSON API calls from the moment the page loads
 * 3. Navigate to the Vehicles/Transportation category via in-page navigation
 *    (either click the category card or use page.evaluate to trigger Angular router)
 * 4. Collect intercepted API responses that look like lot/search results
 * 5. Paginate by injecting page param into the API URL we discover
 *
 * This way we never need to know the URL — we let Angular navigate itself
 * and we capture the API calls it makes.
 */

import { Actor } from 'apify';
import { PlaywrightCrawler } from 'crawlee';

/* ── Constants ─────────────────────────────────────────────── */

const HIGH_RUST_STATES = new Set([
    'OH','MI','PA','NY','WI','MN','IL','IN','MO','IA',
    'ND','SD','NE','KS','WV','ME','NH','VT','MA','RI',
    'CT','NJ','MD','DE',
]);

const HOMEPAGE = 'https://www.govdeals.com/';

const VEHICLE_KEYWORDS = [
    'vehicle','vehicles','transportation','automobile','auto',
    'truck','car','van','bus','motorcycle','trailer',
];

/* ── Actor boot ─────────────────────────────────────────────── */

await Actor.init();

const input = await Actor.getInput() ?? {};
const {
    maxPages      = 8,
    minBid        = 500,
    maxBid        = 35000,
    targetStates  = ['AZ','CA','NV','CO','NM','UT','TX','FL','GA','SC','TN','NC','VA','WA','OR','HI'],
} = input;

let totalFound        = 0;
let totalAfterFilters = 0;

/* ── Helpers ─────────────────────────────────────────────────── */

function extractStateFromLocation(location = '') {
    const m = location.match(/,\s*([A-Z]{2})\s*\d{5}?\s*$/i)
           || location.match(/\b([A-Z]{2})\b\s*\d{5}/i);
    return m ? m[1].toUpperCase() : '';
}

function extractYearFromTitle(title = '') {
    const m = title.match(/\b(19[89]\d|20[0-3]\d)\b/);
    return m ? parseInt(m[1], 10) : null;
}

function parseBid(raw) {
    if (typeof raw === 'number') return raw;
    const m = String(raw ?? '').replace(/,/g, '').match(/[\d.]+/);
    return m ? parseFloat(m[0]) : 0;
}

function extractLotsFromJson(json) {
    if (!json || typeof json !== 'object') return [];
    // Try known Liquidity Services response shapes
    const candidates = [
        json.lots, json.items, json.results, json.data,
        json.data?.lots, json.data?.items, json.data?.results,
        json.payload?.lots, json.payload?.items,
        json.searchResults, json.auctionItems,
    ].filter(Array.isArray);
    if (candidates.length) return candidates[0];
    // If root is an array
    if (Array.isArray(json)) return json;
    return [];
}

function isVehicleLot(lot) {
    const text = [
        lot.title, lot.name, lot.description,
        lot.categoryName, lot.category,
    ].filter(Boolean).join(' ').toLowerCase();
    return VEHICLE_KEYWORDS.some(kw => text.includes(kw));
}

function normalizeLot(lot) {
    const title     = lot.title || lot.name || lot.description || '';
    const location  = lot.location || lot.city || lot.state || '';
    const state     = lot.state || lot.stateCode || extractStateFromLocation(location);
    const bid       = parseBid(lot.currentBid ?? lot.current_bid ?? lot.amount ?? lot.price ?? 0);
    const endTime   = lot.auctionEndDate ?? lot.endDate ?? lot.closingDate ?? lot.endTime ?? null;
    const url       = lot.url || lot.lotUrl || lot.listingUrl
        || (lot.lotId ? `https://www.govdeals.com/lot/${lot.lotId}` : '')
        || (lot.id    ? `https://www.govdeals.com/lot/${lot.id}`    : '');
    return {
        title,
        current_bid:    bid,
        buyer_premium:  0.10,
        doc_fee:        75,
        auction_end_time: endTime,
        location:       location || state,
        state:          String(state).toUpperCase().slice(0, 2),
        listing_url:    url,
        photo_url:      lot.photoUrl || lot.imageUrl || lot.image || '',
        description:    lot.description || '',
        agency_name:    lot.agencyName || lot.agency || lot.sellerName || '',
        source_site:    'govdeals',
        scraped_at:     new Date().toISOString(),
    };
}

async function applyFilters(vehicle) {
    const { state, current_bid: bid, title, mileage } = vehicle;
    if (HIGH_RUST_STATES.has(state)) return false;
    if (bid < minBid || bid > maxBid)  return false;
    const year = extractYearFromTitle(title);
    if (year && (new Date().getFullYear() - year) > 4) return false;
    if (mileage && mileage > 50000) return false;
    return true;
}

/* ── Main crawl ──────────────────────────────────────────────── */

const capturedLotApiUrl = { base: null }; // shared ref for pagination

const crawler = new PlaywrightCrawler({
    maxRequestsPerCrawl: 1, // Single smart session — we handle pagination inside
    requestHandlerTimeoutSecs: 240,
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
        log.info('Loading GovDeals homepage...');

        // ── Helper: register intercept on current page ─────────
        const interceptedLots = [];
        let searchApiUrl = null;

        const registerIntercept = (pg) => {
            pg.on('response', async (response) => {
                const url = response.url();
                const ct  = response.headers()['content-type'] || '';
                if (!ct.includes('json')) return;
                // Skip navigation/menu/recommendation APIs — we want search/lot APIs
                if (url.includes('/menus/') || url.includes('/recommendations') ||
                    url.includes('/navigation') || url.includes('/config')) return;
                if (!url.includes('lqdt') && !url.includes('govdeals') && !url.includes('liquidity')) return;
                try {
                    const body = await response.json().catch(() => null);
                    if (!body) return;
                    const lots = extractLotsFromJson(body);
                    if (lots.length > 0) {
                        log.info(`[INTERCEPT] ${url} → ${lots.length} items`);
                        interceptedLots.push(...lots);
                        if (!searchApiUrl) searchApiUrl = url;
                    }
                } catch (_) { /* ignore */ }
            });
        };

        registerIntercept(page);

        // ── Navigate and wait for Angular to boot ─────────────
        await page.goto(HOMEPAGE, { waitUntil: 'domcontentloaded', timeout: 60000 });
        await page.waitForSelector('app-root, [class*="header"], nav', { timeout: 30000 })
            .catch(() => log.warning('Angular root not found'));
        await page.waitForTimeout(4000);

        // ── Find the MAIN Vehicles/Transportation category ─────
        // Prefer links that say "vehicles and transportation" or just "vehicles"
        // NOT sub-categories like "all-terrain-vehicles", "motorcycles", etc.
        log.info('Finding main Vehicles & Transportation category link...');

        const vehicleHref = await page.evaluate(() => {
            const links = Array.from(document.querySelectorAll('a[href]'));
            const exact  = ['vehicles and transportation', 'vehicles & transportation', 'vehicles'];
            const broad  = ['vehicle', 'transportation', 'automobile'];
            const exclude= ['terrain', 'motorcycle', 'boat', 'watercraft', 'aircraft', 'trailer', 'rv', 'recreational'];

            // First pass: exact match on text
            for (const link of links) {
                const text = (link.textContent || '').trim().toLowerCase();
                if (exact.includes(text)) return link.href;
            }
            // Second pass: broad match, excluding sub-categories
            for (const link of links) {
                const text = (link.textContent || '').trim().toLowerCase();
                const href = (link.href || '').toLowerCase();
                const isExcluded = exclude.some(e => text.includes(e) || href.includes(e));
                if (!isExcluded && broad.some(k => text.includes(k) || href.includes(k))) {
                    return link.href;
                }
            }
            return null;
        });

        if (vehicleHref) {
            log.info(`Navigating to: ${vehicleHref}`);
            await page.goto(vehicleHref, { waitUntil: 'domcontentloaded', timeout: 60000 });
            await page.waitForTimeout(8000);
        } else {
            // Try known GovDeals Angular route patterns for vehicles
            const candidates = [
                'https://www.govdeals.com/en/vehicles-and-transportation',
                'https://www.govdeals.com/en/vehicles',
                'https://www.govdeals.com/en/automobiles',
                'https://www.govdeals.com/search?categoryId=1050',
            ];
            log.info('No nav link found — trying known Angular route patterns');
            for (const url of candidates) {
                await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 }).catch(() => {});
                await page.waitForTimeout(6000);
                if (interceptedLots.length > 0) {
                    log.info(`Got results from: ${url}`);
                    break;
                }
            }
        }

        // ── Process page 1 results ─────────────────────────────
        log.info(`Page 1: intercepted ${interceptedLots.length} lots total`);

        for (const lot of interceptedLots) {
            if (!isVehicleLot(lot)) continue;
            totalFound++;
            const vehicle = normalizeLot(lot);
            if (!(await applyFilters(vehicle))) continue;
            totalAfterFilters++;
            await Actor.pushData(vehicle);
        }
        log.info(`Page 1: found=${totalFound} passed=${totalAfterFilters}`);

        // ── Paginate via page.goto (avoids CORS) ──────────────
        if (searchApiUrl) {
            log.info(`Paginating via: ${searchApiUrl}`);
        } else if (vehicleHref) {
            // No API captured — paginate via Angular URL by appending page param
            log.info('No search API captured — will paginate via URL page params');
        } else {
            log.warning('Could not paginate — no API URL or category URL');
        }

        const baseNavUrl = vehicleHref || null;

        for (let pageNum = 2; pageNum <= maxPages; pageNum++) {
            const prevCount = interceptedLots.length;
            const pageLots  = [];

            // Register fresh intercept for this page's response
            page.on('response', async (response) => {
                const url = response.url();
                const ct  = response.headers()['content-type'] || '';
                if (!ct.includes('json')) return;
                if (url.includes('/menus/') || url.includes('/recommendations') ||
                    url.includes('/navigation') || url.includes('/config')) return;
                if (!url.includes('lqdt') && !url.includes('govdeals') && !url.includes('liquidity')) return;
                try {
                    const body = await response.json().catch(() => null);
                    if (!body) return;
                    const lots = extractLotsFromJson(body);
                    if (lots.length > 0) {
                        log.info(`[P${pageNum} INTERCEPT] ${url} → ${lots.length} items`);
                        pageLots.push(...lots);
                    }
                } catch (_) { /* ignore */ }
            });

            // Navigate to next page
            let nextUrl;
            if (baseNavUrl) {
                const sep = baseNavUrl.includes('?') ? '&' : '?';
                nextUrl = `${baseNavUrl}${sep}page=${pageNum}`;
            } else {
                break;
            }

            log.info(`Navigating page ${pageNum}: ${nextUrl}`);
            await page.goto(nextUrl, { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(() => {});
            await page.waitForTimeout(6000);

            if (!pageLots.length) {
                log.info(`Page ${pageNum}: 0 lots captured — done`);
                break;
            }

            log.info(`Page ${pageNum}: ${pageLots.length} lots`);
            for (const lot of pageLots) {
                if (!isVehicleLot(lot)) continue;
                totalFound++;
                const vehicle = normalizeLot(lot);
                if (!(await applyFilters(vehicle))) continue;
                totalAfterFilters++;
                await Actor.pushData(vehicle);
            }

            await page.waitForTimeout(1500);
        }
    },
});

await crawler.run([{ url: HOMEPAGE }]);

console.log(`[GOVDEALS COMPLETE] Found: ${totalFound} | Passed filters: ${totalAfterFilters}`);
await Actor.exit();
