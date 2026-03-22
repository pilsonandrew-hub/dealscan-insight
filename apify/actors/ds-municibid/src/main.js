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
const { minBid = 200, maxBid = 35000 } = (await Actor.getInput()) ?? {};

let found = 0, passed = 0;
const sampleLocations = [];

function recordLocationSample(location = '') {
    const normalized = location.trim();
    if (!normalized || sampleLocations.includes(normalized) || sampleLocations.length >= 5) return;
    sampleLocations.push(normalized);
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
    const COMMERCIAL = /\b(cargo|cutaway|chassis cab|box truck|stake bed|dump|4500|5500|refuse|crane|utility body)\b/i;
    return !COMMERCIAL.test(t);
}

const crawler = new CheerioCrawler({
    maxRequestsPerCrawl: CATEGORY_URLS.length + 5,  // all items on single page, no pagination
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
            const make = parseMake(title);

            // Filters
            if (!year || !make) return;
            if (!isPassengerVehicle(title)) return;
            if (bid < minBid || bid > maxBid) return;
            const currentYear = new Date().getFullYear();
            if (state) {
                if (!US_STATES.has(state)) return;
                if (HIGH_RUST.has(state)) {
                    if (!(year >= currentYear - 8)) return;
                    console.log(`[BYPASS] Rust state ${state} allowed — vehicle is ${year} (≤8yr old)`);
                }
            }
            const age = currentYear - year;
            if (age > 15 || age < 0) return;

            passed++;
            const model = parseModel(title, make);

            batch.push({
                title,
                year,
                make,
                model,
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
        }
    },
});

await crawler.run(CATEGORY_URLS.map(url => ({ url })));
console.log('[MUNICIBID] Sample locations:', sampleLocations);
console.log(`[MUNICIBID] Found: ${found} | Passed: ${passed}`);
await Actor.exit();
