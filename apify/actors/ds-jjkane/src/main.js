/**
 * ds-jjkane — JJ Kane Government Surplus Vehicle Auction Scraper
 *                + Marketcheck Retail Pricing
 *
 * STATUS: WORKING — Algolia API + Marketcheck price estimation
 *
 * Architecture:
 *   JJ Kane (jjkane.com) is a major government surplus auctioneer.
 *   Uses public Algolia search index.
 *
 *   After scraping each vehicle, calls Marketcheck to get retail price:
 *     estimated_auction_price = marketcheck_median * 0.70
 *   (Government auctions clear at ~60-75% of retail — 70% is conservative floor)
 *
 * Key Algolia fields:
 *   make, model, year, odometer (string like "046379"), offSitePhysicalState,
 *   ringCloseOutDate, catalogDescription, category, webDescription
 *
 * Marketcheck API:
 *   https://mc-api.marketcheck.com/v2/search/car/active
 *   api_key loaded from MARKETCHECK_KEY env var (set in Apify actor input)
 *   params: year, make, model, miles_min, miles_max (±20% of odometer)
 */

import { Actor } from 'apify';

const SOURCE = 'jjkane';
const ALGOLIA_INDEX = 'api_items';
const MARKETCHECK_URL = 'https://mc-api.marketcheck.com/v2/search/car/active';

await Actor.init();
const input = await Actor.getInput() || {};
const ALGOLIA_APP_ID = input.algoliaAppId || process.env.ALGOLIA_APP_ID || 'ICB6K32PD0';
const ALGOLIA_SEARCH_KEY = input.algoliaSearchKey || process.env.ALGOLIA_SEARCH_KEY || '9d3241f7a3ee8947997deaa33cb0b249';
const ALGOLIA_URL = `https://${ALGOLIA_APP_ID}-dsn.algolia.net/1/indexes/${ALGOLIA_INDEX}/query`;

const MARKETCHECK_KEY = input.marketcheckKey || process.env.MARKETCHECK_KEY;
const MARKETCHECK_KEYS = [
    input.marketcheckKey1 || process.env.MARKETCHECK_KEY_1,
    input.marketcheckKey2 || process.env.MARKETCHECK_KEY_2,
    input.marketcheckKey3 || process.env.MARKETCHECK_KEY_3,
    MARKETCHECK_KEY,
].filter((key, index, keys) => key && keys.indexOf(key) === index);
if (MARKETCHECK_KEYS.length === 0) {
    console.warn('[JJKANE] MARKETCHECK_KEY missing — continuing without Marketcheck pricing');
}

// Auction-to-retail discount factor (government surplus clears at 60-75% retail)
const AUCTION_DISCOUNT = 0.70;
const DEFAULT_MAX_YEAR_AGE = 10;
const STANDARD_MAX_MILEAGE = 100000;
const STANDARD_MAX_MILES_PER_YEAR = 18000;
const PREMIUM_MAX_MODEL_AGE_YEARS = 4;
const PREMIUM_MAX_MILEAGE = 50000;

// Vehicle categories we want
const VEHICLE_CATEGORIES = [
    'PICKUP TRUCK',
    'SPORT UTILITY VEHICLE (SUV)',
    'AUTOMOBILE',
    'VAN - FULLSIZE',
    'SERVICE TRUCK (1-TON AND UNDER)',
    'VAN BODY/BOX TRUCK',
    'FLATBED/SERVICE TRUCK',
    'CARGO VAN',
    'SEDAN',
];

function failsDealerScopeAgeMileageGate(year, mileage, currentYear = new Date().getFullYear(), maxYearAge = DEFAULT_MAX_YEAR_AGE) {
    if (!year) return false;
    const ageYears = currentYear - year;
    if (ageYears > maxYearAge || ageYears < 0) return true;
    if (mileage === null || mileage === undefined || mileage <= 0) return false;
    if (mileage > STANDARD_MAX_MILEAGE) return true;
    const denominator = Math.max(1, ageYears);
    // Premium lane (<= PREMIUM_MAX_MODEL_AGE_YEARS old AND <= PREMIUM_MAX_MILEAGE) is exempt from
    // the standard-lane miles/year cap, mirroring backend determine_vehicle_tier. Without this,
    // late-model high-mileage fleet vehicles are silently dropped before scoring.
    if (ageYears <= PREMIUM_MAX_MODEL_AGE_YEARS && mileage <= PREMIUM_MAX_MILEAGE) return false;
    return mileage / denominator > STANDARD_MAX_MILES_PER_YEAR;
}

const TARGET_STATES = [
    'FL', 'NV', 'CA', 'TX', 'AZ', 'CO', 'UT', 'OR', 'WA', 'GA',
    'NC', 'VA', 'TN', 'SC', 'AL', 'LA', 'OK', 'NM', 'ID', 'MT',
    'WY', 'ND', 'SD', 'NE', 'KS',
];

const HIGH_RUST_STATES = new Set([
    'OH', 'MI', 'PA', 'NY', 'WI', 'MN', 'IL', 'IN', 'MO', 'IA',
    'WV', 'ME', 'NH', 'VT', 'MA', 'RI', 'CT', 'NJ', 'MD', 'DE',
]);
const CONDITION_REJECT_PATTERNS = [
    /\bsalvage\b/i,
    /\bflood\b/i,
    /\bframe[\s-]+damage\b/i,
    /\bcrash(?:ed)?\b/i,
    /\bcollision[\s-]+damage\b/i,
    /\bfire[\s-]+damage\b/i,
    /\bhail[\s-]+damage\b/i,
    /\bwrecked\b/i,
    /\bwont\s+start\b/i,
    /\bwon'?t\s+start\b/i,
    /\bdoes\s+not\s+start\b/i,
    /\bnot\s+running\b/i,
    /\bno[\s-]start\b/i,
    /\binop(?:erable)?\b/i,
    /\bdoes\s+not\s+move\b/i,
    /\bbroken\s+axle\b/i,
    /\bparts[\s-]+only\b/i,
    /\bfor\s+parts\b/i,
    /\bproject\s+(?:car|vehicle|truck)\b/i,
    /\brebuilt\s+title\b/i,
    /\bbranded\s+title\b/i,
    /\bstructural[\s-]+damage\b/i,
    /\bblown\s+engine\b/i,
    /\bbad\s+engine\b/i,
    /\bno\s+title\b/i,
    /\btrue\s+mileage\s+unknown\b/i,
    /\bcondition\s+unknown\b/i,
    /\bairbags?\s+deployed\b/i,
    /\bno\s+power\b/i,
    /\bjump\s+to\s+start\b/i,
    /\bdash\s+warning\s+indicators?\s+on\b/i,
    /\bcheck\s+engine\s+light\s+on\b/i,
    /\babs\s+light\s+on\b/i,
    /\btraction\s+control\s+light\s+on\b/i,
];

// ── Helpers ───────────────────────────────────────────────────────────────────

function normalizeText(v) {
    return String(v ?? '').replace(/\s+/g, ' ').trim();
}

function extractVin(text) {
    const normalized = normalizeText(text).toUpperCase();
    const labeled = normalized.match(
        /\b(?:VIN|V\.I\.N\.|S\/N|SERIAL(?:\s+NUMBER)?)\s*[:#-]?\s*([A-HJ-NPR-Z0-9]{17})\b/
    );
    if (labeled) return labeled[1];

    const anyVin = normalized.match(/\b([A-HJ-NPR-Z0-9]{17})\b/);
    return anyVin ? anyVin[1] : null;
}

function decodeHtmlEntities(text) {
    return normalizeText(text)
        .replace(/&nbsp;/gi, ' ')
        .replace(/&amp;/gi, '&')
        .replace(/&#0*39;/g, "'")
        .replace(/&quot;/gi, '"')
        .replace(/&lt;/gi, '<')
        .replace(/&gt;/gi, '>');
}

function stripHtml(text) {
    return decodeHtmlEntities(String(text ?? '').replace(/<[^>]+>/g, ' '));
}

function extractVinFromDetailHtml(html) {
    const source = String(html ?? '');
    const tableVin = source.match(
        /<th\b[^>]*>\s*VIN\s*:?\s*<\/th>\s*<td\b[^>]*>\s*([A-HJ-NPR-Z0-9]{17})\s*<\/td>/i
    );
    if (tableVin) return tableVin[1].toUpperCase();

    return extractVin(stripHtml(source));
}

async function fetchDetailVin(itemId) {
    if (!itemId) return null;
    const url = buildListingUrl(itemId);

    try {
        const resp = await fetch(url, {
            headers: {
                'User-Agent': 'Mozilla/5.0 (compatible; DealerScopeBot/1.0; +https://dealscan-insight-production.up.railway.app)',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            },
            signal: AbortSignal.timeout(15000),
        });

        if (!resp.ok) {
            console.warn(`[JJKANE] Detail page VIN fetch failed for ${itemId}: HTTP ${resp.status}`);
            return null;
        }

        return extractVinFromDetailHtml(await resp.text());
    } catch (err) {
        console.warn(`[JJKANE] Detail page VIN fetch error for ${itemId}: ${err.message}`);
        return null;
    }
}

function parseYear(v) {
    const y = parseInt(String(v ?? '').replace(/\D/g, ''), 10);
    return (y >= 1980 && y <= new Date().getFullYear() + 1) ? y : null;
}

function parseOdometer(v) {
    // e.g. "046379" or "46,379" or "46379 Miles"
    if (!v) return null;
    const clean = String(v).replace(/[^\d]/g, '');
    const miles = parseInt(clean, 10);
    return (!isNaN(miles) && miles > 0 && miles < 1000000) ? miles : null;
}

function parseBid(v) {
    if (!v) return 0;
    const m = String(v).replace(/,/g, '').match(/[\d]+(?:\.\d+)?/);
    return m ? parseFloat(m[0]) : 0;
}

function parseDate(v) {
    if (!v) return null;
    // "MM/DD/YYYY" or "YYYY-MM-DD" or Unix timestamp
    const asNum = Number(v);
    if (!isNaN(asNum) && asNum > 1000000000) {
        return new Date(asNum * 1000).toISOString();
    }
    const m = String(v).match(/(\d{1,2})\/(\d{1,2})\/(\d{4})/);
    if (m) {
        const d = new Date(`${m[3]}-${m[1].padStart(2, '0')}-${m[2].padStart(2, '0')}T23:59:00-05:00`);
        return isNaN(d.getTime()) ? null : d.toISOString();
    }
    try {
        const d = new Date(v);
        return isNaN(d.getTime()) ? null : d.toISOString();
    } catch { return null; }
}

function buildListingUrl(itemId) {
    return `https://www.jjkane.com/items/${itemId}`;
}

function buildImageUrl(itemId) {
    return `https://prod.cdn.jjkane.com/${itemId}-1?template=Medium`;
}

function median(arr) {
    if (!arr || arr.length === 0) return null;
    const sorted = [...arr].sort((a, b) => a - b);
    const mid = Math.floor(sorted.length / 2);
    return sorted.length % 2 === 0
        ? (sorted[mid - 1] + sorted[mid]) / 2
        : sorted[mid];
}

function hasConditionReject(text) {
    const lower = normalizeText(text).toLowerCase();
    return CONDITION_REJECT_PATTERNS.some((pattern) => pattern.test(lower));
}

function incrementCount(map, key) {
    map[key] = (map[key] || 0) + 1;
}

function addSample(samples, sample, limit = 5) {
    if (samples.length >= limit) return;
    samples.push(sample);
}

// ── Marketcheck API ───────────────────────────────────────────────────────────

// Cache to avoid re-querying same make/model/year/mileage band
const marketcheckCache = new Map();
const MAX_MARKETCHECK_CALLS_PER_RUN = 50; // Protect 500/month quota
let marketcheckCallsThisRun = 0;

async function getMarketcheckPrice(year, make, model, odometer) {
    if (MARKETCHECK_KEYS.length === 0 || !year || !make || !model) return null;

    const makeLower = make.toLowerCase().trim();
    const modelRaw = model.toLowerCase().trim();

    // Normalize model name for Marketcheck API
    const modelNormalized = modelRaw
        .replace(/\s*(police|interceptor|package|special|fleet|pursuit|4x4|4wd|awd|rwd|fwd|diesel|hybrid|hev|phev|turbo|sport|limited|xl|xlt|lariat|stx|slt|lt|ltz|ls|le|se|sel|ex|exl|touring|platinum|king\s*ranch|raptor|rebel|laramie|tradesman|big\s*horn|lone\s*star).*$/i, '')
        .replace(/\bf(\d{3})\b/g, 'f-$1')   // f150 → f-150, f250 → f-250, f350 → f-350
        .replace(/\be(\d{3})\b/g, 'e-$1')   // e250 → e-250, e350 → e-350
        .replace(/\bram\b\s+(\d{3,4})/g, '$1') // "ram 1500" → "1500" (Dodge/Ram model)
        .replace(/\bsierr?a\b\s+(\d{3,4})/g, 'sierra $1')
        .replace(/\bsilverado\b\s+(\d{3,4})/g, 'silverado $1')
        .trim();

    // Miles band: ±20% of odometer (or 0–999999 if no odometer)
    let milesMin = 0;
    let milesMax = 999999;
    if (odometer && odometer > 0) {
        milesMin = Math.max(0, Math.floor(odometer * 0.80));
        milesMax = Math.ceil(odometer * 1.20);
    }

    // Round to nearest 5000 for cache key
    const milesKey = odometer ? Math.round(odometer / 5000) * 5000 : 0;
    const cacheKey = `${year}|${makeLower}|${modelNormalized}|${milesKey}`;
    if (marketcheckCallsThisRun >= MAX_MARKETCHECK_CALLS_PER_RUN) {
        return { pricing_unavailable: true, pricing_source: 'marketcheck_quota_exceeded' };
    }
    if (marketcheckCache.has(cacheKey)) {
        return marketcheckCache.get(cacheKey);
    }

    let lastUnavailable = null;
    for (const apiKey of MARKETCHECK_KEYS) {
        if (marketcheckCallsThisRun >= MAX_MARKETCHECK_CALLS_PER_RUN) {
            lastUnavailable = { pricing_unavailable: true, pricing_source: 'marketcheck_quota_exceeded' };
            break;
        }

        const params = new URLSearchParams({
            api_key: apiKey,
            year: String(year),
            make: makeLower,
            model: modelNormalized,
            miles_min: String(milesMin),
            miles_max: String(milesMax),
            rows: '20',
            start: '0',
            fields: 'price,miles',
            has_price: 'true',
            has_miles: 'true',
        });

        try {
            marketcheckCallsThisRun++; // count every actual API call (success or error)
            const resp = await fetch(`${MARKETCHECK_URL}?${params}`, {
                signal: AbortSignal.timeout(10000),
                headers: { 'Accept': 'application/json', 'x-version': 'v4.6.0' },
            });

            if (!resp.ok) {
                console.warn(`[MC] HTTP ${resp.status} for ${year} ${make} ${model}`);
                lastUnavailable = {
                    pricing_unavailable: true,
                    pricing_source: `marketcheck_http_${resp.status}`,
                };
                continue;
            }

            const data = await resp.json();
            const listings = data?.listings ?? [];

            if (listings.length === 0) {
                marketcheckCache.set(cacheKey, null);
                return null;
            }

            // Extract valid prices
            const prices = listings
                .map(l => parseFloat(String(l.price ?? '0').replace(/,/g, '')))
                .filter(p => p > 500 && p < 500000);

            if (prices.length === 0) {
                marketcheckCache.set(cacheKey, null);
                return null;
            }

            const medianPrice = median(prices);
            const result = {
                retail_median: Math.round(medianPrice),
                estimated_auction_price: Math.round(medianPrice * AUCTION_DISCOUNT),
                sample_count: prices.length,
            };

            marketcheckCache.set(cacheKey, result);
            return result;

        } catch (err) {
            console.warn(`[MC] Error for ${year} ${make} ${model}: ${err.message}`);
            lastUnavailable = {
                pricing_unavailable: true,
                pricing_source: 'marketcheck_request_error',
            };
        }
    }

    const result = lastUnavailable || {
        pricing_unavailable: true,
        pricing_source: 'marketcheck_unavailable',
    };
    marketcheckCache.set(cacheKey, result);
    return result;
}

// ── Algolia Query ─────────────────────────────────────────────────────────────

async function queryAlgolia({ categoryFilter, stateFilter, searchQuery: q = '', page = 0, hitsPerPage = 100 }) {
    const filters = [categoryFilter, stateFilter].filter(Boolean).join(' AND ');

    const body = JSON.stringify({
        query: q || '',
        filters,
        page,
        hitsPerPage,
        attributesToRetrieve: [
            'id', 'kp_title', 'webDescription', 'make', 'model', 'year',
            'category', 'odometer', 'catalogDescription',
            'offSitePhysicalCity', 'offSitePhysicalState',
            'ringCloseOutDate', 'currentBid', 'shortDescription',
            'lotNumber', 'auctionId', 'vin',
        ],
    });

    const resp = await fetch(ALGOLIA_URL, {
        method: 'POST',
        headers: {
            'X-Algolia-Application-Id': ALGOLIA_APP_ID,
            'X-Algolia-API-Key': ALGOLIA_SEARCH_KEY,
            'Content-Type': 'application/json',
        },
        body,
        signal: AbortSignal.timeout(15000),
    });

    if (!resp.ok) {
        throw new Error(`Algolia error: ${resp.status} ${await resp.text()}`);
    }

    return await resp.json();
}

// ── Main ──────────────────────────────────────────────────────────────────────

const {
    targetStates = TARGET_STATES,
    searchQuery = '',
    minBid = 0,
    maxBid = 75000,
    maxYearAge = DEFAULT_MAX_YEAR_AGE,
    maxItemsPerState = 500,
    enableMarketcheck = MARKETCHECK_KEYS.length > 0,
    webhookUrl = null,
    webhookSecret = null,
} = input;

const currentYear = new Date().getFullYear();
let totalFound = 0;
let totalPassed = 0;
let totalPushed = 0;
let totalMarketcheck = 0;
let rowsExcludedMissingRequiredData = 0;
let rowsExcludedAgeMileagePrefilter = 0;
let rowsExcludedPolicyPrefilter = 0;
let rowsExcludedRustState = 0;
let rowsExcludedBidRange = 0;
let rowsExcludedZeroPricingSignal = 0;
let rowsExcludedPricingUnavailable = 0;
const rejectionReasons = {};
const prefilterAgeMileageRejectedSamples = [];
const prefilterPolicyRejectedSamples = [];
const zeroPricingRejectedSamples = [];
const pricingUnavailableSamples = [];

// Build Algolia filter for vehicle categories
const categoryFilter = `(${VEHICLE_CATEGORIES.map(c => `category:"${c}"`).join(' OR ')})`;

for (const state of targetStates) {
    const stateFilter = `offSitePhysicalState:${state}`;
    let page = 0;
    let statePassed = 0;

    console.log(`[JJKANE] Querying state: ${state}`);

    try {
        const firstPage = await queryAlgolia({ categoryFilter, stateFilter, searchQuery, page: 0, hitsPerPage: 100 });
        const nbHits = firstPage.nbHits ?? 0;
        const nbPages = firstPage.nbPages ?? 1;

        console.log(`[JJKANE] ${state}: ${nbHits} vehicle lots across ${nbPages} pages`);

        const allPages = [firstPage];

        for (let p = 1; p < nbPages && statePassed < maxItemsPerState; p++) {
            await new Promise(r => setTimeout(r, 250));
            const pageData = await queryAlgolia({ categoryFilter, stateFilter, searchQuery, page: p, hitsPerPage: 100 });
            allPages.push(pageData);
        }

        for (const pageData of allPages) {
            for (const hit of (pageData.hits ?? [])) {
                totalFound++;

                const itemId = hit.id;
                const title = normalizeText(
                    hit.webDescription || hit.kp_title || hit.shortDescription || ''
                );
                const make = normalizeText(hit.make || '');
                const model = normalizeText(hit.model || '');
                const year = parseYear(hit.year);
                const odometer = parseOdometer(hit.odometer);
                const state_code = normalizeText(hit.offSitePhysicalState || state);
                const city = normalizeText(hit.offSitePhysicalCity || '');
                const catalogDescription = normalizeText(hit.catalogDescription || '');
                const conditionText = [
                    title,
                    catalogDescription,
                    normalizeText(hit.webDescription || ''),
                    normalizeText(hit.shortDescription || ''),
                ].filter(Boolean).join(' ');
                const vinFromSourceText = normalizeText(hit.vin || extractVin(conditionText) || '');
                const sample = {
                    title: title || `${year || ''} ${make} ${model}`.trim(),
                    year,
                    odometer,
                    state: state_code,
                    listing_url: itemId ? buildListingUrl(itemId) : null,
                };

                // ── Filters ──────────────────────────────────────────────────
                if (!itemId || !title || !make || !model || !year) {
                    rowsExcludedMissingRequiredData++;
                    incrementCount(rejectionReasons, 'missing_required_data');
                    continue;
                }

                if (hasConditionReject(conditionText)) {
                    rowsExcludedPolicyPrefilter++;
                    incrementCount(rejectionReasons, 'condition_reject_prefilter');
                    addSample(prefilterPolicyRejectedSamples, sample);
                    continue;
                }
                // Rust state — bypass for ≤2yr old
                if (HIGH_RUST_STATES.has(state_code)) {
                    if (!(year && year >= currentYear - 2)) {
                        rowsExcludedRustState++;
                        incrementCount(rejectionReasons, 'rust_state_reject');
                        continue;
                    }
                    console.log(`[BYPASS] Rust ${state_code} — year ${year}`);
                }

                // Year age
                if (failsDealerScopeAgeMileageGate(year, odometer, currentYear, maxYearAge)) {
                    rowsExcludedAgeMileagePrefilter++;
                    incrementCount(rejectionReasons, 'age_or_mileage_exceeded_prefilter');
                    addSample(prefilterAgeMileageRejectedSamples, sample);
                    continue;
                }

                const detailVin = vinFromSourceText ? null : await fetchDetailVin(itemId);
                const vin = normalizeText(vinFromSourceText || detailVin || '');
                const vinSource = hit.vin
                    ? 'algolia_vin'
                    : (vinFromSourceText ? 'jjkane_serial_text' : (detailVin ? 'jjkane_detail_page' : null));

                if (!vin) {
                    rowsExcludedMissingRequiredData++;
                    incrementCount(rejectionReasons, 'missing_vin');
                    continue;
                }

                // ── Marketcheck pricing ───────────────────────────────────────
                let marketcheckMedian = null;
                let estimatedAuctionPrice = 0;
                let pricingSource = 'jjkane_no_bid';
                let pricingUnavailableReason = null;

                if (enableMarketcheck && make && model && year) {
                    const mcResult = await getMarketcheckPrice(year, make, model, odometer);
                    if (mcResult?.pricing_unavailable) {
                        pricingUnavailableReason = mcResult.pricing_source || 'marketcheck_unavailable';
                    } else if (mcResult) {
                        marketcheckMedian = mcResult.retail_median;
                        estimatedAuctionPrice = mcResult.estimated_auction_price;
                        pricingSource = `marketcheck_jjkane_estimated_${mcResult.sample_count}samples`;
                        totalMarketcheck++;
                    }
                    // Polite delay after Marketcheck call
                    await new Promise(r => setTimeout(r, 300));
                }

                // Existing currentBid from Algolia (may be 0 early in auction)
                const currentBid = parseBid(hit.currentBid);

                // Use whichever pricing signal is available.
                // If Marketcheck is unavailable, fall back to live current bid so actor still runs.
                const effectiveBid = currentBid > 0 ? currentBid : estimatedAuctionPrice;

                // Skip only when both pricing signals are missing.
                if (effectiveBid === 0) {
                    if (pricingUnavailableReason) {
                        console.log(`[SKIP-PRICING-UNAVAILABLE] ${title || `${year} ${make} ${model}`} | reason=${pricingUnavailableReason} currentBid=$${currentBid}`);
                        rowsExcludedPricingUnavailable++;
                        incrementCount(rejectionReasons, pricingUnavailableReason);
                        addSample(pricingUnavailableSamples, sample);
                        continue;
                    }
                    console.log(`[SKIP-ZERO-BID] ${title || `${year} ${make} ${model}`} | estimatedAuctionPrice=$${estimatedAuctionPrice} currentBid=$${currentBid}`);
                    rowsExcludedZeroPricingSignal++;
                    incrementCount(rejectionReasons, 'zero_pricing_signal');
                    addSample(zeroPricingRejectedSamples, sample);
                    continue;
                }

                if (currentBid > 0 && !marketcheckMedian) {
                    pricingSource = 'jjkane_live_bid_only';
                }

                // Bid range filter (only applies if we have a real bid or estimate)
                if (effectiveBid > 0 && effectiveBid > maxBid) {
                    rowsExcludedBidRange++;
                    incrementCount(rejectionReasons, 'bid_above_max');
                    continue;
                }
                if (effectiveBid > 0 && effectiveBid < minBid && currentBid > 0) {
                    rowsExcludedBidRange++;
                    incrementCount(rejectionReasons, 'bid_below_min');
                    continue;
                }

                const record = {
                    listing_id: `jjkane-${itemId}`,
                    title,
                    make,
                    model,
                    year,
                    odometer,
                    vin: vin || null,
                    // Pricing fields
                    current_bid: effectiveBid,
                    actual_current_bid: currentBid,
                    mmr: marketcheckMedian,               // retail reference price
                    estimated_auction_price: estimatedAuctionPrice,
                    pricing_source: pricingSource,
                    // Location
                    state: state_code,
                    city,
                    location: [city, state_code].filter(Boolean).join(', '),
                    // Auction info
                    auction_end_date: parseDate(hit.ringCloseOutDate),
                    listing_url: buildListingUrl(itemId),
                    image_url: buildImageUrl(itemId),
                    lot_number: String(hit.lotNumber || ''),
                    auction_id: String(hit.auctionId || ''),
                    category: normalizeText(hit.category || ''),
                    description: catalogDescription,
                    vin_source: vinSource,
                    agency_name: 'JJ Kane Government Surplus',
                    source_site: SOURCE,
                    scraped_at: new Date().toISOString(),
                };

                if (statePassed >= maxItemsPerState) {
                    console.log(`[JJKANE] ${state}: maxItemsPerState (${maxItemsPerState}) reached, stopping`);
                    break;
                }
                await Actor.pushData(record);
                statePassed++;
                totalPassed++;
                totalPushed++;
                console.log(`[PASS] ${title || `${year} ${make} ${model}`} | bid=$${effectiveBid} mmr=$${marketcheckMedian ?? 'N/A'} | ${state_code}`);
            }
        }

        console.log(`[JJKANE] ${state}: ${statePassed} vehicles passed filters`);

    } catch (err) {
        console.error(`[JJKANE] Error querying state ${state}: ${err.message}`);
    }

    await new Promise(r => setTimeout(r, 500));
}

const proofRecord = {
    record_type: 'source_quality_proof',
    source: 'jjkane',
    source_site: SOURCE,
    generated_at: new Date().toISOString(),
    found_rows_total: totalFound,
    prefilter_passed_rows_total: totalPassed,
    pushed_rows_total: totalPushed,
    rows_excluded_missing_required_data: rowsExcludedMissingRequiredData,
    rows_excluded_age_mileage_prefilter: rowsExcludedAgeMileagePrefilter,
    rows_excluded_policy_prefilter: rowsExcludedPolicyPrefilter,
    rows_excluded_rust_state: rowsExcludedRustState,
    rows_excluded_bid_range: rowsExcludedBidRange,
    rows_excluded_zero_pricing_signal: rowsExcludedZeroPricingSignal,
    rows_excluded_pricing_unavailable: rowsExcludedPricingUnavailable,
    max_year_age: maxYearAge,
    max_allowed_mileage: STANDARD_MAX_MILEAGE,
    standard_max_miles_per_year: STANDARD_MAX_MILES_PER_YEAR,
    target_states: targetStates,
    search_query: searchQuery,
    marketcheck_calls: marketcheckCallsThisRun,
    marketcheck_priced_rows: totalMarketcheck,
    rejection_reasons: rejectionReasons,
    prefilter_age_mileage_rejected_samples: prefilterAgeMileageRejectedSamples,
    prefilter_policy_rejected_samples: prefilterPolicyRejectedSamples,
    zero_pricing_rejected_samples: zeroPricingRejectedSamples,
    pricing_unavailable_samples: pricingUnavailableSamples,
};
await Actor.pushData(proofRecord);

// ── Webhook notification ──────────────────────────────────────────────────────

const effectiveWebhookUrl = webhookUrl
    || process.env.WEBHOOK_URL
    || 'https://dealscan-insight-production.up.railway.app/api/ingest/apify';
const effectiveWebhookSecret = webhookSecret || process.env.WEBHOOK_SECRET || '';
const datasetItemCount = totalPushed + 1;

if (effectiveWebhookUrl && datasetItemCount > 0) {
    try {
        const resp = await fetch(effectiveWebhookUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Apify-Webhook-Secret': effectiveWebhookSecret,
            },
            body: JSON.stringify({
                source: SOURCE,
                actorId: process.env.APIFY_ACT_ID ?? null,
                actorRunId: process.env.APIFY_ACTOR_RUN_ID ?? 'local',
                defaultDatasetId: process.env.APIFY_DEFAULT_DATASET_ID ?? null,
                itemCount: datasetItemCount,
                totalScraped: totalFound,
                marketcheckPriced: totalMarketcheck,
                timestamp: new Date().toISOString(),
            }),
            signal: AbortSignal.timeout(10000),
        });
        console.log(`[WEBHOOK] Notified ingest: HTTP ${resp.status}`);
    } catch (err) {
        console.warn(`[WEBHOOK] Failed: ${err.message}`);
    }
}

console.log(`[JJKANE COMPLETE] Found: ${totalFound} | Passed: ${totalPassed} | Marketcheck priced: ${totalMarketcheck}`);

await Actor.exit();

// deploy retry after sequential build gating 2026-06-13
