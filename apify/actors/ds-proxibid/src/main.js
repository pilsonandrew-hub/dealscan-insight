/**
 * ds-proxibid — Proxibid Vehicle Auction Scraper
 *
 * Proxibid.com: No bot protection, server-side rendered (SSR) after JS scroll trigger.
 * Uses Playwright to scroll-load the lazy-rendered lot grid, then parses article cards.
 *
 * Live recon findings (2026-03-17):
 * - Category URLs: /for-sale/cars-vehicles/cars plus focused car subcategories
 * - Lot URL pattern: /Cars-Vehicles/Trucks/{Title}/lotInformation/{lotId}
 * - Card container: <article> elements
 * - Title: a[href*="/lotInformation/"] span[data-testid="body-primary"] (first)
 * - Location: span[data-testid="body-primary"] (second — "City, ST" format)
 * - Price: span[data-testid="body-primary"] (third — "$X,XXX.XX")
 * - Time left: span[data-testid="body-secondary"] (first)
 * - Auction house: a[href*="/auction-house/"]
 * - VIN often in title: "2008 GMC SIERRA K2500HD #1GTHK24K58E139687"
 */

import { Actor } from 'apify';
import { PlaywrightCrawler } from 'crawlee';

const SOURCE = 'proxibid';
const BASE = 'https://www.proxibid.com';
const actorRunId = process.env.APIFY_ACTOR_RUN_ID || process.env.APIFY_RUN_ID || null;

// Vehicle category pages to scrape. Keep focused car subcategories first to improve
// accepted-opportunity VIN/mileage yield without loosening buyer-grade filters.

const TARGET_STATES = new Set([
    'AZ','CA','NV','CO','NM','UT','TX','FL','GA','SC','TN','NC','VA','WA','OR','HI',
]);

const HIGH_RUST = new Set([
    'OH','MI','PA','NY','WI','MN','IL','IN','MO','IA',
    'ND','SD','NE','KS','WV','ME','NH','VT','MA','RI',
    'CT','NJ','MD','DE',
]);

const US_STATES = new Set([
    'AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA','HI','ID','IL','IN','IA',
    'KS','KY','LA','ME','MD','MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ',
    'NM','NY','NC','ND','OH','OK','OR','PA','RI','SC','SD','TN','TX','UT','VT',
    'VA','WA','WV','WI','WY','DC',
]);

const MAKES = [
    'ford','chevrolet','chevy','dodge','ram','toyota','honda','nissan','jeep',
    'gmc','chrysler','hyundai','kia','subaru','mazda','volkswagen','vw',
    'bmw','mercedes','audi','lexus','acura','infiniti','cadillac','lincoln',
    'buick','pontiac','mitsubishi','volvo','tesla','rivian',
];
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
    /\bwreck(?:ed)?\b/i,
    /\btotal(?:ed|led)\b/i,
    /\bnot\s+running\b/i,
    /\bdo\s+not\s+operate\b/i,
    /\bnot\s+operable\b/i,
    /\bnon[\s-]?running\b/i,
    /\bbad\s+transmission\b/i,
    /\btransmission\s+(?:bad|issue|issues|problem|problems)\b/i,
    /\bwhite\s+smoke\b/i,
    /\bairbags?\s+deployed\b/i,
    /\brebuilt\s+title\b/i,
    /\bstructural[\s-]+damage\b/i,
    /\bblown\s+engine\b/i,
    /\bbad\s+engine\b/i,
    /\bno\s+title\b/i,
];

await Actor.init();

const input = await Actor.getInput() ?? {};
const {
    searchQuery = "",
    maxItems = 200,
    maxPages = 5,
    minBid = 500,
    maxBid = 50000,
    minYear = new Date().getFullYear() - 10,
    maxDetailPages = 200,
} = input;

const TARGET_CATEGORY_PATHS = [
    '/for-sale/cars-vehicles/cars',
    '/for-sale/cars-vehicles/wagons',
    '/for-sale/cars-vehicles/passenger-vans',
    '/for-sale/cars-vehicles/coupes',
    '/for-sale/cars-vehicles/hatchbacks',
    '/for-sale/cars-vehicles/sedans',
    '/for-sale/cars-vehicles/suv-s',
    '/for-sale/cars-vehicles/pickup-trucks',
    '/for-sale/cars-vehicles/trucks',
];

const CATEGORY_URLS = TARGET_CATEGORY_PATHS.map(path => {
    const url = `${BASE}${path}`;
    return searchQuery ? `${url}?q=${encodeURIComponent(searchQuery)}` : url;
});

let totalFound = 0;
let totalPassed = 0;
const seenLotIds = new Set();
const sampleLocations = [];
const passingLots = [];
const enrichmentProof = {
    record_type: 'source_quality_proof',
    source_site: SOURCE,
    generated_at: null,
    actor: 'ds-proxibid',
    actor_run_id: actorRunId,
    detail_pages_attempted: 0,
    detail_pages_fetched: 0,
    detail_pages_failed: 0,
    detail_vins_found: 0,
    detail_mileages_found: 0,
    accepted_rows_total: 0,
    rejected_rows_total: 0,
    accepted_rows_with_vin: 0,
    accepted_rows_with_mileage: 0,
    enriched_rows_accepted: 0,
    enriched_rows_rejected: 0,
    rejection_reasons: {},
    accepted_enriched_samples: [],
    rejected_enriched_samples: [],
    input_contract: {
        max_detail_pages_default: 200,
        actor_timeout_secs_expected: 900,
    },
};

function normalize(text) {
    return String(text ?? '').replace(/\s+/g, ' ').trim();
}

function recordLocationSample(loc) {
    const n = normalize(loc);
    if (n && !sampleLocations.includes(n) && sampleLocations.length < 8) sampleLocations.push(n);
}

function parseState(locationText) {
    const loc = normalize(locationText).toUpperCase();
    // "City, ST" or "City, ST ZIPCODE"
    const m = loc.match(/,\s*([A-Z]{2})(?:\s+\d{5})?$/) || loc.match(/\b([A-Z]{2})\s*\d{5}$/);
    if (m && US_STATES.has(m[1])) return m[1];
    return null;
}

function parseYear(text) {
    const m = normalize(text).match(/\b(19[89]\d|20[012]\d)\b/);
    return m ? parseInt(m[1]) : null;
}

function parseMake(text) {
    const lower = normalize(text).toLowerCase();
    return MAKES.find(mk => new RegExp(`\\b${mk}\\b`).test(lower)) ?? null;
}

function parseBid(text) {
    const m = normalize(text).replace(/,/g, '').match(/\$?([\d]+(?:\.\d{2})?)/);
    return m ? parseFloat(m[1]) : 0;
}

function parseMileage(text) {
    const normalized = normalize(text).replace(/,/g, '');
    const patterns = [
        /\b(?:mileage|odometer(?:\s+shows)?)[:\s#\-]*(\d+(?:\.\d+)?)\s*(k)?\s*(?:miles?|mi\.?\b)?/i,
        /\b(\d+(?:\.\d+)?)\s*(k)?\s*(?:miles?|mi\.?\b)(?:\s+on\s+(?:meter|odometer))?/i,
    ];
    for (const pattern of patterns) {
        const match = normalized.match(pattern);
        if (!match) continue;
        const value = parseFloat(match[1]);
        if (Number.isNaN(value) || value <= 0) continue;
        const mileage = match[2] ? Math.round(value * 1000) : Math.round(value);
        if (mileage > 0 && mileage <= 1000000) return mileage;
    }
    return null;
}

function parseVin(text) {
    const normalized = normalize(text);
    const patterns = [
        /\b(?:VIN|Vehicle\s+Identification\s+Number|SN|Serial\s*(?:No\.?|Number)?)[:\s#\-]*([A-HJ-NPR-Z0-9]{17})\b/i,
        /\b#?([A-HJ-NPR-Z0-9]{17})\b/i,
    ];
    for (const pattern of patterns) {
        const match = normalized.match(pattern);
        if (match) return match[1].toUpperCase();
    }
    return null;
}

function hasConditionReject(text) {
    const lower = normalize(text).toLowerCase();
    return CONDITION_REJECT_PATTERNS.some((pattern) => pattern.test(lower));
}

function applyBuyerGradeFilters(lot) {
    const reasons = [];
    const text = `${lot.title ?? ''} ${lot.detail_text ?? ''}`;
    if (hasConditionReject(text)) reasons.push('condition_reject');
    if (lot.mileage !== null && lot.mileage !== undefined && lot.mileage > 50000) reasons.push('mileage_over_50k');
    return reasons;
}

function parseLotId(url) {
    const m = url.match(/\/lotInformation\/(\d+)/i);
    return m ? m[1] : null;
}

const crawler = new PlaywrightCrawler({
    maxRequestsPerCrawl: CATEGORY_URLS.length * maxPages * 50,
    maxConcurrency: 1,
    requestHandlerTimeoutSecs: 120,

    async requestHandler({ page, request, log }) {
        const label = request.userData.label ?? 'LIST';
        const url = request.url;

        if (passingLots.length >= maxItems) {
            log.info(`[Proxibid] Max items reached (${passingLots.length}/${maxItems}); skipping ${url}`);
            return;
        }

        if (label === 'LIST') {
            log.info(`[Proxibid] Loading list page: ${url}`);

            // Wait for Angular/React lot cards to render
            await page.waitForLoadState('networkidle').catch(() => {});
            await page.waitForTimeout(3000);

            // Scroll to trigger lazy load
            for (let i = 0; i < 4; i++) {
                await page.evaluate(() => window.scrollBy(0, 1200));
                await page.waitForTimeout(1500);
            }
            await page.waitForTimeout(2000);

            // Extract all lot links
            const lotLinks = await page.evaluate(() => {
                const links = [...document.querySelectorAll('a[href*="/lotInformation/"]')];
                const seen = new Set();
                return links
                    .map(a => a.href)
                    .filter(href => {
                        if (seen.has(href)) return false;
                        seen.add(href);
                        return true;
                    });
            });

            log.info(`[Proxibid] Found ${lotLinks.length} lot links on ${url}`);

            // Extract card data directly from list page, then enrich missing buyer-grade truth from detail pages.
            const cards = await page.evaluate(() => {
                const articles = [...document.querySelectorAll('article')];
                return articles.map(article => {
                    const lotLink = article.querySelector('a[href*="/lotInformation/"]');
                    const href = lotLink?.href ?? '';
                    const lotIdMatch = href.match(/\/lotInformation\/(\d+)/i);

                    // body-primary spans: [0]=title, [1]=location, [2]=price
                    const primarySpans = [...article.querySelectorAll('span[data-testid="body-primary"]')];
                    const title = primarySpans[0]?.innerText?.trim() ?? '';
                    const location = primarySpans[1]?.innerText?.trim() ?? '';
                    const priceText = primarySpans[2]?.innerText?.trim() ?? '';

                    const auctionHouseLink = article.querySelector('a[href*="/auction-house/"]');
                    const auctionHouse = auctionHouseLink?.innerText?.trim() ?? '';

                    const timeLeft = article.querySelector('span[data-testid="body-secondary"]')?.innerText?.trim() ?? '';
                    const imgSrc = article.querySelector('img')?.src ?? null;

                    return {
                        lotId: lotIdMatch ? lotIdMatch[1] : '',
                        title,
                        location,
                        priceText,
                        auctionHouse,
                        timeLeft,
                        listingUrl: href,
                        photoUrl: imgSrc,
                    };
                }).filter(c => c.lotId && c.title);
            });

            log.info(`[Proxibid] Extracted ${cards.length} cards from ${url}`);

            for (const card of cards) {
                if (passingLots.length >= maxItems) {
                    log.info(`[Proxibid] Max items reached (${passingLots.length}/${maxItems}); stopping card extraction for ${url}`);
                    break;
                }
                totalFound++;
                recordLocationSample(card.location);

                const state = parseState(card.location);
                const year = parseYear(card.title);
                const make = parseMake(card.title);
                const bid = parseBid(card.priceText);
                const vin = parseVin(card.title);
                const mileage = parseMileage(card.title);

                if (seenLotIds.has(card.lotId)) continue;
                seenLotIds.add(card.lotId);

                if (!make) continue;
                if (!year || year < minYear) continue;
                if (bid > 0 && (bid < minBid || bid > maxBid)) continue;
                if (applyBuyerGradeFilters({ title: card.title, mileage }).length > 0) continue;
                if (!state || !US_STATES.has(state)) continue;
                if (HIGH_RUST.has(state)) {
                    const currentYear = new Date().getFullYear();
                    if (!(year && year >= currentYear - 2)) continue;
                    console.log(`[BYPASS] Rust state ${state} allowed — vehicle is ${year} (≤2yr old)`);
                }

                totalPassed++;
                const titleParts = card.title.match(/^(\d{4})\s+(.+)/);
                const model = titleParts ? titleParts[2].replace(new RegExp(`^${make}\\s*`, 'i'), '').trim() : null;

                log.info(`[PASS] ${card.title} | $${bid} | ${state}`);

                passingLots.push({
                    title: card.title,
                    year,
                    make: make.charAt(0).toUpperCase() + make.slice(1),
                    model: model ?? null,
                    current_bid: bid,
                    mileage: mileage ?? null,
                    state,
                    location: card.location,
                    listing_url: card.listingUrl,
                    photo_url: card.photoUrl,
                    auction_house: card.auctionHouse,
                    time_left: card.timeLeft,
                    vin: vin ?? null,
                    source_site: SOURCE,
                    scraped_at: new Date().toISOString(),
                });
            }

            // Pagination: increment page number in URL
            const pageNum = request.userData.page ?? 1;
            if (cards.length > 0 && pageNum < maxPages && passingLots.length < maxItems) {
                let nextUrl;
                if (url.match(/[?&]page=\d+/)) {
                    nextUrl = url.replace(/([?&])page=\d+/, `$1page=${pageNum + 1}`);
                } else {
                    nextUrl = url.includes('?')
                        ? `${url}&page=${pageNum + 1}`
                        : `${url}?page=${pageNum + 1}`;
                }
                await crawler.addRequests([{
                    url: nextUrl,
                    userData: { label: 'LIST', page: pageNum + 1 },
                }]);
            }
        }
    },
});

function decodeHtmlEntities(text) {
    return String(text ?? '')
        .replace(/&#x([0-9a-f]+);/gi, (_, hex) => String.fromCharCode(parseInt(hex, 16)))
        .replace(/&#(\d+);/g, (_, dec) => String.fromCharCode(parseInt(dec, 10)))
        .replace(/&nbsp;/gi, ' ')
        .replace(/&amp;/gi, '&')
        .replace(/&quot;/gi, '"')
        .replace(/&#39;/g, "'")
        .replace(/&lt;/gi, '<')
        .replace(/&gt;/gi, '>');
}

function extractAttributes(tag) {
    const attributes = {};
    const attrPattern = /([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*(["'])([\s\S]*?)\2/g;
    let match;
    while ((match = attrPattern.exec(String(tag ?? ''))) !== null) {
        attributes[match[1].toLowerCase()] = decodeHtmlEntities(match[3]);
    }
    return attributes;
}

function extractMetaDescriptions(html) {
    const descriptions = [];
    const metaPattern = /<meta\b[^>]*>/gi;
    let match;
    while ((match = metaPattern.exec(String(html ?? ''))) !== null) {
        const attrs = extractAttributes(match[0]);
        const label = String(attrs.name ?? attrs.property ?? '').toLowerCase();
        if ((label === 'description' || label === 'og:description') && attrs.content) {
            descriptions.push(attrs.content);
        }
    }
    return descriptions.join(' ');
}


function stripHtmlToText(html) {
    return normalize(decodeHtmlEntities(String(html ?? '')
        .replace(/<script[\s\S]*?<\/script>/gi, ' ')
        .replace(/<style[\s\S]*?<\/style>/gi, ' ')
        .replace(/<[^>]+>/g, ' ')));
}

function detailTextFromHtml(html) {
    return normalize(`${extractMetaDescriptions(html)} ${stripHtmlToText(html)}`);
}

async function enrichFromDetailPages(log) {
    const lotsNeedingDetail = passingLots.filter(lot => lot.listing_url && (!lot.vin || !lot.mileage));
    const detailLimit = Math.min(Math.max(Number(maxDetailPages) || 200, 0), 250);
    const toScrape = lotsNeedingDetail.slice(0, detailLimit);
    enrichmentProof.detail_pages_attempted = toScrape.length;
    if (toScrape.length === 0) {
        log.info('[DETAIL ENRICH] All Proxibid lots already have VIN/mileage or no detail URLs — skipping');
        return;
    }

    log.info(`[DETAIL ENRICH] Fetching ${toScrape.length} Proxibid detail pages for VIN/mileage (bounded to avoid actor timeout)`);
    let vinFound = 0;
    let mileageFound = 0;
    let rejectedAfterDetail = 0;

    for (const lot of toScrape) {
        try {
            const response = await fetch(lot.listing_url, {
                headers: {
                    'User-Agent': 'Mozilla/5.0 (compatible; DealerScopeBot/1.0; +https://dealscan-insight-production.up.railway.app)',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                },
            });
            if (!response.ok) {
                enrichmentProof.detail_pages_failed++;
                log.warning(`[DETAIL ENRICH] HTTP ${response.status} for ${lot.listing_url}`);
                continue;
            }
            enrichmentProof.detail_pages_fetched++;
            const bodyText = detailTextFromHtml(await response.text());
            lot.detail_text = bodyText;

            let enrichedByDetail = false;
            if (!lot.vin) {
                const vin = parseVin(bodyText);
                if (vin) {
                    lot.vin = vin;
                    vinFound++;
                    enrichedByDetail = true;
                    log.info(`[VIN FOUND] ${lot.vin} — ${lot.title}`);
                }
            }

            if (!lot.mileage) {
                const mileage = parseMileage(bodyText);
                if (mileage) {
                    lot.mileage = mileage;
                    mileageFound++;
                    enrichedByDetail = true;
                    log.info(`[MILEAGE FOUND] ${mileage} — ${lot.title}`);
                }
            }
            lot.detail_enriched = Boolean(lot.vin || lot.mileage);
            lot.detail_enriched_by_detail_page = enrichedByDetail;

            const rejectReasons = applyBuyerGradeFilters(lot);
            if (rejectReasons.length > 0) {
                lot.rejected_after_detail = true;
                lot.reject_reasons = rejectReasons;
                rejectedAfterDetail++;
                log.info(`[DETAIL REJECT] ${rejectReasons.join(',')} — ${lot.title}`);
            }

            await new Promise(resolve => setTimeout(resolve, 250));
        } catch (err) {
            enrichmentProof.detail_pages_failed++;
            log.warning(`[DETAIL ENRICH] Failed for ${lot.listing_url}: ${err.message}`);
        }
    }

    enrichmentProof.detail_vins_found = vinFound;
    enrichmentProof.detail_mileages_found = mileageFound;
    log.info(`[DETAIL ENRICH] Complete: fetched ${enrichmentProof.detail_pages_fetched}, found ${vinFound} VINs and ${mileageFound} mileages, rejected ${rejectedAfterDetail}`);
}

function proofSample(lot) {
    return {
        lot_id: parseLotId(lot.listing_url ?? ''),
        title: lot.title,
        state: lot.state,
        mileage_present: Boolean(lot.mileage),
        vin_present: Boolean(lot.vin),
        mileage: lot.mileage ?? null,
        vin: lot.vin ?? null,
        reject_reasons: lot.reject_reasons ?? [],
        source_site: lot.source_site,
    };
}

function finalizeEnrichmentProof(lotsToPush) {
    enrichmentProof.generated_at = new Date().toISOString();
    const accepted = lotsToPush;
    const acceptedEnriched = accepted.filter(lot => lot.detail_enriched);
    const rejected = passingLots.filter(lot => lot.rejected_after_detail);
    enrichmentProof.accepted_rows_total = accepted.length;
    enrichmentProof.rejected_rows_total = rejected.length;
    enrichmentProof.accepted_rows_with_vin = accepted.filter(lot => lot.vin).length;
    enrichmentProof.accepted_rows_with_mileage = accepted.filter(lot => lot.mileage).length;
    enrichmentProof.enriched_rows_accepted = acceptedEnriched.length;
    enrichmentProof.enriched_rows_rejected = rejected.length;
    enrichmentProof.rejection_reasons = {};
    for (const lot of rejected) {
        for (const reason of lot.reject_reasons ?? []) {
            enrichmentProof.rejection_reasons[reason] = (enrichmentProof.rejection_reasons[reason] ?? 0) + 1;
        }
    }
    enrichmentProof.accepted_enriched_samples = acceptedEnriched.slice(0, 5).map(proofSample);
    enrichmentProof.rejected_enriched_samples = rejected.slice(0, 5).map(proofSample);
    return enrichmentProof;
}

function publishableLots() {
    return passingLots
        .filter(lot => !lot.rejected_after_detail && applyBuyerGradeFilters(lot).length === 0)
        .map(({ detail_text, rejected_after_detail, reject_reasons, ...lot }) => ({
            ...lot,
            source_run_id: actorRunId,
            run_id: actorRunId,
            apify_run_id: actorRunId,
            actor_run_id: actorRunId,
            provenance_fields: {
                source_run_id: actorRunId,
                actor_run_id: actorRunId,
                detail_enriched: Boolean(lot.detail_enriched),
                detail_enriched_by_detail_page: Boolean(lot.detail_enriched_by_detail_page),
            },
        }));
}

try {
    await crawler.run(CATEGORY_URLS.map(url => ({ url, userData: { label: 'LIST', page: 1 } })));
    await enrichFromDetailPages(console);
    const lotsToPush = publishableLots();
    for (const lot of lotsToPush) {
        await Actor.pushData(lot);
    }
    const proof = finalizeEnrichmentProof(lotsToPush);
    await Actor.pushData(proof);
    console.log('[PROXIBID ENRICHMENT PROOF]', JSON.stringify(proof));
    console.log('[Proxibid] Sample locations:', sampleLocations);
    console.log(`[PROXIBID COMPLETE] Found: ${totalFound} | Passed list filters: ${totalPassed} | Pushed: ${lotsToPush.length}`);
} catch (err) {
    console.error(`[PROXIBID] Fatal error: ${err.message}`);
} finally {
    // Webhook notification to Railway ingest endpoint
    try {
        const dataset = await Actor.openDataset();
        const env = Actor.getEnv();
        await fetch('https://dealscan-insight-production.up.railway.app/api/ingest/apify', {
            method: 'POST',
            headers: {
                'X-Apify-Webhook-Secret': process.env.WEBHOOK_SECRET || '',
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                eventType: 'ACTOR.RUN.SUCCEEDED',
                eventData: {
                    actorId: env.actorId,
                    actorRunId: env.actorRunId,
                    runId: env.actorRunId,
                    defaultDatasetId: dataset.id,
                },
                actorRunId: env.actorRunId,
                runId: env.actorRunId,
                defaultDatasetId: dataset.id,
            }),
            signal: AbortSignal.timeout(10000),
        });
        console.log('[PROXIBID] Webhook sent to Railway ingest');
    } catch (webhookErr) {
        console.warn(`[PROXIBID] Webhook failed (non-blocking): ${webhookErr.message}`);
    }
    await Actor.exit();
}
