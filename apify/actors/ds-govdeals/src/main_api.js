/**
 * GovDeals Free Replacement Scraper — Token Capture + Direct API
 *
 * STATUS: TEMPLATE — not yet validated. See REVERSE_ENGINEER.md.
 *
 * Strategy:
 * 1. Load GovDeals homepage in Playwright
 * 2. Intercept ALL requests to maestro.lqdt1.com (not just responses)
 * 3. Capture the Authorization/auth headers from the first API call
 * 4. Use those headers to call the search API directly for all pages
 * 5. No DOM scraping — pure JSON API calls after auth capture
 *
 * This replaces parseforge~govdeals-scraper ($14.99/mo) once validated.
 */

import { Actor } from 'apify';
import { PlaywrightCrawler } from 'crawlee';

const HIGH_RUST_STATES = new Set([
    'OH','MI','PA','NY','WI','MN','IL','IN','MO','IA',
    'ND','SD','NE','KS','WV','ME','NH','VT','MA','RI',
    'CT','NJ','MD','DE',
]);

await Actor.init();
const input = await Actor.getInput() ?? {};
const { maxPages = 10, minBid = 500, maxBid = 35000 } = input;

let totalFound = 0, totalPassed = 0;
const capturedAuth = { headers: null, searchUrl: null };

// ── Helper: extract lots from any known Liquidity Services API shape ──
function extractLots(json) {
    if (!json || typeof json !== 'object') return [];
    const candidates = [
        json.assets, json.lots, json.items, json.results,
        json.data?.assets, json.data?.lots, json.data?.items,
        json.payload?.assets, json.payload?.lots,
        json.searchResults,
    ].filter(Array.isArray);
    if (candidates.length) return candidates[0];
    if (Array.isArray(json)) return json;
    return [];
}

function passes(item) {
    const state = (item.locationState || item.state || '').toUpperCase();
    if (HIGH_RUST_STATES.has(state)) return false;
    const bid = item.currentBid || item.current_bid || 0;
    if (bid < minBid || bid > maxBid) return false;
    const year = parseInt(item.modelYear || item.year || 0);
    if (year && (new Date().getFullYear() - year) > 4) return false;
    return true;
}

const crawler = new PlaywrightCrawler({
    maxRequestsPerCrawl: 1,
    requestHandlerTimeoutSecs: 180,
    async requestHandler({ page, log }) {
        log.info('Loading GovDeals — capturing auth token...');

        // ── Intercept REQUESTS to capture auth headers ────────
        page.on('request', (request) => {
            const url = request.url();
            if (!url.includes('maestro.lqdt1.com')) return;
            const headers = request.headers();
            // Capture first request with meaningful auth
            if (!capturedAuth.headers && (
                headers['authorization'] ||
                headers['x-api-key'] ||
                headers['cookie']
            )) {
                log.info(`[AUTH CAPTURED] ${url}`);
                log.info(`Auth headers: ${JSON.stringify({
                    authorization: headers['authorization'],
                    'x-api-key': headers['x-api-key'],
                    cookie: headers['cookie'] ? '[present]' : null,
                })}`);
                capturedAuth.headers = headers;
            }
        });

        // ── Also capture responses to find search endpoint ────
        page.on('response', async (response) => {
            const url = response.url();
            const ct = response.headers()['content-type'] || '';
            if (!url.includes('maestro.lqdt1.com') || !ct.includes('json')) return;
            if (url.includes('/menus/') || url.includes('/recommendations')) return;
            try {
                const body = await response.json().catch(() => null);
                if (!body) return;
                const lots = extractLots(body);
                if (lots.length > 0 && !capturedAuth.searchUrl) {
                    log.info(`[SEARCH URL FOUND] ${url} → ${lots.length} items`);
                    capturedAuth.searchUrl = url;
                }
            } catch (_) {}
        });

        // ── Load homepage and navigate to vehicles ────────────
        await page.goto('https://www.govdeals.com/', {
            waitUntil: 'domcontentloaded', timeout: 60000
        });
        await page.waitForTimeout(5000);

        // Navigate to vehicles category
        const vehicleHref = await page.evaluate(() => {
            const links = Array.from(document.querySelectorAll('a[href]'));
            const exact = ['vehicles and transportation', 'vehicles & transportation', 'vehicles'];
            for (const link of links) {
                const text = (link.textContent || '').trim().toLowerCase();
                if (exact.includes(text)) return link.href;
            }
            for (const link of links) {
                const text = (link.textContent || '').trim().toLowerCase();
                const href = (link.href || '').toLowerCase();
                const exclude = ['terrain', 'motorcycle', 'boat', 'aircraft', 'trailer'];
                if (!exclude.some(e => text.includes(e)) &&
                    (text.includes('vehicle') || href.includes('vehicle'))) {
                    return link.href;
                }
            }
            return null;
        });

        if (vehicleHref) {
            log.info(`Navigating to: ${vehicleHref}`);
            await page.goto(vehicleHref, { waitUntil: 'domcontentloaded', timeout: 60000 });
            await page.waitForTimeout(8000);
        }

        // ── Report auth capture results ────────────────────────
        if (capturedAuth.headers) {
            log.info('✅ Auth headers captured successfully');
            log.info(`Search API URL: ${capturedAuth.searchUrl || 'NOT FOUND'}`);

            // If we have both auth + search URL, paginate directly
            if (capturedAuth.searchUrl) {
                await paginateWithAuth(page, log);
            }
        } else {
            log.warning('❌ No auth headers captured — Angular may not have made authenticated calls yet');
            log.warning('Possible reasons: token in JS bundle, not in request headers, or cookie-based auth');
        }
    },
});

async function paginateWithAuth(page, log) {
    const { headers, searchUrl } = capturedAuth;

    for (let pageNum = 1; pageNum <= maxPages; pageNum++) {
        const nextUrl = searchUrl
            .replace(/([?&]page=)\d+/, `$1${pageNum}`)
            .replace(/([?&]pageNumber=)\d+/, `$1${pageNum}`);

        const finalUrl = nextUrl.includes('page=')
            ? nextUrl
            : nextUrl + (nextUrl.includes('?') ? '&' : '?') + `page=${pageNum}`;

        log.info(`Fetching page ${pageNum}: ${finalUrl}`);

        try {
            const resp = await page.evaluate(async ({ url, hdrs }) => {
                const r = await fetch(url, {
                    method: 'GET',
                    headers: hdrs,
                    credentials: 'include',
                });
                return r.ok ? r.json() : null;
            }, { url: finalUrl, hdrs: headers });

            if (!resp) { log.info(`Page ${pageNum}: no response`); break; }
            const lots = extractLots(resp);
            if (!lots.length) { log.info(`Page ${pageNum}: empty — done`); break; }

            log.info(`Page ${pageNum}: ${lots.length} lots`);
            for (const lot of lots) {
                totalFound++;
                if (!passes(lot)) continue;
                totalPassed++;
                await Actor.pushData({
                    title:         lot.title || '',
                    make:          lot.make || '',
                    model:         lot.model || '',
                    modelYear:     lot.modelYear || lot.year || null,
                    currentBid:    lot.currentBid || lot.current_bid || 0,
                    locationState: lot.locationState || lot.state || '',
                    locationCity:  lot.locationCity || '',
                    auctionEndUtc: lot.auctionEndUtc || lot.auctionEnd || null,
                    url:           lot.url || `https://www.govdeals.com/en/asset/${lot.accountId}/${lot.assetId}`,
                    seller:        lot.seller || '',
                    imageUrl:      lot.imageUrl || '',
                    photos:        lot.photos || [],
                    vin:           lot.vin || null,
                    meterCount:    lot.meterCount || null,
                    breadcrumbs:   lot.breadcrumbs || [],
                    source_site:   'govdeals',
                    scraped_at:    new Date().toISOString(),
                });
            }
        } catch (err) {
            log.warning(`Page ${pageNum} failed: ${err.message}`);
            break;
        }
        await page.waitForTimeout(1000);
    }
}

await crawler.run([{ url: 'https://www.govdeals.com/' }]);
console.log(`[GOVDEALS FREE] Found: ${totalFound} | Passed: ${totalPassed}`);
console.log(`Auth captured: ${!!capturedAuth.headers} | Search URL: ${capturedAuth.searchUrl || 'none'}`);
await Actor.exit();
