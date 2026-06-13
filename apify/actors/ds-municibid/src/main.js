/**
 * ds-municibid — Municibid Automotive Scraper
 *
 * STATUS: FIXED 2026-03-21 — Selectors updated to match current site structure
 * Municibid has zero bot protection on /Browse/C160883/Automotive
 * Cards use: [data-listingid] containers with:
 *   .card-title a  → title + href
 *   .card-subtitle → "City, STATE | Agency Name"
 *   .NumberPart    → price digits
 *   img.card-img-top → photo
 * No pagination — all items load on single page.
 *
 * Categories scraped:
 *   C169048 = Cars, C11965711 = SUV, C169052 = Trucks, C169053 = Vans
 */

import { Actor } from 'apify';
import { CheerioCrawler } from 'crawlee';

const SOURCE = 'municibid';
// NOTE: www.municibid.com 301-redirects to municibid.com (no-www).
// CheerioCrawler must follow the redirect — use non-www base URL.
const BASE = 'https://municibid.com';
const STANDARD_MAX_MODEL_AGE_YEARS = 10;
const STANDARD_MAX_MILEAGE = 100000;
const STANDARD_MAX_MILES_PER_YEAR = 18000;
const PREMIUM_MAX_MODEL_AGE_YEARS = 4;
const PREMIUM_MAX_MILEAGE = 50000;

// Passenger vehicle categories only (no buses, motorcycles, heavy trucks)
const CATEGORY_URLS = [
    `${BASE}/Browse/C160883-C169048/Automotive-Cars`,
    `${BASE}/Browse/C160883-C11965711/Automotive-SUV`,
    `${BASE}/Browse/C160883-C169052/Automotive-Trucks`,
];

const HIGH_RUST = new Set([
    'OH','MI','PA','NY','WI','MN','IL','IN','MO','IA','ND','SD','NE','KS','WV',
    'ME','NH','VT','MA','RI','CT','NJ','MD','DE',
]);
const TARGET = new Set([
    'AZ','CA','NV','CO','NM','UT','TX','FL','GA','SC','TN','NC','VA','WA','OR','HI',
]);

function failsDealerScopeAgeMileageGate(year, mileage, currentYear = new Date().getFullYear()) {
    if (!year) return false;
    const age = currentYear - year;
    if (age > STANDARD_MAX_MODEL_AGE_YEARS || age < 0) return true;
    if (mileage === null || mileage === undefined || mileage <= 0) return false;
    if (mileage > STANDARD_MAX_MILEAGE) return true;
    const ageYears = Math.max(1, age);
    // Premium lane (<= PREMIUM_MAX_MODEL_AGE_YEARS old AND <= PREMIUM_MAX_MILEAGE) is exempt from
    // the standard-lane miles/year cap, mirroring backend determine_vehicle_tier. Without this,
    // late-model high-mileage fleet vehicles are silently dropped before scoring.
    if (age <= PREMIUM_MAX_MODEL_AGE_YEARS && mileage <= PREMIUM_MAX_MILEAGE) return false;
    return mileage / ageYears > STANDARD_MAX_MILES_PER_YEAR;
}
const US_STATES = new Set([
    'AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA','HI','ID','IL','IN','IA',
    'KS','KY','LA','ME','MD','MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ',
    'NM','NY','NC','ND','OH','OK','OR','PA','RI','SC','SD','TN','TX','UT','VT',
    'VA','WA','WV','WI','WY','DC',
]);
const STATE_NAMES = new Map([
    ['ALABAMA', 'AL'], ['ALASKA', 'AK'], ['ARIZONA', 'AZ'], ['ARKANSAS', 'AR'],
    ['CALIFORNIA', 'CA'], ['COLORADO', 'CO'], ['CONNECTICUT', 'CT'], ['DELAWARE', 'DE'],
    ['FLORIDA', 'FL'], ['GEORGIA', 'GA'], ['HAWAII', 'HI'], ['IDAHO', 'ID'],
    ['ILLINOIS', 'IL'], ['INDIANA', 'IN'], ['IOWA', 'IA'], ['KANSAS', 'KS'],
    ['KENTUCKY', 'KY'], ['LOUISIANA', 'LA'], ['MAINE', 'ME'], ['MARYLAND', 'MD'],
    ['MASSACHUSETTS', 'MA'], ['MICHIGAN', 'MI'], ['MINNESOTA', 'MN'], ['MISSISSIPPI', 'MS'],
    ['MISSOURI', 'MO'], ['MONTANA', 'MT'], ['NEBRASKA', 'NE'], ['NEVADA', 'NV'],
    ['NEW HAMPSHIRE', 'NH'], ['NEW JERSEY', 'NJ'], ['NEW MEXICO', 'NM'], ['NEW YORK', 'NY'],
    ['NORTH CAROLINA', 'NC'], ['NORTH DAKOTA', 'ND'], ['OHIO', 'OH'], ['OKLAHOMA', 'OK'],
    ['OREGON', 'OR'], ['PENNSYLVANIA', 'PA'], ['RHODE ISLAND', 'RI'], ['SOUTH CAROLINA', 'SC'],
    ['SOUTH DAKOTA', 'SD'], ['TENNESSEE', 'TN'], ['TEXAS', 'TX'], ['UTAH', 'UT'],
    ['VERMONT', 'VT'], ['VIRGINIA', 'VA'], ['WASHINGTON', 'WA'], ['WEST VIRGINIA', 'WV'],
    ['WISCONSIN', 'WI'], ['WYOMING', 'WY'], ['DISTRICT OF COLUMBIA', 'DC'],
]);
const MAKES = [
    'ford','chevrolet','chevy','dodge','ram','toyota','honda','nissan','jeep','gmc',
    'chrysler','hyundai','kia','subaru','mazda','volkswagen','bmw','mercedes','audi',
    'lexus','acura','infiniti','cadillac','lincoln','buick','pontiac','mitsubishi',
    'volvo','tesla','saturn','isuzu','hummer',
];

await Actor.init();
const { minBid = 200, maxBid = 35000, searchQuery = "" } = (await Actor.getInput()) ?? {};

// When searchQuery is set, append ?q= to each category URL for server-side keyword filtering.
// Post-filter on title as a safety net (MuniciBid may ignore unknown params).
const urls = CATEGORY_URLS.map(url =>
    searchQuery ? `${url}?q=${encodeURIComponent(searchQuery)}` : url
);

let found = 0, passed = 0;
let pushed = 0;
const sampleLocations = [];
const proofCounters = {
    rows_excluded_missing_required_data: 0,
    rows_excluded_age_mileage_prefilter: 0,
    rows_excluded_policy_prefilter: 0,
    rows_excluded_non_vehicle: 0,
    rows_excluded_bid_range: 0,
    rows_excluded_rust_state: 0,
    rows_excluded_search_filter: 0,
};
const proofSamples = {
    missing_required_data: [],
    age_mileage_prefilter: [],
    policy_prefilter: [],
};

function recordLocationSample(location = '') {
    const normalized = location.trim();
    if (!normalized || sampleLocations.includes(normalized) || sampleLocations.length >= 5) return;
    sampleLocations.push(normalized);
}

function addProofSample(bucket, item) {
    const samples = proofSamples[bucket];
    if (!samples || samples.length >= 5) return;
    samples.push({
        title: String(item.title || '').slice(0, 120),
        year: item.year ?? null,
        mileage: item.mileage ?? null,
        state: item.state || null,
        bid: item.bid ?? null,
        listing_url: item.listing_url || null,
        reason: item.reason || null,
    });
}

function parseState(location = '') {
    const normalized = location.replace(/\s+/g, ' ').trim();
    if (!normalized) return '';

    const m = normalized.match(/,\s*([A-Z]{2})(?:\s+\d{5}(?:-\d{4})?)?\s*$/i) ||
              normalized.match(/\b([A-Z]{2})\b\s*\d{5}(?:-\d{4})?/i) ||
              normalized.match(/\b([A-Z]{2})\s*$/i);
    const abbreviation = m ? m[1].toUpperCase() : '';
    if (US_STATES.has(abbreviation)) return abbreviation;

    const upper = normalized.toUpperCase();
    for (const [stateName, stateCode] of STATE_NAMES) {
        const pattern = new RegExp(`(?:,|\\b)\\s*${stateName}(?:\\s+\\d{5}(?:-\\d{4})?)?\\s*$`, 'i');
        if (pattern.test(upper)) return stateCode;
    }

    return '';
}

function parseYear(title = '') {
    const m = title.match(/\b(19[89]\d|20[012]\d)\b/);
    return m ? parseInt(m[1]) : null;
}

function parseMileage(text = '') {
    const m = String(text).replace(/,/g, '').match(/\b(\d{1,3}(?:\d{3})+|\d+)\s*(?:miles?|mi\.?)\b/i);
    return m ? parseInt(m[1], 10) : null;
}

function parseMake(title = '') {
    const lower = title.toLowerCase();
    const found = MAKES.find(mk => new RegExp(`\\b${mk}\\b`).test(lower));
    if (!found) return null;
    const canonical = { 'chevy': 'Chevrolet' };
    return canonical[found] || (found.charAt(0).toUpperCase() + found.slice(1));
}

function parseModel(title = '', make = '') {
    if (!make) return null;
    const lower = title.toLowerCase();
    const idx = lower.indexOf(make.toLowerCase());
    if (idx === -1) return null;
    const after = title.slice(idx + make.length).trim();
    // Strip leading year if present
    const clean = after.replace(/^(19|20)\d{2}\s+/, '');
    // Take first 1-2 words, strip trailing colors
    const COLORS = /\b(black|white|silver|gray|grey|red|blue|green|yellow|orange|brown|beige|tan|gold|maroon|charcoal|navy|cream|burgundy)\b.*/i;
    const m = clean.match(/^([A-Za-z0-9][-A-Za-z0-9]*(?:\s+[A-Za-z0-9][-A-Za-z0-9]*)?)/);
    return m ? m[1].replace(COLORS, '').trim() : null;
}

function isPassengerVehicle(title = '') {
    const t = title.toLowerCase();
    const COMMERCIAL = /\b(cargo|cutaway|chassis cab|box truck|stake bed|dump|4500|5500|refuse|crane|utility body|service body|truck bed|pickup bed|camper shell|tonneau|bed cap|truck cap|truck topper|vehicle parts)\b/i;
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
    if (NON_VEHICLE_PART_PATTERNS.some((pattern) => pattern.test(t))) return false;
    return !COMMERCIAL.test(t);
}

const crawler = new CheerioCrawler({
    maxRequestsPerCrawl: urls.length + 5,  // all items on single page, no pagination
    requestHandlerTimeoutSecs: 30,
    async requestHandler({ $, request, log }) {
        const url = request.url;

        // Municibid uses [data-listingid] containers for each listing.
        // Structure (as of 2026-03-21):
        //   .card-title a        → title text + href="/Listing/Details/{id}/..."
        //   .card-subtitle       → "City , STATE | Agency Name"
        //   .NumberPart          → price digits (e.g. "1,000.00")
        //   img.card-img-top     → photo src
        // All listings load on a single page — no pagination.
        const cards = $('[data-listingid]');
        log.info(`${url} → ${cards.length} listings`);

        if (!cards.length) {
            log.warning(`No [data-listingid] cards found on: ${url}`);
            // Debug: dump first 500 chars of body
            log.warning(`Body preview: ${$('body').text().slice(0, 500)}`);
            return;
        }

        const batch = [];
        cards.each((_, el) => {
            // Use the mobile card (.d-md-none) which is always rendered server-side.
            // If both mobile and desktop variants exist, jQuery will pick the first.
            const titleEl = $(el).find('.card-title a').first();
            const title = titleEl.text().trim();
            const relHref = titleEl.attr('href') || '';
            const listingUrl = relHref ? `${BASE}${relHref}` : '';

            // Location: "Pelham , NY | Village of Pelham Department of Public Works"
            const locationRaw = $(el).find('.card-subtitle').first().text().trim();
            // Normalize double spaces around comma
            const location = locationRaw.replace(/\s*,\s*/g, ', ').replace(/\s+\|\s+.*$/, '').trim();

            recordLocationSample(location);

            // Price: first .NumberPart inside this card
            const priceText = $(el).find('.NumberPart').first().text().replace(/[^0-9.]/g, '');
            const bid = parseFloat(priceText) || 0;

            // Photo
            const photoUrl = $(el).find('img').first().attr('src') || null;

            found++;

            const state = parseState(location);
            const year = parseYear(title);
            const mileage = parseMileage(title);
            const make = parseMake(title);
            const lower = title.toLowerCase();
            const conditionRejectPatterns = [
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

            // Keyword post-filter: if searchQuery is set, title must contain it
            if (searchQuery && !title.toLowerCase().includes(searchQuery.toLowerCase())) {
                proofCounters.rows_excluded_search_filter++;
                return;
            }

            // Filters
            if (!year || !make) {
                proofCounters.rows_excluded_missing_required_data++;
                addProofSample('missing_required_data', { title, year, mileage, state, bid, listing_url: listingUrl, reason: 'missing_year_or_make' });
                return;
            }
            if (conditionRejectPatterns.some((pattern) => pattern.test(lower))) {
                proofCounters.rows_excluded_policy_prefilter++;
                addProofSample('policy_prefilter', { title, year, mileage, state, bid, listing_url: listingUrl, reason: 'condition_reject_pattern' });
                return;
            }
            if (failsDealerScopeAgeMileageGate(year, mileage)) {
                proofCounters.rows_excluded_age_mileage_prefilter++;
                addProofSample('age_mileage_prefilter', { title, year, mileage, state, bid, listing_url: listingUrl, reason: 'age_or_mileage_exceeded' });
                return;
            }
            if (!isPassengerVehicle(title)) {
                proofCounters.rows_excluded_non_vehicle++;
                return;
            }
            if (bid < minBid || bid > maxBid) {
                proofCounters.rows_excluded_bid_range++;
                return;
            }
            const currentYear = new Date().getFullYear();
            if (state) {
                if (!US_STATES.has(state)) {
                    proofCounters.rows_excluded_missing_required_data++;
                    addProofSample('missing_required_data', { title, year, mileage, state, bid, listing_url: listingUrl, reason: 'unknown_state' });
                    return;
                }
                if (HIGH_RUST.has(state)) {
                    if (!(year >= currentYear - 2)) {
                        proofCounters.rows_excluded_rust_state++;
                        return;
                    }
                    console.log(`[BYPASS] Rust state ${state} allowed — vehicle is ${year} (≤2yr old)`);
                }
            }
            passed++;
            const model = parseModel(title, make);

            batch.push({
                title,
                year,
                make,
                model,
                mileage,
                current_bid: bid,
                state,
                location,
                listing_url: listingUrl,
                photo_url: photoUrl,
                source_site: SOURCE,
                scraped_at: new Date().toISOString(),
            });
        });

        if (batch.length > 0) {
            await Actor.pushData(batch);
            pushed += batch.length;
        }
    },
});

if (searchQuery) console.log(`[MUNICIBID] Keyword search: "${searchQuery}"`);
await crawler.run(urls.map(url => ({ url })));
console.log('[MUNICIBID] Sample locations:', sampleLocations);
console.log(`[MUNICIBID] Found: ${found} | Passed: ${passed}`);
const proof = {
    record_type: 'source_quality_proof',
    source_site: SOURCE,
    scraped_at: new Date().toISOString(),
    found_rows_total: found,
    prefilter_passed_rows_total: passed,
    pushed_rows_total: pushed,
    ...proofCounters,
    sample_locations: sampleLocations,
    missing_required_data_samples: proofSamples.missing_required_data,
    prefilter_age_mileage_rejected_samples: proofSamples.age_mileage_prefilter,
    prefilter_policy_rejected_samples: proofSamples.policy_prefilter,
};
await Actor.pushData(proof);
await Actor.exit();
