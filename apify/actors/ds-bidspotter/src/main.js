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

        // DEBUG: capture actual HTML structure to find correct selectors
        const html = await page.content();
        await Actor.setValue('PAGE_HTML', html, { contentType: 'text/html' });
        const classes = await page.$$eval('[class]', els =>
            [...new Set(els.flatMap(el => Array.from(el.classList)))].slice(0, 60)
        ).catch(() => []);
        log.info('[BIDSPOTTER DEBUG] Classes: ' + classes.join(', '));

        // Use Playwright native selectors — no cheerio needed
        const listings = [];
        const selectors = ['.lot-card', '.sr_lot_item', '[data-testid="lot"]', '.auction-item', '.item-card', '.listing-card', '.vehicle-card'];

        for (const sel of selectors) {
            const count = await page.$$(sel).then(els => els.length);
            if (count > 0) {
                const extracted = await page.$$eval(sel, (els, base) => {
                    return els.map(el => ({
                        title: el.querySelector('h2,h3,.title,.lot-title')?.textContent?.trim() || '',
                        price: el.querySelector('.current-bid,.price,.amount')?.textContent?.trim() || '',
                        location: el.querySelector('.location,.lot-location,.city-state')?.textContent?.trim() || '',
                        link: el.querySelector('a')?.href || '',
                    })).filter(item => item.title.length > 3);
                }, BASE);
                listings.push(...extracted);
                break;
            }
        }

        log.info(`[BIDSPOTTER] Page ${request.userData.pageNum || 1}: ${listings.length} listings`);
        totalFound += listings.length;

        for (const listing of listings) {
            const stateMatch = listing.location.match(/\b([A-Z]{2})\b/);
            if (stateMatch && HIGH_RUST.has(stateMatch[1])) {
                const currentYear = new Date().getFullYear();
                const year = listing.year || parseInt((listing.title || '').match(/\b(20\d{2}|19[89]\d)\b/)?.[1] || '0');
                if (!(year && year >= currentYear - 2)) continue;
                console.log(`[BYPASS] Rust state ${stateMatch[1]} allowed — vehicle is ${year} (≤3yr old)`);
            }
            await Actor.pushData(listing);
            totalPassed++;
        }

        // Pagination using Playwright
        const pageNum = request.userData.pageNum || 1;
        if (pageNum < MAX_PAGES) {
            const nextHref = await page.$eval('a[rel="next"], [aria-label="Next page"]', el => el.href).catch(() => null);
            if (nextHref) {
                await crawler.addRequests([{
                    url: nextHref,
                    userData: { pageNum: pageNum + 1 }
                }]);
            }
        }
    },
});

await crawler.run([{ url: START_URL, userData: { pageNum: 1 } }]);
console.log(`[BIDSPOTTER] Found: ${totalFound} | Passed filters: ${totalPassed}`);
await Actor.exit();
