import { Actor } from 'apify';
import { PlaywrightCrawler } from 'crawlee';

const HIGH_RUST_STATES = new Set([
    'OH','MI','PA','NY','WI','MN','IL','IN','MO','IA',
    'ND','SD','NE','KS','WV','ME','NH','VT','MA','RI',
    'CT','NJ','MD','DE'
]);

// catid=57 = Vehicles & Transportation on PublicSurplus
const BASE_URL = 'https://www.publicsurplus.com/sms/browse/cataucs?catid=57&page={PAGE}';

await Actor.init();

const input = await Actor.getInput() ?? {};
const {
    maxPages = 10,
    minBid = 500,
    maxBid = 35000,
    targetStates = ['AZ','CA','NV','CO','NM','UT','TX','FL','GA','SC','TN','NC','VA','WA','OR','HI'],
} = input;

let totalFound = 0;
let totalAfterFilters = 0;

const crawler = new PlaywrightCrawler({
    launchContext: {
        launchOptions: {
            headless: true,
        },
    },
    maxRequestsPerCrawl: maxPages * 2 + 50,

    async requestHandler({ page, request, enqueueLinks, log }) {
        const url = request.url;
        log.info(`Processing: ${url}`);

        if (request.label === 'DETAIL') {
            await handleDetailPage(page, request, log);
            return;
        }

        // Listing page — wait for auction rows or table
        await page.waitForSelector('table tr a, a[href*="/sms/auction/view"], body', { timeout: 30000 });

        // Extract listing rows from PublicSurplus table layout
        const listings = await page.evaluate(() => {
            const links = [];
            // Primary: PublicSurplus auction detail links
            document.querySelectorAll('a[href*="/sms/auction/view"]').forEach(a => links.push(a.href));
            // Secondary: table rows with auction links (odd/even row classes)
            if (links.length === 0) {
                const rows = document.querySelectorAll('table tr.odd, table tr.even, table tr');
                rows.forEach(row => {
                    const link = row.querySelector('a[href*="auction"]');
                    if (link && link.href.includes('/sms/')) links.push(link.href);
                });
            }
            return [...new Set(links)];
        });

        log.info(`Found ${listings.length} listing links on page`);
        totalFound += listings.length;

        if (listings.length > 0) {
            await enqueueLinks({
                urls: listings,
                label: 'DETAIL',
            });
        }

        // Pagination
        const currentPage = request.userData?.pageNum ?? 1;
        if (listings.length > 0 && currentPage < maxPages) {
            const nextPageUrl = BASE_URL.replace('{PAGE}', currentPage + 1);
            await enqueueLinks({
                urls: [nextPageUrl],
                label: 'LIST',
                userData: { pageNum: currentPage + 1 },
            });
        }
    },
});

async function handleDetailPage(page, request, log) {
    await page.waitForSelector('body', { timeout: 30000 });

    const data = await page.evaluate(() => {
        const getText = (selector) => {
            const el = document.querySelector(selector);
            return el ? el.textContent.trim() : '';
        };

        // Item number from URL
        const urlMatch = window.location.href.match(/auctionId=(\d+)/i) ||
                         window.location.href.match(/\/(\d+)\/?$/);
        const itemNumber = urlMatch ? urlMatch[1] : '';

        // Title
        const title = getText('h1.auc-title, h1, .auction-title, [class*="title"]') ||
                      document.title.split('|')[0].trim();

        // Current bid
        const bidSelectors = [
            '.current-bid', '[class*="current-bid"]', '#high-bid-amount',
            '[class*="high-bid"]', '.bid-value'
        ];
        let currentBidText = '';
        for (const sel of bidSelectors) {
            const el = document.querySelector(sel);
            if (el) { currentBidText = el.textContent; break; }
        }
        // Fallback: search for "$X,XXX" pattern near "Current Bid" label
        if (!currentBidText) {
            const labels = document.querySelectorAll('td, th, dt, .label');
            labels.forEach(label => {
                if (label.textContent.match(/current\s*bid/i)) {
                    const next = label.nextElementSibling || label.parentElement?.nextElementSibling;
                    if (next) currentBidText = next.textContent;
                }
            });
        }
        const bidMatch = currentBidText.match(/[\d,]+\.?\d*/);
        const currentBid = bidMatch ? parseFloat(bidMatch[0].replace(/,/g, '')) : 0;

        // Location — PublicSurplus shows "City, ST" format
        const locationSelectors = [
            '.auction-location', '[class*="location"]',
            'td[data-label="Location"]', '.seller-location'
        ];
        let location = '';
        for (const sel of locationSelectors) {
            const el = document.querySelector(sel);
            if (el) { location = el.textContent.trim(); break; }
        }
        // Fallback: scan table for Location label
        if (!location) {
            const cells = document.querySelectorAll('td, th');
            cells.forEach((cell, i) => {
                if (cell.textContent.match(/^location$/i)) {
                    const next = cells[i + 1];
                    if (next) location = next.textContent.trim();
                }
            });
        }

        const stateMatch = location.match(/,\s*([A-Z]{2})\s*(\d{5})?$/i) ||
                           location.match(/\b([A-Z]{2})\b/);
        const state = stateMatch ? stateMatch[1].toUpperCase() : '';

        // End time
        const endSelectors = ['.auc-ends', '[class*="end-time"]', '[data-end]', '.countdown'];
        let auctionEndTime = '';
        for (const sel of endSelectors) {
            const el = document.querySelector(sel);
            if (el) { auctionEndTime = el.getAttribute('data-end') || el.textContent.trim(); break; }
        }

        // Photo
        const imgEl = document.querySelector('#main-photo img, .auc-photo img, [class*="photo"] img, .gallery img');
        const photoUrl = imgEl ? (imgEl.getAttribute('data-src') || imgEl.src) : null;

        // Description
        const descEl = document.querySelector('.auc-description, #description, [class*="description"]');
        const description = descEl ? descEl.textContent.trim().slice(0, 1000) : '';

        // Agency / seller
        const agencySelectors = ['.agency-name', '[class*="agency"]', '.seller-name', '[class*="seller"]'];
        let agencyName = '';
        for (const sel of agencySelectors) {
            const el = document.querySelector(sel);
            if (el) { agencyName = el.textContent.trim(); break; }
        }

        return { title, currentBid, location, state, auctionEndTime, photoUrl, description, agencyName, itemNumber };
    });

    const bid = data.currentBid || 0;
    const state = data.state || '';

    // Apply filters
    if (HIGH_RUST_STATES.has(state)) {
        log.debug(`Skipping high-rust state: ${state} — ${data.title}`);
        return;
    }
    if (bid < minBid || bid > maxBid) {
        log.debug(`Skipping out-of-range bid $${bid} — ${data.title}`);
        return;
    }
    if (!data.title) {
        log.debug(`Skipping listing with no title: ${request.url}`);
        return;
    }

    const vehicle = {
        title: data.title,
        current_bid: bid,
        buyer_premium: 0.10,
        doc_fee: 50,
        auction_end_time: data.auctionEndTime || null,
        location: data.location,
        state,
        listing_url: request.url,
        item_number: data.itemNumber || '',
        photo_url: data.photoUrl || null,
        description: data.description || '',
        agency_name: data.agencyName || '',
        source_site: 'publicsurplus',
        scraped_at: new Date().toISOString(),
    };

    totalAfterFilters++;
    log.info(`[PASS] ${vehicle.title} | $${vehicle.current_bid} | ${vehicle.state}`);
    await Actor.pushData(vehicle);
}

// Start crawl from page 1
const startUrl = BASE_URL.replace('{PAGE}', '1');
await crawler.run([
    { url: startUrl, label: 'LIST', userData: { pageNum: 1 } },
]);

console.log(`[PUBLICSURPLUS COMPLETE] Found: ${totalFound} | Passed filters: ${totalAfterFilters}`);

await Actor.exit();
