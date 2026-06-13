import { Actor } from 'apify';

const SOURCE = 'purplewave';
const SOURCE_TYPE = 'purplewave_proof';
const BASE_URL = 'https://www.purplewave.com';
const SEARCH_URL = `${BASE_URL}/v1/search/search`;
const CURRENT_YEAR = new Date().getFullYear();
const DEFAULT_MIN_YEAR = CURRENT_YEAR - 10;
const DEFAULT_MAX_MILEAGE = 100000;
const STANDARD_MAX_MILES_PER_YEAR = 18000;
const PREMIUM_MAX_MODEL_AGE_YEARS = 4;
const PREMIUM_MAX_MILEAGE = 50000;

const HIGH_RUST_STATES = new Set([
    'OH', 'MI', 'PA', 'NY', 'WI', 'MN', 'IL', 'IN', 'MO', 'IA',
    'ND', 'SD', 'NE', 'KS', 'WV', 'ME', 'NH', 'VT', 'MA', 'RI',
    'CT', 'NJ', 'MD', 'DE',
]);

const TITLE_ONLY_PART_PATTERNS = [
    /^\s*truck\s+bed\b/i,
    /^\s*pickup\s+bed\b/i,
    /^\s*camper\s+shell\b/i,
    /^\s*service\s+body\b/i,
    /^\s*utility\s+body\b/i,
    /^\s*tailgate\b/i,
    /^\s*tonneau(?:\s+cover)?\b/i,
];

const NON_VEHICLE_PART_PATTERNS = [
    /\bfor\s+parts\b/i,
    /\bparts\s+only\b/i,
];

const CONDITION_REJECT_PATTERNS = [
    /\bsalvage\b/i,
    /\bflood\b/i,
    /\bframe[\s-]+damage\b/i,
    /\bstructural[\s-]+damage\b/i,
    /\bno\s+title\b/i,
    /\brebuilt\s+title\b/i,
    /\bdoes\s+not\s+run\b/i,
    /\bdoes\s+not\s+start\b/i,
    /\bno[\s-]start\b/i,
    /\binop(?:erable)?\b/i,
    /\bengine\s+(?:issue|damage|knock|bad|blown)\b/i,
    /\btransmission\s+(?:issue|damage|bad)\b/i,
];

const MAKE_NORMALIZATION = new Map([
    ['CHEVROLET', 'Chevrolet'],
    ['CHEVY', 'Chevrolet'],
    ['FORD', 'Ford'],
    ['GMC', 'GMC'],
    ['DODGE', 'Dodge'],
    ['RAM', 'Ram'],
    ['TOYOTA', 'Toyota'],
    ['HONDA', 'Honda'],
    ['NISSAN', 'Nissan'],
    ['JEEP', 'Jeep'],
    ['HYUNDAI', 'Hyundai'],
    ['KIA', 'Kia'],
]);

const TITLE_MODEL_STOP_WORDS = new Set([
    'CREW', 'EXTENDED', 'REGULAR', 'CAB', 'PICKUP', 'TRUCK', 'VAN',
    'SUV', 'SEDAN', 'COUPE', 'HATCHBACK', 'WAGON', '4X4', 'AWD',
]);

function normalizeText(value) {
    return String(value ?? '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
}

function parseNumber(value) {
    if (value === null || value === undefined || value === '') return null;
    if (typeof value === 'number') return Number.isFinite(value) ? value : null;
    const match = String(value).replace(/,/g, '').match(/-?\d+(?:\.\d+)?/);
    return match ? Number(match[0]) : null;
}

function titleCaseToken(value) {
    const token = String(value ?? '').trim();
    if (!token) return '';
    if (/^\d/.test(token)) return token;
    return token.charAt(0).toUpperCase() + token.slice(1).toLowerCase();
}

function parseIdentityFromTitle(title) {
    const normalized = normalizeText(title).toUpperCase();
    const match = normalized.match(/\b((?:19|20)\d{2})\s+([A-Z]+)\s+(.+?)$/);
    if (!match) return {};
    const year = parseInt(match[1], 10);
    const make = MAKE_NORMALIZATION.get(match[2]);
    if (!Number.isFinite(year) || !make) return {};
    const model = [];
    for (const token of match[3].replace(/[()/]/g, ' ').split(/\s+/).filter(Boolean)) {
        if (TITLE_MODEL_STOP_WORDS.has(token)) break;
        model.push(titleCaseToken(token));
        if (model.length >= 3) break;
    }
    return { year, make, model: model.join(' ').trim() };
}

function parseMileage(raw) {
    const direct = parseNumber(raw);
    if (direct !== null) return direct;
    return null;
}

function parseMileageFromDescription(raw) {
    const text = normalizeText(raw);
    const match = text.match(/\b(?:miles?|odometer)\D{0,20}([\d,]{2,8})\b/i)
        ?? text.match(/\b([\d,]{2,8})\s+(?:miles?|mi)\b/i);
    return match ? parseNumber(match[1]) : null;
}

function parseLocationFromMarkup(...values) {
    const raw = values.filter(Boolean).join(' ');
    const htmlBreakMatch = raw.match(/(?:<br\s*\/?>|\n)\s*([^<>\n,]+?),\s*([A-Z]{2})\s+\d{5}\b/i)
        ?? raw.match(/(?:<br\s*\/?>|\n)\s*([^<>\n,]+?),\s*([A-Z]{2})\b/i);
    const text = normalizeText(raw);
    const match = htmlBreakMatch
        ?? text.match(/\b([A-Z][A-Za-z .'-]+),\s*([A-Z]{2})\s+\d{5}\b/)
        ?? text.match(/\b([A-Z][A-Za-z .'-]+),\s*([A-Z]{2})\b/);
    if (!match) return { city: '', state: '', location: '' };
    return {
        city: normalizeText(match[1]),
        state: match[2].toUpperCase(),
        location: `${normalizeText(match[1])}, ${match[2].toUpperCase()}`,
    };
}

function buildListingUrl(raw) {
    if (raw.url || raw.listing_url || raw.listingUrl) {
        const value = String(raw.url || raw.listing_url || raw.listingUrl);
        return value.startsWith('http') ? value : `${BASE_URL}${value.startsWith('/') ? '' : '/'}${value}`;
    }
    const auction = raw.auction || raw.auction_id || raw.auctionId;
    const item = raw.item || raw.item_id || raw.id;
    if (auction && item) {
        return `${BASE_URL}/auction/${auction}/item/${item}`;
    }
    return '';
}

function normalizePurpleWaveLot(raw) {
    const description = normalizeText(raw.description || raw.new_description || raw.additionalDescription || '');
    const parsed = parseIdentityFromTitle(raw.first_line_description || raw.title || description);
    const bid = parseNumber(raw.current_bid ?? raw.currentBid ?? raw.sortgroups?.current_bid ?? raw.bid);
    const mileage = parseMileage(raw.mileage ?? raw.miles) ?? parseMileageFromDescription(description);
    const parsedLocation = parseLocationFromMarkup(raw.description, raw.additionalDescription, raw.location);
    const state = String(raw.state || raw.location_state || parsedLocation.state || '').trim().toUpperCase();
    const city = normalizeText(raw.city || parsedLocation.city || '');
    const endTime = raw.close_date || raw.auction_timestamp || raw.auction_end_time || null;

    return {
        title: normalizeText(raw.first_line_description || raw.title || parsed.model || ''),
        year: raw.year ? Number(raw.year) : parsed.year ?? null,
        make: raw.make || parsed.make || '',
        model: raw.model || parsed.model || '',
        vin: normalizeText(raw.vin || raw.VIN || ''),
        mileage,
        current_bid: bid,
        state,
        city,
        location: normalizeText(raw.location || parsedLocation.location || [city, state].filter(Boolean).join(', ')),
        auction_end_time: endTime,
        listing_url: buildListingUrl(raw),
        source_site: SOURCE,
        source_type: SOURCE_TYPE,
        agency_name: normalizeText(raw.company || raw.entities || ''),
        description,
        photo_url: raw.image_url ? String(raw.image_url) : '',
        scraped_at: new Date().toISOString(),
    };
}

function hasCompleteIdentity(row) {
    return Boolean(row.year && row.make && row.model && row.vin && row.mileage !== null);
}

function failsDealerScopeAgeMileageGate(year, mileage, minYear, maxMileage) {
    const numericYear = Number(year);
    const numericMileage = Number(mileage);
    if (!numericYear || numericYear < minYear) return true;
    if (!numericMileage || numericMileage <= 0) return false;
    if (numericMileage > maxMileage) return true;
    const ageYears = Math.max(1, CURRENT_YEAR - numericYear);
    // Premium lane (<= PREMIUM_MAX_MODEL_AGE_YEARS old AND <= PREMIUM_MAX_MILEAGE) is exempt from
    // the standard-lane miles/year cap, mirroring backend determine_vehicle_tier. Without this,
    // late-model high-mileage fleet vehicles are silently dropped before scoring.
    if (ageYears <= PREMIUM_MAX_MODEL_AGE_YEARS && numericMileage <= PREMIUM_MAX_MILEAGE) return false;
    return numericMileage / ageYears > STANDARD_MAX_MILES_PER_YEAR;
}

function classifyPurpleWaveLot(row, options = {}) {
    const {
        minYear = DEFAULT_MIN_YEAR,
        maxMileage = DEFAULT_MAX_MILEAGE,
        minBid = 500,
        maxBid = 75000,
        requireMarketPrice = true,
    } = options;
    const text = `${row.title} ${row.description}`.toLowerCase();
    const title = String(row.title ?? '').toLowerCase();

    if (
        NON_VEHICLE_PART_PATTERNS.some((pattern) => pattern.test(text))
        || TITLE_ONLY_PART_PATTERNS.some((pattern) => pattern.test(title))
    ) {
        return { accepted: false, reason: 'non_vehicle_part' };
    }
    if (CONDITION_REJECT_PATTERNS.some((pattern) => pattern.test(text))) {
        return { accepted: false, reason: 'condition_policy_reject' };
    }
    if (!hasCompleteIdentity(row)) {
        return { accepted: false, reason: 'missing_required_data' };
    }
    if (failsDealerScopeAgeMileageGate(row.year, row.mileage, minYear, maxMileage)) {
        return { accepted: false, reason: 'age_mileage_prefilter' };
    }
    if (HIGH_RUST_STATES.has(row.state) && Number(row.year) < CURRENT_YEAR - 2) {
        return { accepted: false, reason: 'rust_state' };
    }
    if (!row.current_bid || row.current_bid < minBid || row.current_bid > maxBid) {
        return { accepted: false, reason: 'bid_range' };
    }
    if (requireMarketPrice && !row.market_price_evidence_id && !row.market_price_avg) {
        return { accepted: false, reason: 'missing_market_price_evidence' };
    }
    return { accepted: true, reason: 'accepted_for_proof' };
}

function buildSourceQualityProof(rows, options = {}) {
    const counts = {
        accepted_for_proof: 0,
        non_vehicle_part: 0,
        condition_policy_reject: 0,
        missing_required_data: 0,
        age_mileage_prefilter: 0,
        rust_state: 0,
        bid_range: 0,
        missing_market_price_evidence: 0,
    };
    const samples = [];

    for (const row of rows) {
        const classification = classifyPurpleWaveLot(row, options);
        counts[classification.reason] = (counts[classification.reason] ?? 0) + 1;
        if (!classification.accepted && samples.length < 8) {
            samples.push({
                title: row.title,
                year: row.year,
                make: row.make,
                model: row.model,
                vin_present: Boolean(row.vin),
                mileage: row.mileage,
                current_bid: row.current_bid,
                state: row.state,
                reason: classification.reason,
            });
        }
    }

    const acceptedRows = rows.filter((row) => classifyPurpleWaveLot(row, options).accepted);
    const pushedRows = options.fetchFailed ? [] : acceptedRows;

    return {
        record_type: 'source_quality_proof',
        source_site: SOURCE,
        source_type: SOURCE_TYPE,
        found_rows_total: rows.length,
        identity_complete_rows_total: rows.filter(hasCompleteIdentity).length,
        prefilter_passed_rows_total: counts.accepted_for_proof,
        pushed_rows_total: pushedRows.length,
        pushed_rows_with_vin: pushedRows.filter((row) => row.vin).length,
        pushed_rows_with_mileage: pushedRows.filter((row) => row.mileage !== null).length,
        pushed_rows_with_auction_end: pushedRows.filter((row) => row.auction_end_time).length,
        rows_excluded_non_vehicle_part_prefilter: counts.non_vehicle_part,
        rows_excluded_policy_prefilter: counts.condition_policy_reject,
        rows_excluded_missing_required_data: counts.missing_required_data,
        rows_excluded_age_mileage_prefilter: counts.age_mileage_prefilter,
        rows_excluded_rust_state: counts.rust_state,
        rows_excluded_bid_range: counts.bid_range,
        rows_excluded_missing_market_price: counts.missing_market_price_evidence,
        rejected_samples: samples,
        fetch_failed: Boolean(options.fetchFailed),
        fetch_error: options.fetchError || '',
        target_contract: {
            minYear: options.minYear ?? DEFAULT_MIN_YEAR,
            maxMileage: options.maxMileage ?? DEFAULT_MAX_MILEAGE,
            standardMaxMilesPerYear: STANDARD_MAX_MILES_PER_YEAR,
            minBid: options.minBid ?? 500,
            maxBid: options.maxBid ?? 75000,
            requireMarketPrice: options.requireMarketPrice ?? true,
        },
    };
}

// ── Actor runtime ───────────────────────────────────────────────────────────

async function fetchPurpleWavePage(page, perPage) {
    const params = new URLSearchParams({
        showHalted: 'false',
        dateType: 'upcoming',
        filters: 'industry_category_id:277;family_category_id:293',
        page: String(page),
        perPage: String(perPage),
        sortBy: 'current_bid-desc',
    });
    const url = `${SEARCH_URL}?${params.toString()}`;
    const response = await fetch(url, { headers: { accept: 'application/json' } });
    if (!response.ok) {
        throw new Error(`Purple Wave search failed with HTTP ${response.status}`);
    }
    const data = await response.json();
    return Array.isArray(data) ? data : data.items || data.results || [];
}

await Actor.init();

try {
    const input = await Actor.getInput() || {};
    const maxPages = Number(input.maxPages || 1);
    const perPage = Number(input.perPage || 30);
    const options = {
        minYear: Number(input.minYear || DEFAULT_MIN_YEAR),
        maxMileage: Number(input.maxMileage || DEFAULT_MAX_MILEAGE),
        minBid: Number(input.minBid || 500),
        maxBid: Number(input.maxBid || 75000),
        requireMarketPrice: input.requireMarketPrice !== false,
    };
    const rows = [];
    let fetchError = '';
    for (let page = 1; page <= maxPages; page += 1) {
        let pageRows;
        try {
            pageRows = await fetchPurpleWavePage(page, perPage);
        } catch (error) {
            fetchError = error instanceof Error ? error.message : String(error);
            break;
        }
        rows.push(...pageRows.map(normalizePurpleWaveLot));
        if (pageRows.length < perPage) break;
    }

    const proofOptions = {
        ...options,
        fetchFailed: Boolean(fetchError),
        fetchError,
    };
    const accepted = fetchError ? [] : rows.filter((row) => classifyPurpleWaveLot(row, options).accepted);
    if (!fetchError && accepted.length) {
        await Actor.pushData(accepted);
    }
    await Actor.pushData(buildSourceQualityProof(rows, proofOptions));
} finally {
    await Actor.exit();
}
