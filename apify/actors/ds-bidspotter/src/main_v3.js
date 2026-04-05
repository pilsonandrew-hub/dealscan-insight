/**
 * ds-bidspotter v3.0 — Raw Playwright actor (catalogue-level extraction)
 *
 * Strategy: Use raw Playwright (NOT PlaywrightCrawler) because the WAF challenge
 * handling requires manual control of the navigation lifecycle:
 * - BidSpotter returns 202 + JS challenge that auto-redirects to real page
 * - PlaywrightCrawler's auto-navigation runs the handler before redirect completes
 * - Raw Playwright lets us detect 202, wait for redirect, then extract
 *
 * Key finding from testing: lot detail pages are blocked by WAF regardless of
 * approach (proxy, fresh context, etc). Therefore we extract ALL data from
 * catalogue pages only — titles, bids, lot URLs from the lot listing.
 *
 * Flow:
 * 1. Load category search page (always works, ~2s)
 * 2. Extract catalogue links
 * 3. For each catalogue (fresh page per): detect WAF, wait for resolution,
 *    extract lot data from catalogue page
 * 4. Filter + push to dataset
 */

import { Actor } from 'apify';

const SOURCE = 'bidspotter';
const BASE_URL = 'https://www.bidspotter.com';
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
];

const EXCLUDED_PATTERN = /\b(forklift|tractor(?!\s+truck)|loader|backhoe|excavator|grader|dozer|bulldozer|skid\s*steer|trencher|mower|generator|compressor|sprayer|sweeper|boat|marine|camper|rv|motorhome|jet\s*ski|snowmobile|motorcycle|atv|utv|golf\s*cart|ambulance|fire\s*truck|box\s*truck|cargo\s+van|step\s+van|cutaway|chassis\s+cab|semitrailer|furniture|desk|chair|cabinet|computer|electronics|industrial|scissor\s*lift|telehandler|dumper|combine|harvester|baler)\b/i;

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
    const m = normalizeText(text).match(/([\d,]+)\s*(?:mi(?:les?)?|km)/i);
    if (!m) return null;
    const v = parseFloat(m[1].replace(/,/g, ''));
    return /km/i.test(m[0]) ? Math.round(v * 0.621371) : v;
}

function parseDate(v) {
    const t = normalizeText(v).replace(/^(ends?|closing|end\s*date|auction\s*end)\s*:?\s*/i, '').replace(/\bat\b/i, ' ');
    if (!t) return null;
    const d = new Date(t);
    return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// ── Main ────────────────────────────────────────────────────────────────────

await Actor.init();

const input = await Actor.getInput() ?? {};
const { maxCatalogues = 15, maxPages = 5, minYear = CURRENT_YEAR - 10, maxMileage = 100000 } = input;

let totalFound = 0, totalAfterFilters = 0;
let cataloguesProcessed = 0, cataloguesSkippedNonUS = 0, cataloguesSkippedWAF = 0;
const seenUrls = new Set();

// ── Launch browser ──────────────────────────────────────────────────────────

const { chromium } = await import('playwright');

const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-blink-features=AutomationControlled', '--disable-dev-shm-usage'],
});

const context = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    viewport: { width: 1280, height: 800 },
    locale: 'en-US',
    timezoneId: 'America/Chicago',
});
await context.addInitScript(() => {
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
});

console.log('[BS] Browser launched');

// ── Navigate with WAF handling ──────────────────────────────────────────────

async function navigateWAF(page, url, label) {
    try {
        const resp = await page.goto(url, { waitUntil: 'load', timeout: 45000 });
        const status = resp?.status() ?? 0;

        if (status === 202 || status === 403) {
            console.log(`[BS] WAF ${status} on ${label}, waiting...`);
            try { await page.waitForNavigation({ timeout: 12000, waitUntil: 'load' }); } catch {}
            try { await page.waitForLoadState('networkidle', { timeout: 10000 }); } catch {}
        } else {
            try { await page.waitForLoadState('networkidle', { timeout: 8000 }); } catch {}
        }

        const len = await page.evaluate(() => document.documentElement.innerHTML.length);
        return len > 500;
    } catch (err) {
        console.warn(`[BS] Nav error ${label}: ${err.message.split('\n')[0]}`);
        return false;
    }
}

// ── Extract lot data from catalogue page (no lot page visits needed) ────────

async function extractLotsFromCataloguePage(page) {
    return page.evaluate(() => {
        const lots = [];

        // Find all lot link elements
        const lotAnchors = document.querySelectorAll('a[href*="/lot-"]');
        const seen = new Set();

        for (const anchor of lotAnchors) {
            const href = anchor.getAttribute('href') || '';
            if (!href.includes('/auction-catalogues/') || href.includes('/search-filter')) continue;
            if (seen.has(href)) continue;
            seen.add(href);

            // Walk up to find the lot card container
            let container = anchor.closest('.lot-card, .lot-item, [class*="lot-card"], [class*="lot-item"], li, tr, .row, article');
            if (!container) container = anchor.parentElement?.parentElement || anchor.parentElement;

            // Extract title — try multiple approaches
            let title = '';
            const titleEl = container?.querySelector('.lot-title, [class*="lot-title"], [class*="lotTitle"], h3, h4, h5');
            if (titleEl) {
                title = titleEl.textContent?.trim() || '';
            }
            if (!title) {
                // Try the anchor text itself
                title = anchor.textContent?.trim() || '';
            }
            if (!title) {
                // Try nearby text
                title = container?.textContent?.trim()?.split('\n')[0] || '';
            }

            // Extract bid — look for price-like text in the container
            let bidText = '';
            if (container) {
                const priceEl = container.querySelector('[class*="price"], [class*="bid"], [class*="Price"], [class*="Bid"]');
                if (priceEl) bidText = priceEl.textContent?.trim() || '';
            }
            if (!bidText && container) {
                // Regex for price in container text
                const text = container.textContent || '';
                const m = text.match(/(?:£|\$|€)\s*([\d,]+(?:\.\d{2})?)/);
                if (m) bidText = m[0];
            }

            // Extract image
            let imageUrl = '';
            const imgEl = container?.querySelector('img');
            if (imgEl) {
                imageUrl = imgEl.src || imgEl.getAttribute('data-src') || '';
                if (imageUrl.includes('placeholder') || imageUrl.includes('no-image')) imageUrl = '';
            }

            lots.push({ href, title: title.slice(0, 200), bidText, imageUrl });
        }

        return lots;
    });
}

// ── STEP 1: Category page ───────────────────────────────────────────────────

const page = await context.newPage();
const categoryUrl = `${BASE_URL}/en-us/auction-catalogues/search-filter?categorytags=Automobiles%2c+Trucks+%26+Vans&country=US`;

console.log('[BS] Loading category page...');
const catOk = await navigateWAF(page, categoryUrl, 'category');

const allCatLinks = [];
if (catOk) {
    for (let p = 1; p <= maxPages; p++) {
        if (p > 1) {
            if (!await navigateWAF(page, `${categoryUrl}&page=${p}`, `cat-p${p}`)) break;
        }
        const links = await page.evaluate(() => {
            const s = new Set();
            for (const a of document.querySelectorAll('a[href*="/catalogue-id-"]')) {
                const h = a.getAttribute('href');
                if (h && !h.includes('/search-filter')) s.add(h);
            }
            return [...s];
        });
        console.log(`[BS] Category page ${p}: ${links.length} catalogues`);
        allCatLinks.push(...links);
        if (allCatLinks.length >= maxCatalogues || links.length < 20) break;
        await sleep(1000);
    }
}
await page.close();

const catalogueUrls = [...new Set(allCatLinks)].slice(0, maxCatalogues);
console.log(`[BS] ${catalogueUrls.length} catalogues to process`);

// ── STEP 2: Process catalogues ──────────────────────────────────────────────

for (const catPath of catalogueUrls) {
    const catUrl = catPath.startsWith('http') ? catPath : `${BASE_URL}${catPath}`;
    const catPage = await context.newPage();

    try {
        const ok = await navigateWAF(catPage, catUrl, 'catalogue');
        if (!ok) {
            cataloguesSkippedWAF++;
            continue;
        }

        // dataLayer for country/city
        const dl = await catPage.evaluate(() => {
            const merged = {};
            for (const e of (window.dataLayer || [])) {
                if (typeof e === 'object' && e !== null) Object.assign(merged, e);
            }
            return merged;
        });

        const auctionCountry = dl.auctionCountry || '';
        const auctionCity = dl.auctionCity || '';
        const catName = dl.catalogueName || catPath.split('/').pop();

        if (auctionCountry && auctionCountry !== 'United States') {
            cataloguesSkippedNonUS++;
            console.log(`[BS] Skip non-US: ${auctionCountry} | ${catName}`);
            continue;
        }

        cataloguesProcessed++;
        const state = parseStateFromCity(auctionCity);
        console.log(`[BS] US Catalogue: ${catName} | ${auctionCity} → ${state || '??'}`);

        // Extract ALL lot data directly from catalogue page
        const lots = await extractLotsFromCataloguePage(catPage);
        const auctionEnd = parseDate(dl.lotEndsFrom || '');
        console.log(`[BS] ${lots.length} lots extracted from page`);

        for (const lot of lots) {
            const lotUrl = lot.href.startsWith('http') ? lot.href : `${BASE_URL}${lot.href}`;
            if (seenUrls.has(lotUrl)) continue;
            seenUrls.add(lotUrl);

            if (!lot.title) continue;
            totalFound++;

            const { year, make, model, lower } = parseVehicleTitle(lot.title);
            const currentBid = parseBid(lot.bidText);
            const mileage = parseMileage(lot.title);
            const lotNumberMatch = lotUrl.match(/\/lot-([^/?#]+)/);
            const imageUrl = lot.imageUrl ? lot.imageUrl.split('?')[0] : null;

            const listing = {
                title: lot.title,
                make: make || null,
                model: model || null,
                year: year || null,
                current_bid: currentBid,
                mileage: mileage || null,
                state: state || null,
                listing_url: lotUrl,
                photos: imageUrl ? [imageUrl] : [],
                image_url: imageUrl,
                source_site: SOURCE,
                auction_end: auctionEnd,
                auction_end_date: auctionEnd,
                lot_number: lotNumberMatch ? lotNumberMatch[1] : null,
                description: null,
                scraped_at: new Date().toISOString(),
            };

            // ── Filters ─────────────────────────────────────────────────────
            if (!make && !isVehicleLot(lot.title)) { continue; }
            if (!make) { continue; }
            if (CONDITION_REJECT_PATTERNS.some(p => p.test(lower))) {
                console.log(`[SKIP] Condition: ${lot.title.slice(0, 60)}`);
                continue;
            }
            if (EXCLUDED_PATTERN.test(lower)) { continue; }
            if (listing.state && CANADIAN_PROVINCES.has(listing.state)) { continue; }
            if (listing.state && !TARGET_STATES.has(listing.state)) {
                console.log(`[SKIP] State ${listing.state}: ${lot.title.slice(0, 60)}`);
                continue;
            }
            if (listing.state && HIGH_RUST_STATES.has(listing.state)) {
                if (!year || (CURRENT_YEAR - year) > 3) {
                    console.log(`[SKIP] Rust ${listing.state}: ${lot.title.slice(0, 60)}`);
                    continue;
                }
                console.log(`[BYPASS] Rust ${listing.state} allowed — ${year}`);
            }
            if (!year || year < minYear) {
                console.log(`[SKIP] Year ${year}: ${lot.title.slice(0, 60)}`);
                continue;
            }
            if (mileage != null && mileage > maxMileage) { continue; }
            // Allow null bids through (catalogue might not show price)
            // We'll mark them as "Price TBD"
            if (currentBid != null && currentBid <= 0) { continue; }

            totalAfterFilters++;
            const bidLabel = currentBid != null ? `$${currentBid}` : 'TBD';
            console.log(`[PASS] ${year} ${make} ${model || ''} | ${bidLabel} | ${state || 'US'} | ${lot.title.slice(0, 60)}`);
            await Actor.pushData(listing);
        }
    } finally {
        await catPage.close();
    }
    await sleep(1500);
}

// ── Cleanup ─────────────────────────────────────────────────────────────────

await context.close();
await browser.close();

console.log(`[BIDSPOTTER COMPLETE] Found: ${totalFound} | Passed filters: ${totalAfterFilters}`);
console.log(`[BIDSPOTTER STATS] Catalogues: ${cataloguesProcessed} | Non-US: ${cataloguesSkippedNonUS} | WAF: ${cataloguesSkippedWAF}`);

// ── Webhook ─────────────────────────────────────────────────────────────────

try {
    const dataset = await Actor.openDataset();
    const env = Actor.getEnv();
    await fetch('https://dealscan-insight-production.up.railway.app/api/ingest/apify', {
        method: 'POST',
        headers: { 'X-Apify-Webhook-Secret': process.env.WEBHOOK_SECRET || '', 'Content-Type': 'application/json' },
        body: JSON.stringify({
            eventType: 'ACTOR.RUN.SUCCEEDED',
            eventData: { actorId: env.actorId, defaultDatasetId: dataset.id },
            source: SOURCE, itemCount: totalAfterFilters, totalScraped: totalFound,
            timestamp: new Date().toISOString(),
        }),
        signal: AbortSignal.timeout(60000),
    });
    console.log('[BS] Webhook sent');
} catch (err) {
    console.warn(`[BS] Webhook failed: ${err.message}`);
}

await Actor.exit();
