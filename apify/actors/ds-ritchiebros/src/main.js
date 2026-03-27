import { Actor } from 'apify';
import { PlaywrightCrawler } from 'crawlee';

await Actor.init();
const HIGH_RUST = new Set(['OH','MI','PA','NY','WI','MN','IL','IN','MO','IA','ND','SD','NE','KS','WV','ME','NH','VT','MA','RI','CT','NJ','MD','DE']);
const CONDITION_REJECT_PATTERNS = [
    /\bsalvage\b/i,
    /\bflood\b/i,
    /\bframe[\s-]+damage\b/i,
    /\bcrash(?:ed)?\b/i,
    /\bcollision[\s-]+damage\b/i,
    /\bfire[\s-]+damage\b/i,
    /\bhail[\s-]+damage\b/i,
    /\bwont\s+start\b/i,
    /\bwon'?t\s+start\b/i,
    /\bdoes\s+not\s+start\b/i,
    /\bno[\s-]start\b/i,
    /\binop(?:erable)?\b/i,
    /\bparts[\s-]+only\b/i,
    /\bfor\s+parts\b/i,
    /\bproject\s+(?:car|vehicle|truck)\b/i,
    /\brebuilt\s+title\b/i,
    /\bstructural[\s-]+damage\b/i,
    /\bblown\s+engine\b/i,
    /\bbad\s+engine\b/i,
    /\bno\s+title\b/i,
];
let found = 0, passed = 0;

const proxyConfiguration = await Actor.createProxyConfiguration({ groups: ['RESIDENTIAL'], countryCode: 'US' });

function extractMileage(text = '') {
    const match = String(text).replace(/,/g, '').match(/\b(\d{1,3}(?:\d{3})+|\d+)\s*(?:miles?|mi\.?)\b/i);
    return match ? parseInt(match[1], 10) : null;
}

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
            if (CONDITION_REJECT_PATTERNS.some((pattern) => pattern.test((item.title || '').toLowerCase()))) continue;
            const state = item.location?.match(/\b([A-Z]{2})\b/)?.[1];
            const mileage = extractMileage(item.title || '');
            if (state && HIGH_RUST.has(state)) {
                const yearMatch = (item.title || '').match(/\b(20\d{2}|19[89]\d)\b/);
                const year = yearMatch ? parseInt(yearMatch[1]) : null;
                const currentYear = new Date().getFullYear();
                if (!(year && year >= currentYear - 2)) continue;
                log.info(`[BYPASS] Rust state ${state} allowed — vehicle is ${year} (≤3yr old)`);
            }
            const yearMatch = (item.title || '').match(/\b(20\d{2}|19[89]\d)\b/);
            const year = yearMatch ? parseInt(yearMatch[1]) : null;
            const age = new Date().getFullYear() - year;
            if (!year || age > 10 || age < 0) continue;
            if (mileage !== null && mileage > 100000) continue;
            await Actor.pushData({...item, mileage, source: 'ritchiebros'});
            passed++;
        }
    }
});

await crawler.run([{ url: 'https://www.rbauction.com/equipment-for-sale?cat=trucks-trailers-transport&country=US' }]);
console.log('[RITCHIEBROS] Found: ' + found + ' | Passed: ' + passed);
await Actor.exit();
