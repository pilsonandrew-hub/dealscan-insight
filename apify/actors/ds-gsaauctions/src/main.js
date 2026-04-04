/**
 * ds-gsaauctions — GSA Auctions Vehicle Scraper
 *
 * STATUS: FIXED 2026-03-21 — Replaced broken Playwright SPA scraper with
 * direct REST API calls to ppms.gov backend.
 *
 * ROOT CAUSE: gsaauctions.gov is a React SPA. Playwright couldn't reliably
 * wait for Angular hydration. But the underlying API at
 * https://www.ppms.gov/gw/auction/ppms/api/v1/auctions is public and
 * accessible without auth.
 *
 * API NOTES:
 *   - POST to /api/v1/auctions with page (1-indexed) as query param
 *   - Items are sorted by endDate ASC (oldest first)
 *   - Active items are at the END (last pages)
 *   - Total pages ≈ 6993 with size=50
 *   - Active items start around page 6980+ (scan last 20 pages)
 *   - Vehicle categoryCode = 300-399 (320=trucks, 310=sedans, 340=vans, etc.)
 *   - Status field: "Active", "Preview", "Closed"
 *
 * Listing URL: https://www.gsaauctions.gov/auctions/preview/{lotId}
 * Image URL: https://www.ppms.gov/gw/property-reporting/ppms/api/v1/downloadFile?path={uri}
 */

import { Actor } from 'apify';

const SOURCE = 'gsaauctions';
const API_URL = 'https://www.ppms.gov/gw/auction/ppms/api/v1/auctions';
const BASE_UI_URL = 'https://www.gsaauctions.gov';

// Vehicle category codes
const VEHICLE_CATEGORY_CODES = new Set(['300', '310', '320', '330', '340', '350', '360', '370']);

const US_STATES = new Set([
    'AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA','HI','ID','IL','IN','IA',
    'KS','KY','LA','ME','MD','MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ',
    'NM','NY','NC','ND','OH','OK','OR','PA','RI','SC','SD','TN','TX','UT','VT',
    'VA','WA','WV','WI','WY','DC'
]);

const TARGET_STATES = new Set([
    'AZ', 'CA', 'NV', 'CO', 'NM', 'UT', 'TX', 'FL', 'GA', 'SC', 'TN', 'NC', 'VA', 'WA', 'OR', 'HI',
    'AL', 'LA', 'OK', 'AR', 'MS', 'KY', 'WV', 'MD', 'DE', 'NJ', 'PA', 'OH', 'MI', 'IN', 'IL',
    'WI', 'MN', 'IA', 'MO', 'KS', 'NE', 'SD', 'ND', 'MT', 'ID', 'WY', 'AK',
]);

const HIGH_RUST_STATES = new Set([
    'OH', 'MI', 'PA', 'NY', 'WI', 'MN', 'IL', 'IN', 'MO', 'IA',
    'ND', 'SD', 'NE', 'KS', 'WV', 'ME', 'NH', 'VT', 'MA', 'RI',
    'CT', 'NJ', 'MD', 'DE',
]);

const MAKES = [
    'ford', 'chevrolet', 'chevy', 'dodge', 'ram', 'toyota', 'honda', 'nissan', 'jeep', 'gmc',
    'chrysler', 'hyundai', 'kia', 'subaru', 'mazda', 'volkswagen', 'vw', 'bmw', 'mercedes',
    'audi', 'lexus', 'acura', 'infiniti', 'cadillac', 'lincoln', 'buick', 'pontiac',
    'mitsubishi', 'volvo', 'tesla', 'mini', 'saturn', 'scion', 'international', 'sterling',
];

const EXCLUDED_PATTERN = /\b(forklift|tractor|loader|backhoe|excavator|grader|dozer|bulldozer|skid\s*steer|trencher|mower|generator|compressor|sprayer|sweeper|boat|marine|trailer|camper|rv|motorhome|jet\s*ski|snowmobile|motorcycle|atv|utv|golf\s*cart|bus|ambulance|fire\s*truck|dump\s*truck|flatbed|box\s*truck|step\s+van|cutaway|chassis\s+cab|stake\s*bed|forklift|pallet|raft|printer|computer|furniture|desk|chair|cabinet|aircraft|plane|helicopter)\b/i;
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

function normalizeText(v) {
    return String(v ?? '').replace(/\s+/g, ' ').trim();
}

function parseBid(v) {
    if (!v) return 0;
    const m = String(v).replace(/,/g, '').match(/[\d]+(?:\.\d+)?/);
    return m ? parseFloat(m[0]) : 0;
}

function parseVehicleTitle(title) {
    const norm = normalizeText(title);
    const lower = norm.toLowerCase();

    const yearMatch = norm.match(/\b(19[89]\d|20[0-3]\d)\b/);
    const year = yearMatch ? parseInt(yearMatch[1], 10) : null;

    let make = null, model = null;
    for (const candidate of MAKES) {
        const pattern = new RegExp(`\\b${candidate.replace(/\s+/g, '\\s+')}\\b`, 'i');
        const match = norm.match(pattern);
        if (!match) continue;
        const canonical = candidate === 'chevy' ? 'Chevrolet' : candidate === 'vw' ? 'Volkswagen' : candidate.replace(/\b\w/g, c => c.toUpperCase());
        make = canonical;
        const afterMake = norm.slice(match.index + match[0].length).replace(/^[\s\-:]+/, '').replace(/\b(4x4|awd|fwd|rwd|vin|odometer|extended|crew|single|double)\b.*$/i, '').trim();
        const modelMatch = afterMake.match(/^([A-Za-z0-9][A-Za-z0-9\-]*(?:\s+[A-Za-z0-9][A-Za-z0-9\-]*)?)/);
        model = modelMatch ? modelMatch[1] : null;
        break;
    }

    return { year, make, model };
}

function isPassengerVehicle(title, categoryCode) {
    const lower = normalizeText(title).toLowerCase();
    if (CONDITION_REJECT_PATTERNS.some((pattern) => pattern.test(lower))) return false;
    if (!VEHICLE_CATEGORY_CODES.has(String(categoryCode))) return false;
    if (EXCLUDED_PATTERN.test(title)) return false;
    return true;
}

// Fetch one page from the GSA API
async function fetchPage(page, size = 50) {
    const url = `${API_URL}?page=${page}&size=${size}`;
    const resp = await fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Origin': 'https://www.gsaauctions.gov',
            'Referer': 'https://www.gsaauctions.gov/',
        },
        body: JSON.stringify({}),
        signal: AbortSignal.timeout(20000),
    });

    if (!resp.ok) {
        throw new Error(`GSA API error: ${resp.status}`);
    }

    return resp.json();
}

await Actor.init();

const input = await Actor.getInput() ?? {};
const {
    minBid = 100,
    maxBid = 75000,
    minYear = new Date().getFullYear() - 10,
    maxYear = new Date().getFullYear() + 1,
    pageSize = 50,
    // Number of pages from the END to scan (active items are at the end)
    pagesToScan = 20,
    // Whether to also accept Preview status (upcoming auctions)
    includePreview = false,
    webhookUrl = null,
    webhookSecret = null,
    searchQuery = null,
} = input;

const currentYear = new Date().getFullYear();
const seenIds = new Set();
let totalFound = 0;
let totalPassed = 0;

console.log('[GSA] Fetching total page count...');

// Get first page to determine total pages
const firstPage = await fetchPage(1, pageSize);
const totalPages = firstPage.totalPages ?? 1;
const totalElements = firstPage.totalElements ?? 0;

console.log(`[GSA] Total items: ${totalElements} | Total pages: ${totalPages} | Scanning last ${pagesToScan} pages`);

// Scan last N pages (where active auctions live)
const startPage = Math.max(1, totalPages - pagesToScan + 1);

for (let page = startPage; page <= totalPages; page++) {
    console.log(`[GSA] Fetching page ${page}/${totalPages}...`);

    let pageData;
    try {
        pageData = page === 1 ? firstPage : await fetchPage(page, pageSize);
    } catch (err) {
        console.warn(`[GSA] Error fetching page ${page}: ${err.message}`);
        await new Promise(r => setTimeout(r, 2000));
        continue;
    }

    const items = pageData.auctionDTOList ?? [];

    for (const item of items) {
        const status = item.status ?? '';
        if (status !== 'Active' && !(includePreview && status === 'Preview')) continue;

        const lotId = item.lotId;
        const auctionId = item.auctionId;
        if (!lotId || seenIds.has(lotId)) continue;
        seenIds.add(lotId);

        const title = normalizeText(item.lotName || '');
        const categoryCode = String(item.categoryCode ?? '');
        const location = item.location ?? {};
        const stateCode = normalizeText(location.state || '');
        const city = normalizeText(location.city || '');
        const zip = normalizeText(location.zipCode || '');

        totalFound++;

        // Vehicle check
        if (!isPassengerVehicle(title, categoryCode)) continue;

        // Keyword search filter
        if (searchQuery && !title.toLowerCase().includes(searchQuery.toLowerCase())) continue;

        // State filter: only reject non-US states — let ingest pipeline apply rust/target-state logic
        if (stateCode && !US_STATES.has(stateCode)) {
            console.log(`[GSA] Skipping non-US state ${stateCode}: ${title}`);
            continue;
        }

        const currentBid = parseBid(item.currentBid);
        const minBidAmount = parseBid(item.minBid);
        const effectiveBid = currentBid || minBidAmount;

        if (effectiveBid > 0 && effectiveBid > maxBid) continue;
        if (currentBid > 0 && currentBid < minBid) continue;

        const { year, make, model } = parseVehicleTitle(title);

        if (!year || year < minYear || year > maxYear) continue;

        const listingId = String(auctionId || lotId);
        const listingUrl = `${BASE_UI_URL}/auctions/preview/${listingId}`;

        // Image URL construction
        let imageUrl = null;
        if (item.uri) {
            imageUrl = `https://www.ppms.gov/gw/property-reporting/ppms/api/v1/downloadFile?path=${encodeURIComponent(item.uri)}`;
        }

        const record = {
            listing_id: `gsa-${listingId}`,
            title,
            year,
            make,
            model,
            current_bid: effectiveBid,
            actual_current_bid: currentBid,
            min_bid: minBidAmount,
            state: stateCode || null,
            city: city || null,
            zip: zip || null,
            location: [city, stateCode].filter(Boolean).join(', ') || null,
            auction_end_date: item.endDate ? new Date(item.endDate).toISOString() : null,
            auction_start_date: item.startDate ? new Date(item.startDate).toISOString() : null,
            listing_url: listingUrl,
            image_url: imageUrl,
            lot_id: lotId,
            auction_id: auctionId,
            lot_number: item.lotNumber,
            sales_number: item.salesNumber || null,
            category_code: categoryCode,
            status,
            num_bidders: item.numberOfBidders ?? 0,
            source_site: SOURCE,
            scraped_at: new Date().toISOString(),
        };

        await Actor.pushData(record);
        totalPassed++;
        console.log(`[PASS] ${title} | bid=$${effectiveBid} | ${stateCode} | end=${item.endDate}`);
    }

    // Polite delay between pages
    if (page < totalPages) {
        await new Promise(r => setTimeout(r, 500));
    }
}

// Webhook notification
const effectiveWebhookUrl = webhookUrl || process.env.WEBHOOK_URL || 'https://dealscan-insight-production.up.railway.app/api/ingest/apify';
const effectiveWebhookSecret = webhookSecret || process.env.WEBHOOK_SECRET || '';

if (effectiveWebhookUrl && totalPassed > 0) {
    try {
        const resp = await fetch(effectiveWebhookUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'x-webhook-secret': effectiveWebhookSecret,
            },
            body: JSON.stringify({
                source: SOURCE,
                actorRunId: process.env.APIFY_ACTOR_RUN_ID ?? 'local',
                itemCount: totalPassed,
                totalScraped: totalFound,
                timestamp: new Date().toISOString(),
            }),
            signal: AbortSignal.timeout(10000),
        });
        console.log(`[WEBHOOK] Notified ingest: HTTP ${resp.status}`);
    } catch (err) {
        console.warn(`[WEBHOOK] Failed: ${err.message}`);
    }
}

console.log(`[GSA COMPLETE] Found: ${totalFound} vehicles | Passed filters: ${totalPassed}`);
await Actor.exit();
