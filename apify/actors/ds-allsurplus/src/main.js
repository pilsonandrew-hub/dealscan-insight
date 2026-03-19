import { Actor } from 'apify';

// AllSurplus Maestro API - reverse-engineered from JS bundle
const MAESTRO_URL = 'https://maestro.lqdt1.com';
const MAESTRO_API_KEY = 'af93060f-337e-428c-87b8-c74b5837d6cd';
const MAESTRO_SUBSCRIPTION_KEY = 'cf620d1d8f904b5797507dc5fd1fdb80';
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
    
    // Auto-qualify on category
    if (catLower.match(/\b(pickup|sedan|suv|coupe|convertible|hatchback|crossover|passenger car|vehicles?\s*misc|cars?\s*&|automobile)\b/)) {
        return true;
    }
    
    // Reject non-vehicles
    for (const pattern of REJECT_PATTERNS) {
        if (pattern.test(lower)) return false;
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

await Actor.init();

const input = await Actor.getInput() ?? {};
// Age gate: ingest.py allows max 4 years old for AllSurplus
// Calculate dynamic minYear to match the gate (current year - 4)
const currentYear = new Date().getFullYear();
const defaultMinYear = currentYear - 4;

const {
    maxSearchPages = 5,
    displayRows = 50,
    minBid = 3000,
    maxBid = 35000,
    maxMileage = 50000,
    minYear = defaultMinYear,
    targetStatesOnly = false,
    allowHighRust = false,
    searchTerms = VEHICLE_SEARCHES,
} = input;

const sessionId = `ds-allsurplus-${Date.now()}`;
const seenIds = new Set();
const allListings = [];
let totalFound = 0;
let totalPassed = 0;

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
                if (seenIds.has(itemId)) continue;
                seenIds.add(itemId);
                
                const title = (item.assetShortDescription || '').trim();
                const categoryDesc = item.categoryDescription || '';
                
                // Vehicle check
                if (!isVehicle(title, categoryDesc)) {
                    continue;
                }
                
                // State check - must be US state
                const state = parseState(item.locationState);
                if (!state) {
                    console.log(`[SKIP] Non-US state: ${item.locationState} — ${title}`);
                    continue;
                }
                
                // Currency check - must be USD
                if (item.currencyCode && item.currencyCode !== 'USD') {
                    console.log(`[SKIP] Non-USD currency: ${item.currencyCode} — ${title}`);
                    continue;
                }
                
                const year = item.modelYear ? parseInt(item.modelYear) : null;

                if (!allowHighRust && HIGH_RUST_STATES.has(state)) {
                    if (year && year >= currentYear - 2) {
                        console.log(`[BYPASS] Rust state ${state} allowed — vehicle is ${year} (≤3yr old)`);
                    } else {
                        console.log(`[SKIP] High-rust state: ${state} — ${title}`);
                        continue;
                    }
                }

                if (targetStatesOnly && !TARGET_STATES.has(state)) {
                    console.log(`[SKIP] Non-target state: ${state}`);
                    continue;
                }

                const bid = parseBid(item.currentBid);

                if (bid > 0 && bid < minBid) {
                    console.log(`[SKIP] Bid too low: $${bid} — ${title}`);
                    continue;
                }
                if (bid > 0 && bid > maxBid) {
                    console.log(`[SKIP] Bid too high: $${bid} — ${title}`);
                    continue;
                }

                if (year && year < minYear) {
                    console.log(`[SKIP] Too old: ${year} — ${title}`);
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
                    mileage: null, // not available from search list API
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
                
                totalPassed++;
                console.log(`[PASS] ${title} | $${bid} | ${state} | ${year || '?'} ${item.makebrand || '?'} ${item.model || '?'}`);
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

await Actor.exit();
