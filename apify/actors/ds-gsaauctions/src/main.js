import { Actor } from 'apify';
import { CheerioCrawler } from 'crawlee';

const WEBHOOK_URL = 'https://dealscan-insight-production.up.railway.app/api/ingest/apify';
const WEBHOOK_SECRET = 'sbEC0dNgb7Ohg3rDV';
const SOURCE = 'gsaauctions';

const BASE = 'https://gsaauctions.gov';

// Known GSA auction index endpoint
const GSA_INDEX_URL = `${BASE}/gsaauctions/aucindx`;
// Vehicle-specific search/filter
const GSA_VEHICLE_URL = `${BASE}/gsaauctions/aucindx?selloccd=&category=7170&sortorder=a&s2=Search`;
// GSA also has a data feed endpoint
const GSA_DATA_URLS = [
    `${BASE}/gsaauctions/aucindxresults?category=7170&sortorder=a`,
    `${BASE}/gsaauctions/aucindx?category=7170`,
    `${BASE}/auctions/open?category=vehicles`,
    `${BASE}/api/v1/auctions?category=vehicles`,
];

const TARGET_STATES = new Set([
    'AZ','CA','NV','CO','NM','UT','TX','FL','GA','SC','TN','NC','VA','WA','OR','HI'
]);

const HIGH_RUST_STATES = new Set([
    'OH','MI','PA','NY','WI','MN','IL','IN','MO','IA',
    'ND','SD','NE','KS','WV','ME','NH','VT','MA','RI',
    'CT','NJ','MD','DE'
]);

const VEHICLE_KEYWORDS = ['car','truck','suv','van','pickup','sedan','coupe','wagon','vehicle','automobile','motor','4wd','awd'];
const VEHICLE_MAKES = ['ford','chevrolet','chevy','dodge','ram','toyota','honda','nissan','jeep','gmc','chrysler',
    'hyundai','kia','subaru','mazda','volkswagen','vw','bmw','mercedes','audi','lexus','acura','infiniti',
    'cadillac','lincoln','buick','pontiac','mitsubishi','volvo','tesla'];

// GSA vehicle category codes
const GSA_VEHICLE_CATEGORIES = ['7170', '7105', '7110', '7115', '7120', '7125', '7130', '7135'];

await Actor.init();

const input = await Actor.getInput() ?? {};
const {
    maxPages = 20,
    minBid = 1000,
    maxMileage = 50000,
    minYear = 2022,
    targetStates = [...TARGET_STATES],
} = input;

const targetStateSet = new Set(targetStates.map(s => s.toUpperCase()));
const allListings = [];
let totalFound = 0;
let totalAfterFilters = 0;

function isVehicle(title) {
    const lower = title.toLowerCase();
    return VEHICLE_KEYWORDS.some(kw => lower.includes(kw)) ||
           VEHICLE_MAKES.some(make => lower.includes(make));
}

function parseVehicleTitle(title) {
    const yearMatch = title.match(/\b(20\d{2}|19[89]\d)\b/);
    const year = yearMatch ? parseInt(yearMatch[1]) : null;

    let make = null;
    let model = null;
    const lower = title.toLowerCase();

    for (const m of VEHICLE_MAKES) {
        if (lower.includes(m)) {
            make = m.charAt(0).toUpperCase() + m.slice(1);
            if (make === 'Chevy') make = 'Chevrolet';
            if (make === 'Vw') make = 'Volkswagen';
            const makeIdx = lower.indexOf(m);
            const afterMake = title.slice(makeIdx + m.length).trim();
            const modelMatch = afterMake.match(/^([A-Za-z0-9\-]+(?:\s+[A-Za-z0-9\-]+)?)/);
            if (modelMatch) model = modelMatch[1].trim();
            break;
        }
    }

    return { year, make, model };
}

function parseState(text) {
    if (!text) return null;
    const match = text.match(/,\s*([A-Z]{2})\b/) ||
                  text.match(/\b([A-Z]{2})\s*\d{5}/) ||
                  text.match(/\b([A-Z]{2})\b/);
    if (match) {
        const st = match[1].toUpperCase();
        // Validate it looks like a US state (not random 2-letter match)
        const allStates = new Set([
            'AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA','HI','ID','IL','IN','IA',
            'KS','KY','LA','ME','MD','MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ',
            'NM','NY','NC','ND','OH','OK','OR','PA','RI','SC','SD','TN','TX','UT','VT',
            'VA','WA','WV','WI','WY','DC'
        ]);
        return allStates.has(st) ? st : null;
    }
    return null;
}

function parseBid(text) {
    if (!text) return 0;
    const match = String(text).replace(/,/g, '').match(/[\d]+\.?\d*/);
    return match ? parseFloat(match[0]) : 0;
}

function parseDate(text) {
    if (!text) return null;
    try {
        // Handle GSA date format: "MM/DD/YYYY" or "MM/DD/YYYY HH:MM"
        const mmddyyyy = text.match(/(\d{1,2})\/(\d{1,2})\/(\d{4})/);
        if (mmddyyyy) {
            const d = new Date(`${mmddyyyy[3]}-${mmddyyyy[1].padStart(2,'0')}-${mmddyyyy[2].padStart(2,'0')}`);
            if (!isNaN(d.getTime())) return d.toISOString();
        }
        const d = new Date(text);
        if (!isNaN(d.getTime())) return d.toISOString();
    } catch {}
    return null;
}

function applyFilters(listing, log) {
    if (!isVehicle(listing.title)) {
        log.debug(`[SKIP] Not a vehicle: ${listing.title}`);
        return false;
    }
    const state = listing.state;
    if (state && HIGH_RUST_STATES.has(state)) {
        log.debug(`[SKIP] High-rust state: ${state} — ${listing.title}`);
        return false;
    }
    if (state && !targetStateSet.has(state)) {
        log.debug(`[SKIP] Out-of-target state: ${state}`);
        return false;
    }
    if (listing.current_bid > 0 && listing.current_bid < minBid) {
        log.debug(`[SKIP] Bid too low: $${listing.current_bid}`);
        return false;
    }
    if (listing.year && listing.year < minYear) {
        log.debug(`[SKIP] Too old: ${listing.year}`);
        return false;
    }
    if (listing.mileage && listing.mileage > maxMileage) {
        log.debug(`[SKIP] Too many miles: ${listing.mileage}`);
        return false;
    }
    return true;
}

// Try JSON API endpoints first
async function tryApiFetch(log) {
    for (const endpoint of GSA_DATA_URLS) {
        try {
            log.info(`[GSA] Trying API: ${endpoint}`);
            const res = await fetch(endpoint, {
                headers: {
                    'Accept': 'application/json',
                    'User-Agent': 'Mozilla/5.0 (compatible; DealerScope/1.0)',
                },
                signal: AbortSignal.timeout(10000),
            });

            if (!res.ok) continue;
            const ct = res.headers.get('content-type') || '';
            if (!ct.includes('json')) continue;

            const data = await res.json();
            const items = Array.isArray(data) ? data :
                          data.auctions ?? data.items ?? data.results ?? data.data ?? [];

            if (!Array.isArray(items) || items.length === 0) continue;

            log.info(`[GSA] API returned ${items.length} items`);

            for (const item of items) {
                totalFound++;
                const title = item.title || item.itemDescription || item.description || item.name || '';
                const location = item.location || item.city || item.address || '';
                const stateRaw = item.state || item.stateCode || item.state_cd || parseState(location);
                const state = stateRaw ? stateRaw.toUpperCase().trim() : null;
                const bid = parseBid(item.currentBid || item.current_bid || item.highBid || item.bid || 0);
                const { year, make, model } = parseVehicleTitle(title);

                const listing = {
                    listing_id: String(item.id || item.auctionId || item.lotId || `gsa-api-${totalFound}`),
                    title,
                    current_bid: bid,
                    buy_now_price: null,
                    auction_end_date: parseDate(item.closeDate || item.endDate || item.auctionEnd || null),
                    state,
                    listing_url: item.url || item.auctionUrl || `${BASE}/gsaauctions/aucdetail?auctionId=${item.id}`,
                    image_url: item.imageUrl || item.photo || null,
                    mileage: item.mileage ? parseInt(item.mileage) : null,
                    vin: item.vin || null,
                    year,
                    make,
                    model,
                    scraped_at: new Date().toISOString(),
                };

                if (applyFilters(listing, log)) {
                    totalAfterFilters++;
                    log.info(`[PASS] ${listing.title} | $${listing.current_bid} | ${listing.state}`);
                    allListings.push(listing);
                    await Actor.pushData(listing);
                }
            }
            return true;
        } catch (err) {
            log.debug(`[GSA] API attempt failed: ${endpoint} — ${err.message}`);
        }
    }
    return false;
}

// Web crawler for GSA Auctions HTML pages
const crawler = new CheerioCrawler({
    maxRequestsPerCrawl: maxPages * 3 + 50,
    requestHandlerTimeoutSecs: 60,
    maxConcurrency: 1, // GSA is a government site — be gentle
    // Respect rate limits
    minConcurrency: 1,

    async requestHandler({ $, request, enqueueLinks, log }) {
        const url = request.url;
        log.info(`[GSA] Processing: ${url}`);

        if (request.label === 'DETAIL') {
            await handleDetailPage($, request, log);
            return;
        }

        // LIST page — GSA auction index
        // GSA uses a table-based layout with rows for each auction lot
        const detailLinks = [];

        // Primary pattern: links to aucdetail pages
        $('a[href*="aucdetail"], a[href*="auctionDetail"], a[href*="lotDetail"]').each((_, el) => {
            const href = $(el).attr('href');
            if (!href) return;
            const abs = href.startsWith('http') ? href : `${BASE}${href}`;
            detailLinks.push(abs);
        });

        // Fallback: table rows with clickable lot titles
        if (detailLinks.length === 0) {
            $('table.aucTable tr, table[class*="auction"] tr, .auction-list tr').each((_, row) => {
                const link = $(row).find('a').first();
                const href = link.attr('href');
                if (!href) return;
                const abs = href.startsWith('http') ? href : `${BASE}${href}`;
                detailLinks.push(abs);
            });
        }

        // Also try direct lot extraction from the index table
        const tableRows = extractTableListings($, request.url, log);
        for (const listing of tableRows) {
            if (applyFilters(listing, log)) {
                totalAfterFilters++;
                log.info(`[PASS-TABLE] ${listing.title} | $${listing.current_bid} | ${listing.state}`);
                allListings.push(listing);
                await Actor.pushData(listing);
            }
        }

        const uniqueLinks = [...new Set(detailLinks)];
        log.info(`Found ${uniqueLinks.length} detail links on page`);
        totalFound += uniqueLinks.length;

        if (uniqueLinks.length > 0) {
            await enqueueLinks({
                urls: uniqueLinks,
                label: 'DETAIL',
            });
        }

        // Pagination — GSA uses form-based pagination with "Next" links or page params
        const nextLink = $('a:contains("Next"), a[rel="next"], a[href*="page="]').last();
        const nextHref = nextLink.attr('href');
        const currentPage = request.userData?.pageNum ?? 1;

        if (nextHref && currentPage < maxPages) {
            const abs = nextHref.startsWith('http') ? nextHref : `${BASE}${nextHref}`;
            await enqueueLinks({
                urls: [abs],
                label: 'LIST',
                userData: { pageNum: currentPage + 1 },
            });
        } else if (uniqueLinks.length > 0 && currentPage < maxPages) {
            // Try numeric pagination
            const nextUrl = new URL(url);
            const currentPageNum = parseInt(nextUrl.searchParams.get('page') || '1');
            nextUrl.searchParams.set('page', currentPageNum + 1);
            await enqueueLinks({
                urls: [nextUrl.toString()],
                label: 'LIST',
                userData: { pageNum: currentPage + 1 },
            });
        }
    },
});

function extractTableListings($, sourceUrl, log) {
    const listings = [];

    // GSA table rows typically have: Lot#, Description, Location, End Date, Current Bid
    $('table tr').each((i, row) => {
        if (i === 0) return; // Skip header row
        const cells = $(row).find('td');
        if (cells.length < 3) return;

        // Extract cells by position or content
        let title = '';
        let location = '';
        let endText = '';
        let bidText = '';
        let lotId = '';
        let listingUrl = sourceUrl;

        cells.each((j, cell) => {
            const text = $(cell).text().trim();
            const link = $(cell).find('a').first();
            const href = link.attr('href');

            if (j === 0) {
                // Often lot number
                lotId = text;
            } else if (j === 1 || (link.length && href && href.includes('aucdetail'))) {
                // Title/description cell
                title = text.slice(0, 200);
                if (href) {
                    listingUrl = href.startsWith('http') ? href : `${BASE}${href}`;
                }
            } else if (text.match(/,\s*[A-Z]{2}/) || text.match(/\b[A-Z]{2}\s+\d{5}/)) {
                // Location-like cell
                location = text;
            } else if (text.match(/\d{1,2}\/\d{1,2}\/\d{4}/)) {
                // Date-like cell
                endText = text;
            } else if (text.match(/^\$[\d,]+/) || text.match(/^[\d,]+\.?\d*$/)) {
                // Bid amount cell
                bidText = text;
            }
        });

        if (!title || title.length < 3) return;

        const state = parseState(location);
        const bid = parseBid(bidText);
        const { year, make, model } = parseVehicleTitle(title);

        listings.push({
            listing_id: lotId || `gsa-table-${i}-${Date.now()}`,
            title,
            current_bid: bid,
            buy_now_price: null,
            auction_end_date: parseDate(endText),
            state,
            listing_url: listingUrl,
            image_url: null,
            mileage: null,
            vin: null,
            year,
            make,
            model,
            scraped_at: new Date().toISOString(),
        });
    });

    return listings;
}

async function handleDetailPage($, request, log) {
    // GSA detail page — lot info
    const title = $('h1, .lot-title, .auction-title, [class*="item-title"]').first().text().trim() ||
                  $('title').text().split('|')[0].trim();

    if (!title) {
        log.debug(`[SKIP] No title: ${request.url}`);
        return;
    }

    // Bid amount — GSA often has "Current Bid: $X,XXX" in a table
    let bidText = '';
    $('td, th, dt, label, .field-label').each((_, el) => {
        const text = $(el).text().trim();
        if (text.match(/current\s*bid|high\s*bid/i)) {
            const next = $(el).next('td, dd, .field-value');
            bidText = next.text().trim() || $(el).parent().next('tr').find('td').first().text().trim();
        }
    });
    if (!bidText) {
        for (const sel of ['.current-bid', '[class*="current-bid"]', '#currentBid', '[class*="high-bid"]']) {
            const t = $(sel).first().text().trim();
            if (t) { bidText = t; break; }
        }
    }
    const bid = parseBid(bidText);

    // Location
    let location = '';
    $('td, th, dt, label').each((_, el) => {
        const text = $(el).text().trim();
        if (text.match(/^location$/i) || text.match(/pickup\s*location/i)) {
            const next = $(el).next('td, dd');
            location = next.text().trim() || $(el).parent().next('tr').find('td').first().text().trim();
        }
    });
    if (!location) {
        for (const sel of ['[class*="location"]', '.pickup-location', '.auction-location']) {
            const t = $(sel).first().text().trim();
            if (t) { location = t; break; }
        }
    }

    // End date
    let endText = '';
    $('td, th, dt, label').each((_, el) => {
        const text = $(el).text().trim();
        if (text.match(/close\s*date|end\s*date|auction\s*end/i)) {
            const next = $(el).next('td, dd');
            endText = next.text().trim() || $(el).parent().next('tr').find('td').first().text().trim();
        }
    });
    if (!endText) {
        for (const sel of ['[class*="close-date"]', '[class*="end-date"]', '.auction-end']) {
            const t = $(sel).first().attr('datetime') || $(sel).first().text().trim();
            if (t) { endText = t; break; }
        }
    }

    // Image
    const imgEl = $('img.lot-image, img.item-photo, .main-image img, .lot-photo img, #mainImage').first();
    const imageUrl = imgEl.attr('data-src') || imgEl.attr('src') || null;

    // Lot ID from URL
    const idMatch = request.url.match(/[Ll]ot[Ii]d=(\d+)/) ||
                    request.url.match(/[Aa]uction[Ii]d=(\d+)/) ||
                    request.url.match(/\/(\d+)\/?(?:\?|$)/);
    const lotId = idMatch ? idMatch[1] : `gsa-${Date.now()}`;

    // Description for mileage/VIN
    const description = $('[class*="description"], #description, .lot-description, .item-description').text();
    const pageText = $('body').text();
    const mileageMatch = (description || pageText).match(/(\d[\d,]+)\s*(?:miles?|mi\.?|odometer)\b/i);
    const mileage = mileageMatch ? parseInt(mileageMatch[1].replace(/,/g, '')) : null;
    const vinMatch = (description || pageText).match(/\bVIN[:\s#]*([A-HJ-NPR-Z0-9]{17})\b/i) ||
                     pageText.match(/\b([A-HJ-NPR-Z0-9]{17})\b/);
    const vin = vinMatch ? vinMatch[1] : null;

    const state = parseState(location);
    const { year, make, model } = parseVehicleTitle(title);

    const listing = {
        listing_id: lotId,
        title,
        current_bid: bid,
        buy_now_price: null,
        auction_end_date: parseDate(endText),
        state,
        listing_url: request.url,
        image_url: imageUrl,
        mileage,
        vin,
        year,
        make,
        model,
        scraped_at: new Date().toISOString(),
    };

    if (!applyFilters(listing, log)) return;

    totalAfterFilters++;
    log.info(`[PASS] ${listing.title} | $${listing.current_bid} | ${listing.state}`);
    allListings.push(listing);
    await Actor.pushData(listing);
}

async function sendWebhook(listings, log) {
    if (listings.length === 0) {
        log.info('[Webhook] No listings to send.');
        return;
    }

    const payload = { source: SOURCE, listings };

    try {
        log.info(`[Webhook] Sending ${listings.length} listings to ${WEBHOOK_URL}`);
        const response = await fetch(WEBHOOK_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Apify-Webhook-Secret': WEBHOOK_SECRET,
            },
            body: JSON.stringify(payload),
        });
        if (!response.ok) {
            const body = await response.text().catch(() => '');
            console.error(`[Webhook] Failed: HTTP ${response.status} — ${body}`);
        } else {
            console.log(`[Webhook] Success: HTTP ${response.status}`);
        }
    } catch (err) {
        console.error(`[Webhook] Error: ${err.message}`);
    }
}

const log = { info: console.log, debug: () => {}, error: console.error };

// Try API first
const apiSuccess = await tryApiFetch(log);

if (!apiSuccess) {
    console.log('[GSA] API not available — crawling HTML');

    // Build start URLs for all vehicle category codes
    const startUrls = GSA_VEHICLE_CATEGORIES.map((cat, i) => ({
        url: `${GSA_INDEX_URL}?selloccd=&category=${cat}&sortorder=a&s2=Search`,
        label: 'LIST',
        userData: { pageNum: 1, category: cat },
        uniqueKey: `gsa-list-cat-${cat}`,
    }));

    // Also try the main vehicle URL
    startUrls.push({
        url: GSA_VEHICLE_URL,
        label: 'LIST',
        userData: { pageNum: 1 },
        uniqueKey: 'gsa-list-main',
    });

    await crawler.run(startUrls);
}

console.log(`[GSA COMPLETE] Found: ${totalFound} | Passed filters: ${totalAfterFilters}`);

await sendWebhook(allListings, log);

await Actor.exit();
