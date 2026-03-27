/**
 * ds-hibid-v2 — HiBid GraphQL Custom Scraper
 *
 * STATUS: WORKING — Direct GraphQL API, no Playwright, no rented actors.
 *
 * Reverse-engineered from HiBid PWA JS bundle (v1.17.9).
 * API: https://hibid.com/graphql
 * - No Cloudflare on the /graphql endpoint itself (separate from the web UI)
 * - Uses Apollo Client GraphQL with query: lotSearch
 * - Auth: no authentication required for public lot browsing
 *
 * Confirmed schema fields (2026-03-21):
 *   LotSearchInput: auctionId, category (CategoryId), searchText, zip, miles,
 *     shippingOffered, countryName, state, status (AuctionLotStatus),
 *     sortOrder, filter, isArchive, dateStart, dateEnd, countAsView,
 *     hideGoogle, eventItemIds
 *   Lot: id, lotNumber, description, lead, bidAmount (placeholder=123.45),
 *     bidList, lotState { highBid, isClosed, timeLeftSeconds, minBid, buyNow,
 *       bidCount, reserveSatisfied, priceRealized }, featuredPicture,
 *     site { domain, subdomain }, auction { id, eventName, eventCity, eventState,
 *       eventZip, currencyAbbreviation, bidCloseDateTime }
 *
 * IMPORTANT: bidAmount field is always 123.45 (placeholder). Use lotState.highBid.
 *
 * Category 700006 = Cars & Vehicles
 * US filter: countryName = "United States"
 * State filter: state = "TX" etc. (but we paginate all US states ourselves)
 */

import { Actor } from 'apify';

const SOURCE = 'hibid';
const BASE_URL = 'https://hibid.com';
const GRAPHQL_URL = `${BASE_URL}/graphql`;

// --- Canadian province codes to reject ---
const CANADIAN_PROVINCES = new Set([
    'AB','BC','ON','QC','MB','SK','NS','NB','PE','NL','YT','NT','NU',
]);

// --- Target US states (sunbelt / south / west focus) ---
const TARGET_STATES = new Set([
    'AZ','CA','NV','CO','NM','UT','TX','FL','GA','SC','TN','NC','VA',
    'WA','OR','HI','ID','MT','WY','ND','SD','NE','KS','AL','LA','OK',
]);

// High-rust states — only allow vehicles <= 3yr old
const HIGH_RUST_STATES = new Set([
    'OH','MI','PA','NY','WI','MN','IL','IN','MO','IA',
    'ND','SD','NE','KS','WV','ME','NH','VT','MA','RI',
    'CT','NJ','MD','DE',
]);

// --- Vehicle detection ---
const VEHICLE_MAKES = new Set([
    'ford','chevrolet','chevy','dodge','ram','toyota','honda','nissan','jeep',
    'gmc','chrysler','hyundai','kia','subaru','mazda','volkswagen','vw','bmw',
    'mercedes','audi','lexus','acura','infiniti','cadillac','lincoln','buick',
    'pontiac','mitsubishi','volvo','tesla','rivian','lucid','genesis','saturn',
    'isuzu','hummer','mini','scion','oldsmobile',
]);

const VEHICLE_KEYWORDS = [
    'sedan','coupe','hatchback','pickup','suv','sport utility','crossover',
    'minivan','passenger van','4x4','awd','fwd','rwd',
];

const EXCLUDED_PATTERNS = /\b(forklift|tractor(?!\s+trailer)|loader|backhoe|excavator|grader|dozer|bulldozer|skid\s*steer|trencher|mower|generator|compressor|sprayer|sweeper|boat|marine|trailer|camper|rv|motorhome|jet\s*ski|snowmobile|motorcycle|atv(?!\s*vehicle)|utv|golf\s*cart|bus|ambulance|fire\s*truck|dump\s*truck|flatbed\s+truck|box\s*truck|cargo\s+van|step\s+van|cutaway|chassis\s+cab|stake\s*bed|lug\s*nut|auto\s*part|spare\s*tire|wheel\s+cover|tonneau|bed\s+cover|floor\s+mat|car\s+seat|child\s+seat|car\s+cover)\b/i;
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

// US state abbreviations set
const US_STATES = new Set([
    'AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA','HI','ID','IL','IN','IA',
    'KS','KY','LA','ME','MD','MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ',
    'NM','NY','NC','ND','OH','OK','OR','PA','RI','SC','SD','TN','TX','UT','VT',
    'VA','WA','WV','WI','WY','DC',
]);

await Actor.init();

const input = await Actor.getInput() ?? {};
const {
    maxPages = 20,          // per search batch (pageLength=50, so 20*50=1000 max)
    pageLength = 50,        // lots per GraphQL page
    minBid = 500,
    maxBid = 75000,
    minYear = new Date().getFullYear() - 10,
    maxMileage = 100000,
    targetStates = [...TARGET_STATES],
    searchTerms = [         // Multiple search passes to maximize vehicle coverage
        'ford', 'chevrolet', 'toyota', 'honda', 'dodge', 'nissan', 'jeep',
        'gmc', 'hyundai', 'kia', 'subaru', 'mazda', 'bmw', 'mercedes',
        'audi', 'lexus', 'cadillac', 'lincoln', 'buick', 'mitsubishi',
        'volkswagen', 'volvo', 'tesla', 'chrysler', 'pontiac', 'saturn',
    ],
    webhookUrl = null,
    webhookSecret = null,
} = input;

const targetStateSet = new Set(targetStates.map(s => String(s).toUpperCase()));
const seenLotIds = new Set();
let totalFound = 0;
let totalPassed = 0;

// ── Helpers ───────────────────────────────────────────────────────────────────

function normalizeState(rawState) {
    if (!rawState) return null;
    const s = String(rawState).toUpperCase().trim();
    // Handle mixed-case like "Ut", "ca", "TX"
    const abbr = s.slice(0, 2);
    if (US_STATES.has(abbr)) return abbr;
    return null;
}

function isCanadian(stateRaw) {
    if (!stateRaw) return false;
    const s = String(stateRaw).toUpperCase().trim().slice(0, 2);
    return CANADIAN_PROVINCES.has(s);
}

function parseVehicleTitle(text) {
    if (!text) return { year: null, make: null, model: null };
    const normalized = String(text).replace(/\s+/g, ' ').trim();
    const lower = normalized.toLowerCase();

    // Year: 1990–2030
    const yearMatch = normalized.match(/\b(19[9]\d|20[0-3]\d)\b/);
    const year = yearMatch ? parseInt(yearMatch[1], 10) : null;

    let make = null;
    let model = null;

    for (const candidateMake of VEHICLE_MAKES) {
        const pattern = new RegExp(`\\b${candidateMake.replace(/\s+/g, '\\s+')}\\b`, 'i');
        if (!pattern.test(lower)) continue;

        make = candidateMake === 'chevy' ? 'Chevrolet'
             : candidateMake === 'vw'   ? 'Volkswagen'
             : candidateMake.replace(/\b\w/g, c => c.toUpperCase());

        const matchResult = normalized.match(pattern);
        if (matchResult) {
            const afterMake = normalized
                .slice(matchResult.index + matchResult[0].length)
                .replace(/^[\s\-:]+/, '')
                .replace(/\b(4x4|awd|fwd|rwd|vin|odometer|miles|mi\b|lot|auction|surplus|gov|fleet|salvage|repo|vehicle|4door|4wd|2wd)\b.*/i, '')
                .trim();
            const modelMatch = afterMake.match(/^([A-Za-z0-9][A-Za-z0-9\-]*(?:\s+[A-Za-z0-9][A-Za-z0-9\-]*)?)/);
            if (modelMatch) {
                model = modelMatch[1].trim();
                // Reject if model looks like a year
                if (/^\d{4}$/.test(model)) model = null;
            }
        }
        break;
    }

    return { year, make, model };
}

function isVehicle(text) {
    if (!text) return false;
    const lower = String(text).toLowerCase();
    if (CONDITION_REJECT_PATTERNS.some((pattern) => pattern.test(lower))) return false;
    if (EXCLUDED_PATTERNS.test(lower)) return false;
    const hasMake = [...VEHICLE_MAKES].some(m => new RegExp(`\\b${m}\\b`).test(lower));
    const hasKeyword = VEHICLE_KEYWORDS.some(k => lower.includes(k));
    const hasYear = /\b(199\d|20[0-3]\d)\b/.test(lower);
    return hasMake || (hasKeyword && hasYear);
}

function parseMileage(text) {
    if (!text) return null;
    const m = String(text).replace(/,/g, '').match(/(\d+)\s*(?:miles?|mi\.?)\b/i);
    return m ? parseInt(m[1], 10) : null;
}

function parseVin(text) {
    if (!text) return null;
    const m = String(text).match(/\bVIN[:\s#-]*([A-HJ-NPR-Z0-9]{17})\b/i)
           || String(text).match(/\b([A-HJ-NPR-Z0-9]{17})\b/);
    return m ? m[1] : null;
}

function buildLotUrl(lotId, siteSubdomain) {
    if (siteSubdomain && siteSubdomain !== 'WWW') {
        return `https://${siteSubdomain.toLowerCase()}.hibid.com/lot/${lotId}/`;
    }
    return `${BASE_URL}/lot/${lotId}/`;
}

function passesFilters(listing, log) {
    if (CONDITION_REJECT_PATTERNS.some((pattern) => pattern.test(String(listing.title || '').toLowerCase()))) {
        log.debug(`[SKIP] Condition reject: ${listing.title || 'unknown title'}`);
        return false;
    }
    if (!isVehicle(listing.title)) {
        log.debug(`[SKIP-NON-VEH] ${listing.title?.slice(0, 60)}`);
        return false;
    }

    // Currency guard — reject non-USD (Canadian CAD)
    if (listing._currency && listing._currency !== 'USD') {
        log.debug(`[SKIP-CURRENCY] ${listing._currency}: ${listing.title?.slice(0, 50)}`);
        return false;
    }

    // Canadian province rejection
    if (isCanadian(listing._rawState)) {
        log.debug(`[SKIP-CA] Province=${listing._rawState}: ${listing.title?.slice(0, 50)}`);
        return false;
    }

    // US state validation
    const state = listing.state;
    if (state && !US_STATES.has(state)) {
        log.debug(`[SKIP-STATE] Unknown state ${state}: ${listing.title?.slice(0, 50)}`);
        return false;
    }

    // High-rust bypass by year
    if (state && HIGH_RUST_STATES.has(state)) {
        const currentYear = new Date().getFullYear();
        if (!(listing.year && listing.year >= currentYear - 2)) {
            log.debug(`[SKIP-RUST] ${state} + year ${listing.year}: ${listing.title?.slice(0, 50)}`);
            return false;
        }
        log.info(`[BYPASS-RUST] ${state} year=${listing.year} — recent vehicle allowed`);
    }

    // Target state filter
    if (state && targetStateSet.size > 0 && !targetStateSet.has(state)) {
        log.debug(`[SKIP-OOT] State ${state} not in target list`);
        return false;
    }

    // Bid range
    const bid = listing.current_bid;
    if (bid === 0) {
        log.debug(`[SKIP-ZERO-BID] Pre-auction item with no pricing: ${listing.title?.slice(0, 60)}`);
        return false;
    }
    if (bid > 0 && bid < minBid) {
        log.debug(`[SKIP-BID-LOW] $${bid}`);
        return false;
    }
    if (bid > 0 && bid > maxBid) {
        log.debug(`[SKIP-BID-HIGH] $${bid}`);
        return false;
    }

    // Year
    if (!listing.year || listing.year < minYear) {
        log.debug(`[SKIP-YEAR] ${listing.year}`);
        return false;
    }

    // Mileage
    if (listing.mileage !== null && listing.mileage > maxMileage) {
        log.debug(`[SKIP-MILES] ${listing.mileage}`);
        return false;
    }

    return true;
}

// ── GraphQL Query ─────────────────────────────────────────────────────────────

const LOT_SEARCH_QUERY = `
query LotSearch(
  $pageNumber: Int!
  $pageLength: Int!
  $category: CategoryId
  $searchText: String
  $countryName: String
  $status: AuctionLotStatus
  $sortOrder: EventItemSortOrder
) {
  lotSearch(
    input: {
      category: $category
      searchText: $searchText
      countryName: $countryName
      status: $status
      sortOrder: $sortOrder
      countAsView: false
      hideGoogle: false
    }
    pageNumber: $pageNumber
    pageLength: $pageLength
  ) {
    pagedResults {
      pageLength
      pageNumber
      totalCount
      filteredCount
      results {
        id
        lotNumber
        description
        lead
        bidAmount
        lotState {
          highBid
          isClosed
          timeLeftSeconds
          minBid
          buyNow
          bidCount
          reserveSatisfied
          priceRealized
        }
        featuredPicture {
          thumbnailLocation
          fullSizeLocation
        }
        site {
          domain
          subdomain
        }
        auction {
          id
          eventName
          eventCity
          eventState
          eventZip
          currencyAbbreviation
          bidCloseDateTime
        }
      }
    }
  }
}
`;

async function gqlFetch(variables, log) {
    const headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Origin': 'https://www.hibid.com',
        'Referer': 'https://www.hibid.com/lots/700006/cars-and-vehicles',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'sec-ch-ua': '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
        'sec-ch-ua-mobile': '?0',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
    };

    const body = JSON.stringify({ query: LOT_SEARCH_QUERY, variables });

    for (let attempt = 1; attempt <= 3; attempt++) {
        try {
            const resp = await fetch(GRAPHQL_URL, {
                method: 'POST',
                headers,
                body,
                signal: AbortSignal.timeout(30000),
            });

            if (!resp.ok) {
                log.warning(`[GQL] HTTP ${resp.status} on attempt ${attempt}`);
                if (attempt < 3) await new Promise(r => setTimeout(r, 2000 * attempt));
                continue;
            }

            const json = await resp.json();
            if (json.errors) {
                log.warning(`[GQL] GraphQL errors: ${JSON.stringify(json.errors).slice(0, 200)}`);
                return null;
            }
            return json.data?.lotSearch?.pagedResults ?? null;
        } catch (err) {
            log.warning(`[GQL] Fetch error attempt ${attempt}: ${err.message}`);
            if (attempt < 3) await new Promise(r => setTimeout(r, 3000 * attempt));
        }
    }
    return null;
}

async function processLot(lot, log) {
    const lotId = lot.id;
    if (seenLotIds.has(lotId)) return false;
    seenLotIds.add(lotId);

    totalFound++;

    const auction = lot.auction ?? {};
    const ls = lot.lotState ?? {};
    const pic = lot.featuredPicture ?? {};
    const site = lot.site ?? {};

    // Build title from lead + description
    const lead = (lot.lead ?? '').trim();
    const desc = (lot.description ?? '').trim();
    // Lead is usually the first ~50 chars of description — use it as title
    const title = lead || desc.slice(0, 100).split('\n')[0].trim();

    const rawState = auction.eventState ?? null;
    const state = normalizeState(rawState);
    const currency = auction.currencyAbbreviation ?? 'USD';

    // Real bid is in lotState.highBid (bidAmount is always placeholder 123.45)
    const currentBid = ls.highBid ?? 0;
    const buyNow = ls.buyNow && ls.buyNow > 0 ? ls.buyNow : null;

    const combinedText = `${title} ${desc}`;
    const mileage = parseMileage(combinedText);
    const vin = parseVin(combinedText);

    const { year, make, model } = parseVehicleTitle(title || desc.split('\n')[0]);

    const listingUrl = buildLotUrl(lotId, site.subdomain);

    const listing = {
        listing_id: `hibid-${lotId}`,
        title,
        year,
        make,
        model,
        current_bid: currentBid,
        buy_now_price: buyNow,
        auction_end_date: auction.bidCloseDateTime ?? null,
        state,
        city: auction.eventCity ?? null,
        zip: auction.eventZip ?? null,
        listing_url: listingUrl,
        image_url: pic.thumbnailLocation ?? pic.fullSizeLocation ?? null,
        mileage,
        vin,
        source_site: SOURCE,
        auction_name: auction.eventName ?? null,
        auction_id: auction.id ?? null,
        time_left_seconds: ls.timeLeftSeconds ?? null,
        bid_count: ls.bidCount ?? null,
        reserve_satisfied: ls.reserveSatisfied ?? null,
        scraped_at: new Date().toISOString(),
        // Internal fields for filter logic (not pushed to dataset)
        _currency: currency,
        _rawState: rawState,
    };

    if (!passesFilters(listing, log)) return false;

    // Clean internal fields before pushing
    const { _currency, _rawState, ...cleanListing } = listing;

    totalPassed++;
    log.info(`[PASS] ${title.slice(0, 60)} | $${currentBid} | ${state} | ${listingUrl}`);
    await Actor.pushData(cleanListing);
    return true;
}

// ── Main scrape loop ──────────────────────────────────────────────────────────

const log = {
    info: (msg) => console.log(`[INFO] ${msg}`),
    debug: (msg) => {},  // Set to console.log for verbose debugging
    warning: (msg) => console.warn(`[WARN] ${msg}`),
    error: (msg) => console.error(`[ERROR] ${msg}`),
};

// We run multiple search passes with different vehicle make keywords
// Each pass gets category 700006 (Cars & Vehicles) + US country filter
for (const searchText of searchTerms) {
    log.info(`\n=== Starting search: "${searchText}" ===`);

    let pageNumber = 1;
    let totalInSearch = null;

    while (pageNumber <= maxPages) {
        log.info(`[${searchText}] Page ${pageNumber}/${maxPages}...`);

        const variables = {
            pageNumber,
            pageLength,
            category: 700006,   // Cars & Vehicles
            searchText,
            countryName: 'United States',
            status: 'Open',
        };

        const pagedResults = await gqlFetch(variables, log);

        if (!pagedResults) {
            log.warning(`[${searchText}] No results on page ${pageNumber}, stopping`);
            break;
        }

        const { results, totalCount, filteredCount } = pagedResults;

        if (totalInSearch === null) {
            totalInSearch = filteredCount ?? totalCount ?? 0;
            log.info(`[${searchText}] Total matching lots: ${totalInSearch}`);
        }

        if (!results || results.length === 0) {
            log.info(`[${searchText}] Empty results page, done`);
            break;
        }

        log.info(`[${searchText}] Page ${pageNumber}: ${results.length} lots`);

        for (const lot of results) {
            if (lot.lotState?.isClosed) continue;   // skip already-closed lots
            await processLot(lot, log);
        }

        // Check if we've fetched all available pages
        const fetched = pageNumber * pageLength;
        if (fetched >= totalInSearch) {
            log.info(`[${searchText}] All ${totalInSearch} lots fetched`);
            break;
        }

        pageNumber++;

        // Polite delay between pages
        await new Promise(r => setTimeout(r, 500));
    }
}

// ── Webhook notification ──────────────────────────────────────────────────────

const effectiveWebhookUrl = webhookUrl
    || process.env.WEBHOOK_URL
    || 'https://dealscan-insight-production.up.railway.app/api/ingest/apify';
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
        log.info(`[WEBHOOK] Notified ingest: HTTP ${resp.status}`);
    } catch (err) {
        log.warning(`[WEBHOOK] Failed to notify: ${err.message}`);
    }
}

console.log(`\n[HIBID-V2 COMPLETE] Scraped: ${totalFound} | Passed filters: ${totalPassed}`);

await Actor.exit();
