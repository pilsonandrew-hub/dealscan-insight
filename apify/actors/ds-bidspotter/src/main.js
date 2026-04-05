/**
 * ds-bidspotter v4.0 — Firecrawl API actor (no Playwright)
 *
 * Firecrawl bypasses BidSpotter's AWS WAF/Cloudflare completely.
 * Pure Node.js HTTP actor — no browser, no crawlee.
 *
 * Flow:
 * 1. For each categoryCode, fetch catalogue list via Firecrawl
 * 2. Parse markdown for catalogue-id URLs, deduplicate
 * 3. For each catalogue, fetch via Firecrawl with 4s wait, parse lots from markdown
 * 4. Filter + push to dataset
 * 5. Send webhook
 */

import { Actor } from 'apify';

const SOURCE = 'bidspotter';
const CURRENT_YEAR = new Date().getFullYear();

// ── State sets ──────────────────────────────────────────────────────────────

const TARGET_STATES = new Set([
    'AZ', 'CA', 'NV', 'CO', 'NM', 'UT', 'TX', 'FL', 'GA', 'SC', 'TN', 'NC', 'VA', 'WA', 'OR', 'HI',
    'ID', 'MT', 'WY', 'ND', 'SD', 'NE', 'KS', 'AL', 'LA', 'OK',
]);

const HIGH_RUST_STATES = new Set([
    'OH', 'MI', 'PA', 'NY', 'WI', 'MN', 'IL', 'IN', 'MO', 'IA',
    'ND', 'SD', 'NE', 'KS', 'WV', 'ME', 'NH', 'VT', 'MA', 'RI',
    'CT', 'NJ', 'MD', 'DE',
]);

const CANADIAN_PROVINCES = new Set([
    'AB', 'BC', 'ON', 'QC', 'MB', 'SK', 'NS', 'NB', 'PE', 'NL', 'YT', 'NT', 'NU',
]);

const ALL_US_STATES = new Set([
    'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA', 'HI', 'ID', 'IL', 'IN', 'IA',
    'KS', 'KY', 'LA', 'ME', 'MD', 'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
    'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC', 'SD', 'TN', 'TX', 'UT', 'VT',
    'VA', 'WA', 'WV', 'WI', 'WY', 'DC',
]);

const CITY_TO_STATE = {
    'odessa': 'TX', 'dallas': 'TX', 'houston': 'TX', 'austin': 'TX', 'san antonio': 'TX',
    'fort worth': 'TX', 'el paso': 'TX', 'arlington': 'TX', 'corpus christi': 'TX',
    'lubbock': 'TX', 'plano': 'TX', 'laredo': 'TX', 'irving': 'TX', 'garland': 'TX',
    'tampa': 'FL', 'miami': 'FL', 'orlando': 'FL', 'jacksonville': 'FL', 'fort lauderdale': 'FL',
    'tallahassee': 'FL', 'st. petersburg': 'FL', 'hialeah': 'FL', 'panama city': 'FL',
    'pensacola': 'FL', 'gainesville': 'FL', 'clearwater': 'FL', 'cape coral': 'FL',
    'atlanta': 'GA', 'savannah': 'GA', 'augusta': 'GA', 'macon': 'GA', 'columbus': 'GA',
    'charleston': 'SC', 'columbia': 'SC', 'greenville': 'SC', 'ladson': 'SC', 'spartanburg': 'SC',
    'charlotte': 'NC', 'raleigh': 'NC', 'greensboro': 'NC', 'durham': 'NC', 'winston-salem': 'NC',
    'nashville': 'TN', 'memphis': 'TN', 'knoxville': 'TN', 'chattanooga': 'TN',
    'richmond': 'VA', 'virginia beach': 'VA', 'norfolk': 'VA', 'chesapeake': 'VA',
    'los angeles': 'CA', 'san francisco': 'CA', 'san diego': 'CA', 'sacramento': 'CA',
    'fresno': 'CA', 'long beach': 'CA', 'oakland': 'CA', 'bakersfield': 'CA',
    'anaheim': 'CA', 'santa ana': 'CA', 'riverside': 'CA', 'stockton': 'CA',
    'las vegas': 'NV', 'henderson': 'NV', 'reno': 'NV', 'north las vegas': 'NV',
    'phoenix': 'AZ', 'tucson': 'AZ', 'mesa': 'AZ', 'chandler': 'AZ', 'scottsdale': 'AZ',
    'tempe': 'AZ', 'gilbert': 'AZ', 'glendale': 'AZ', 'peoria': 'AZ',
    'seattle': 'WA', 'spokane': 'WA', 'tacoma': 'WA', 'bellevue': 'WA', 'kent': 'WA',
    'portland': 'OR', 'salem': 'OR', 'eugene': 'OR', 'gresham': 'OR',
    'denver': 'CO', 'colorado springs': 'CO', 'aurora': 'CO', 'fort collins': 'CO',
    'albuquerque': 'NM', 'santa fe': 'NM', 'las cruces': 'NM',
    'birmingham': 'AL', 'montgomery': 'AL', 'huntsville': 'AL', 'mobile': 'AL',
    'new orleans': 'LA', 'baton rouge': 'LA', 'shreveport': 'LA', 'lafayette': 'LA',
    'oklahoma city': 'OK', 'tulsa': 'OK', 'norman': 'OK', 'broken arrow': 'OK',
    'wichita': 'KS', 'overland park': 'KS', 'kansas city': 'KS',
    'omaha': 'NE', 'lincoln': 'NE',
    'sioux falls': 'SD', 'rapid city': 'SD',
    'salt lake city': 'UT', 'provo': 'UT', 'west valley city': 'UT',
    'boise': 'ID', 'nampa': 'ID', 'meridian': 'ID',
    'honolulu': 'HI',
    'washington': 'DC', 'washington, d.c.': 'DC',
    'swedesboro': 'NJ',
};

// ── Vehicle parsing ─────────────────────────────────────────────────────────

const VEHICLE_MAKES = [
    'ford', 'chevrolet', 'chevy', 'dodge', 'ram', 'toyota', 'honda', 'nissan', 'jeep', 'gmc',
    'chrysler', 'hyundai', 'kia', 'subaru', 'mazda', 'volkswagen', 'vw', 'bmw', 'mercedes',
    'audi', 'lexus', 'acura', 'infiniti', 'cadillac', 'lincoln', 'buick', 'pontiac',
    'mitsubishi', 'volvo', 'tesla', 'mini', 'saturn', 'scion', 'land rover', 'jaguar',
    'porsche', 'maserati', 'alfa romeo', 'fiat', 'genesis', 'rivian', 'lucid',
    'international', 'kenworth', 'peterbilt', 'mack', 'freightliner', 'western star', 'sterling',
];

const CONDITION_REJECT_PATTERNS = [
    /\bsalvage\b/i, /\bflood\b/i, /\bframe[\s-]+damage\b/i, /\bcrash(?:ed)?\b/i,
    /\bcollision[\s-]+damage\b/i, /\bfire[\s-]+damage\b/i, /\bhail[\s-]+damage\b/i,
    /\bwon'?t\s+start\b/i, /\bdoes\s+not\s+start\b/i, /\bno[\s-]start\b/i,
    /\binop(?:erable)?\b/i, /\bparts[\s-]+only\b/i, /\bfor\s+parts\b/i,
    /\bproject\s+(?:car|vehicle|truck)\b/i, /\brebuilt\s+title\b/i,
    /\bstructural[\s-]+damage\b/i, /\bblown\s+engine\b/i, /\bbad\s+engine\b/i, /\bno\s+title\b/i,
    /engine\s+(?:block|only|assembly)/i,
];

const EXCLUDED_PATTERN = /\b(forklift|tractor(?!\s+truck)|loader|backhoe|excavator|grader|dozer|bulldozer|skid\s*steer|trencher|mower|generator|compressor|sprayer|sweeper|boat|marine|camper|rv|motorhome|jet\s*ski|snowmobile|motorcycle|atv|utv|golf\s*cart|ambulance|fire\s*truck|box\s*truck|cargo\s+van|step\s+van|cutaway|chassis\s+cab|semitrailer|furniture|desk|chair|cabinet|computer|electronics|industrial|scissor\s*lift|telehandler|dumper|combine|harvester|baler|aircraft|airplane|engine\s+block|engine\s+only|transmission\s+only)\b/i;

const VEHICLE_KEYWORDS = [
    'sedan', 'coupe', 'hatchback', 'wagon', 'convertible', 'suv', 'sport utility',
    'crossover', 'pickup', 'crew cab', 'extended cab', 'minivan', 'passenger van',
    '4x4', 'awd', 'fwd', 'rwd', 'passenger car', 'automobile',
    'f-150', 'f-250', 'f-350', 'silverado', 'sierra', 'ranger', 'explorer',
    'expedition', 'tahoe', 'suburban', 'escalade', 'navigator', 'wrangler', 'cherokee',
];

// ── Utility functions ───────────────────────────────────────────────────────

function normalizeText(v) { return String(v ?? '').replace(/\s+/g, ' ').trim(); }

function parseBid(v) {
    if (v == null) return null;
    const m = normalizeText(v).replace(/,/g, '').match(/\$?\s*([\d]+(?:\.\d+)?)/);
    return m ? parseFloat(m[1]) : null;
}

function parseVehicleTitle(title) {
    const normalized = normalizeText(title);
    const lower = normalized.toLowerCase();
    const yearMatch = normalized.match(/\b(19[89]\d|20[0-3]\d)\b/);
    const year = yearMatch ? parseInt(yearMatch[1], 10) : null;
    let make = null, model = null;
    for (const c of VEHICLE_MAKES) {
        const pat = new RegExp(`\\b${c.replace(/\s+/g, '\\s+')}\\b`, 'i');
        const m = normalized.match(pat);
        if (!m) continue;
        make = c === 'chevy' ? 'Chevrolet' : c === 'vw' ? 'Volkswagen'
            : c.replace(/\b\w/g, ch => ch.toUpperCase());
        const after = normalized.slice(m.index + m[0].length)
            .replace(/^[\s\-:]+/, '').replace(/\b(4x4|awd|fwd|rwd|vin|odometer|mileage)\b.*$/i, '').trim();
        const mm = after.match(/^([A-Za-z0-9][A-Za-z0-9\-]*(?:\s+[A-Za-z0-9][A-Za-z0-9\-]*)?)/);
        model = mm ? mm[1] : null;
        break;
    }
    return { year, make, model, lower };
}

function isVehicleLot(title) {
    const { lower } = parseVehicleTitle(title);
    if (!lower) return false;
    if (CONDITION_REJECT_PATTERNS.some(p => p.test(lower))) return false;
    if (EXCLUDED_PATTERN.test(lower)) return false;
    return VEHICLE_MAKES.some(m => lower.includes(m)) || VEHICLE_KEYWORDS.some(k => lower.includes(k));
}

function parseStateFromCity(cityText) {
    if (!cityText) return null;
    const text = normalizeText(cityText);
    const lower = text.toLowerCase();
    const sc = text.match(/,\s*([A-Z]{2})\b/) ?? text.match(/\b([A-Z]{2})\s*(?:\d{5})?\s*$/) ?? text.match(/\s([A-Z]{2})\s*$/);
    if (sc) { const c = sc[1]; if (ALL_US_STATES.has(c) && !CANADIAN_PROVINCES.has(c)) return c; }
    for (const [city, state] of Object.entries(CITY_TO_STATE)) { if (lower.includes(city)) return state; }
    return null;
}

function parseMileage(text) {
    if (!text) return null;
    const m = normalizeText(text).match(/([\d,]+)\s*(?:miles?|mi\b)/i);
    if (!m) return null;
    const v = parseFloat(m[1].replace(/,/g, ''));
    return v > 0 && v < 500000 ? v : null;
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// ── Firecrawl API ───────────────────────────────────────────────────────────

async function firecrawlScrape(apiKey, url, waitMs = 3000) {
    const body = JSON.stringify({
        url,
        formats: ['markdown'],
        actions: [{ type: 'wait', milliseconds: waitMs }],
    });
    const headers = {
        'Authorization': `Bearer ${apiKey}`,
        'Content-Type': 'application/json',
    };

    const res = await fetch('https://api.firecrawl.dev/v1/scrape', {
        method: 'POST', headers, body,
    });

    if (res.status === 429) {
        console.log('[FC] Rate limited (429), waiting 10s...');
        await sleep(10000);
        const retry = await fetch('https://api.firecrawl.dev/v1/scrape', {
            method: 'POST', headers, body,
        });
        if (!retry.ok) { console.warn(`[FC] Retry failed: ${retry.status}`); return null; }
        const data = await retry.json();
        return data.success ? data.data : null;
    }

    if (!res.ok) { console.warn(`[FC] HTTP ${res.status} for ${url}`); return null; }
    const data = await res.json();
    if (!data.success) { console.warn(`[FC] success:false for ${url}`); return null; }
    return data.data;
}

// ── Lot extraction from markdown ────────────────────────────────────────────

function extractLotsFromMarkdown(md) {
    const lots = [];
    const seenUrls = new Set();

    // Primary: ### [TITLE](URL) heading pattern
    const headingPattern = /#{2,4}\s*\[([^\]]+)\]\((https?:\/\/[^)]*\/lot-[^)]+)\)/g;
    let match;
    while ((match = headingPattern.exec(md)) !== null) {
        const title = match[1].trim();
        const url = match[2].replace(/\?.*$/, '');
        if (seenUrls.has(url)) continue;
        seenUrls.add(url);

        const blockStart = match.index + match[0].length;
        const nextHeading = md.indexOf('\n##', blockStart);
        const nextSep = md.indexOf('\n---', blockStart);
        let blockEnd = md.length;
        if (nextHeading > -1 && nextHeading < blockEnd) blockEnd = nextHeading;
        if (nextSep > -1 && nextSep < blockEnd) blockEnd = nextSep;
        const block = md.slice(blockStart, blockEnd);

        lots.push({ title, url, block });
    }

    // Fallback: any markdown link to a /lot- URL
    if (lots.length === 0) {
        const linkPattern = /\[([^\]]+)\]\((https?:\/\/[^)]*\/lot-[^)]+)\)/g;
        while ((match = linkPattern.exec(md)) !== null) {
            const title = match[1].trim();
            if (!title || title.length < 5) continue;
            const url = match[2].replace(/\?.*$/, '');
            if (seenUrls.has(url)) continue;
            seenUrls.add(url);

            const blockStart = match.index + match[0].length;
            const nextLink = md.indexOf('\n[', blockStart);
            const nextHeading = md.indexOf('\n#', blockStart);
            let blockEnd = md.length;
            if (nextLink > -1 && nextLink < blockEnd) blockEnd = nextLink;
            if (nextHeading > -1 && nextHeading < blockEnd) blockEnd = nextHeading;
            const block = md.slice(blockStart, Math.min(blockEnd, blockStart + 1000));

            lots.push({ title, url, block });
        }
    }

    return lots;
}

function parseLotDetails(lot) {
    const { title, url, block } = lot;
    const combined = `${title}\n${block}`;

    // Current bid
    let currentBid = null;
    const bidPatterns = [
        /Current\s+Bid\s*\n?\s*\$?\s*([\d,]+(?:\.\d+)?)/i,
        /Current\s+Bid[^\n$]*?\$\s*([\d,]+(?:\.\d+)?)/i,
        /Opening\s+Bid[^\n$]*?\$\s*([\d,]+(?:\.\d+)?)/i,
    ];
    for (const pat of bidPatterns) {
        const m = block.match(pat);
        if (m) { currentBid = parseFloat(m[1].replace(/,/g, '')); break; }
    }
    if (currentBid == null) {
        const dollarMatch = block.match(/\$\s*([\d,]+(?:\.\d{2})?)/);
        if (dollarMatch) currentBid = parseFloat(dollarMatch[1].replace(/,/g, ''));
    }

    // State / city / location
    let state = null, city = null, location = null;
    const locMatch = combined.match(/([A-Za-z][A-Za-z\s.'-]+),\s*([A-Z]{2})\b/);
    if (locMatch) {
        const possibleState = locMatch[2];
        if (ALL_US_STATES.has(possibleState) && !CANADIAN_PROVINCES.has(possibleState)) {
            state = possibleState;
            city = locMatch[1].trim();
            location = `${city}, ${state}`;
        }
    }
    if (!state) state = parseStateFromCity(block) || parseStateFromCity(title);

    // Mileage
    const mileage = parseMileage(combined);

    // Photo URL — markdown image pattern
    let photoUrl = null;
    const imgMatch = block.match(/!\[[^\]]*\]\((https?:\/\/[^)]+\.(?:jpg|jpeg|png|webp)[^)]*)\)/i);
    if (imgMatch) photoUrl = imgMatch[1];

    // Lot number from URL
    const lotNumMatch = url.match(/\/lot-([^/?#]+)/);
    const lotNumber = lotNumMatch ? lotNumMatch[1] : null;

    // Description — clean markdown artifacts
    const description = block
        .replace(/!\[[^\]]*\]\([^)]*\)/g, '')
        .replace(/\[[^\]]*\]\([^)]*\)/g, '')
        .replace(/[#*_~`|]/g, '')
        .replace(/\s+/g, ' ')
        .trim()
        .slice(0, 500) || null;

    return { currentBid, state, city, location, mileage, photoUrl, lotNumber, description };
}

// ── Main ────────────────────────────────────────────────────────────────────

await Actor.init();

const input = await Actor.getInput() ?? {};
const {
    firecrawlApiKey = process.env.FIRECRAWL_API_KEY,
    webhookUrl = 'https://dealscan-insight-production.up.railway.app/api/ingest/apify',
    webhookSecret = 'rDyApg2UUIMl0a8ZUz_swOqsHX7HbjN-gly3xHNwiyA',
    maxCatalogues = 30,
    categoryCode = 'Automobiles',
} = input;

if (!firecrawlApiKey) {
    console.error('[BS] FIRECRAWL_API_KEY is required (via input or env)');
    await Actor.exit({ exitCode: 1 });
}

const MIN_BID = 500;
const MAX_BID = 75000;
const MIN_YEAR = CURRENT_YEAR - 10;

let totalFound = 0, totalPassed = 0;

// ── STEP 1: Find vehicle catalogues from Automobiles category page ──────────
// Fetch the category page once, parse catalogue links WITH titles, keep only
// catalogues whose title matches whole-vehicle patterns (reject parts/equipment)

const VEHICLE_CATALOGUE_PATTERN = /\b(pickup trucks?|automobiles|sedan|suvs?|crossover|fleet vehicle|cars &|government vehicle|4wd vehicle|commercial vehicle|vans?|coupe|hatchback|station wagon|trucks?)\b/i;
const PARTS_PATTERN = /\bparts\b/i;
const NON_US_SLUGS = new Set(['eamagroup', 'comind', 'lambert-smith-hampton', 'eddisons', 'ncm']);

const categoryUrl = `https://www.bidspotter.com/en-us/auction-catalogues/search-filter?countries=US&categories=${encodeURIComponent(categoryCode)}`;
console.log(`[FC] Fetching category page: ${categoryCode}`);

const catResult = await firecrawlScrape(firecrawlApiKey, categoryUrl, 3000);
if (!catResult?.markdown) {
    console.error('[BS] No markdown from category page — exiting');
    await Actor.exit({ exitCode: 1 });
}

const catalogueLinkRegex = /\[([^\]]{5,120})\]\(https:\/\/www\.bidspotter\.com\/en-us\/auction-catalogues\/([^/]+)\/catalogue-id-([^\s\)"#?/]+)/g;
const catalogueSet = new Set();
const catalogueUrls = [];
let catMatch;

while ((catMatch = catalogueLinkRegex.exec(catResult.markdown)) !== null) {
    const title = catMatch[1].trim();
    const slug = catMatch[2].toLowerCase();
    const catalogueId = catMatch[3];
    const dedupeKey = `${slug}/${catalogueId}`;

    if (catalogueSet.has(dedupeKey)) continue;
    if (NON_US_SLUGS.has(slug)) { console.log(`[SKIP] Non-US slug: ${slug}`); continue; }
    if (!VEHICLE_CATALOGUE_PATTERN.test(title)) { console.log(`[SKIP] Non-vehicle catalogue: ${title.slice(0, 60)}`); continue; }
    if (PARTS_PATTERN.test(title)) { console.log(`[SKIP] Parts catalogue: ${title.slice(0, 60)}`); continue; }

    catalogueSet.add(dedupeKey);
    const url = `https://www.bidspotter.com/en-us/auction-catalogues/${slug}/catalogue-id-${catalogueId}`;
    catalogueUrls.push(url);
    console.log(`[CAT] ✓ ${title.slice(0, 70)} → ${slug}/${catalogueId}`);
}

const toProcess = catalogueUrls.slice(0, maxCatalogues);
console.log(`[BS] ${toProcess.length} vehicle catalogues to process (${catalogueUrls.length} matched, limit ${maxCatalogues})`);


// ── STEP 2: Fetch each catalogue page ──────────────────────────────────────

const seenLotUrls = new Set();

for (let i = 0; i < toProcess.length; i++) {
    const catUrl = toProcess[i];
    console.log(`[FC] GET catalogue ${i + 1}/${toProcess.length}: ${catUrl}`);

    const result = await firecrawlScrape(firecrawlApiKey, catUrl, 4000);
    if (!result?.markdown) {
        console.warn(`[FC] No markdown for catalogue — skipping`);
        await sleep(500);
        continue;
    }

    const rawLots = extractLotsFromMarkdown(result.markdown);
    console.log(`[BS] Catalogue ${i + 1}: ${rawLots.length} lots found`);

    for (const lot of rawLots) {
        if (seenLotUrls.has(lot.url)) continue;
        seenLotUrls.add(lot.url);

        totalFound++;
        const details = parseLotDetails(lot);
        const { year, make, model, lower } = parseVehicleTitle(lot.title);

        // ── Filters ────────────────────────────────────────────────────
        if (!make && !isVehicleLot(lot.title)) continue;
        // Require at least one strong vehicle signal: recognized make, VIN, or mileage
        const lotDesc = lot.block || '';
        const hasVIN = /\b[A-HJ-NPR-Z0-9]{17}\b/i.test(lotDesc);
        const hasMileage = /\b(mileage|odometer|miles|mi\.)\b/i.test(lotDesc);
        const hasMake = Boolean(make);
        if (!hasMake && !hasVIN && !hasMileage) {
            console.log(`[SKIP] No make/VIN/mileage: ${lot.title.slice(0, 60)}`);
            continue;
        }
        if (CONDITION_REJECT_PATTERNS.some(p => p.test(lower))) {
            console.log(`[SKIP] Condition: ${lot.title.slice(0, 60)}`);
            continue;
        }
        if (EXCLUDED_PATTERN.test(lower)) continue;
        if (details.state && CANADIAN_PROVINCES.has(details.state)) continue;
        if (details.state && !TARGET_STATES.has(details.state)) {
            console.log(`[SKIP] State ${details.state}: ${lot.title.slice(0, 60)}`);
            continue;
        }
        if (details.state && HIGH_RUST_STATES.has(details.state)) {
            if (!year || (CURRENT_YEAR - year) > 3) {
                console.log(`[SKIP] Rust ${details.state}: ${lot.title.slice(0, 60)}`);
                continue;
            }
            console.log(`[BYPASS] Rust ${details.state} allowed — ${year}`);
        }
        if (!year || year < MIN_YEAR) {
            console.log(`[SKIP] Year ${year}: ${lot.title.slice(0, 60)}`);
            continue;
        }
        if (details.currentBid != null && (details.currentBid < MIN_BID || details.currentBid > MAX_BID)) {
            console.log(`[SKIP] Bid $${details.currentBid}: ${lot.title.slice(0, 60)}`);
            continue;
        }

        totalPassed++;
        const bidLabel = details.currentBid != null ? `$${details.currentBid}` : 'TBD';
        console.log(`[PASS] ${year} ${make} ${model || ''} | ${bidLabel} | ${details.state || 'US'}`);

        await Actor.pushData({
            source: SOURCE,
            title: lot.title,
            listing_url: lot.url,
            current_bid: details.currentBid,
            year,
            make,
            model,
            mileage: details.mileage || null,
            state: details.state,
            city: details.city || null,
            location: details.location || null,
            auction_end_time: null,
            photo_url: details.photoUrl,
            lot_number: details.lotNumber,
            description: details.description,
            raw_title: lot.title,
        });
    }

    await sleep(500);
}

// ── Summary + Webhook ──────────────────────────────────────────────────────

console.log(`[BS COMPLETE] Found: ${totalFound} | Passed: ${totalPassed}`);

if (totalPassed > 0) {
    try {
        const env = Actor.getEnv();
        const res = await fetch(webhookUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'x-apify-webhook-secret': webhookSecret,
            },
            body: JSON.stringify({
                source: SOURCE,
                runId: env.actorRunId,
                actorId: env.actorId,
                datasetId: env.defaultDatasetId,
                itemCount: totalPassed,
            }),
        });
        console.log(`[BS] Webhook → ${res.status}`);
    } catch (err) {
        console.warn(`[BS] Webhook failed: ${err.message}`);
    }
}

await Actor.exit();
