/**
 * GovDeals Apify Actor — API-intercept approach
 *
 * GovDeals is now a Liquidity Services Angular SPA. Rather than scraping DOM
 * selectors that will keep breaking, we use Playwright to load the search page
 * and intercept the XHR/fetch calls the Angular app makes to its backend API.
 * The captured JSON responses contain full lot data — no detail-page crawling
 * needed for the core fields.
 *
 * API discovery: the Angular app calls endpoints on maestro.lqdt1.com or
 * govdeals.com/api. We capture whichever fires and process the JSON.
 *
 * Fallback: if no API JSON is captured after Angular boots, we wait for the
 * rendered Angular DOM cards and scrape with updated selectors.
 */

import { Actor } from 'apify';
import { PlaywrightCrawler } from 'crawlee';

/* ── Constants ─────────────────────────────────────────────── */

const HIGH_RUST_STATES = new Set([
    'OH','MI','PA','NY','WI','MN','IL','IN','MO','IA',
    'ND','SD','NE','KS','WV','ME','NH','VT','MA','RI',
    'CT','NJ','MD','DE',
]);

/**
 * GovDeals search URL for vehicles (category 1050).
 * The Angular SPA still responds to the old CFM query string; Angular picks
 * up the params and fires its own API calls for the results.
 */
const SEARCH_URL = (page) =>
    `https://www.govdeals.com/index.cfm?fa=Main.AdvSearchResultsNew&searchPg=${page}&category=1050&sortBy=ad&sortOrder=D`;

/** Alternate Angular-native URL if CFM variant stops working */
const SEARCH_URL_ALT = (page) =>
    `https://www.govdeals.com/listings?categoryId=1050&page=${page}&sortBy=auctionEndDate&sortOrder=asc`;

/* ── Actor boot ─────────────────────────────────────────────── */

await Actor.init();

const input = await Actor.getInput() ?? {};
const {
    maxPages      = 10,
    minBid        = 500,
    maxBid        = 35000,
    targetStates  = ['AZ','CA','NV','CO','NM','UT','TX','FL','GA','SC','TN','NC','VA','WA','OR','HI'],
    webhookUrl    = process.env.RAILWAY_WEBHOOK_URL ?? '',
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

/**
 * Attempt to extract an array of lot objects from an intercepted API response.
 * Liquidity Services uses several different shapes depending on endpoint version.
 */
function extractLotsFromJson(json) {
    if (!json || typeof json !== 'object') return [];
    // Most common shapes:
    if (Array.isArray(json.lots))        return json.lots;
    if (Array.isArray(json.items))       return json.items;
    if (Array.isArray(json.results))     return json.results;
    if (Array.isArray(json.data))        return json.data;
    if (json.searchResults && Array.isArray(json.searchResults.lots))
        return json.searchResults.lots;
    if (json.page && Array.isArray(json.page.results))
        return json.page.results;
    // Some versions wrap in a nested response object
    for (const key of Object.keys(json)) {
        const v = json[key];
        if (Array.isArray(v) && v.length > 0 && v[0] && (v[0].lotNumber || v[0].itemId || v[0].auctionId)) {
            return v;
        }
    }
    return [];
}

/**
 * Normalize a raw lot object (from API JSON or DOM) into a DealerScope vehicle.
 * Field names vary across Liquidity Services API versions — cover them all.
 */
function normalizeLot(lot, sourceUrl) {
    const title =
        lot.title || lot.itemTitle || lot.name || lot.description?.slice(0, 120) || '';

    const currentBid = parseBid(
        lot.currentBid ?? lot.currentBidAmount ?? lot.highBid ??
        lot.currentPrice ?? lot.winningBid ?? lot.openingBid ?? 0
    );

    // Location: may be a string or nested object
    let location = '';
    if (typeof lot.location === 'string') {
        location = lot.location;
    } else if (lot.location && typeof lot.location === 'object') {
        const l = lot.location;
        location = [l.city, l.state, l.zip].filter(Boolean).join(', ');
    } else {
        location = [lot.city, lot.state, lot.zipCode].filter(Boolean).join(', ');
    }

    const state = (
        lot.state ||
        lot.locationState ||
        lot.location?.state ||
        extractStateFromLocation(location)
    ).toUpperCase().slice(0, 2);

    const endTime =
        lot.auctionEndDate ?? lot.endDate ?? lot.closeDate ??
        lot.auctionEnd ?? lot.endTime ?? null;

    // Photo: may be array or single string
    let photoUrl = null;
    if (Array.isArray(lot.images) && lot.images.length > 0) {
        photoUrl = lot.images[0].url || lot.images[0].thumbnailUrl || lot.images[0];
    } else {
        photoUrl = lot.imageUrl || lot.thumbnailUrl || lot.primaryImage || null;
    }

    // Listing URL
    const lotNumber = lot.lotNumber || lot.itemNumber || lot.itemId || lot.auctionId || '';
    const agencyId  = lot.agencyId || lot.sellerId || lot.organizationId || '';
    let listingUrl  = lot.url || lot.listingUrl || lot.itemUrl || sourceUrl || '';
    if (!listingUrl && lotNumber) {
        listingUrl = agencyId
            ? `https://www.govdeals.com/item/${agencyId}/${lotNumber}`
            : `https://www.govdeals.com/item/${lotNumber}`;
    }

    const mileage = lot.mileage || lot.odometer || lot.miles || null;
    const vin     = lot.vin || lot.serialNumber || null;

    return {
        title,
        current_bid:    currentBid,
        buyer_premium:  0.125,       // GovDeals standard 12.5 %
        doc_fee:        75,
        state,
        location,
        auction_end_time: endTime,
        listing_url:    listingUrl,
        item_number:    String(lotNumber),
        photo_url:      photoUrl,
        description:    (lot.description || lot.itemDescription || '').slice(0, 800),
        agency_name:    lot.agencyName || lot.sellerName || lot.organizationName || '',
        mileage:        mileage ? String(mileage).replace(/,/g, '') : null,
        vin,
        year:           extractYearFromTitle(title),
        source_site:    'govdeals',
        scraped_at:     new Date().toISOString(),
    };
}

/** Apply all vehicle filters; returns true if the lot should be saved. */
function passesFilters(v, log) {
    if (HIGH_RUST_STATES.has(v.state)) {
        log.debug(`SKIP high-rust: ${v.state} — ${v.title}`);
        return false;
    }
    if (v.current_bid < minBid || v.current_bid > maxBid) {
        log.debug(`SKIP bid $${v.current_bid} out of range — ${v.title}`);
        return false;
    }
    if (!v.title) {
        log.debug(`SKIP no title: ${v.listing_url}`);
        return false;
    }
    return true;
}

/** Push vehicle to Actor dataset and optionally notify webhook. */
async function saveLot(vehicle, log) {
    totalAfterFilters++;
    log.info(`[PASS] ${vehicle.title} | $${vehicle.current_bid} | ${vehicle.state}`);
    await Actor.pushData(vehicle);
}

/* ── Crawler ─────────────────────────────────────────────────── */

const crawler = new PlaywrightCrawler({
    launchContext: {
        launchOptions: {
            headless: true,
            args: [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
            ],
        },
    },
    maxRequestsPerCrawl: maxPages * 3 + 20,
    requestHandlerTimeoutSecs: 90,

    async requestHandler({ page, request, enqueueLinks, log }) {
        const url      = request.url;
        const pageNum  = request.userData?.pageNum ?? 1;
        log.info(`[PAGE ${pageNum}] ${url}`);

        /* ── Step 1: intercept API responses ── */
        const capturedLots = [];

        const responseHandler = async (response) => {
            const rUrl = response.url();
            // Only inspect XHR/fetch from Liquidity Services backends or govdeals API
            if (
                !/lqdt|govdeals|liquidity/i.test(rUrl)   ||
                response.status() !== 200                  ||
                !rUrl.includes('/api/')                    &&
                !rUrl.includes('/lots')                    &&
                !rUrl.includes('/search')                  &&
                !rUrl.includes('/items')
            ) return;

            try {
                const ct = response.headers()['content-type'] || '';
                if (!ct.includes('json')) return;
                const json = await response.json();
                const lots = extractLotsFromJson(json);
                if (lots.length > 0) {
                    log.info(`[API] Captured ${lots.length} lots from ${rUrl}`);
                    capturedLots.push(...lots);
                }
            } catch (_) { /* not JSON or empty */ }
        };

        page.on('response', responseHandler);

        /* ── Step 2: navigate and wait for Angular ── */
        try {
            await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
        } catch (e) {
            log.warning(`Navigation error (non-fatal): ${e.message}`);
        }

        // Wait up to 15 s for Angular to bootstrap and fire its API calls
        // We wait for either a known Angular selector or the response listener to fire
        try {
            await page.waitForFunction(
                () => document.querySelector(
                    'app-root, [ng-version], .search-results, .lot-list, ' +
                    '.auction-item, [class*="lot-card"], [class*="item-card"], ' +
                    '.item-list, [data-testid="lot"]'
                ) !== null,
                { timeout: 15000 }
            );
        } catch (_) {
            // Angular may not have rendered a recognisable root — just wait a bit
            await page.waitForTimeout(8000);
        }

        // Give a little extra time for XHR to complete after DOM ready
        await page.waitForTimeout(2000);
        page.off('response', responseHandler);

        totalFound += capturedLots.length;
        log.info(`[PAGE ${pageNum}] API lots captured: ${capturedLots.length}`);

        /* ── Step 3a: process intercepted lots ── */
        if (capturedLots.length > 0) {
            for (const raw of capturedLots) {
                const v = normalizeLot(raw, url);
                if (passesFilters(v, log)) await saveLot(v, log);
            }

        } else {
            /* ── Step 3b: DOM fallback — Angular rendered cards ── */
            log.info(`[PAGE ${pageNum}] No API data — falling back to DOM extraction`);

            const domLots = await page.evaluate(() => {
                const results = [];

                // Angular component selectors (Liquidity Services SPA patterns)
                const cardSelectors = [
                    'app-lot-card',
                    'app-auction-item',
                    '[class*="lot-card"]',
                    '[class*="item-card"]',
                    '[class*="auction-card"]',
                    '.lot-tile',
                    '.search-result-item',
                    'li[class*="result"]',
                    'div[class*="result-item"]',
                ].join(',');

                const cards = document.querySelectorAll(cardSelectors);

                cards.forEach(card => {
                    try {
                        const linkEl = card.querySelector('a[href]');
                        const titleEl = card.querySelector(
                            'h2,h3,h4,[class*="title"],[class*="name"],[class*="heading"]'
                        );
                        const bidEl = card.querySelector(
                            '[class*="bid"],[class*="price"],[class*="amount"]'
                        );
                        const locEl = card.querySelector(
                            '[class*="location"],[class*="city"],[class*="state"]'
                        );
                        const imgEl = card.querySelector('img');
                        const endEl = card.querySelector(
                            '[class*="end"],[class*="close"],[class*="expire"],[class*="countdown"]'
                        );

                        const title  = titleEl?.textContent?.trim() || '';
                        const bidTxt = bidEl?.textContent?.trim() || '0';
                        const bidM   = bidTxt.replace(/,/g, '').match(/[\d.]+/);
                        const bid    = bidM ? parseFloat(bidM[0]) : 0;

                        results.push({
                            title,
                            current_bid: bid,
                            location: locEl?.textContent?.trim() || '',
                            listing_url: linkEl
                                ? (linkEl.href || linkEl.getAttribute('href'))
                                : '',
                            photo_url: imgEl?.src || imgEl?.dataset?.src || null,
                            auction_end_time: endEl?.textContent?.trim() || null,
                        });
                    } catch (_) {}
                });

                return results;
            });

            totalFound += domLots.length;
            log.info(`[PAGE ${pageNum}] DOM cards found: ${domLots.length}`);

            for (const raw of domLots) {
                const v = {
                    ...raw,
                    buyer_premium: 0.125,
                    doc_fee:       75,
                    state:         extractStateFromLocation(raw.location),
                    year:          extractYearFromTitle(raw.title),
                    mileage:       null,
                    vin:           null,
                    agency_name:   '',
                    description:   '',
                    item_number:   '',
                    source_site:   'govdeals',
                    scraped_at:    new Date().toISOString(),
                };
                if (passesFilters(v, log)) await saveLot(v, log);
            }

            // If still nothing, log the page title so we can debug
            if (domLots.length === 0) {
                const pageTitle = await page.title();
                const bodySnip  = await page.evaluate(
                    () => document.body?.innerText?.slice(0, 300) || ''
                );
                log.warning(`[PAGE ${pageNum}] 0 results. Title="${pageTitle}" Body="${bodySnip}"`);
            }
        }

        /* ── Step 4: enqueue next page ── */
        if (
            (capturedLots.length > 0 || /* DOM had results */ true) &&
            pageNum < maxPages
        ) {
            const nextUrl = SEARCH_URL(pageNum + 1);
            await enqueueLinks({
                urls: [nextUrl],
                label: 'SEARCH',
                userData: { pageNum: pageNum + 1 },
            });
        }
    },
});

/* ── Start crawl ─────────────────────────────────────────────── */

await crawler.run([
    { url: SEARCH_URL(1), label: 'SEARCH', userData: { pageNum: 1 } },
]);

console.log(`[SUMMARY] Found: ${totalFound} | Passed filters: ${totalAfterFilters}`);
console.log(`[GOVDEALS COMPLETE] Found=${totalFound} passed=${totalAfterFilters}`);

await Actor.exit();
