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
    const { state, current_bid: bid, title } = vehicle;
    if (HIGH_RUST_STATES.has(state)) return false;
    if (bid < minBid || bid > maxBid)  return false;
    const year = extractYearFromTitle(title);
    if (year && (new Date().getFullYear() - year) > 4) return false;
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

        // ── Intercept ALL JSON API responses ──────────────────
        const interceptedRequests = [];
        page.on('response', async (response) => {
            const url = response.url();
            const ct  = response.headers()['content-type'] || '';
            if (!ct.includes('json')) return;
            if (!url.includes('lqdt') && !url.includes('govdeals') && !url.includes('liquidity')) return;
            try {
                const body = await response.json().catch(() => null);
                if (!body) return;
                const lots = extractLotsFromJson(body);
                if (lots.length > 0) {
                    log.info(`[INTERCEPT] ${url} → ${lots.length} items`);
                    interceptedRequests.push({ url, lots, body });
                    // Save the base API URL for pagination
                    if (!capturedLotApiUrl.base) {
                        capturedLotApiUrl.base = url;
                    }
                }
            } catch (_) { /* ignore */ }
        });

        // ── Navigate and wait for Angular to boot ─────────────
        await page.goto(HOMEPAGE, { waitUntil: 'domcontentloaded', timeout: 60000 });

        // Wait for Angular root element and some navigation to render
        await page.waitForSelector('app-root, [class*="header"], nav', { timeout: 30000 })
            .catch(() => log.warning('Angular root not found — continuing anyway'));

        // Give Angular time to hydrate and register routes
        await page.waitForTimeout(5000);

        // ── Find and navigate to Vehicles category ────────────
        log.info('Looking for Vehicles/Transportation category link...');

        const vehicleHref = await page.evaluate(() => {
            const links = Array.from(document.querySelectorAll('a[href]'));
            const kws   = ['vehicle','vehicles','transportation','automobile','auto','truck'];
            for (const link of links) {
                const text = (link.textContent || '').trim().toLowerCase();
                const href = (link.href || '').toLowerCase();
                if (kws.some(k => text.includes(k) || href.includes(k))) {
                    return link.href;
                }
            }
            return null;
        });

        if (vehicleHref) {
            log.info(`Found vehicle category link: ${vehicleHref}`);
            await page.goto(vehicleHref, { waitUntil: 'domcontentloaded', timeout: 60000 });
            await page.waitForTimeout(8000); // Wait for Angular to fetch search results
        } else {
            // Try Angular router navigation via evaluate
            log.info('No direct link found — trying Angular router navigation...');
            await page.evaluate(() => {
                // Look for Angular router instance and navigate
                const routerLinks = Array.from(document.querySelectorAll('[routerLink], [ng-reflect-router-link]'));
                for (const el of routerLinks) {
                    const val = el.getAttribute('routerLink') || el.getAttribute('ng-reflect-router-link') || '';
                    if (val.toLowerCase().includes('vehicle') || val.toLowerCase().includes('transport')) {
                        el.click();
                        return;
                    }
                }
                // Last resort: search for vehicles via URL injection
                window.location.hash = '#/search?categoryId=1050';
            });
            await page.waitForTimeout(8000);
        }

        // ── Collect from first page ────────────────────────────
        log.info(`Intercepted ${interceptedRequests.length} API response(s) so far`);

        // Process all intercepted lots from first page
        for (const { lots } of interceptedRequests) {
            for (const lot of lots) {
                if (!isVehicleLot(lot)) continue;
                totalFound++;
                const vehicle = normalizeLot(lot);
                if (!(await applyFilters(vehicle))) continue;
                totalAfterFilters++;
                await Actor.pushData(vehicle);
            }
        }

        log.info(`Page 1: found=${totalFound} passed=${totalAfterFilters}`);

        // ── Paginate via direct API calls ──────────────────────
        if (capturedLotApiUrl.base) {
            log.info(`Paginating via captured API: ${capturedLotApiUrl.base}`);

            for (let pageNum = 2; pageNum <= maxPages; pageNum++) {
                // Build next-page URL — try common pagination param patterns
                let nextUrl = capturedLotApiUrl.base
                    .replace(/([?&]page=)\d+/, `$1${pageNum}`)
                    .replace(/([?&]pageNumber=)\d+/, `$1${pageNum}`)
                    .replace(/([?&]pageNum=)\d+/, `$1${pageNum}`)
                    .replace(/([?&]offset=)\d+/, (_, prefix) => `${prefix}${(pageNum - 1) * 20}`);

                // If no page param found, append it
                if (!nextUrl.match(/[?&]page=/)) {
                    nextUrl += (nextUrl.includes('?') ? '&' : '?') + `page=${pageNum}`;
                }

                log.info(`Fetching page ${pageNum}: ${nextUrl}`);

                try {
                    const resp = await page.evaluate(async (url) => {
                        const r = await fetch(url, {
                            credentials: 'include',
                            headers: { 'Accept': 'application/json' },
                        });
                        return r.ok ? r.json() : null;
                    }, nextUrl);

                    if (!resp) { log.info(`Page ${pageNum}: no response`); break; }

                    const lots = extractLotsFromJson(resp);
                    if (!lots.length) { log.info(`Page ${pageNum}: 0 lots — done`); break; }

                    log.info(`Page ${pageNum}: ${lots.length} lots`);
                    for (const lot of lots) {
                        if (!isVehicleLot(lot)) continue;
                        totalFound++;
                        const vehicle = normalizeLot(lot);
                        if (!(await applyFilters(vehicle))) continue;
                        totalAfterFilters++;
                        await Actor.pushData(vehicle);
                    }
                } catch (err) {
                    log.warning(`Page ${pageNum} fetch failed: ${err.message}`);
                    break;
                }

                await page.waitForTimeout(2000); // polite delay
            }
        } else {
            log.warning('No API URL captured — could not paginate. DOM body preview:');
            const preview = await page.evaluate(() => document.body.innerText.slice(0, 500));
            log.warning(preview);
        }
    },
});

await crawler.run([{ url: HOMEPAGE }]);

console.log(`[GOVDEALS COMPLETE] Found: ${totalFound} | Passed filters: ${totalAfterFilters}`);
await Actor.exit();
