import { Actor } from 'apify';
import { PlaywrightCrawler } from 'crawlee';

const HIGH_RUST_STATES = new Set([
    'OH','MI','PA','NY','WI','MN','IL','IN','MO','IA',
    'ND','SD','NE','KS','WV','ME','NH','VT','MA','RI',
    'CT','NJ','MD','DE'
]);

const BASE_URL = 'https://www.govdeals.com/index.cfm?fa=Main.AdvSearchResultsNew&searchPg={PAGE}&category=1050&sortBy=ad&sortOrder=D';

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

        // Check if this is a listing detail page
        if (request.label === 'DETAIL') {
            await handleDetailPage(page, request, log);
            return;
        }

        // Listing page — extract vehicle cards
        await page.waitForSelector('body', { timeout: 30000 });

        // Extract listing links
        const listings = await page.evaluate(() => {
            const cards = document.querySelectorAll('.auction-results-body .col-xs-12.col-sm-6.col-md-4, .item-card, [class*="auction-item"], a[href*="itemDetail"]');
            const results = [];
            cards.forEach(card => {
                const link = card.querySelector('a[href*="itemDetail"]') || (card.tagName === 'A' ? card : null);
                if (link) {
                    results.push(link.href);
                }
            });
            return [...new Set(results)];
        });

        log.info(`Found ${listings.length} listing links on page`);
        totalFound += listings.length;

        // Also try to extract data directly from listing cards if available
        const cardData = await page.evaluate((minBid, maxBid) => {
            const items = [];
            // GovDeals search results layout
            const rows = document.querySelectorAll('.search-results-item, .result-item, [class*="lot-"], tr[class*="row"]');
            rows.forEach(row => {
                try {
                    const titleEl = row.querySelector('.item-title, h3, h4, [class*="title"]');
                    const bidEl = row.querySelector('.current-bid, [class*="bid"], [class*="price"]');
                    const locEl = row.querySelector('.location, [class*="location"], [class*="city"]');
                    const linkEl = row.querySelector('a[href*="itemDetail"], a[href*="item"]');
                    const imgEl = row.querySelector('img');
                    const endEl = row.querySelector('.end-time, [class*="end"], [class*="closes"]');

                    if (!linkEl) return;

                    const bidText = bidEl ? bidEl.textContent.trim() : '';
                    const bidMatch = bidText.match(/[\d,]+/);
                    const bid = bidMatch ? parseFloat(bidMatch[0].replace(/,/g, '')) : 0;

                    items.push({
                        title: titleEl ? titleEl.textContent.trim() : '',
                        current_bid: bid,
                        location: locEl ? locEl.textContent.trim() : '',
                        listing_url: linkEl ? linkEl.href : '',
                        photo_url: imgEl ? imgEl.src : null,
                        auction_end_time: endEl ? endEl.textContent.trim() : null,
                    });
                } catch (e) {}
            });
            return items;
        }, minBid, maxBid);

        // If we got card data directly, process it
        for (const item of cardData) {
            if (item.listing_url) {
                // Queue detail page for full data extraction
                await enqueueLinks({
                    urls: [item.listing_url],
                    label: 'DETAIL',
                    userData: { partialData: item },
                });
            }
        }

        // If no card data, queue the listing links we found
        if (cardData.length === 0 && listings.length > 0) {
            await enqueueLinks({
                urls: listings,
                label: 'DETAIL',
            });
        }

        // Handle pagination
        const currentPage = request.userData?.pageNum ?? 1;
        if (currentPage < maxPages) {
            const nextPageUrl = BASE_URL.replace('{PAGE}', currentPage + 1);
            await enqueueLinks({
                urls: [nextPageUrl],
                label: 'LIST',
                userData: { pageNum: currentPage + 1 },
            });
        }
    },
});

// Add detail page handler
crawler.router.addHandler('DETAIL', async ({ page, request, log }) => {
    await handleDetailPage(page, request, log);
});

async function handleDetailPage(page, request, log) {
    await page.waitForSelector('body', { timeout: 30000 });

    const partialData = request.userData?.partialData ?? {};

    const data = await page.evaluate(() => {
        const getText = (selector) => {
            const el = document.querySelector(selector);
            return el ? el.textContent.trim() : '';
        };

        // Extract item number from URL or page
        const urlMatch = window.location.href.match(/itemNumber=(\d+)/i) || window.location.href.match(/item[_-]?(\d+)/i);
        const itemNumber = urlMatch ? urlMatch[1] : '';

        // Title
        const title = getText('h1, .item-title, [class*="item-title"], .auction-title') ||
                      getText('.page-header h2') || getText('title').split('|')[0].trim();

        // Current bid
        const bidSelectors = ['.current-bid-amount', '[class*="current-bid"]', '[class*="high-bid"]', '.bid-amount'];
        let currentBidText = '';
        for (const sel of bidSelectors) {
            const el = document.querySelector(sel);
            if (el) { currentBidText = el.textContent; break; }
        }
        const bidMatch = currentBidText.match(/[\d,]+\.?\d*/);
        const currentBid = bidMatch ? parseFloat(bidMatch[0].replace(/,/g, '')) : 0;

        // Location
        const locationSelectors = ['.item-location', '[class*="location"]', '[data-label="Location"]'];
        let location = '';
        for (const sel of locationSelectors) {
            const el = document.querySelector(sel);
            if (el) { location = el.textContent.trim(); break; }
        }

        // State extraction from location
        const stateMatch = location.match(/,\s*([A-Z]{2})\s*(\d{5})?$/i) ||
                           location.match(/\b([A-Z]{2})\b\s*\d{5}/i);
        const state = stateMatch ? stateMatch[1].toUpperCase() : '';

        // End time
        const endSelectors = ['.auction-ends', '[class*="end-time"]', '[class*="closes"]', '.countdown'];
        let auctionEndTime = '';
        for (const sel of endSelectors) {
            const el = document.querySelector(sel);
            if (el) { auctionEndTime = el.getAttribute('data-end') || el.textContent.trim(); break; }
        }

        // Photo
        const imgEl = document.querySelector('.item-photo img, .auction-photo img, [class*="item-image"] img, .gallery img');
        const photoUrl = imgEl ? (imgEl.getAttribute('data-src') || imgEl.src) : null;

        // Description
        const descEl = document.querySelector('.item-description, [class*="description"], #description');
        const description = descEl ? descEl.textContent.trim().slice(0, 1000) : '';

        // Agency
        const agencySelectors = ['.agency-name', '[class*="agency"]', '[class*="seller"]'];
        let agencyName = '';
        for (const sel of agencySelectors) {
            const el = document.querySelector(sel);
            if (el) { agencyName = el.textContent.trim(); break; }
        }

        return { title, currentBid, location, state, auctionEndTime, photoUrl, description, agencyName, itemNumber };
    });

    const bid = data.currentBid || partialData.current_bid || 0;
    const state = data.state || extractStateFromLocation(partialData.location || '');
    const location = data.location || partialData.location || '';

    // Apply filters
    if (HIGH_RUST_STATES.has(state)) {
        log.debug(`Skipping high-rust state: ${state} — ${data.title}`);
        return;
    }
    if (bid < minBid || bid > maxBid) {
        log.debug(`Skipping out-of-range bid $${bid} — ${data.title}`);
        return;
    }
    if (!data.title && !partialData.title) {
        log.debug(`Skipping listing with no title: ${request.url}`);
        return;
    }

    const vehicle = {
        title: data.title || partialData.title || '',
        current_bid: bid,
        buyer_premium: 0.125,
        doc_fee: 75,
        auction_end_time: data.auctionEndTime || partialData.auction_end_time || null,
        location,
        state,
        listing_url: request.url,
        item_number: data.itemNumber || '',
        photo_url: data.photoUrl || partialData.photo_url || null,
        description: data.description || '',
        agency_name: data.agencyName || '',
        source_site: 'govdeals',
        scraped_at: new Date().toISOString(),
    };

    totalAfterFilters++;
    log.info(`[PASS] ${vehicle.title} | $${vehicle.current_bid} | ${vehicle.state}`);
    await Actor.pushData(vehicle);
}

function extractStateFromLocation(location) {
    const match = location.match(/,\s*([A-Z]{2})\s*(\d{5})?$/i);
    return match ? match[1].toUpperCase() : '';
}

// Start crawl from page 1
const startUrl = BASE_URL.replace('{PAGE}', '1');
await crawler.run([
    { url: startUrl, label: 'LIST', userData: { pageNum: 1 } },
]);

log.info(`[SUMMARY] Total listings found: ${totalFound} | After filters: ${totalAfterFilters}`);
console.log(`[GOVDEALS COMPLETE] Found: ${totalFound} | Passed filters: ${totalAfterFilters}`);

await Actor.exit();
