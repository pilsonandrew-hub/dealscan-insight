/**
 * ds-bidcal — BidCal Auction Scraper
 *
 * STATUS: NOT A SEPARATE SOURCE — BidCal is a HiBid white-label customer.
 *
 * Investigation results (2026-03-13):
 * - bidcal.com loads without bot protection (200 OK on all pages).
 * - However, BidCal's actual auction catalog lives at bidcal.hibid.com (HiBid white-label).
 * - All lot/item links on bidcal.com redirect to the HiBid platform.
 * - Scraping bidcal.com itself yields no lot data — only auction event listings with links
 *   into the HiBid platform where Cloudflare Turnstile is enforced.
 * - BidCal focuses on farm equipment, construction equipment, and Northern California
 *   government surplus — not primarily consumer/passenger vehicles.
 *
 * This actor should be RETIRED. The ds-hibid actor covers the HiBid platform.
 * No separate deployment needed for BidCal specifically.
 */

import { Actor } from 'apify';
import { CheerioCrawler } from 'crawlee';

const SOURCE = 'bidcal';

const BASE = 'https://www.bidcal.com';

const TARGET_STATES = new Set([
    'AZ','CA','NV','CO','NM','UT','TX','FL','GA','SC','TN','NC','VA','WA','OR','HI'
]);

const HIGH_RUST_STATES = new Set([
    'OH','MI','PA','NY','WI','MN','IL','IN','MO','IA',
    'ND','SD','NE','KS','WV','ME','NH','VT','MA','RI',
    'CT','NJ','MD','DE'
]);

const VEHICLE_KEYWORDS = ['car','truck','suv','van','pickup','sedan','coupe','wagon','vehicle','automobile','motor','4wd','awd','hybrid'];
const VEHICLE_MAKES = ['ford','chevrolet','chevy','dodge','ram','toyota','honda','nissan','jeep','gmc','chrysler',
    'hyundai','kia','subaru','mazda','volkswagen','vw','bmw','mercedes','audi','lexus','acura','infiniti',
    'cadillac','lincoln','buick','pontiac','mitsubishi','volvo','tesla','rivian','lucid','genesis'];

const SEARCH_URLS = [
    `${BASE}/?s=truck`,
    `${BASE}/?s=car+suv`,
];

await Actor.init();

const input = await Actor.getInput() ?? {};
const {
    maxPages = 20,
    minBid = 3000,
    maxBid = 35000,
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
    return match ? match[1].toUpperCase() : null;
}

function parseBid(text) {
    if (!text) return 0;
    const match = String(text).replace(/,/g, '').match(/[\d]+\.?\d*/);
    return match ? parseFloat(match[0]) : 0;
}

function parseDate(text) {
    if (!text) return null;
    try {
        const d = new Date(text);
        if (!isNaN(d.getTime())) return d.toISOString();
    } catch {}
    return null;
}

function normalizeText(text) {
    return String(text || '').replace(/\s+/g, ' ').trim();
}

function toAbsoluteUrl(href) {
    if (!href) return null;
    try {
        return new URL(href, BASE).toString();
    } catch {
        return null;
    }
}

function isLikelyDetailUrl(url) {
    if (!url) return false;
    const normalized = url.toLowerCase();
    if (normalized.includes('#')) return false;
    return normalized.includes('hibid.com') ||
        /\/(auction|auctions|listing|listings|item|items|lot|lots)\b/.test(normalized);
}

function applyFilters(listing, log) {
    if (!isVehicle(listing.title)) {
        log.debug(`[SKIP] Not a vehicle: ${listing.title}`);
        return false;
    }
    const state = listing.state;
    if (state && HIGH_RUST_STATES.has(state)) {
        const currentYear = new Date().getFullYear();
        if (listing.year && listing.year >= currentYear - 2) {
            log.info(`[BYPASS] Rust state ${state} allowed — vehicle is ${listing.year} (≤3yr old)`);
        } else {
            log.debug(`[SKIP] High-rust state: ${state} — ${listing.title}`);
            return false;
        }
    }
    if (state && !targetStateSet.has(state)) {
        log.debug(`[SKIP] Out-of-target state: ${state}`);
        return false;
    }
    if (listing.current_bid > 0 && listing.current_bid < minBid) {
        log.debug(`[SKIP] Bid too low: $${listing.current_bid}`);
        return false;
    }
    if (listing.current_bid > 0 && listing.current_bid > maxBid) {
        log.debug(`[SKIP] Bid too high: $${listing.current_bid}`);
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

const crawler = new CheerioCrawler({
    maxRequestsPerCrawl: maxPages * 3 + 50,
    requestHandlerTimeoutSecs: 60,
    maxConcurrency: 2,
    minConcurrency: 1,

    async requestHandler({ $, request, enqueueLinks, log }) {
        const url = request.url;
        log.info(`[BidCal] Processing: ${url}`);

        if (request.label === 'DETAIL') {
            await handleDetailPage($, request, log);
            return;
        }

        // LIST page — BidCal auction cards and gallery pages
        const listingLinks = [];

        for (const selector of ['.auction-card a', '.listing a', 'h2 a', '.item-title a', `a[href*='auction']`]) {
            $(selector).each((_, el) => {
                const abs = toAbsoluteUrl($(el).attr('href'));
                if (isLikelyDetailUrl(abs)) listingLinks.push(abs);
            });
            if (listingLinks.length > 0) break;
        }

        const inlineListings = [];
        $('[class*="auction-listing"]').each((_, card) => {
            const el = $(card);
            const title = normalizeText(el.find('h3').first().text());
            if (!title || !isVehicle(title)) return;

            const bidText = normalizeText(el.find('.price, [class*="price"], [class*="amount"]').first().text());
            const bid = parseBid(bidText);
            const locationText = normalizeText(el.find('.listing-location, .listing-location a').first().text());
            const state = parseState(locationText);
            const endText = normalizeText(el.find('.listing-date, .listing-time, time').first().text());
            const auctionHouse = 'BidCal';
            const linkEl = el.find('a[href^="/auctions/gallery/"]').first();
            const href = linkEl.attr('href') || '';
            const listingUrl = href ? (href.startsWith('http') ? href : `${BASE}${href}`) : url;
            const imgEl = el.find('.listing-images img, img').first();
            const imageUrl = imgEl.attr('data-src') || imgEl.attr('src') || null;

            const { year, make, model } = parseVehicleTitle(title);
            const listing = {
                listing_id: `bidcal-inline-${Buffer.from(listingUrl).toString('base64').slice(0, 16)}`,
                title,
                current_bid: bid,
                buy_now_price: null,
                auction_end_date: parseDate(endText),
                state,
                city: locationText.split(',')[0].trim() || null,
                listing_url: listingUrl,
                image_url: imageUrl,
                auction_house: auctionHouse || null,
                mileage: null,
                vin: null,
                year,
                make,
                model,
                source: SOURCE,
                scraped_at: new Date().toISOString(),
            };

            if (applyFilters(listing, log)) {
                totalAfterFilters++;
                log.info(`[PASS-INLINE] ${listing.title} | $${listing.current_bid} | ${listing.state}`);
                allListings.push(listing);
                inlineListings.push(listing);
            }
            totalFound++;
        });
        for (const listing of inlineListings) {
            await Actor.pushData(listing);
        }

        const uniqueLinks = [...new Set(listingLinks)];
        log.info(`Found ${uniqueLinks.length} detail links on page`);
        totalFound += uniqueLinks.length;

        if (uniqueLinks.length > 0) {
            await enqueueLinks({
                urls: uniqueLinks,
                label: 'DETAIL',
            });
        }

        // Pagination
        const currentPage = request.userData?.pageNum ?? 1;
        if (currentPage < maxPages) {
            // Try next page link first
            const nextHref = $('a[rel="next"], a[aria-label*="Next"], [class*="pagination"] a[class*="next"]').attr('href');
            if (nextHref) {
                const nextAbs = nextHref.startsWith('http') ? nextHref : `${BASE}${nextHref}`;
                await enqueueLinks({
                    urls: [nextAbs],
                    label: 'LIST',
                    userData: { pageNum: currentPage + 1 },
                });
            } else if (uniqueLinks.length > 0) {
                const nextUrl = new URL(url);
                nextUrl.searchParams.set('page', currentPage + 1);
                await enqueueLinks({
                    urls: [nextUrl.toString()],
                    label: 'LIST',
                    userData: { pageNum: currentPage + 1 },
                });
            }
        }
    },
});

async function handleDetailPage($, request, log) {
    const title = $('section.masthead h1, h1, .gallery-header h1')
        .first().text().trim() ||
        $('title').text().split('|')[0].trim();

    if (!title) {
        log.debug(`[SKIP] No title: ${request.url}`);
        return;
    }

    // Current bid
    let bidText = '';
    for (const sel of ['.current-bid', '[class*="current-bid"]', '[class*="high-bid"]',
                        '[class*="current-price"]', '.bid-amount', '[class*="bid-value"]']) {
        const t = $(sel).first().text().trim();
        if (t) { bidText = t; break; }
    }
    if (!bidText) {
        $('td, th, dt, label, span').each((_, el) => {
            if ($(el).text().match(/current\s*bid|high\s*bid|current\s*price/i)) {
                bidText = $(el).next().text().trim() ||
                          $(el).parent().next().text().trim();
            }
        });
    }
    const bid = parseBid(bidText);

    // Location / city / state
    let location = '';
    for (const sel of ['.listing-location', '.listing-location a', '[class*="location"]',
                        '.auction-location', '[class*="address"]']) {
        const t = $(sel).first().text().trim();
        if (t) { location = t; break; }
    }

    // Auction house
    let auctionHouse = '';
    for (const sel of ['.header-logo a', '[class*="auction-house"]', '[class*="company"]', '[class*="seller"]', '.auctioneer']) {
        const t = $(sel).first().text().trim();
        if (t) { auctionHouse = t; break; }
    }

    // End date
    let endText = '';
    for (const sel of ['[class*="end-time"]', '[class*="closes"]', '[data-end]', '.auction-end',
                        '.close-date', 'time[datetime]']) {
        const el = $(sel).first();
        endText = el.attr('data-end') || el.attr('datetime') || el.text().trim();
        if (endText) break;
    }

    // Image
    const imgEl = $('ul.gallery-thumbs a.gallery-item img, img.listing-image, img.lot-photo, .gallery img').first();
    const imageUrl = imgEl.attr('data-src') || imgEl.attr('src') || null;

    // ID from URL
    const idMatch = request.url.match(/\/auctions\/gallery\/(\d+)$/i) ||
                    request.url.match(/catalog\/(\d+)\//i) ||
                    request.url.match(/\/(auction|lot|listing|item)\/([a-z0-9\-]+)/i);
    const itemId = idMatch ? `bidcal-${idMatch[2] || idMatch[1]}` : `bidcal-${Date.now()}`;

    // Description for mileage/VIN
    const description = normalizeText($('body').text());
    const mileageMatch = description.match(/(\d[\d,]+)\s*(?:miles?|mi\.?)\b/i);
    const mileage = mileageMatch ? parseInt(mileageMatch[1].replace(/,/g, '')) : null;
    const vinMatch = description.match(/\bVIN[:\s#]*([A-HJ-NPR-Z0-9]{17})\b/i) ||
                     description.match(/\b([A-HJ-NPR-Z0-9]{17})\b/);
    const vin = vinMatch ? vinMatch[1] : null;

    const state = parseState(location);
    const city = location.split(',')[0].trim() || null;
    const { year, make, model } = parseVehicleTitle(title);

    const listing = {
        listing_id: itemId,
        title,
        current_bid: bid,
        buy_now_price: null,
        auction_end_date: parseDate(endText),
        state,
        city,
        listing_url: request.url,
        image_url: imageUrl,
        auction_house: auctionHouse || null,
        mileage,
        vin,
        year,
        make,
        model,
        source: SOURCE,
        scraped_at: new Date().toISOString(),
    };

    if (!applyFilters(listing, log)) return;

    totalAfterFilters++;
    log.info(`[PASS] ${listing.title} | $${listing.current_bid} | ${listing.state}`);
    allListings.push(listing);
    await Actor.pushData(listing);
}

const log = { info: console.log, debug: () => {}, error: console.error };

await crawler.run(
    SEARCH_URLS.map((url, i) => ({
        url,
        label: 'LIST',
        userData: { pageNum: 1 },
        uniqueKey: `list-start-${i}`,
    }))
);

console.log(`[BIDCAL COMPLETE] Found: ${totalFound} | Passed filters: ${totalAfterFilters}`);

await Actor.exit();
