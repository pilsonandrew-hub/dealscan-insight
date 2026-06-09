/**
 * ds-govplanet — GovPlanet Government Surplus Vehicle Scraper
 *
 * Strategy: CheerioCrawler (pure HTTP, no browser) against public category pages.
 * Each listing page renders vehicle data in quickviews.push({...}) JS blocks.
 * All needed fields (description, price, location, mileage, equipId, timeLeft)
 * are in those blocks — zero detail-page visits required.
 *
 * Sources scraped:
 *   - /Pickup+Trucks?ct=3         → 491 vehicles
 *   - /Automobiles?ct=3           → 268 vehicles
 *   - /Vans?ct=3                  → 165 vehicles
 *   - /Compact+Sport+Utility+Vehicles → 56 vehicles
 *   Total: ~980 unique live vehicles per run
 *
 * Pagination: pstart=0,60,120,... (60 items/page)
 */

import { Actor } from 'apify';
import { CheerioCrawler, RequestQueue } from 'crawlee';

const SOURCE = 'govplanet';
const BASE   = 'https://www.govplanet.com';

// Vehicle category URLs — l2=USA filters to US listings at source (no client-side country filter needed)
// Priority order: highest DOS score first
const CATEGORY_URLS = [
    { url: `${BASE}/Pickup+Trucks?ct=3&l2=USA`,                    label: 'pickup_trucks' },  // 367
    { url: `${BASE}/Van+Trucks?ct=3&l2=USA`,                       label: 'van_trucks' },     // 230
    { url: `${BASE}/Service+and+Utility+Trucks?ct=3&l2=USA`,       label: 'service_trucks' }, // 182
    { url: `${BASE}/Vans?ct=3&l2=USA`,                             label: 'vans' },           // 89
    { url: `${BASE}/Automobiles?ct=3&l2=USA`,                      label: 'automobiles' },    // 40
    { url: `${BASE}/Full+Size+Sport+Utility+Vehicles?l2=USA`,      label: 'full_suv' },       // 37
    { url: `${BASE}/Compact+Sport+Utility+Vehicles?l2=USA`,        label: 'compact_suv' },    // 37
];

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

const STATE_NAMES = {
    ALABAMA:'AL', ALASKA:'AK', ARIZONA:'AZ', ARKANSAS:'AR', CALIFORNIA:'CA',
    COLORADO:'CO', CONNECTICUT:'CT', DELAWARE:'DE', FLORIDA:'FL', GEORGIA:'GA',
    HAWAII:'HI', IDAHO:'ID', ILLINOIS:'IL', INDIANA:'IN', IOWA:'IA',
    KANSAS:'KS', KENTUCKY:'KY', LOUISIANA:'LA', MAINE:'ME', MARYLAND:'MD',
    MASSACHUSETTS:'MA', MICHIGAN:'MI', MINNESOTA:'MN', MISSISSIPPI:'MS', MISSOURI:'MO',
    MONTANA:'MT', NEBRASKA:'NE', NEVADA:'NV', 'NEW HAMPSHIRE':'NH', 'NEW JERSEY':'NJ',
    'NEW MEXICO':'NM', 'NEW YORK':'NY', 'NORTH CAROLINA':'NC', 'NORTH DAKOTA':'ND',
    OHIO:'OH', OKLAHOMA:'OK', OREGON:'OR', PENNSYLVANIA:'PA', 'RHODE ISLAND':'RI',
    'SOUTH CAROLINA':'SC', 'SOUTH DAKOTA':'SD', TENNESSEE:'TN', TEXAS:'TX',
    UTAH:'UT', VERMONT:'VT', VIRGINIA:'VA', WASHINGTON:'WA', 'WEST VIRGINIA':'WV',
    WISCONSIN:'WI', WYOMING:'WY', 'DISTRICT OF COLUMBIA':'DC',
};

const COMMERCIAL_PATTERN = /\b(dump truck|flatbed|refuse|crane|utility body|step van|panel van|ambulance|fire truck|bucket truck|aerial lift|sewer|sweeper|plow truck|tractor|forklift|loader|backhoe|excavator|grader|boat|trailer|motorcycle|atv|utv|rv|camper|spreader|mixer|tank|tanker)\b/i;
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
const NON_VEHICLE_PART_PATTERNS = [
    /\btruck\s+bed\b/i, // truck bed
    /\bpickup\s+bed\b/i, // pickup bed
    /\bcamper\s+shell\b/i, // camper shell
    /\btonneau\s+cover\b/i, // tonneau
    /\bbed\s+cap\b/i, // bed cap
    /\butility\s+body\b/i, // utility body
    /\bservice\s+body\b/i, // service body
    /\btruck\s+cap\b/i, // truck cap
    /\btruck\s+topper\b/i, // truck topper
    /\b(?:ford|chevrolet|chevy|gmc|dodge|ram|toyota|nissan)\s+(?:\w+\s+){0,3}tailgate\b/i, // tailgate
    /\btailgate\s+(?:assembly|part|only)\b/i, // tailgate
    /\b(?:truck|pickup)\s+bed\s+liner\b/i, // bed liner
    /\bbed\s+liner\s+(?:kit|only)\b/i, // bed liner
    /\bvehicle\s+parts\b/i, // vehicle parts
];

const MAKES = new Set([
    'ford','chevrolet','chevy','dodge','ram','toyota','honda','nissan','jeep','gmc',
    'chrysler','hyundai','kia','subaru','mazda','volkswagen','vw','bmw','mercedes',
    'audi','lexus','acura','infiniti','cadillac','lincoln','buick','pontiac',
    'mitsubishi','volvo','tesla','saturn','isuzu','hummer','land rover','mini',
    'suzuki','fiat','scion','mercury','oldsmobile',
]);

// ── Helpers ──────────────────────────────────────────────────────────────────

function extractState(locationText = '') {
    const upper = locationText.toUpperCase().trim();
    if (!upper) return '';
    // "California" → CA
    for (const [name, code] of Object.entries(STATE_NAMES)) {
        if (upper.includes(name)) return code;
    }
    // Two-letter match at end "..., TX"
    const m = upper.match(/,\s*([A-Z]{2})\b/) ?? upper.match(/\b([A-Z]{2})$/);
    const abbrev = m?.[1] ?? '';
    return US_STATES.has(abbrev) ? abbrev : '';
}

function parseMileage(usageStr = '') {
    // "127,717 mi" → 127717  |  "13,886 hrs" → null (hours, not miles)
    const clean = usageStr.replace(/,/g, '');
    const m = clean.match(/([\d]+(?:\.\d+)?)\s*(mi|miles?)\b/i);
    if (m) return parseInt(m[1], 10);
    // km → convert
    const km = clean.match(/([\d]+(?:\.\d+)?)\s*(km|kilometers?)\b/i);
    if (km) return Math.round(parseFloat(km[1]) * 0.621371);
    return null;
}

function extractVin(text = '') {
    const m = String(text || '').match(/\b([A-HJ-NPR-Z0-9]{17})\b/i);
    return m ? m[1].toUpperCase() : null;
}

function parseDetailVin(html = '') {
    const text = String(html || '')
        .replace(/<script[\s\S]*?<\/script>/gi, ' ')
        .replace(/<style[\s\S]*?<\/style>/gi, ' ')
        .replace(/<[^>]+>/g, ' ')
        .replace(/&nbsp;/gi, ' ')
        .replace(/&#39;/g, "'")
        .replace(/&quot;/gi, '"')
        .replace(/&amp;/gi, '&')
        .replace(/\s+/g, ' ')
        .trim();
    const patterns = [
        /\bVIN\b\s*[:#\-]?\s*([A-HJ-NPR-Z0-9]{17})\b/i,
        /\bVehicle\s+Identification\s+Number\b\s*[:#\-]?\s*([A-HJ-NPR-Z0-9]{17})\b/i,
        /\bSerial\s+(?:Number|No\.?|#)\b\s*[:#\-]?\s*([A-HJ-NPR-Z0-9]{17})\b/i,
        /\bS\/N\b\s*[:#\-]?\s*([A-HJ-NPR-Z0-9]{17})\b/i,
    ];
    for (const pattern of patterns) {
        const match = text.match(pattern);
        if (match) return extractVin(match[1]);
    }
    return null;
}

function parsePrice(priceStr = '') {
    const m = priceStr.replace(/,/g, '').match(/[\d]+(?:\.\d+)?/);
    return m ? parseFloat(m[0]) : 0;
}

function parseAuctionEnd(timeLeft = '', now = new Date()) {
    const text = String(timeLeft || '').trim();
    if (!text) return null;

    const daysMatch = text.match(/(\d+)\s*day/i);
    const hoursMatch = text.match(/(\d+)\s*hour/i);
    if (daysMatch || hoursMatch) {
        const days = daysMatch ? parseInt(daysMatch[1], 10) : 0;
        const hours = hoursMatch ? parseInt(hoursMatch[1], 10) : 0;
        const ms = days * 86400000 + hours * 3600000;
        return ms > 0 ? new Date(now.getTime() + ms).toISOString() : null;
    }

    const monthDay = text.match(/\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2})(?:,\s*(\d{4}))?\b/i);
    if (!monthDay) return null;

    const monthIndex = ['jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec']
        .indexOf(monthDay[1].slice(0, 3).toLowerCase());
    if (monthIndex < 0) return null;

    let year = monthDay[3] ? parseInt(monthDay[3], 10) : now.getUTCFullYear();
    let end = new Date(Date.UTC(year, monthIndex, parseInt(monthDay[2], 10), 23, 59, 59));
    if (!monthDay[3] && end.getTime() < now.getTime() - 86400000) {
        year += 1;
        end = new Date(Date.UTC(year, monthIndex, parseInt(monthDay[2], 10), 23, 59, 59));
    }
    return Number.isNaN(end.getTime()) ? null : end.toISOString();
}

function extractYear(desc = '') {
    const m = desc.match(/\b(19[89]\d|20[0-3]\d)\b/);
    return m ? parseInt(m[1], 10) : null;
}

function extractMake(desc = '') {
    const lower = desc.toLowerCase();
    for (const make of MAKES) {
        if (new RegExp(`\\b${make.replace(/\s+/g,'\\s+')}\\b`, 'i').test(lower)) {
            if (make === 'chevy') return 'Chevrolet';
            if (make === 'vw')    return 'Volkswagen';
            return make.replace(/\b\w/g, c => c.toUpperCase());
        }
    }
    return null;
}

function extractModel(desc = '', make = '') {
    if (!make) return null;
    const m = desc.match(new RegExp(`\\b${make}\\b(.+)`, 'i'));
    if (!m) return null;
    const after = m[1].replace(/^[\s\-:]+/, '').trim();
    const model = after.match(/^([A-Za-z0-9][A-Za-z0-9\-]*(?:\s+[A-Za-z0-9][A-Za-z0-9\-]*){0,2})/);
    return model ? model[1].trim() : null;
}

function isVehicle(desc = '') {
    // l2=USA already filters to US at source — no flagPath check needed
    const lower = desc.toLowerCase();
    if (CONDITION_REJECT_PATTERNS.some((pattern) => pattern.test(lower))) return false;
    if (NON_VEHICLE_PART_PATTERNS.some((pattern) => pattern.test(lower))) return false;
    if (COMMERCIAL_PATTERN.test(desc)) return false; // skip heavy equipment
    return true;
}

// DC location fix — "Dist. of Columbia" doesn't match standard state names
const DC_PATTERN = /dist.*columbia|washington.*d\.?c\.?/i;

function isMileageOverLimit(mileage, maxMileage) {
    return mileage !== null && mileage !== undefined && maxMileage > 0 && mileage > maxMileage;
}

function isAgeOverLimit(year, maxAgeYears, now = new Date()) {
    if (!year || maxAgeYears <= 0) return false;
    return (now.getFullYear() - year) > maxAgeYears;
}

function isMilesPerYearOverLimit(year, mileage, maxMilesPerYear = 18000, now = new Date()) {
    if (!year || mileage === null || mileage === undefined || mileage <= 0) return false;
    const ageYears = Math.max(1, now.getFullYear() - Number(year));
    return mileage / ageYears > maxMilesPerYear;
}

function isGovPlanetMarketplace(item = {}) {
    return String(item.marketplace || '').toUpperCase() === 'G';
}

function passesFilters({ year, price, state, locationText = '', mileage = null, maxMileage = 100000, maxAgeYears = 10 }) {
    // Accept DC regardless of state extraction
    const isDC = DC_PATTERN.test(locationText);
    if (!isDC && (!state || !US_STATES.has(state))) return false;
    const currentYear = new Date().getFullYear();
    if (!year || isAgeOverLimit(year, maxAgeYears)) return false;
    if (isMileageOverLimit(mileage, maxMileage)) return false;
    if (isMilesPerYearOverLimit(year, mileage)) return false;
    if (year && year < 1970) return false;
    // Rust-state: bypass for <=2yr old vehicles in high-rust states
    if (state && HIGH_RUST.has(state)) {
        if (!(year && year >= currentYear - 2)) return false;
    }
    if (price > 0 && price > 55000) return false;
    return true;
}

// ── Parse quickviews from a page ──────────────────────────────────────────────

function parseQuickviews(html) {
    const results = [];
    const pattern = /quickviews\.push\((\{.+?\})\);/gs;
    let m;
    while ((m = pattern.exec(html)) !== null) {
        try {
            const item = JSON.parse(m[1]);
            results.push(item);
        } catch (_) {
            // skip malformed
        }
    }
    return results;
}

// ── Actor ─────────────────────────────────────────────────────────────────────

await Actor.init();

const input = await Actor.getInput() ?? {};
const {
    maxItemsPerCategory = 500,   // safety cap per category (override to 0 for unlimited)
    minBid = 200,
    maxBid = 40000,
    maxMileage = 100000,
    maxAgeYears = 10,
    maxDetailPages = 120,
    searchQuery = '',
    webhookUrl = null,
    webhookSecret = null,
} = input;

// If searchQuery is set, replace category URLs with a single keyword search URL
const startUrls = searchQuery
    ? [{ url: `${BASE}/for-sale?q=${encodeURIComponent(searchQuery)}&ct=3&l2=USA`, label: 'search_results' }]
    : CATEGORY_URLS;

let totalPushed = 0;
let totalSkipped = 0;
let totalDetailQueued = 0;
let totalDetailAttempted = 0;
let totalDetailVinFound = 0;
let totalDetailMissingVin = 0;
let totalDetailFetched = 0;
let totalDetailFailed = 0;
let totalDetailCaptcha = 0;
let totalFound = 0;
let totalPassed = 0;
let totalQuickviewsWithVin = 0;
let totalQuickviewsWithMileage = 0;
let totalQuickviewsWithAuctionEnd = 0;
let totalPushedWithVin = 0;
let totalPushedWithMileage = 0;
let totalPushedWithAuctionEnd = 0;
let totalMissingVinWithoutDetail = 0;
let totalMileageOverLimit = 0;
let totalAgeOverLimit = 0;
let totalNonGovPlanetMarketplace = 0;
const excludedMissingVinSamples = [];
const detailCaptchaSamples = [];
const seenEquipIds = new Set();
const pendingPages  = new Map(); // categoryLabel → Set of pstart values already queued

const queue = await RequestQueue.open();

// Seed initial pages
if (searchQuery) {
    console.log(`[GOVPLANET] Keyword search: "${searchQuery}"`);
}

for (const cat of startUrls) {
    await queue.addRequest({
        url: cat.url,
        uniqueKey: `${cat.label}:pstart=0`,
        userData: { label: cat.label, baseUrl: cat.url, pstart: 0 },
    });
}

const crawler = new CheerioCrawler({
    requestQueue: queue,
    maxConcurrency: 3,
    requestHandlerTimeoutSecs: 60,
    maxRequestRetries: 2,
    additionalMimeTypes: ['text/html'],

    async requestHandler({ request, body, log }) {
        const { label, baseUrl, pstart } = request.userData;
        const html = typeof body === 'string' ? body : body.toString('utf-8');

        if (request.userData?.kind === 'detail') {
            const vehicle = request.userData.vehicle;
            totalDetailAttempted++;
            totalDetailFetched++;
            const isCaptcha = /Human Verification|captcha-container|AwsWafIntegration|x-amzn-waf-action/i.test(html);
            if (isCaptcha) {
                totalDetailCaptcha++;
                if (detailCaptchaSamples.length < 10) {
                    detailCaptchaSamples.push({
                        title: vehicle.title,
                        listing_url: vehicle.listing_url,
                        equip_id: vehicle.equip_id,
                    });
                }
            }
            const detailVin = parseDetailVin(html);
            if (!detailVin) {
                totalDetailMissingVin++;
                totalSkipped++;
                if (excludedMissingVinSamples.length < 10) {
                    excludedMissingVinSamples.push({
                        title: vehicle.title,
                        listing_url: vehicle.listing_url,
                        mileage: vehicle.mileage,
                        auction_end_time: vehicle.auction_end_time,
                        detail_attempted: true,
                        detail_captcha: isCaptcha,
                    });
                }
                log.info(`[${label}] Skipped missing_vin_after_detail: ${vehicle.title} (${vehicle.equip_id})`);
                return;
            }
            const enriched = {
                ...vehicle,
                vin: detailVin,
                detail_enriched_by_detail_page: true,
            };
            await Actor.pushData(enriched);
            totalPushed++;
            totalPushedWithVin++;
            if (enriched.mileage) totalPushedWithMileage++;
            if (enriched.auction_end_time) totalPushedWithAuctionEnd++;
            totalDetailVinFound++;
            log.info(`[${label}] Detail enriched VIN for ${vehicle.title} (${vehicle.equip_id})`);
            return;
        }

        // ── Parse total items ──
        const totalMatch = html.match(/sr_total_results.*?value="(\d+)"/);
        const total = totalMatch ? parseInt(totalMatch[1], 10) : 0;

        // ── Extract quickviews ──
        const items = parseQuickviews(html);
        totalFound += items.length;
        log.info(`[${label}] pstart=${pstart} → ${items.length} items (total=${total})`);

        // ── Process items ──
        const records = [];
        for (const item of items) {
            const equipId = String(item.equipId || '');
            if (!equipId || seenEquipIds.has(equipId)) continue;
            seenEquipIds.add(equipId);

            if (!isGovPlanetMarketplace(item)) {
                totalSkipped++;
                totalNonGovPlanetMarketplace++;
                continue;
            }

            const desc     = (item.description || '').trim();
            const flagPath = (item.flagPath || '');
            const price    = parsePrice(item.convPrice || '');
            const state    = extractState(item.eumeLocation || '');
            const year     = extractYear(desc);
            const make     = extractMake(desc);
            const model    = extractModel(desc, make || '');
            const mileage  = parseMileage(item.usage || '');
            const auctionEndTime = parseAuctionEnd(item.timeLeft || '');
            const listingUrl = item.itemPageUri
                ? `${BASE}${item.itemPageUri.split('?')[0]}`
                : null;
            const vin = extractVin(item.vin || item.vehicleVin || item.vinNumber || item.title || '');
            if (vin) totalQuickviewsWithVin++;
            if (mileage) totalQuickviewsWithMileage++;
            if (auctionEndTime) totalQuickviewsWithAuctionEnd++;

            if (!isVehicle(desc)) { totalSkipped++; continue; }
            if (isMileageOverLimit(mileage, maxMileage) || isMilesPerYearOverLimit(year, mileage)) {
                totalSkipped++;
                totalMileageOverLimit++;
                continue;
            }
            if (isAgeOverLimit(year, maxAgeYears)) {
                totalSkipped++;
                totalAgeOverLimit++;
                continue;
            }
            if (!passesFilters({ year, price, state, locationText: item.eumeLocation || '', mileage, maxMileage, maxAgeYears })) { totalSkipped++; continue; }
            if (price < minBid || (maxBid > 0 && price > maxBid)) { totalSkipped++; continue; }
            totalPassed++;

            const vehicle = {
                title:            desc,
                year,
                make,
                model,
                current_bid:      price,
                state,
                city:             (item.eumeLocation || '').split(',')[0].trim() || null,
                mileage,
                auction_end_time: auctionEndTime,
                listing_url:      listingUrl,
                photo_url:        item.photo || item.photoThumb || null,
                vin,
                source_site:      SOURCE,
                equip_id:         equipId,
                scraped_at:       new Date().toISOString(),
            };

            if (!vin) {
                if (listingUrl && totalDetailQueued < maxDetailPages) {
                    totalDetailQueued++;
                    await queue.addRequest({
                        url: listingUrl,
                        uniqueKey: `detail:${equipId}`,
                        userData: { kind: 'detail', label, vehicle },
                    });
                    continue;
                }
                totalSkipped++;
                totalMissingVinWithoutDetail++;
                if (excludedMissingVinSamples.length < 10) {
                    excludedMissingVinSamples.push({
                        title: desc,
                        listing_url: listingUrl,
                        mileage,
                        auction_end_time: auctionEndTime,
                        detail_attempted: false,
                        detail_captcha: false,
                    });
                }
                log.info(`[${label}] Skipped missing_vin_without_detail: ${desc} (${equipId})`);
                continue;
            }

            records.push(vehicle);
        }

        if (records.length > 0) {
            await Actor.pushData(records);
            totalPushed += records.length;
            totalPushedWithVin += records.filter(record => Boolean(record.vin)).length;
            totalPushedWithMileage += records.filter(record => Boolean(record.mileage)).length;
            totalPushedWithAuctionEnd += records.filter(record => Boolean(record.auction_end_time)).length;
            log.info(`[${label}] Pushed ${records.length} records (total so far: ${totalPushed})`);
        }

        // ── Enqueue next pages ──
        if (items.length === 0 || total === 0) return;
        if (maxItemsPerCategory > 0 && pstart + 60 >= maxItemsPerCategory) return;

        const nextPstart = pstart + 60;
        if (nextPstart >= total) return;

        const pendingKey = `${label}:pstart=${nextPstart}`;
        const sep = baseUrl.includes('?') ? '&' : '?';
        const nextUrl = `${baseUrl}${sep}pstart=${nextPstart}`;

        await queue.addRequest({
            url: nextUrl,
            uniqueKey: pendingKey,
            userData: { label, baseUrl, pstart: nextPstart },
        });
    },

    failedRequestHandler({ request, log }) {
        if (request.userData?.kind === 'detail') {
            totalDetailFailed++;
        }
        log.error(`Request failed: ${request.url}`);
    },
});

await crawler.run();

console.log(`[GOVPLANET] Done. Pushed: ${totalPushed} | Skipped: ${totalSkipped} | Unique equipIds: ${seenEquipIds.size} | Detail queued: ${totalDetailQueued} | Detail attempted: ${totalDetailAttempted} | Detail VIN found: ${totalDetailVinFound} | Detail missing VIN: ${totalDetailMissingVin}`);

const sourceQualityProof = {
    record_type: 'source_quality_proof',
    source_site: SOURCE,
    generated_at: new Date().toISOString(),
    found_rows_total: totalFound,
    prefilter_passed_rows_total: totalPassed,
    pushed_rows_total: totalPushed,
    pushed_rows_with_vin: totalPushedWithVin,
    pushed_rows_with_mileage: totalPushedWithMileage,
    pushed_rows_with_auction_end: totalPushedWithAuctionEnd,
    pushed_rows_missing_vin: Math.max(0, totalPushed - totalPushedWithVin),
    pushed_rows_missing_mileage: Math.max(0, totalPushed - totalPushedWithMileage),
    pushed_rows_missing_auction_end: Math.max(0, totalPushed - totalPushedWithAuctionEnd),
    quickview_rows_with_vin: totalQuickviewsWithVin,
    quickview_rows_with_mileage: totalQuickviewsWithMileage,
    quickview_rows_with_auction_end: totalQuickviewsWithAuctionEnd,
    rows_excluded_missing_vin: totalDetailMissingVin + totalMissingVinWithoutDetail,
    rows_excluded_mileage_over_limit: totalMileageOverLimit,
    rows_excluded_age_over_limit: totalAgeOverLimit,
    rows_excluded_non_govplanet_marketplace: totalNonGovPlanetMarketplace,
    detail_pages_queued: totalDetailQueued,
    detail_pages_attempted: totalDetailAttempted,
    detail_pages_fetched: totalDetailFetched,
    detail_pages_failed: totalDetailFailed,
    detail_pages_captcha: totalDetailCaptcha,
    detail_vins_found: totalDetailVinFound,
    detail_missing_vin: totalDetailMissingVin,
    excluded_missing_vin_samples: excludedMissingVinSamples,
    detail_captcha_samples: detailCaptchaSamples,
    target_contract: {
        maxItemsPerCategory,
        minBid,
        maxBid,
        maxMileage,
        maxAgeYears,
        maxDetailPages,
        searchQuery,
    },
};
await Actor.pushData(sourceQualityProof);
console.log(`[SOURCE QUALITY PROOF] ${JSON.stringify(sourceQualityProof)}`);

// ── Webhook notification ──────────────────────────────────────────────────────
if (webhookUrl && totalPushed > 0) {
    try {
        const runInfo = Actor.getEnv();
        const res = await fetch(webhookUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...(webhookSecret ? { 'x-apify-webhook-secret': webhookSecret } : {}),
            },
            body: JSON.stringify({
                source: SOURCE,
                actorRunId: runInfo.actorRunId,
                datasetId:  runInfo.defaultDatasetId,
                itemCount:  totalPushed,
                skipped:    totalSkipped,
            }),
        });
        console.log(`[GOVPLANET] Webhook → ${res.status}`);
    } catch (err) {
        console.warn(`[GOVPLANET] Webhook failed: ${err.message}`);
    }
}

await Actor.exit();
