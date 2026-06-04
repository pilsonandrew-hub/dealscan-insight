const SEO_BASE_URL = 'https://prod-seo.govdeals.com';
const GOVDEALS_BASE_URL = 'https://www.govdeals.com';
const ASSET_PATH_PATTERN = /\/en\/asset\/(\d+)\/(\d+)/gi;

function htmlDecode(value) {
    return String(value || '')
        .replace(/&amp;/g, '&')
        .replace(/&quot;/g, '"')
        .replace(/&#39;/g, "'")
        .replace(/&lt;/g, '<')
        .replace(/&gt;/g, '>');
}

function numeric(value) {
    if (value === null || value === undefined || value === '') return null;
    const parsed = Number(String(value).replace(/[^0-9.-]/g, ''));
    return Number.isFinite(parsed) ? parsed : null;
}

function parseDateIso(value) {
    if (!value) return null;
    const parsed = new Date(String(value));
    return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
}

function arrayify(value) {
    return Array.isArray(value) ? value : [value];
}

function schemaTypeMatches(schema, type) {
    const values = arrayify(schema?.['@type']).map(item => String(item || '').toLowerCase());
    return values.includes(type.toLowerCase());
}

function findVehicleSchema(value) {
    if (!value || typeof value !== 'object') return null;
    if (schemaTypeMatches(value, 'Vehicle')) return value;
    for (const key of ['@graph', 'itemListElement']) {
        const children = value[key];
        if (Array.isArray(children)) {
            for (const child of children) {
                const found = findVehicleSchema(child?.item || child);
                if (found) return found;
            }
        }
    }
    return null;
}

function jsonLdBlocks(html) {
    const blocks = [];
    const pattern = /<script\b[^>]*type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi;
    for (const match of html.matchAll(pattern)) {
        const text = htmlDecode(match[1]).trim();
        if (!text) continue;
        try {
            blocks.push(JSON.parse(text));
        } catch (_) {}
    }
    return blocks;
}

function extractDataValue(html, id) {
    const pattern = new RegExp(`<[^>]+id=["']${id}["'][^>]*data-value=["']([^"']+)["'][^>]*>`, 'i');
    return numeric(htmlDecode(html.match(pattern)?.[1] || ''));
}

function canonicalAssetUrl(url) {
    const match = String(url || '').match(/\/en\/asset\/(\d+)\/(\d+)/i);
    return match ? `${SEO_BASE_URL}/en/asset/${match[1]}/${match[2]}` : null;
}

function makeFromSchema(schema) {
    const brand = schema?.brand;
    if (typeof brand === 'string') return brand;
    if (brand?.name) return brand.name;
    const title = String(schema?.name || '');
    for (const candidate of ['Ford', 'Chevrolet', 'Ram']) {
        if (new RegExp(`\\b${candidate}\\b`, 'i').test(title)) return candidate;
    }
    return '';
}

function stateFromAddress(address) {
    if (!address || typeof address !== 'object') return '';
    return address.addressRegion || address.addressState || address.region || '';
}

export function seoSearchUrl(searchText) {
    return `${SEO_BASE_URL}/en/search?keyword=${encodeURIComponent(String(searchText || '').trim())}&timing=completed`;
}

export function extractSeoAssetUrls(html, limit = null) {
    const urls = [];
    const seen = new Set();
    for (const match of String(html || '').matchAll(ASSET_PATH_PATTERN)) {
        const url = `${SEO_BASE_URL}/en/asset/${match[1]}/${match[2]}`;
        if (seen.has(url)) continue;
        seen.add(url);
        urls.push(url);
        if (Number.isFinite(Number(limit)) && Number(limit) > 0 && urls.length >= Number(limit)) break;
    }
    return urls;
}

export function parseGovDealsSeoAsset(html, assetUrl) {
    const schema = jsonLdBlocks(String(html || ''))
        .map(findVehicleSchema)
        .find(Boolean);
    if (!schema) return null;

    const offer = Array.isArray(schema.offers) ? schema.offers[0] : schema.offers;
    const availability = String(offer?.availability || '');
    if (!availability.toLowerCase().includes('soldout')) return null;

    const canonicalUrl = canonicalAssetUrl(assetUrl) || canonicalAssetUrl(offer?.url) || canonicalAssetUrl(schema.url);
    if (!canonicalUrl) return null;
    const assetMatch = canonicalUrl.match(/\/en\/asset\/(\d+)\/(\d+)/i);
    const seller = schema.seller || {};
    const address = seller.address || {};
    const auction = schema.subjectOf || {};
    const saleDate = parseDateIso(auction.endDate);
    const hammerPrice = numeric(offer?.price);
    const soldAmount = extractDataValue(html, 'lblSoldAmount');
    const totalPrice = extractDataValue(html, 'lblTotalAmount');

    return {
        assetId: assetMatch[1],
        accountId: assetMatch[2],
        assetShortDescription: schema.name || '',
        title: schema.name || '',
        makebrand: makeFromSchema(schema),
        make: makeFromSchema(schema),
        model: schema.model || '',
        modelYear: numeric(schema.vehicleModelDate),
        year: numeric(schema.vehicleModelDate),
        winningBid: hammerPrice,
        soldPrice: hammerPrice,
        currentBid: hammerPrice,
        sold_price: hammerPrice,
        sold_price_all_in: soldAmount || totalPrice || hammerPrice,
        total_price: totalPrice,
        price_basis: soldAmount ? 'source_sold_amount_with_visible_fees' : 'source_reported',
        currency: offer?.priceCurrency || 'USD',
        locationCity: address.addressLocality || '',
        locationState: stateFromAddress(address),
        city: address.addressLocality || '',
        state: stateFromAddress(address),
        auctionEndUtc: saleDate,
        auction_end_time: saleDate,
        sale_date: saleDate,
        url: canonicalUrl.replace(SEO_BASE_URL, GOVDEALS_BASE_URL),
        listing_url: canonicalUrl.replace(SEO_BASE_URL, GOVDEALS_BASE_URL),
        displaySellerName: seller.name || auction.organizer?.name || '',
        seller: seller.name || auction.organizer?.name || '',
        imageUrl: schema.image || '',
        vin: schema.vehicleIdentificationNumber || null,
        meterCount: numeric(schema.mileageFromOdometer?.value),
        mileage: numeric(schema.mileageFromOdometer?.value),
        source_site: 'govdeals-sold',
        source_discovery: 'govdeals-seo',
    };
}
