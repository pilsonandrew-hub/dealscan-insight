/**
 * GovDeals COMPLETED Auctions Scraper — Sold prices for DOS calibration
 *
 * Strategy:
 * 1. Load GovDeals with ?timing=completed in Playwright
 * 2. Intercept requests to maestro.lqdt1.com to capture x-api-key
 * 3. Call search API with timing: 'completed' to get closed auctions
 * 4. Capture ALL completed sales (no filtering) for dealer_sales DOS calibration
 *
 * Key API parameter: timing: 'completed' in POST payload
 */

import { Actor } from 'apify';
import { PlaywrightCrawler } from 'crawlee';

// Standard 17-char VIN pattern (no I, O, Q)
const VIN_PATTERN = /\b([A-HJ-NPR-Z0-9]{17})\b/i;
const MAX_DETAIL_PAGES = 100;  // Reduced for sold auctions

await Actor.init();
const input = await Actor.getInput() ?? {};
const { maxPages = 10, maxItems = 500 } = input;

let totalFound = 0, totalPassed = 0;
const capturedApi = {
    apiKey: null,
    searchUrl: 'https://maestro.lqdt1.com/search/list',
    searchPayload: null,
    requestHeaders: null,
    interceptedLots: [],  // lots captured directly from page responses
};

// Collect passing lots in memory so we can VIN-enrich before pushing
const passingLots = [];

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

/**
 * Extract VIN from lot JSON fields. Checks explicit vin field first,
 * then falls back to regex over description/notes text.
 */
function extractVinFromLot(lot) {
    // 1. Explicit VIN field
    if (lot.vin && VIN_PATTERN.test(lot.vin)) return lot.vin.toUpperCase();

    // 2. Regex over description/notes fields
    const textFields = [
        lot.assetShortDescription,
        lot.longDescription,
        lot.itemDescription,
        lot.description,
        lot.notes,
        lot.assetLongDescription,
        lot.itemNotes,
    ].filter(Boolean).join(' ');

    const match = textFields.match(VIN_PATTERN);
    return match ? match[1].toUpperCase() : null;
}

const crawler = new PlaywrightCrawler({
    maxRequestsPerCrawl: 3,
    requestHandlerTimeoutSecs: 360, // extended for detail page scraping
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
        // Query completed/sold auctions for clearance price data
        const VEHICLE_CATEGORY_URLS = [
            'https://www.govdeals.com/en/passenger-vehicles?timing=completed',
            'https://www.govdeals.com/en/trucks-and-vans?timing=completed',
            'https://www.govdeals.com/en/suvs?timing=completed',
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

        // ── Save results ───────────────────────────────────────
        if (capturedApi.apiKey) {
            log.info('✅ maestro x-api-key captured successfully');
            log.info(`Search API URL: ${capturedApi.searchUrl || 'NOT FOUND'}`);

            // Step 1: Collect intercepted lots from page load (page 1)
            const seenIds = new Set();
            if (capturedApi.interceptedLots.length > 0) {
                log.info(`Processing ${capturedApi.interceptedLots.length} intercepted lots from page load`);
                for (const lot of capturedApi.interceptedLots) {
                    seenIds.add(lot.assetId);
                    totalFound++;
                    // No filtering for sold actor — capture ALL completed sales for DOS calibration
                    totalPassed++;
                    passingLots.push(normalizeLot(lot));
                    if (passingLots.length >= maxItems) break;
                }
            }

            // Step 2: Attempt direct API pagination for pages 2+ (Node.js fetch, no CORS)
            if (capturedApi.searchPayload && passingLots.length < maxItems) {
                await paginateWithAuth(page, log, seenIds);
            }

            // Step 3: Push all lots immediately (before VIN scraping to avoid data loss)
            for (const lot of passingLots) {
                await Actor.pushData(lot);
            }
            log.info(`[GOVDEALS-SOLD] Pushed ${passingLots.length} completed auction records`);
        } else {
            log.warning('❌ No maestro x-api-key captured');
            log.warning('Angular may not have hit maestro yet, or the request pattern changed');
        }
    },
});

function normalizeLot(lot) {
    // For completed auctions, sold_price is the key field — try multiple API field names
    const soldPrice = lot.winningBid || lot.soldPrice || lot.assetWinningBid ||
                      lot.closingBid || lot.finalBid || lot.awardAmount ||
                      lot.currentBid || lot.assetBidPrice || 0;
    return {
        title:         lot.assetShortDescription || lot.title || '',
        make:          lot.makebrand || lot.make || '',
        model:         lot.model || '',
        year:          lot.modelYear || lot.year || null,
        current_bid:   lot.currentBid || lot.current_bid || lot.assetBidPrice || 0,
        sold_price:    soldPrice,
        state:         lot.locationState || lot.state || '',
        city:          lot.locationCity || lot.city || '',
        auction_end_time: lot.assetAuctionEndDateUtc || lot.auctionEndUtc || lot.auctionEnd || null,
        listing_url:   lot.url || `https://www.govdeals.com/asset/${lot.assetId}/${lot.accountId}`,
        seller:        lot.displaySellerName || lot.companyName || lot.seller || '',
        photo_url:     lot.imageUrl || (lot.photo ? `https://webassets.lqdt1.com/assets/photos/${lot.photo}` : ''),
        vin:           extractVinFromLot(lot),
        mileage:       lot.meterCount || null,
        source_site:   'govdeals-sold',
        scraped_at:    new Date().toISOString(),
    };
}

/**
 * Visit GovDeals detail pages for lots missing a VIN.
 * Caps at MAX_DETAIL_PAGES (200) to stay within Apify free tier limits.
 * Rate-limited to ~1 req/sec.
 */
async function scrapeDetailPagesForVin(page, lots, log) {
    const lotsWithoutVin = lots.filter(l => !l.vin && l.listing_url);
    const toScrape = lotsWithoutVin.slice(0, MAX_DETAIL_PAGES);

    if (toScrape.length === 0) {
        log.info('[VIN DETAIL] All lots already have VINs or no detail URLs — skipping detail scrape');
        return;
    }

    log.info(`[VIN DETAIL] Scraping detail pages for ${toScrape.length} lots without VIN`);
    let vinFound = 0;

    for (const lot of toScrape) {
        try {
            await page.goto(lot.listing_url, { waitUntil: 'domcontentloaded', timeout: 30000 });
            // GovDeals is Angular SPA — wait for content to render
            await page.waitForTimeout(2000);

            const bodyText = await page.evaluate(() => document.body.innerText || document.body.textContent || '');

            // Look for explicit VIN label first
            const vinLabelMatch = bodyText.match(/\bVIN[:\s#\-]*([A-HJ-NPR-Z0-9]{17})\b/i)
                ?? bodyText.match(/Vehicle Identification Number[:\s]*([A-HJ-NPR-Z0-9]{17})\b/i);
            const rawMatch = vinLabelMatch ?? bodyText.match(VIN_PATTERN);

            if (rawMatch) {
                lot.vin = rawMatch[1].toUpperCase();
                vinFound++;
                log.info(`[VIN FOUND] ${lot.vin} — ${lot.title}`);
            }

            // ~1 req/sec
            await page.waitForTimeout(1000);
        } catch (err) {
            log.warning(`[VIN DETAIL] Failed for ${lot.listing_url}: ${err.message}`);
        }
    }

    log.info(`[VIN DETAIL] Complete: scraped ${toScrape.length} pages, found ${vinFound} VINs`);
}

async function paginateWithAuth(page, log, seenIds = new Set()) {
    const { requestHeaders, searchPayload, searchUrl } = capturedApi;

    for (let pageNum = 1; pageNum <= maxPages; pageNum++) {
        const payload = {
            ...searchPayload,
            page: pageNum,
            displayRows: searchPayload.displayRows || 24,
            requestType: searchPayload.requestType || 'search',
            responseStyle: searchPayload.responseStyle || 'productsOnly',
            timing: 'completed',  // Filter for completed/sold auctions
        };

        log.info(`Fetching page ${pageNum} via Node fetch: ${searchUrl}`);

        try {
            // Use Node.js fetch (no CORS restrictions, unlike page.evaluate browser fetch)
            const nodeResp = await fetch(searchUrl, {
                method: 'POST',
                headers: {
                    ...requestHeaders,
                    'content-type': 'application/json',
                    'origin': 'https://www.govdeals.com',
                    'referer': 'https://www.govdeals.com/',
                },
                body: JSON.stringify(payload),
            });
            const resp = {
                ok: nodeResp.ok,
                status: nodeResp.status,
                total: nodeResp.headers.get('x-total-count'),
                json: nodeResp.ok ? await nodeResp.json() : null,
            };

            if (!resp?.ok || !resp.json) {
                log.info(`Page ${pageNum}: no response (status ${resp?.status ?? 'unknown'})`);
                break;
            }

            const lots = extractLots(resp.json);
            if (!lots.length) { log.info(`Page ${pageNum}: empty — done`); break; }

            log.info(`Page ${pageNum}: ${lots.length} lots (x-total-count: ${resp.total || 'n/a'})`);
            for (const lot of lots) {
                if (seenIds.has(lot.assetId)) continue; // already saved from intercept
                seenIds.add(lot.assetId);
                totalFound++;
                // No filtering for sold actor — capture ALL completed sales for DOS calibration
                totalPassed++;
                passingLots.push(normalizeLot(lot));
                if (passingLots.length >= maxItems) {
                    log.info(`Reached maxItems limit (${maxItems}) — stopping pagination`);
                    return;
                }
            }
        } catch (err) {
            log.warning(`Page ${pageNum} failed: ${err.message}`);
            break;
        }
        await page.waitForTimeout(1000);
    }
}

await crawler.run([{ url: 'https://www.govdeals.com/' }]);
console.log(`[GOVDEALS-SOLD] Found: ${totalFound} | Collected: ${totalPassed}`);
console.log(`API key captured: ${!!capturedApi.apiKey} | Search URL: ${capturedApi.searchUrl || 'none'}`);
console.log(`VINs extracted: ${passingLots.filter(l => l.vin).length} / ${passingLots.length} lots`);
await Actor.exit();
