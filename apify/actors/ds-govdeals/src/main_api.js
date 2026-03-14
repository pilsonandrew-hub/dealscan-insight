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
    interceptedLots: [],  // lots captured directly from page responses
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
    if (year && (new Date().getFullYear() - year) > 12) return false;
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
                    // Save intercepted lots directly — don't rely on direct API replay
                    for (const lot of lots) {
                        if (!capturedApi.interceptedLots.find(l => l.assetId === lot.assetId)) {
                            capturedApi.interceptedLots.push(lot);
                        }
                    }
                }
            } catch (_) {}
        });

        // ── Load homepage and navigate to passenger vehicles ────────────
        // GovDeals category URLs for passenger/light vehicles:
        // /en/passenger-vehicles  (sedans, SUVs, trucks)
        // /en/trucks-and-vans     (pickup trucks, vans)
        // We hit both to maximize coverage
        const VEHICLE_CATEGORY_URLS = [
            'https://www.govdeals.com/en/passenger-vehicles',
            'https://www.govdeals.com/en/trucks-and-vans',
            'https://www.govdeals.com/en/suvs',
        ];

        // Start with homepage to capture API key, then navigate to passenger vehicles
        await page.goto('https://www.govdeals.com/', {
            waitUntil: 'domcontentloaded', timeout: 60000
        });
        await page.waitForTimeout(4000);

        // Navigate to first passenger vehicle category directly
        for (const categoryUrl of VEHICLE_CATEGORY_URLS) {
            if (capturedApi.interceptedLots.length >= 20) break;
            log.info(`Navigating to: ${categoryUrl}`);
            await page.goto(categoryUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
            await page.waitForTimeout(6000);
        }

        // ── Report capture results ─────────────────────────────
        if (capturedApi.apiKey) {
            log.info('✅ maestro x-api-key captured successfully');
            log.info(`Search API URL: ${capturedApi.searchUrl || 'NOT FOUND'}`);

            // Attempt direct API pagination
            if (capturedApi.searchPayload) {
                await paginateWithAuth(page, log);
            }

            // Fallback: if pagination saved nothing, use intercepted lots from response listener
            if (totalPassed === 0 && capturedApi.interceptedLots.length > 0) {
                log.info(`Pagination saved 0 — falling back to ${capturedApi.interceptedLots.length} intercepted lots`);
                for (const lot of capturedApi.interceptedLots) {
                    totalFound++;
                    if (!passes(lot)) continue;
                    totalPassed++;
                    await Actor.pushData(normalizeLot(lot));
                }
            }
        } else {
            log.warning('❌ No maestro x-api-key captured');
            log.warning('Angular may not have hit maestro yet, or the request pattern changed');
        }
    },
});

function normalizeLot(lot) {
    return {
        title:         lot.assetShortDescription || lot.title || '',
        make:          lot.makebrand || lot.make || '',
        model:         lot.model || '',
        year:          lot.modelYear || lot.year || null,
        current_bid:   lot.currentBid || lot.current_bid || lot.assetBidPrice || 0,
        state:         lot.locationState || lot.state || '',
        city:          lot.locationCity || lot.city || '',
        auction_end_time: lot.assetAuctionEndDateUtc || lot.auctionEndUtc || lot.auctionEnd || null,
        listing_url:   lot.url || `https://www.govdeals.com/asset/${lot.assetId}/${lot.accountId}`,
        seller:        lot.displaySellerName || lot.companyName || lot.seller || '',
        photo_url:     lot.imageUrl || (lot.photo ? `https://webassets.lqdt1.com/assets/photos/${lot.photo}` : ''),
        vin:           lot.vin || null,
        mileage:       lot.meterCount || null,
        source_site:   'govdeals',
        scraped_at:    new Date().toISOString(),
    };
}

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
                    headers: { ...hdrs, origin: 'https://www.govdeals.com', referer: 'https://www.govdeals.com/' },
                    credentials: 'include',
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
                await Actor.pushData(normalizeLot(lot));
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
