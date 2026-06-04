/**
 * GovDeals COMPLETED Auctions Scraper — Sold prices for DOS calibration
 *
 * Strategy:
 * 1. Load GovDeals with ?timing=completed in Playwright
 * 2. Intercept requests to maestro.lqdt1.com to capture x-api-key
 * 3. Call search API with timing: 'completed' to get closed auctions
 * 4. Capture approved DealerScope comp models for dealer_sales DOS calibration
 *
 * Key API parameter: timing: 'completed' in POST payload
 */

import { Actor } from 'apify';
import { PlaywrightCrawler } from 'crawlee';
import { randomUUID } from 'node:crypto';
import {
    completedSaleDate,
    completedSaleRejectionReason,
} from './sold_date_contract.js';
import {
    createQueryDiagnostics,
    recordLotDecision,
} from './source_quality_diagnostics.js';
import {
    DEFAULT_TARGET_TERMS,
    matchesTargetTerms,
    normalizeTargetSearchQueries,
    normalizeTargetTerms,
} from './target_scope.js';

// Standard 17-char VIN pattern (no I, O, Q)
const VIN_PATTERN = /\b([A-HJ-NPR-Z0-9]{17})\b/i;
const MAX_DETAIL_PAGES = 100;  // Reduced for sold auctions
const GOVDEALS_COMPLETED_SEARCH_URL_BASE = 'https://www.govdeals.com/index.cfm?fa=Main.AdvSearchResultsNew&searchPg=1&category=4100&timing=completed';
const DEFAULT_DISPLAY_ROWS = 24;
const DEFAULT_MAX_SEARCH_QUERIES = DEFAULT_TARGET_TERMS.length;
const runStartedAt = new Date();

await Actor.init();
const input = await Actor.getInput() ?? {};
const { maxPages = 10, maxItems = 500, searchQuery = "", maxSearchQueries = DEFAULT_MAX_SEARCH_QUERIES } = input;
const targetTerms = normalizeTargetTerms(input.targetTerms);
const targetSearchQueries = normalizeTargetSearchQueries({
    searchQuery,
    targetSearchQueries: input.targetSearchQueries,
    targetTerms: input.targetTerms,
    maxSearchQueries,
});

let totalFound = 0, totalPassed = 0, totalSkippedOutOfScope = 0, totalSkippedNotCompleted = 0;
const completedSaleRejectionCounts = {};
const queryDiagnostics = createQueryDiagnostics(['intercepted', ...targetSearchQueries]);
const capturedApi = {
    apiKey: null,
    searchUrl: 'https://maestro.lqdt1.com/search/list',
    searchPayload: null,
    requestHeaders: null,
    interceptedLots: [],  // lots captured directly from page responses
};

// Collect passing lots in memory so we can VIN-enrich before pushing
const passingLots = [];

function replayHeadersFromBrowser(headers) {
    const required = [
        'x-api-key',
        'x-user-id',
    ];
    const replay = {};
    for (const key of required) {
        if (headers[key]) replay[key] = headers[key];
    }
    replay.accept = headers.accept || 'application/json, text/plain, */*';
    replay['content-type'] = headers['content-type'] || 'application/json';
    replay.origin = 'https://www.govdeals.com';
    replay.referer = 'https://www.govdeals.com/';
    if (headers['user-agent']) replay['user-agent'] = headers['user-agent'];
    return replay;
}

function headersForReplayPage(headers) {
    return {
        ...headers,
        'x-api-correlation-id': randomUUID(),
    };
}

function completedSearchUrl(searchText) {
    const trimmed = String(searchText || '').trim();
    return trimmed
        ? `${GOVDEALS_COMPLETED_SEARCH_URL_BASE}&kWord=${encodeURIComponent(trimmed)}`
        : GOVDEALS_COMPLETED_SEARCH_URL_BASE;
}

function safeJsonParse(text) {
    try {
        return JSON.parse(text);
    } catch (_) {
        return null;
    }
}

function stageTargetLot(lot, seenIds = null, searchText = 'intercepted') {
    if (seenIds) seenIds.add(lot.assetId);
    totalFound++;
    if (!matchesTargetTerms(lot, targetTerms)) {
        totalSkippedOutOfScope++;
        recordLotDecision(queryDiagnostics, searchText, 'out_of_scope', lot);
        return false;
    }
    const saleRejectionReason = completedSaleRejectionReason(lot, runStartedAt);
    if (saleRejectionReason) {
        totalSkippedNotCompleted++;
        completedSaleRejectionCounts[saleRejectionReason] = (completedSaleRejectionCounts[saleRejectionReason] || 0) + 1;
        recordLotDecision(queryDiagnostics, searchText, saleRejectionReason, lot);
        return false;
    }
    totalPassed++;
    recordLotDecision(queryDiagnostics, searchText, 'passed', lot);
    passingLots.push(normalizeLot(lot));
    return true;
}

function sourceQualityProof() {
    return {
        record_type: 'source_quality_proof',
        source_site: 'govdeals-sold',
        found_rows_total: totalFound,
        prefilter_passed_rows_total: totalPassed,
        pushed_rows_total: passingLots.length,
        pushed_rows_with_vin: passingLots.filter(lot => lot.vin).length,
        pushed_rows_with_mileage: passingLots.filter(lot => lot.mileage !== null && lot.mileage !== undefined && lot.mileage !== '').length,
        pushed_rows_missing_vin: passingLots.filter(lot => !lot.vin).length,
        pushed_rows_missing_mileage: passingLots.filter(lot => lot.mileage === null || lot.mileage === undefined || lot.mileage === '').length,
        rows_excluded_out_of_scope: totalSkippedOutOfScope,
        rows_excluded_not_completed_sale: totalSkippedNotCompleted,
        completed_sale_rejection_reasons: completedSaleRejectionCounts,
        target_search_queries: targetSearchQueries,
        query_diagnostics: queryDiagnostics.query_counts,
        out_of_scope_examples: queryDiagnostics.out_of_scope_examples,
        out_of_scope_examples_by_query: queryDiagnostics.out_of_scope_examples_by_query,
        max_pages_total: maxPages,
        generated_at: new Date().toISOString(),
    };
}

function buildCompletedSearchPayload(searchText, basePayload = {}) {
    const payload = { ...(basePayload || {}) };
    const query = String(searchText || '').trim() || '*';
    const displayRows = Number(payload.displayRows || payload.pageSize || DEFAULT_DISPLAY_ROWS);

    payload.categoryIds = payload.categoryIds || '4100';
    payload.requestType = payload.requestType || 'search';
    payload.responseStyle = payload.responseStyle || 'productsOnly';
    payload.businessId = payload.businessId || 'GD';
    payload.searchText = query;
    payload.isQAL = payload.isQAL ?? false;
    payload.page = 1;
    payload.displayRows = displayRows > 0 ? displayRows : DEFAULT_DISPLAY_ROWS;
    payload.sortField = payload.sortField || 'assetcloseutcdatetime';
    payload.sortOrder = payload.sortOrder || 'desc';
    payload.timeType = payload.timeType || 'completed';
    payload.timing = payload.timing || 'completed';
    payload.sellerTypeId = payload.sellerTypeId ?? null;
    payload.accountIds = Array.isArray(payload.accountIds) ? payload.accountIds : [];
    payload.facets = Array.isArray(payload.facets) ? payload.facets : [];

    delete payload.pageSize;
    delete payload.pageNumber;
    delete payload.searchPg;
    delete payload.offset;
    delete payload.start;
    delete payload.skip;

    return payload;
}

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
                capturedApi.requestHeaders = replayHeadersFromBrowser(headers);
                log.info(`[API KEY CAPTURED] ${headers['x-api-key'].slice(0, 8)}*** via ${url}`);
            }

            if (url.includes('/search/list') && request.method() === 'POST') {
                capturedApi.requestHeaders = replayHeadersFromBrowser(headers);
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

        // ── Load homepage and navigate to completed target searches ─────
        // Query completed/sold auctions for clearance price data. The
        // direct target searches are the source-side guard; targetTerms
        // remains the local safety filter before any row is pushed.
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

        for (const query of targetSearchQueries) {
            if (capturedApi.interceptedLots.length >= 20) break;
            const searchUrl = completedSearchUrl(query);
            log.info(`Navigating to completed search for "${query}": ${searchUrl}`);
            await page.goto(searchUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
            await page.waitForTimeout(6000);
        }

        // Keep one broad completed vehicle pass as a fallback auth/payload
        // capture path, but every row still has to pass targetTerms.
        for (const categoryUrl of VEHICLE_CATEGORY_URLS) {
            if (capturedApi.interceptedLots.length >= 20) break;
            log.info(`Navigating to fallback completed category: ${categoryUrl}`);
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
                    stageTargetLot(lot, seenIds, 'intercepted');
                    if (passingLots.length >= maxItems) break;
                }
            }

            // Step 2: Fetch each target search from page 1 onward. Intercepted
            // page-1 rows dedupe through seenIds; non-intercepted queries need
            // their own page-1 fetch.
            if (capturedApi.searchPayload && passingLots.length < maxItems) {
                let remainingPageBudget = Math.max(1, Number(maxPages) || 1);
                for (let queryIndex = 0; queryIndex < targetSearchQueries.length; queryIndex++) {
                    const query = targetSearchQueries[queryIndex];
                    if (passingLots.length >= maxItems) break;
                    if (remainingPageBudget <= 0) break;
                    const remainingQueries = targetSearchQueries.length - queryIndex;
                    const pagesForQuery = Math.max(1, Math.floor(remainingPageBudget / remainingQueries));
                    const usedPages = await paginateWithAuth(page, log, seenIds, query, pagesForQuery);
                    remainingPageBudget -= usedPages;
                }
            }

            // Step 3: Push all lots immediately (before VIN scraping to avoid data loss)
            for (const lot of passingLots) {
                await Actor.pushData(lot);
            }
            await Actor.pushData(sourceQualityProof());
            log.info(`[GOVDEALS-SOLD] Pushed ${passingLots.length} completed auction records`);
            log.info(`[GOVDEALS-SOLD] Target filter skipped ${totalSkippedOutOfScope} out-of-scope completed lots`);
            log.info(`[GOVDEALS-SOLD] Completed-sale filter skipped ${totalSkippedNotCompleted} lots: ${JSON.stringify(completedSaleRejectionCounts)}`);
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
    const saleDate = completedSaleDate(lot, runStartedAt);
    return {
        title:         lot.assetShortDescription || lot.title || '',
        make:          lot.makebrand || lot.make || '',
        model:         lot.model || '',
        year:          lot.modelYear || lot.year || null,
        current_bid:   lot.currentBid || lot.current_bid || lot.assetBidPrice || 0,
        sold_price:    soldPrice,
        state:         lot.locationState || lot.state || '',
        city:          lot.locationCity || lot.city || '',
        sale_date:      saleDate,
        auction_end_time: saleDate,
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

async function paginateWithAuth(page, log, seenIds = new Set(), searchText = '', pageLimit = maxPages) {
    const { requestHeaders, searchPayload, searchUrl } = capturedApi;
    const completedSearchPayload = buildCompletedSearchPayload(searchText, searchPayload);
    let pagesAttempted = 0;

    for (let pageNum = 1; pageNum <= pageLimit; pageNum++) {
        pagesAttempted++;
        const payload = {
            ...completedSearchPayload,
            page: pageNum,
            displayRows: completedSearchPayload.displayRows || DEFAULT_DISPLAY_ROWS,
            requestType: completedSearchPayload.requestType || 'search',
            responseStyle: completedSearchPayload.responseStyle || 'productsOnly',
        };

        log.info(`Fetching completed search "${payload.searchText}" page ${pageNum} via Node fetch: ${searchUrl}`);

        try {
            // Use Node.js fetch (no CORS restrictions, unlike page.evaluate browser fetch)
            const nodeResp = await fetch(searchUrl, {
                method: 'POST',
                headers: headersForReplayPage(requestHeaders),
                body: JSON.stringify(payload),
            });
            const responseText = await nodeResp.text();
            const responseJson = nodeResp.ok ? safeJsonParse(responseText) : null;
            const resp = {
                ok: nodeResp.ok,
                status: nodeResp.status,
                total: nodeResp.headers.get('x-total-count'),
                json: responseJson,
                body: responseText,
            };

            if (!resp?.ok || !resp.json) {
                log.info(`Page ${pageNum}: no response (status ${resp?.status ?? 'unknown'}): ${String(resp?.body || '').slice(0, 240)}`);
                break;
            }

            const lots = extractLots(resp.json);
            if (!lots.length) { log.info(`Page ${pageNum}: empty — done`); break; }

            log.info(`Page ${pageNum}: ${lots.length} lots (x-total-count: ${resp.total || 'n/a'})`);
            for (const lot of lots) {
                if (seenIds.has(lot.assetId)) continue; // already saved from intercept
                stageTargetLot(lot, seenIds, searchText);
                if (passingLots.length >= maxItems) {
                    log.info(`Reached maxItems limit (${maxItems}) — stopping pagination`);
                    return pagesAttempted;
                }
            }
        } catch (err) {
            log.warning(`Page ${pageNum} failed: ${err.message}`);
            break;
        }
        await page.waitForTimeout(1000);
    }
    return pagesAttempted;
}

await crawler.run([{ url: 'https://www.govdeals.com/' }]);
console.log(`[GOVDEALS-SOLD] Found: ${totalFound} | Collected: ${totalPassed}`);
console.log(`[GOVDEALS-SOLD] Skipped out-of-scope: ${totalSkippedOutOfScope}`);
console.log(`[GOVDEALS-SOLD] Skipped not-completed: ${totalSkippedNotCompleted}`);
console.log(`[GOVDEALS-SOLD] Auth initialized`);
console.log(`VINs extracted: ${passingLots.filter(l => l.vin).length} / ${passingLots.length} lots`);
await Actor.exit();
