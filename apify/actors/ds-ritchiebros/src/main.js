import { Actor } from 'apify';
import { PlaywrightCrawler } from 'crawlee';

await Actor.init();
const HIGH_RUST = new Set(['OH','MI','PA','NY','WI','MN','IL','IN','MO','IA','ND','SD','NE','KS','WV','ME','NH','VT','MA','RI','CT','NJ','MD','DE']);
let found = 0, passed = 0;

const proxyConfiguration = await Actor.createProxyConfiguration({ groups: ['RESIDENTIAL'], countryCode: 'US' });

const crawler = new PlaywrightCrawler({
    proxyConfiguration,
    maxRequestsPerCrawl: 30,
    maxConcurrency: 1,
    requestHandlerTimeoutSecs: 90,
    async requestHandler({ page, log }) {
        await page.waitForLoadState('domcontentloaded');
        await page.waitForTimeout(3000);
        const items = await page.$$eval('article, [class*="item"], [class*="lot"], [class*="result"], [data-testid]', els => 
            els.map(el => ({ title: el.querySelector('h2,h3,h4')?.textContent?.trim() || '', location: el.textContent?.match(/[A-Z]{2}/)?.input?.slice(0,50) || '' })).filter(i => i.title.length > 5)
        ).catch(() => []);
        log.info('[RITCHIEBROS] Found: ' + items.length);
        found += items.length;
        for (const item of items) {
            const state = item.location?.match(/\b([A-Z]{2})\b/)?.[1];
            if (state && HIGH_RUST.has(state)) {
                const yearMatch = (item.title || '').match(/\b(20\d{2}|19[89]\d)\b/);
                const year = yearMatch ? parseInt(yearMatch[1]) : null;
                const currentYear = new Date().getFullYear();
                if (!(year && year >= currentYear - 2)) continue;
                log.info(`[BYPASS] Rust state ${state} allowed — vehicle is ${year} (≤3yr old)`);
            }
            await Actor.pushData({...item, source: 'ritchiebros'});
            passed++;
        }
    }
});

await crawler.run([{ url: 'https://www.rbauction.com/equipment-for-sale?cat=trucks-trailers-transport&country=US' }]);
console.log('[RITCHIEBROS] Found: ' + found + ' | Passed: ' + passed);
await Actor.exit();
