/**
 * GovDeals Free Replacement Scraper — Token Capture + Direct API
 *
 * STATUS: Phase 5 recon wired in. See REVERSE_ENGINEER.md for captured traffic.
 *
 * Strategy:
 * 1. Load GovDeals homepage in Playwright
 * 2. Intercept ALL requests to maestro.lqdt1.com (not just responses)
 * 3. Capture the x-api-key header and POST payload shape from /search/list
 * 4. Use those values to call the search API directly for all pages
 * 5. No DOM scraping — pure JSON API calls after auth capture
 *
 * Phase 5 captured:
 * - POST https://maestro.lqdt1.com/search/list
 * - x-api-key auth header
 * - assetSearchResults response shape
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
const capturedApi = {
    apiKey: null,
    searchUrl: 'https://maestro.lqdt1.com/search/list',
    searchPayload: null,
    requestHeaders: null,
};

// ── Helper: extract lots from any known Liquidity Services API shape ──
function extractLots(json) {
    if (!json || typeof json !== 'object') return [];
    const candidates = [
        json.assetSearchResults,
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
    const bid = item.currentBid || item.current_bid || item.assetBidPrice || 0;
    if (bid < minBid || bid > maxBid) return false;
    const year = parseInt(item.modelYear || item.year || 0);
    if (year && (new Date().getFullYear() - year) > 4) return false;
    return true;
}

const crawler = new PlaywrightCrawler({
    maxRequestsPerCrawl: 1,
    requestHandlerTimeoutSecs: 180,
    async requestHandler({ page, log }) {
        log.info('Loading GovDeals and capturing maestro /search/list traffic...');

        // ── Intercept REQUESTS to capture the x-api-key and search payload ──
        page.on('request', (request) => {
            const url = request.url();
            if (!url.includes('maestro.lqdt1.com')) return;
            const headers = request.headers();

            if (!capturedApi.apiKey && headers['x-api-key']) {
                capturedApi.apiKey = headers['x-api-key'];
                capturedApi.requestHeaders = {
                    accept: headers.accept || 'application/json, text/plain, */*',
                    'content-type': headers['content-type'] || 'application/json',
                    'x-api-key': headers['x-api-key'],
                };
                log.info(`[API KEY CAPTURED] ${headers['x-api-key']} via ${url}`);
            }

            if (url.includes('/search/list') && request.method() === 'POST') {
                const postData = request.postData();
                if (!postData) return;
                try {
                    capturedApi.searchPayload = JSON.parse(postData);
                    capturedApi.searchUrl = url;
                    log.info(`[SEARCH PAYLOAD CAPTURED] ${url}`);
                } catch (err) {
                    log.warning(`Failed to parse search payload: ${err.message}`);
                }
            }
        });

        // ── Capture response metadata to confirm the real search endpoint ───
        page.on('response', async (response) => {
            const url = response.url();
            const ct = response.headers()['content-type'] || '';
            if (!url.includes('maestro.lqdt1.com') || !ct.includes('json')) return;
            try {
                const body = await response.json().catch(() => null);
                if (!body) return;
                const lots = extractLots(body);
                if (lots.length > 0 && url.includes('/search/list')) {
                    log.info(`[SEARCH URL FOUND] ${url} → ${lots.length} items`);
                    capturedApi.searchUrl = url;
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

        // ── Report capture results ─────────────────────────────
        if (capturedApi.apiKey) {
            log.info('✅ maestro x-api-key captured successfully');
            log.info(`Search API URL: ${capturedApi.searchUrl || 'NOT FOUND'}`);

            if (capturedApi.searchPayload) {
                await paginateWithAuth(page, log);
            } else {
                log.warning('❌ Search payload not captured — no /search/list replay yet');
            }
        } else {
            log.warning('❌ No maestro x-api-key captured');
            log.warning('Angular may not have hit maestro yet, or the request pattern changed');
        }
    },
});

async function paginateWithAuth(page, log) {
    const { requestHeaders, searchPayload, searchUrl } = capturedApi;

    for (let pageNum = 1; pageNum <= maxPages; pageNum++) {
        const payload = {
            ...searchPayload,
            page: pageNum,
            displayRows: searchPayload.displayRows || 24,
            requestType: searchPayload.requestType || 'search',
            responseStyle: searchPayload.responseStyle || 'productsOnly',
        };

        log.info(`Fetching page ${pageNum}: ${searchUrl}`);

        try {
            const resp = await page.evaluate(async ({ url, hdrs, body }) => {
                const r = await fetch(url, {
                    method: 'POST',
                    headers: hdrs,
                    body: JSON.stringify(body),
                });
                const json = r.ok ? await r.json() : null;
                return {
                    ok: r.ok,
                    status: r.status,
                    total: r.headers.get('x-total-count'),
                    json,
                };
            }, { url: searchUrl, hdrs: requestHeaders, body: payload });

            if (!resp?.ok || !resp.json) {
                log.info(`Page ${pageNum}: no response (status ${resp?.status ?? 'unknown'})`);
                break;
            }

            const lots = extractLots(resp.json);
            if (!lots.length) { log.info(`Page ${pageNum}: empty — done`); break; }

            log.info(`Page ${pageNum}: ${lots.length} lots (x-total-count: ${resp.total || 'n/a'})`);
            for (const lot of lots) {
                totalFound++;
                if (!passes(lot)) continue;
                totalPassed++;
                await Actor.pushData({
                    title:         lot.assetShortDescription || lot.title || '',
                    make:          lot.makebrand || lot.make || '',
                    model:         lot.model || '',
                    modelYear:     lot.modelYear || lot.year || null,
                    currentBid:    lot.currentBid || lot.current_bid || lot.assetBidPrice || 0,
                    locationState: lot.locationState || lot.state || '',
                    locationCity:  lot.locationCity || lot.city || '',
                    auctionEndUtc: lot.assetAuctionEndDateUtc || lot.auctionEndUtc || lot.auctionEnd || null,
                    url:           lot.url || `https://www.govdeals.com/asset/${lot.assetId}/${lot.accountId}`,
                    seller:        lot.displaySellerName || lot.companyName || lot.seller || '',
                    imageUrl:      lot.imageUrl || (lot.photo ? `https://webassets.lqdt1.com/assets/photos/${lot.photo}` : ''),
                    photos:        lot.photos || (lot.photo ? [`https://webassets.lqdt1.com/assets/photos/${lot.photo}`] : []),
                    vin:           lot.vin || null,
                    meterCount:    lot.meterCount || null,
                    breadcrumbs:   lot.breadcrumbs || [lot.categoryDescription].filter(Boolean),
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
console.log(`API key captured: ${!!capturedApi.apiKey} | Search URL: ${capturedApi.searchUrl || 'none'}`);
await Actor.exit();
