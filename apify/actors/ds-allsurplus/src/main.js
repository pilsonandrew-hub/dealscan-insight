import { Actor } from 'apify';

const DEFAULT_WEBHOOK_SECRET = 'rDyApg2UUIMl0a8ZUz_swOqsHX7HbjN-gly3xHNwiyA';

if (!process.env.WEBHOOK_SECRET) {
    console.warn('[ALLSURPLUS] WARNING: WEBHOOK_SECRET env var not set; using deployed fallback secret');
}

await Actor.init();
const input = await Actor.getInput() || {};

// AllSurplus Maestro API - reverse-engineered from JS bundle
const MAESTRO_URL = 'https://maestro.lqdt1.com';
const MAESTRO_API_KEY = input.maestroApiKey || process.env.MAESTRO_API_KEY;
const MAESTRO_SUBSCRIPTION_KEY = input.maestroSubscriptionKey || process.env.MAESTRO_SUBSCRIPTION_KEY;
const BUSINESS_ID = 'AD'; // AllSurplus bizId
const IMAGE_BASE = 'https://webassets.lqdt1.com/assets';
const ASSET_URL_BASE = 'https://www.allsurplus.com/asset';

const US_STATES = new Set([
    'AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA','HI','ID','IL','IN','IA',
    'KS','KY','LA','ME','MD','MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ',
    'NM','NY','NC','ND','OH','OK','OR','PA','RI','SC','SD','TN','TX','UT','VT',
    'VA','WA','WV','WI','WY','DC'
]);

const TARGET_STATES = new Set([
    'AZ','CA','NV','CO','NM','UT','TX','FL','GA','SC','TN','NC','VA','WA','OR','HI'
]);

const HIGH_RUST_STATES = new Set([
    'OH','MI','PA','NY','WI','MN','IL','IN','MO','IA','ND','SD','NE','KS','WV',
    'ME','NH','VT','MA','RI','CT','NJ','MD','DE'
]);

// Vehicle-related search terms to cover the category
const VEHICLE_SEARCHES = [
    'ford truck pickup',
    'chevrolet chevy pickup truck',
    'toyota tacoma tundra',
    'dodge ram pickup',
    'honda accord civic',
    'nissan truck suv',
    'jeep wrangler cherokee',
    'gmc sierra canyon',
    'hyundai kia suv',
    'subaru outback forester',
    'sedan SUV van',
];

// Vehicle category IDs from AllSurplus
// t6 = Transportation (Segment level 1)
const VEHICLE_CATEGORY_FACET = '{!tag=product_category_external_id}product_category_external_id:"t6"';

const VEHICLE_MAKES = new Set([
    'ford','chevrolet','chevy','dodge','ram','toyota','honda','nissan','jeep','gmc',
    'chrysler','hyundai','kia','subaru','mazda','volkswagen','vw','bmw','mercedes',
    'audi','lexus','acura','infiniti','cadillac','lincoln','buick','pontiac',
    'mitsubishi','volvo','tesla','rivian','lucid','genesis','saturn','oldsmobile',
    'mercury','hummer','mini','fiat','alfa','maserati','ferrari','lamborghini',
    'bentley','rolls','jaguar','land rover','range rover','porsche','saab',
    'suzuki','isuzu','daihatsu','datsun','geo','scion','smart','rivian',
    'freightliner','kenworth','peterbilt','mack','volvo trucks','international',
    'pierce','american lafrance','seagrave','rosenbauer',
]);

const VEHICLE_KEYWORDS = [
    'car','truck','suv','van','pickup','sedan','coupe','wagon','vehicle',
    '4wd','awd','4x4','hybrid','electric','ev','crossover','hatchback',
    'convertible','roadster','cab','crew','extended cab','regular cab',
];

// Non-vehicle patterns to reject
const REJECT_PATTERNS = [
    /\btransformer\b/i, /\bturbine\b/i, /\bgenerator\b/i, /\bexcavator\b/i,
    /\bbulldozer\b/i, /\bforklift\b/i, /\bcrane\b/i, /\bloader\b/i,
    /\bcompressor\b/i, /\bpump\b/i, /\bboiler\b/i, /\bchipper\b/i,
    /\breal estate\b/i, /\bproperty\b/i, /\bhome\b.*\bbedroom/i,
    /\bboat\b/i, /\bvessel\b/i, /\baircraft\b/i, /\bplane\b/i, /\bhelicopter\b/i,
    /\btrailer\b/i, /\bdumpster\b/i, /\bscraper\b.*\beach/i,
    /\btractors?\b(?!.*\bford\b)/i,
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
    /\bas[\s-]?is\b.*\bno\s+warrant/i,
    /\bno\s+warrant.*\bas[\s-]?is\b/i,
    /\bsold\s+as\s+is\b.*\bno\s+(?:guarantees?|warrant(?:y|ies))/i,
    /\bno\s+(?:guarantees?|warrant(?:y|ies))\b.*\bsold\s+as\s+is\b/i,
    /\bsold\b[\s"'\u201c\u201d]+as[\s"'\u201c\u201d]+is\b.*\bno\s+(?:guarantees?|warrant(?:y|ies))/i,
    /\bno\s+(?:guarantees?|warrant(?:y|ies))\b.*\bsold\b[\s"'\u201c\u201d]+as[\s"'\u201c\u201d]+is\b/i,
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

// Commercial/fleet patterns
const COMMERCIAL_PATTERNS = [
    /\bfire\s*truck\b/i, /\bambulance\b/i, /\bgarbage\b.*\btruck/i,
    /\bvacuum\s*truck\b/i, /\bbucket\s*truck\b/i, /\bcherry\s*picker\b/i,
    /\bstreet\s*sweeper\b/i, /\bconcrete\s*mixer\b/i, /\bcement\s*truck\b/i,
    /\bdump\s*truck\b/i, /\bbox\s*truck\b/i, /\bcargo\s*van\b/i,
    /\bstep\s*van\b/i, /\bshuttle\s*bus\b/i, /\bschool\s*bus\b/i,
    /\btransit\s*bus\b/i, /\bcoach\s*bus\b/i,
    /\bhydro\s*excavation\b/i, /\bvactor\b/i,
    /\bE-250\b/i, /\bE-350\b/i, /\b2500\b.*\bcargo\b/i, /\b3500\b.*\bcargo\b/i,
];

function isVehicle(title, categoryDesc) {
    const lower = title.toLowerCase();
    const catLower = (categoryDesc || '').toLowerCase();

    // Reject non-vehicles
    for (const pattern of REJECT_PATTERNS) {
        if (pattern.test(lower)) return false;
    }
    for (const pattern of NON_VEHICLE_PART_PATTERNS) {
        if (pattern.test(lower)) return false;
    }

    // Auto-qualify on category only after source-identity rejects.
    if (catLower.match(/\b(pickup|sedan|suv|coupe|convertible|hatchback|crossover|passenger car|vehicles?\s*misc|cars?\s*&|automobile)\b/)) {
        return true;
    }
    
    // Reject commercial
    for (const pattern of COMMERCIAL_PATTERNS) {
        if (pattern.test(lower)) return false;
    }
    
    // Check for year + make pattern (strong signal)
    const yearMatch = lower.match(/\b(20\d{2}|19[89]\d)\b/);
    if (yearMatch) {
        for (const make of VEHICLE_MAKES) {
            if (lower.includes(make)) return true;
        }
    }
    
    // Check for vehicle keywords  
    for (const kw of VEHICLE_KEYWORDS) {
        if (lower.includes(kw)) return true;
    }
    
    return false;
}

function parseState(locationState) {
    if (!locationState) return null;
    // AllSurplus returns 2-letter US codes or "ZA-NL" format for other countries
    if (US_STATES.has(locationState)) return locationState;
    // Try extracting from "XX-YY" format (non-US)
    return null;
}

function parseBid(val) {
    if (!val) return 0;
    const n = parseFloat(String(val).replace(/,/g, ''));
    return isNaN(n) ? 0 : n;
}

function buildLotUrl(assetId, accountId) {
    return `${ASSET_URL_BASE}/${assetId}/${accountId}`;
}

function buildImageUrl(photo) {
    if (!photo) return null;
    // photo field is like "31315_5_uuid.jpg?cb=260410070000"
    const base = photo.split('?')[0];
    return `${IMAGE_BASE}/${base}`;
}

function inferTitleStatus(description) {
    if (!description) return 'Unknown';
    const lower = description.toLowerCase();
    if (/\bsalvage\b/.test(lower)) return 'Salvage';
    if (/\brebuilt\b/.test(lower)) return 'Rebuilt';
    if (/\bclean\b/.test(lower)) return 'Clean';
    return 'Unknown';
}

function stripHtmlToText(html) {
    return String(html || '')
        .replace(/<script[\s\S]*?<\/script>/gi, ' ')
        .replace(/<style[\s\S]*?<\/style>/gi, ' ')
        .replace(/<[^>]+>/g, ' ')
        .replace(/&nbsp;/gi, ' ')
        .replace(/&amp;/gi, '&')
        .replace(/&quot;/gi, '"')
        .replace(/&#39;/gi, "'")
        .replace(/\s+/g, ' ')
        .trim();
}

function parseVin(text) {
    const match = String(text || '').match(/\b([A-HJ-NPR-Z0-9]{17})\b/i);
    return match ? match[1].toUpperCase() : null;
}

function parseMileage(text) {
    const match = String(text || '').replace(/,/g, '').match(/\b(?:mileage|odometer|miles?)[:\s-]*(\d{2,7})\b/i)
        || String(text || '').replace(/,/g, '').match(/\b(\d{2,7})\s*(?:miles?|mi\b)/i);
    return match ? parseInt(match[1], 10) : null;
}

async function searchMaestro(searchText, page, displayRows, facetsFilter = [], sessionId) {
    const correlationId = crypto.randomUUID ? crypto.randomUUID() : 
        Math.random().toString(36).substr(2, 9) + '-' + Date.now().toString(36);
    
    const body = {
        businessId: BUSINESS_ID,
        searchText,
        isQAL: false,
        page,
        displayRows,
        sortField: 'closeDatetime',
        sortOrder: 'asc',
        sessionId,
        requestType: 1,
        responseStyle: 1,
        facets: [],
        facetsFilter,
        isVehicleSearch: false,
    };
    
    const response = await fetch(`${MAESTRO_URL}/search/list`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Accept-Encoding': 'gzip',
            'Origin': 'https://www.allsurplus.com',
            'Referer': 'https://www.allsurplus.com/',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'x-api-key': MAESTRO_API_KEY,
            'x-user-id': '-1',
            'x-api-correlation-id': correlationId,
            'Ocp-Apim-Subscription-Key': MAESTRO_SUBSCRIPTION_KEY,
        },
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(30000),
    });
    
    if (!response.ok) {
        const text = await response.text();
        throw new Error(`API error ${response.status}: ${text.slice(0, 200)}`);
    }
    
    return await response.json();
}

async function getAssetDetail(assetId, accountId) {
    const correlationId = crypto.randomUUID ? crypto.randomUUID() :
        Math.random().toString(36).substr(2, 9) + '-' + Date.now().toString(36);

    const response = await fetch(`${MAESTRO_URL}/assets/${assetId}/${accountId}/false`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Accept-Encoding': 'gzip',
            'Origin': 'https://www.allsurplus.com',
            'Referer': `${ASSET_URL_BASE}/${assetId}/${accountId}`,
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'x-api-key': MAESTRO_API_KEY,
            'x-user-id': '-1',
            'x-api-correlation-id': correlationId,
            'Ocp-Apim-Subscription-Key': MAESTRO_SUBSCRIPTION_KEY,
        },
        body: JSON.stringify({ businessId: BUSINESS_ID, siteId: 1 }),
        signal: AbortSignal.timeout(30000),
    });

    if (!response.ok) {
        const text = await response.text();
        throw new Error(`detail API error ${response.status}: ${text.slice(0, 200)}`);
    }

    return await response.json();
}

function enrichListingFromDetail(listing, detail) {
    if (!detail) return listing;

    const detailText = stripHtmlToText(detail.assetLongDesc || detail.assetShortDesc || '');
    const detailMileage = Number.parseInt(String(detail.meterCount || '').replace(/,/g, ''), 10);
    const parsedMileage = parseMileage(detailText);
    const mileage = Number.isFinite(detailMileage) && detailMileage > 0 ? detailMileage : parsedMileage;
    const vin = parseVin(detail.vinserial) || parseVin(detailText);

    if (mileage && mileage > 0) listing.mileage = mileage;
    if (vin) listing.vin = vin;
    if (detail.assetLongDesc || detail.assetShortDesc) {
        listing.description = detailText || listing.description;
        listing.raw_detail_description = detailText || null;
    }
    if (detail.assetShortDesc) listing.title = stripHtmlToText(detail.assetShortDesc);
    if (detail.catDesc) listing.category = detail.catDesc;
    if (detail.state) {
        listing.state = detail.state;
        listing.location_state = detail.state;
    }
    listing.detail_enriched = Boolean(detail.assetId || detail.assetLongDesc || detail.meterCount || detail.vinserial);
    return listing;
}

// Age/mileage gate mirrors backend standard lane so public-auction rows reach scoring.
const currentYear = new Date().getFullYear();
const defaultMinYear = currentYear - 10;
const STANDARD_MAX_MILES_PER_YEAR = 18000;
const PREMIUM_MAX_MODEL_AGE_YEARS = 4;
const PREMIUM_MAX_MILEAGE = 50000;

const searchQuery = input.searchQuery || "";

const {
    maxSearchPages = 5,
    displayRows = 50,
    minBid = 3000,
    maxBid = 35000,
    maxMileage = 100000,
    minYear = defaultMinYear,
    targetStatesOnly = false,
    allowHighRust = false,
    searchTerms = searchQuery ? [searchQuery] : VEHICLE_SEARCHES,
} = input;

const sessionId = `ds-allsurplus-${Date.now()}`;
const seenIds = new Set();

function failsDealerScopeAgeMileageGate(year, mileage) {
    if (!year || year < minYear) return true;
    if (mileage === null || mileage === undefined || mileage <= 0) return false;
    if (mileage > maxMileage) return true;
    const ageYears = Math.max(1, currentYear - Number(year));
    // Premium lane (<= PREMIUM_MAX_MODEL_AGE_YEARS old AND <= PREMIUM_MAX_MILEAGE) is exempt from
    // the standard-lane miles/year cap, mirroring backend determine_vehicle_tier. Without this,
    // late-model high-mileage fleet vehicles are silently dropped before scoring.
    if (ageYears <= PREMIUM_MAX_MODEL_AGE_YEARS && mileage <= PREMIUM_MAX_MILEAGE) return false;
    return mileage / ageYears > STANDARD_MAX_MILES_PER_YEAR;
}
const allListings = [];
const excludedMissingRequiredSamples = [];
let totalFound = 0;
let totalPassed = 0;
let listRowsWithVin = 0;
let listRowsWithMileage = 0;
let detailPagesAttempted = 0;
let detailPagesFetched = 0;
let detailPagesFailed = 0;
let detailVinsFound = 0;
let detailMileagesFound = 0;
let rowsExcludedDuplicate = 0;
let rowsExcludedNonVehicle = 0;
let rowsExcludedNonUsState = 0;
let rowsExcludedNonUsdCurrency = 0;
let rowsExcludedRustState = 0;
let rowsExcludedNonTargetState = 0;
let rowsExcludedBidRange = 0;
let rowsExcludedAgeMileagePrefilter = 0;
let rowsExcludedAgeMileageAfterDetail = 0;
let rowsExcludedPolicyAfterDetail = 0;
let rowsExcludedMissingRequiredData = 0;
let rowsExcludedMissingVin = 0;
let rowsExcludedMissingMileage = 0;

console.log(`[AllSurplus] Starting maestro API scraper | sessionId=${sessionId}`);

for (const searchText of searchTerms) {
    console.log(`[AllSurplus] Searching: "${searchText}"`);
    
    for (let page = 1; page <= maxSearchPages; page++) {
        try {
            const data = await searchMaestro(searchText, page, displayRows, [], sessionId);
            
            if (!data || !Array.isArray(data.assetSearchResults)) {
                console.log(`[AllSurplus] No results for "${searchText}" page ${page}`);
                break;
            }
            
            const results = data.assetSearchResults;
            console.log(`[AllSurplus] "${searchText}" page ${page}: ${results.length} results`);
            
            if (results.length === 0) break;
            
            for (const item of results) {
                totalFound++;
                
                const itemId = `${item.accountId}-${item.assetId}`;
                if (seenIds.has(itemId)) {
                    rowsExcludedDuplicate++;
                    continue;
                }
                seenIds.add(itemId);
                
                const title = (item.assetShortDescription || '').trim();
                const categoryDesc = item.categoryDescription || '';
                
                // Vehicle check
                if (!isVehicle(title, categoryDesc)) {
                    rowsExcludedNonVehicle++;
                    continue;
                }
                
                // State check - must be US state
                const state = parseState(item.locationState);
                if (!state) {
                    console.log(`[SKIP] Non-US state: ${item.locationState} — ${title}`);
                    rowsExcludedNonUsState++;
                    continue;
                }
                
                // Currency check - must be USD
                if (item.currencyCode && item.currencyCode !== 'USD') {
                    console.log(`[SKIP] Non-USD currency: ${item.currencyCode} — ${title}`);
                    rowsExcludedNonUsdCurrency++;
                    continue;
                }
                
                const year = item.modelYear ? parseInt(item.modelYear) : null;

                if (!allowHighRust && HIGH_RUST_STATES.has(state)) {
                    const currentYear = new Date().getFullYear();
                    if (year && year >= currentYear - 2) {
                        console.log(`[BYPASS] Rust state ${state} allowed — vehicle is ${year} (≤2yr old)`);
                    } else {
                        console.log(`[SKIP] High-rust state: ${state} — ${title}`);
                        rowsExcludedRustState++;
                        continue;
                    }
                }

                if (targetStatesOnly && !TARGET_STATES.has(state)) {
                    console.log(`[SKIP] Non-target state: ${state}`);
                    rowsExcludedNonTargetState++;
                    continue;
                }

                const bid = parseBid(item.currentBid);

                if (bid > 0 && bid < minBid) {
                    console.log(`[SKIP] Bid too low: $${bid} — ${title}`);
                    rowsExcludedBidRange++;
                    continue;
                }
                if (bid > 0 && bid > maxBid) {
                    console.log(`[SKIP] Bid too high: $${bid} — ${title}`);
                    rowsExcludedBidRange++;
                    continue;
                }

                if (failsDealerScopeAgeMileageGate(year, null)) {
                    console.log(`[SKIP] Too old: ${year} — ${title}`);
                    rowsExcludedAgeMileagePrefilter++;
                    continue;
                }

                const mileageRaw = item.mileage || item.meter_reading || '';
                const mileageNum = parseInt(mileageRaw.toString().replace(/,/g, ''), 10);
                if (parseVin(item.vinserial || item.vin || '')) listRowsWithVin++;
                if (!isNaN(mileageNum) && mileageNum > 0) listRowsWithMileage++;

                if (!isNaN(mileageNum) && mileageNum > 0 && failsDealerScopeAgeMileageGate(year, mileageNum)) {
                    console.log('[SKIP-MILEAGE]', title, '| mileage:', mileageNum);
                    rowsExcludedAgeMileagePrefilter++;
                    continue;
                }
                
                const lotUrl = buildLotUrl(item.assetId, item.accountId);
                const imageUrl = buildImageUrl(item.photo);
                const auctionEndDate = item.assetAuctionEndDateUtc || item.assetAuctionEndDate 
                    ? new Date(item.assetAuctionEndDateUtc || item.assetAuctionEndDate).toISOString()
                    : null;
                
                // Ensure make is populated - fallback to title parsing
                let make = item.makebrand || null;
                if (!make && title) {
                    for (const m of VEHICLE_MAKES) {
                        if (title.toLowerCase().includes(m)) {
                            make = m.charAt(0).toUpperCase() + m.slice(1);
                            if (make === 'Chevy') make = 'Chevrolet';
                            if (make === 'Vw') make = 'Volkswagen';
                            break;
                        }
                    }
                }

                const listing = {
                    // Required DealerScope fields (normalize_apify_vehicle compatible)
                    year: year || null,
                    make: make || null,
                    model: item.model || null,
                    mileage: !isNaN(mileageNum) && mileageNum > 0 ? mileageNum : null,
                    title_status: 'Unknown', // not in list API
                    auction_source: 'AllSurplus',
                    source_site: 'allsurplus',
                    source: 'allsurplus',
                    current_bid: bid,
                    auction_end_date: auctionEndDate,
                    // Field aliases for ingest compatibility
                    state: state,           // normalize_apify_vehicle reads "state"
                    location_state: state,  // extra alias
                    listing_url: lotUrl,    // normalize_apify_vehicle reads "listing_url" or "url"
                    lot_url: lotUrl,        // extra alias
                    image_url: imageUrl,
                    photo_url: imageUrl,    // normalize_apify_vehicle reads "image_url" or "photo_url"
                    description: title,
                    
                    // Additional metadata
                    listing_id: itemId,
                    title,
                    lot_number: String(item.lotNumber || item.assetId),
                    vin: null,
                    category: categoryDesc,
                    company_name: item.companyName || null,
                    account_id: item.accountId,
                    asset_id: item.assetId,
                    event_id: item.eventId,
                    scraped_at: new Date().toISOString(),
                };
                
                try {
                    detailPagesAttempted++;
                    const detail = await getAssetDetail(item.assetId, item.accountId);
                    detailPagesFetched++;
                    enrichListingFromDetail(listing, detail);
                } catch (err) {
                    detailPagesFailed++;
                    console.warn(`[DETAIL] Failed ${itemId} — ${err.message}`);
                }

                if (listing.vin) detailVinsFound++;
                if (listing.mileage) detailMileagesFound++;

                if (listing.mileage && failsDealerScopeAgeMileageGate(listing.year, listing.mileage)) {
                    console.log(`[SKIP-MILEAGE-DETAIL] ${listing.title} | mileage: ${listing.mileage}`);
                    rowsExcludedAgeMileageAfterDetail++;
                    continue;
                }

                const missingRequiredReasons = [];
                if (!listing.vin) missingRequiredReasons.push('missing_vin_after_detail');
                if (!listing.mileage) missingRequiredReasons.push('missing_mileage_after_detail');
                if (missingRequiredReasons.length > 0) {
                    rowsExcludedMissingRequiredData++;
                    if (!listing.vin) rowsExcludedMissingVin++;
                    if (!listing.mileage) rowsExcludedMissingMileage++;
                    if (excludedMissingRequiredSamples.length < 10) {
                        excludedMissingRequiredSamples.push({
                            listing_id: listing.listing_id,
                            listing_url: listing.listing_url,
                            title: listing.title,
                            year: listing.year,
                            make: listing.make,
                            model: listing.model,
                            state: listing.state,
                            mileage: listing.mileage,
                            has_vin: Boolean(listing.vin),
                            detail_enriched: Boolean(listing.detail_enriched),
                            rejection_reasons: missingRequiredReasons,
                        });
                    }
                    console.log(`[SKIP-REQUIRED-DATA] ${listing.title} | ${missingRequiredReasons.join(',')}`);
                    continue;
                }

                if (REJECT_PATTERNS.some((pattern) => pattern.test(listing.description || listing.title || ''))) {
                    console.log(`[SKIP-CONDITION-DETAIL] ${listing.title}`);
                    rowsExcludedPolicyAfterDetail++;
                    continue;
                }

                totalPassed++;
                console.log(`[PASS] ${listing.title} | ${bid} | ${listing.state} | ${year || '?'} ${listing.make || '?'} ${listing.model || '?'} | ${listing.mileage ?? 'mileage?'} mi | VIN ${listing.vin ? 'yes' : 'no'}`);
                allListings.push(listing);
                await Actor.pushData(listing);
            }
            
            // Check if there are more pages
            if (results.length < displayRows) break;
            
            // Small delay between pages
            await new Promise(r => setTimeout(r, 500));
            
        } catch (err) {
            console.error(`[AllSurplus] Error searching "${searchText}" page ${page}: ${err.message}`);
            break;
        }
    }
    
    // Small delay between search terms
    await new Promise(r => setTimeout(r, 1000));
}

console.log(`[ALLSURPLUS COMPLETE] Found: ${totalFound} | Passed filters: ${totalPassed} | Unique: ${seenIds.size}`);

const accountedRows = totalPassed
    + rowsExcludedDuplicate
    + rowsExcludedNonVehicle
    + rowsExcludedNonUsState
    + rowsExcludedNonUsdCurrency
    + rowsExcludedRustState
    + rowsExcludedNonTargetState
    + rowsExcludedBidRange
    + rowsExcludedAgeMileagePrefilter
    + rowsExcludedAgeMileageAfterDetail
    + rowsExcludedMissingRequiredData
    + rowsExcludedPolicyAfterDetail;

await Actor.pushData({
    record_type: 'source_quality_proof',
    source_site: 'allsurplus',
    run_id: process.env.APIFY_ACTOR_RUN_ID ?? 'local',
    generated_at: new Date().toISOString(),
    found_rows_total: totalFound,
    unique_rows_total: seenIds.size,
    pushed_rows_total: totalPassed,
    list_rows_with_vin: listRowsWithVin,
    list_rows_with_mileage: listRowsWithMileage,
    detail_pages_attempted: detailPagesAttempted,
    detail_pages_fetched: detailPagesFetched,
    detail_pages_failed: detailPagesFailed,
    detail_vins_found: detailVinsFound,
    detail_mileages_found: detailMileagesFound,
    rows_excluded_duplicate: rowsExcludedDuplicate,
    rows_excluded_non_vehicle: rowsExcludedNonVehicle,
    rows_excluded_non_us_state: rowsExcludedNonUsState,
    rows_excluded_non_usd_currency: rowsExcludedNonUsdCurrency,
    rows_excluded_rust_state: rowsExcludedRustState,
    rows_excluded_non_target_state: rowsExcludedNonTargetState,
    rows_excluded_bid_range: rowsExcludedBidRange,
    rows_excluded_age_mileage_prefilter: rowsExcludedAgeMileagePrefilter,
    rows_excluded_age_mileage_after_detail: rowsExcludedAgeMileageAfterDetail,
    rows_excluded_policy_after_detail: rowsExcludedPolicyAfterDetail,
    rows_excluded_missing_required_data: rowsExcludedMissingRequiredData,
    rows_excluded_missing_vin: rowsExcludedMissingVin,
    rows_excluded_missing_mileage: rowsExcludedMissingMileage,
    rows_excluded_unaccounted_after_prefilter: Math.max(0, totalFound - accountedRows),
    excluded_missing_required_samples: excludedMissingRequiredSamples,
});

// ── Webhook notification ──────────────────────────────────────────────────────
if (totalPassed > 0) {
    try {
        const effectiveWebhookSecret = process.env.WEBHOOK_SECRET || DEFAULT_WEBHOOK_SECRET;
        const webhookResp = await fetch('https://dealscan-insight-production.up.railway.app/api/ingest/apify', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Apify-Webhook-Secret': effectiveWebhookSecret,
            },
            body: JSON.stringify({
                source: 'allsurplus',
                actorRunId: process.env.APIFY_ACTOR_RUN_ID ?? 'local',
                itemCount: totalPassed,
                totalScraped: totalFound,
                timestamp: new Date().toISOString(),
            }),
            signal: AbortSignal.timeout(10000),
        });
        console.log(`[WEBHOOK] Notified ingest: HTTP ${webhookResp.status}`);
    } catch (err) {
        console.warn(`[WEBHOOK] Failed: ${err.message}`);
    }
}

await Actor.exit();
