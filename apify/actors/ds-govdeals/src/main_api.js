import { randomUUID } from 'crypto';
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
 *
 * VIN extraction strategy:
 * 1. Check lot.vin field from API response
 * 2. Extract VIN regex from lot description/notes fields
 * 3. Fallback: visit GovDeals detail page via Playwright (up to 200/run, 1 req/sec)
 */

import { Actor } from 'apify';
import { PlaywrightCrawler } from 'crawlee';

const HIGH_RUST_STATES = new Set([
    'OH','MI','PA','NY','WI','MN','IL','IN','MO','IA',
    'ND','SD','NE','KS','WV','ME','NH','VT','MA','RI',
    'CT','NJ','MD','DE',
]);

const GOVDEALS_VEHICLE_SEARCH_URL_BASE = 'https://www.govdeals.com/index.cfm?fa=Main.AdvSearchResultsNew&searchPg=1&category=4100';
const GOVDEALS_VEHICLE_CATEGORY_FACETS = [
    '{!tag=product_category_external_id}product_category_external_id:"t6"',
    '{!tag=product_category_external_id}product_category_external_id:"94Q"',
];
const GOVDEALS_FACET_FIELDS = [
    'categoryName','auctionTypeID','condition','saleEventName','sellerDisplayName',
    'product_pricecents','isReserveMet','hasBuyNowPrice','isReserveNotMet',
    'sellerType','warehouseId','region','currencyTypeCode','categoryName','tierId'
];
const DEFAULT_DISPLAY_ROWS = 50;
const HARD_MAX_PAGES = 200;

// Standard 17-char VIN pattern (no I, O, Q)
const VIN_PATTERN = /\b([A-HJ-NPR-Z0-9]{17})\b/i;
const MAX_DETAIL_PAGES = 200;
const CONDITION_REJECT_PATTERNS = [
    /\bsalvage\b/i,
    /\bflood\b/i,
    /\bframe[\s-]+damage\b/i,
    /\bcrash(?:ed)?\b/i,
    /\bcollision[\s-]+damage\b/i,
    /\bfire[\s-]+damage\b/i,
    /\bhail[\s-]+damage\b/i,
    /\bwont\s+start\b/i,
    /\bwon'?t\s+start\b/i,
    /\bdoes\s+not\s+start\b/i,
    /\bno[\s-]start\b/i,
    /\binop(?:erable)?\b/i,
    /\bparts[\s-]+only\b/i,
    /\bfor\s+parts\b/i,
    /\bproject\s+(?:car|vehicle|truck)\b/i,
    /\brebuilt\s+title\b/i,
    /\bstructural[\s-]+damage\b/i,
    /\bblown\s+engine\b/i,
    /\bbad\s+engine\b/i,
    /\bno\s+title\b/i,
];

await Actor.init();
const input = await Actor.getInput() ?? {};
const { maxPages = HARD_MAX_PAGES, minBid = 500, maxBid = 75000, searchQuery = "" } = input;

const GOVDEALS_VEHICLE_SEARCH_URL = searchQuery
    ? `${GOVDEALS_VEHICLE_SEARCH_URL_BASE}&kWord=${encodeURIComponent(searchQuery)}`
    : GOVDEALS_VEHICLE_SEARCH_URL_BASE;

let totalFound = 0, totalPassed = 0;
const capturedApi = {
    apiKey: null,
    userId: null,
    sessionId: null,
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

function passes(item) {
    const conditionText = [
        item.assetTitle,
        item.assetShortDescription,
        item.longDescription,
        item.itemDescription,
        item.description,
        item.notes,
        item.assetLongDescription,
        item.itemNotes,
        item.title,
    ].filter(Boolean).join(' ').toLowerCase();
    if (CONDITION_REJECT_PATTERNS.some((pattern) => pattern.test(conditionText))) return false;
    const state = (item.locationState || item.state || '').toUpperCase();
    const bid = item.currentBid || item.current_bid || item.assetBidPrice || 0;
    if (bid < minBid || bid > maxBid) return false;
    const year = parseInt(item.modelYear || item.year || 0);
    const currentYear = new Date().getFullYear();
    if (year && (currentYear - year) > 10) return false;
    const mileage = parseInt(item.meterCount || item.meter_count || 0);
    if (mileage > 0 && mileage > 100000) return false;
    if (HIGH_RUST_STATES.has(state)) {
        if (!(year && year >= currentYear - 2)) return false;
        console.log(`[BYPASS] Rust state ${state} allowed — vehicle is ${year} (≤3yr old)`);
    }
    return true;
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
    maxRequestsPerCrawl: 20,
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
                capturedApi.userId = headers['x-user-id'] || headers['x-userid'] || 'anonymous';
                capturedApi.requestHeaders = {
                    accept: headers.accept || 'application/json, text/plain, */*',
                    'content-type': headers['content-type'] || 'application/json',
                    'x-api-key': headers['x-api-key'],
                    'x-user-id': capturedApi.userId,
                };
                log.info(`[API KEY CAPTURED] [REDACTED] via ${url}, userId=${capturedApi.userId}`);
            }

            if (url.includes('/search/list') && request.method() === 'POST') {
                const postData = request.postData();
                if (!postData) return;
                try {
                    const nextPayload = JSON.parse(postData);
                    if (!capturedApi.searchPayload || isBroaderVehiclePayload(nextPayload, capturedApi.searchPayload)) {
                        capturedApi.searchPayload = nextPayload;
                        capturedApi.searchUrl = url;
                        capturedApi.sessionId = capturedApi.searchPayload.sessionId || null;
                        log.info(`[SEARCH PAYLOAD CAPTURED] ${url} sessionId=${capturedApi.sessionId}`);
                    }
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
        // GovDeals vehicle search is exposed through the legacy advanced search
        // route. The broad category=4100 listing covers the full vehicle family.
        const VEHICLE_CATEGORY_URLS = [
            GOVDEALS_VEHICLE_SEARCH_URL,
            'https://www.govdeals.com/en/passenger-vehicles',
            'https://www.govdeals.com/en/trucks-and-vans',
            'https://www.govdeals.com/en/suvs',
        ];

        // Start with homepage to capture API key, then navigate to passenger vehicles
        await page.goto('https://www.govdeals.com/', {
            waitUntil: 'domcontentloaded', timeout: 60000
        });
        await page.waitForTimeout(4000);

        // Navigate to search URL (with keyword if searchQuery set) or category URLs
        if (searchQuery) {
            log.info(`Navigating to search URL with keyword: ${GOVDEALS_VEHICLE_SEARCH_URL}`);
            await page.goto(GOVDEALS_VEHICLE_SEARCH_URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
            await page.waitForTimeout(6000);
        } else {
            for (const categoryUrl of VEHICLE_CATEGORY_URLS) {
                if (capturedApi.interceptedLots.length >= 20) break;
                log.info(`Navigating to: ${categoryUrl}`);
                await page.goto(categoryUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
                await page.waitForTimeout(6000);
            }
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
                    if (!passes(lot)) continue;
                    totalPassed++;
                    passingLots.push(normalizeLot(lot));
                }
            }

            // Step 2: Build/use Maestro payload
            // If searchQuery is set OR no payload was intercepted, build fresh payload
            if (searchQuery || !capturedApi.searchPayload) {
                log.info(`Building direct Maestro payload with searchText="${searchQuery || '*'}"`);
                capturedApi.searchPayload = {
                    categoryIds: '',
                    requestType: 'search',
                    responseStyle: 'productsOnly',
                    businessId: 'GD',
                    searchText: searchQuery || '*',
                    isQAL: false,
                    locationId: null,
                    model: '',
                    makebrand: '',
                    auctionTypeId: null,
                    page: 1,
                    displayRows: 24,
                    sortField: 'currentbid',
                    sortOrder: 'desc',
                    sessionId: capturedApi.sessionId || generateUUID(),
                    facets: [...GOVDEALS_FACET_FIELDS],
                    facetsFilter: [...GOVDEALS_VEHICLE_CATEGORY_FACETS],
                    timeType: '',
                    sellerTypeId: null,
                    accountIds: [],
                };
            } else if (capturedApi.searchPayload) {
                capturedApi.searchPayload = ensureBroadVehiclePayload(capturedApi.searchPayload);
            }
            if (capturedApi.searchPayload && !capturedApi.searchPayload.sessionId) {
                capturedApi.searchPayload.sessionId = `ds-govdeals-${Date.now()}`;
            }
            if (capturedApi.searchPayload && !Array.isArray(capturedApi.searchPayload.facetsFilter)) {
                capturedApi.searchPayload.facetsFilter = [...GOVDEALS_VEHICLE_CATEGORY_FACETS];
            }
            if (capturedApi.searchPayload && !capturedApi.searchPayload.categoryIds) {
                capturedApi.searchPayload.categoryIds = '4100';
            }
            if (capturedApi.searchPayload && !capturedApi.searchPayload.displayRows) {
                capturedApi.searchPayload.displayRows = DEFAULT_DISPLAY_ROWS;
            }
            if (capturedApi.searchPayload) {
                // 1. Force the payload to use our actual search query
                capturedApi.searchPayload.searchText = searchQuery || '*';
                // 2. Clear any intercepted page filters that conflict with the keyword
                capturedApi.searchPayload.facets = [];
            }
            if (capturedApi.searchPayload && capturedApi.searchUrl) {
                await paginateWithAuth(page, log, seenIds);
            } else {
                log.warning('Cannot paginate — searchPayload or searchUrl missing');
            }

            // Step 3: VIN enrichment before pushing so populated VINs are preserved in the dataset
            await scrapeDetailPagesForVin(page, passingLots, log);

            // Step 4: Push all passing lots after VIN enrichment completes
            for (const lot of passingLots) {
                await Actor.pushData(lot);
            }
            log.info(`[GOVDEALS] Pushed ${passingLots.length} lots to dataset`);
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
        vin:           extractVinFromLot(lot),
        mileage:       lot.meterCount || null,
        source_site:   'govdeals',
        scraped_at:    new Date().toISOString(),
    };
}

function ensureBroadVehiclePayload(payload) {
    const normalized = { ...payload };
    const displayRows = Number(normalized.displayRows || normalized.pageSize || DEFAULT_DISPLAY_ROWS);
    const hasBroadCategory = isBroadVehiclePayload(normalized);

    normalized.businessId = normalized.businessId || 'GD';
    normalized.searchText = normalized.searchText || '*';
    normalized.isQAL = normalized.isQAL ?? false;
    normalized.page = 1;
    normalized.displayRows = displayRows > 0 ? displayRows : DEFAULT_DISPLAY_ROWS;
    normalized.sortField = normalized.sortField || 'currentbid';
    normalized.sortOrder = normalized.sortOrder || 'desc';
    normalized.requestType = normalized.requestType || 'search';
    normalized.responseStyle = normalized.responseStyle || 'productsOnly';
    normalized.timeType = normalized.timeType || '';
    normalized.sellerTypeId = normalized.sellerTypeId ?? null;
    normalized.accountIds = Array.isArray(normalized.accountIds) ? normalized.accountIds : [];
    normalized.facets = Array.isArray(normalized.facets) ? normalized.facets : [];
    normalized.facetsFilter = hasBroadCategory && Array.isArray(normalized.facetsFilter) && normalized.facetsFilter.length > 0
        ? normalized.facetsFilter
        : [...GOVDEALS_VEHICLE_CATEGORY_FACETS];
    normalized.categoryIds = hasBroadCategory && normalized.categoryIds
        ? normalized.categoryIds
        : '4100';
    delete normalized.pageSize;
    delete normalized.pageNumber;
    delete normalized.searchPg;
    delete normalized.offset;
    delete normalized.start;
    delete normalized.skip;
    return normalized;
}

function isBroadVehiclePayload(candidate, reference = null) {
    const inspect = (value) => {
        if (!value || typeof value !== 'object') return false;
        const categoryIds = String(value.categoryIds || '').toLowerCase();
        if (categoryIds.includes('4100')) return true;

        const filters = Array.isArray(value.facetsFilter) ? value.facetsFilter : [];
        return filters.some((entry) => String(entry).includes('product_category_external_id:"4100"'));
    };

    const candidateBroad = inspect(candidate);
    if (!reference) return candidateBroad;

    const referenceBroad = inspect(reference);
    if (candidateBroad && !referenceBroad) return true;
    if (!candidateBroad && referenceBroad) return false;

    return false;
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


function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        const r = Math.random() * 16 | 0;
        return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
    });
}

async function paginateWithAuth(page, log, seenIds = new Set()) {
    const { requestHeaders, searchPayload, searchUrl } = capturedApi;
    const pageSize = Number(searchPayload.displayRows || searchPayload.pageSize || DEFAULT_DISPLAY_ROWS);
    const seenPageSignatures = new Set();
    let zeroNewItemPages = 0;
    let totalCount = null;
    let totalPages = Number.isFinite(maxPages) ? maxPages : HARD_MAX_PAGES;

    // Paginate the REST endpoint directly using the Maestro `page` parameter.
    for (let pageNum = 1; pageNum <= Math.min(totalPages, HARD_MAX_PAGES); pageNum++) {
        const payload = {
            ...ensureBroadVehiclePayload(searchPayload),
            page: pageNum,
            displayRows: pageSize,
        };

        const _debugPayload = {...payload};
        if (_debugPayload['x-api-key']) delete _debugPayload['x-api-key'];
        log.info(`Fetching Maestro page ${pageNum} via Node fetch: ${searchUrl} payload=${JSON.stringify(_debugPayload).slice(0,500)}`);

        try {
            // Use Node.js fetch (no CORS restrictions, unlike page.evaluate browser fetch)
            const nodeResp = await fetch(searchUrl, {
                method: 'POST',
                headers: {
                    ...requestHeaders,
                    'content-type': 'application/json',
                    'origin': 'https://www.govdeals.com',
                    'referer': 'https://www.govdeals.com/',
                    'x-user-id': capturedApi.userId || 'anonymous',
                    'x-api-correlation-id': generateUUID(),
                },
                body: JSON.stringify(payload),
            });
            const resp = {
                ok: nodeResp.ok,
                status: nodeResp.status,
                total: nodeResp.headers.get('x-total-count'),
                json: nodeResp.ok ? await nodeResp.json() : null,
            };
            if (resp.total && Number.isFinite(Number(resp.total))) {
                totalCount = Number(resp.total);
                totalPages = Math.min(
                    Math.max(totalPages, Math.ceil(totalCount / pageSize)),
                    HARD_MAX_PAGES,
                );
            }

            if (!resp?.ok || !resp.json) {
                const errBody = await nodeResp.text().catch(() => '');
                log.info(`Page ${pageNum}: no response (status ${resp?.status ?? 'unknown'}) body=${errBody.slice(0,300)}`);
                break;
            }

            const lots = extractLots(resp.json);
            if (!lots.length) { log.info(`Page ${pageNum}: empty — done`); break; }

            const pageSignature = lots
                .map((lot) => String(lot.assetId ?? lot.id ?? ''))
                .join('|');
            if (seenPageSignatures.has(pageSignature)) {
                log.info(`Page ${pageNum}: repeated prior results — stopping pagination`);
                break;
            }
            seenPageSignatures.add(pageSignature);

            log.info(`Page ${pageNum}: ${lots.length} lots (x-total-count: ${resp.total || 'n/a'})`);
            let newItemCount = 0;
            for (const lot of lots) {
                const lotId = String(lot.assetId ?? lot.id ?? '');
                if (lotId && seenIds.has(lotId)) continue; // already saved from intercept
                if (lotId) seenIds.add(lotId);
                newItemCount++;
                totalFound++;
                if (!passes(lot)) continue;
                totalPassed++;
                passingLots.push(normalizeLot(lot));
            }

            if (newItemCount === 0) {
                zeroNewItemPages++;
                if (zeroNewItemPages >= 3) {
                    log.info(`Page ${pageNum}: 3 consecutive pages with no new items — stopping pagination`);
                    break;
                }
            } else {
                zeroNewItemPages = 0;
            }

            if (totalCount != null && pageNum * pageSize >= totalCount) {
                log.info(`Page ${pageNum}: reached x-total-count ${totalCount}, pagination complete`);
                break;
            }
        } catch (err) {
            log.warning(`Page ${pageNum} failed: ${err.message}`);
            break;
        }
        await page.waitForTimeout(1000);
    }
}

try {
    await crawler.run([{ url: 'https://www.govdeals.com/' }]);
    console.log(`[GOVDEALS FREE] Found: ${totalFound} | Passed: ${totalPassed}`);
    console.log(`[GOVDEALS] Auth initialized`);
    console.log(`VINs extracted: ${passingLots.filter(l => l.vin).length} / ${passingLots.length} passing lots`);
} catch (err) {
    console.error(`[GOVDEALS] Fatal error: ${err.message}`);
} finally {
    await Actor.exit();
}
