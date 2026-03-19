console.log('[BIDSPOTTER] Actor starting...');
import { Actor } from 'apify';
import { PlaywrightCrawler } from 'crawlee';

const SOURCE = 'bidspotter';
const BASE = 'https://www.bidspotter.com';
const START_URL = `${BASE}/en-us/for-sale/automotive-and-vehicles`;
const MAX_PAGES = 10;

const HIGH_RUST = new Set([
    'OH','MI','PA','NY','WI','MN','IL','IN','MO','IA','ND','SD','NE','KS',
    'WV','ME','NH','VT','MA','RI','CT','NJ','MD','DE',
]);

await Actor.init();

const proxyConfiguration = await Actor.createProxyConfiguration({
    groups: ['RESIDENTIAL'],
    countryCode: 'US',
});

let totalFound = 0;
let totalPassed = 0;

const crawler = new PlaywrightCrawler({
    proxyConfiguration,
    maxRequestsPerCrawl: MAX_PAGES * 50 + 10,
    maxConcurrency: 1,
    requestHandlerTimeoutSecs: 120,
    launchContext: {
        launchOptions: {
            headless: true,
            args: [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled',
                '--disable-features=IsolateOrigins,site-per-process',
            ],
        },
    },
    async requestHandler({ page, request, log, enqueueLinks }) {
        // Override webdriver detection
        await page.addInitScript(() => {
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
        });

        await page.waitForLoadState('domcontentloaded');

        // Handle Cloudflare challenge
        const title = await page.title();
        if (title.includes('Just a moment') || title.includes('Cloudflare')) {
            log.info('[BIDSPOTTER] Cloudflare detected, waiting 15s...');
            await page.waitForTimeout(15000);
            await page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => {});
        }

        const html = await page.content();
        const $ = cheerio.load(html);

        // Try multiple selectors for BidSpotter listings
        const listings = [];
        const selectors = [
            '.lot-card', '.sr_lot_item', '[data-testid="lot"]',
            '.auction-item', '.item-card', 'article.lot',
            '.listing-card', '.vehicle-card'
        ];

        for (const sel of selectors) {
            $(sel).each((i, el) => {
                const title = $(el).find('h2,h3,.title,.lot-title').first().text().trim();
                const price = $(el).find('.current-bid,.price,.amount').first().text().trim();
                const location = $(el).find('.location,.lot-location,.city-state').first().text().trim();
                const link = $(el).find('a').first().attr('href');
                if (title && title.length > 3) {
                    listings.push({ title, price, location, link: link ? new URL(link, BASE).href : '', source: SOURCE });
                }
            });
            if (listings.length > 0) break;
        }

        log.info(`[BIDSPOTTER] Page ${request.userData.pageNum || 1}: ${listings.length} listings`);
        totalFound += listings.length;

        for (const listing of listings) {
            const stateMatch = listing.location.match(/\b([A-Z]{2})\b/);
            if (stateMatch && HIGH_RUST.has(stateMatch[1])) continue;
            await Actor.pushData(listing);
            totalPassed++;
        }

        // Pagination
        const pageNum = request.userData.pageNum || 1;
        if (pageNum < MAX_PAGES) {
            const nextHref = $('a[rel="next"]').attr('href') ||
                $('[aria-label="Next page"]').attr('href');
            if (nextHref) {
                await crawler.addRequests([{
                    url: new URL(nextHref, BASE).href,
                    userData: { pageNum: pageNum + 1 }
                }]);
            }
        }
    },
});

await crawler.run([{ url: START_URL, userData: { pageNum: 1 } }]);
console.log(`[BIDSPOTTER] Found: ${totalFound} | Passed filters: ${totalPassed}`);
await Actor.exit();
