import { Actor } from 'apify';
import { PlaywrightCrawler } from 'crawlee';

const HIGH_RUST_STATES = new Set([
    'OH','MI','PA','NY','WI','MN','IL','IN','MO','IA',
    'ND','SD','NE','KS','WV','ME','NH','VT','MA','RI',
    'CT','NJ','MD','DE'
]);

// catid=4 = Motor Pool on PublicSurplus
const BASE_URL = 'https://www.publicsurplus.com/sms/all,wa/browse/cataucs?catid=4&page={PAGE}';

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

function normalizeText(value) {
    return String(value ?? '')
        .replace(/\u00a0/g, ' ')
        .replace(/[ \t]+/g, ' ')
        .replace(/\s*\n\s*/g, '\n')
        .trim();
}

function parseMoney(value) {
    const match = normalizeText(value).match(/\$?([\d,]+(?:\.\d+)?)/);
    return match ? parseFloat(match[1].replace(/,/g, '')) : 0;
}

function parseAuctionDate(value) {
    const normalized = normalizeText(value);
    if (!normalized) return null;

    const parsed = new Date(normalized);
    return Number.isNaN(parsed.getTime()) ? normalized : parsed.toISOString();
}

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

        await page.waitForSelector('#auctionTableView tbody tr[id$="catList"], a[href*="/auction/view?auc="], body', { timeout: 30000 });

        const listings = await page.evaluate(() => {
            const rows = Array.from(document.querySelectorAll('#auctionTableView tbody tr[id$="catList"]'));

            return rows.map((row) => {
                const titleLink = row.querySelector('td.text-start a[href*="/auction/view?auc="]');
                if (!titleLink) return null;

                const title = titleLink.textContent?.trim() ?? '';
                const bidText = row.querySelector('td[id^="val_"]')?.textContent ?? '';
                const location = row.querySelector('td.text-success.fw-bold')?.textContent?.trim() ?? '';
                const endDate = row.querySelector('.auction-time_left span, [id^="timeLeftValue"]')?.textContent?.trim() ?? '';
                const itemNumber = row.querySelector('td:first-child')?.textContent?.trim() ?? '';

                return {
                    itemNumber,
                    title,
                    currentBid: bidText,
                    location,
                    endDate,
                    listingUrl: titleLink.href,
                };
            }).filter(Boolean);
        });

        log.info(`Found ${listings.length} listing rows on page`);
        totalFound += listings.length;

        if (listings.length > 0) {
            await enqueueLinks({
                urls: listings.map((listing) => listing.listingUrl),
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
        const lines = document.body.innerText
            .replace(/\u00a0/g, ' ')
            .split('\n')
            .map((line) => line.trim())
            .filter(Boolean);

        const findLineValue = (label) => {
            const normalizedLabel = label.toLowerCase();
            const index = lines.findIndex((line) => {
                const lower = line.toLowerCase();
                return lower === normalizedLabel || lower.startsWith(`${normalizedLabel}:`);
            });

            if (index === -1) return '';

            const inlineValue = lines[index].slice(label.length).replace(/^[:\s-]+/, '').trim();
            if (inlineValue) return inlineValue;

            return lines[index + 1] ?? '';
        };

        const titleLine = lines.find((line) => /^Auction #\d+\s+-\s+/.test(line)) ?? '';
        const title = titleLine.replace(/^Auction #\d+\s+-\s+/, '').trim() || document.title.split(':').slice(1).join(':').trim();

        const itemNumber = window.location.href.match(/[?&]auc=(\d+)/i)?.[1] ?? '';
        const currentBid = findLineValue('Current Price');
        const state = findLineValue('Region');

        const pickupIndex = lines.findIndex((line) => line.toLowerCase() === 'pick-up location');
        const locationLines = pickupIndex === -1 ? [] : lines.slice(pickupIndex + 1).filter((line) => {
            const lower = line.toLowerCase();
            return ![
                'auction contact',
                'payment',
                'shipping',
                'bid on item',
                'region:',
            ].includes(lower);
        });
        const location = locationLines.slice(0, 2).join(' ').trim();

        const descriptionStart = lines.findIndex((line) => line.toLowerCase() === 'description');
        const descriptionEnd = lines.findIndex((line) => line.toLowerCase() === 'online payment instructions');
        const description = descriptionStart === -1
            ? ''
            : lines
                .slice(descriptionStart + 1, descriptionEnd === -1 ? descriptionStart + 16 : descriptionEnd)
                .join(' ')
                .trim();

        const agencyLink = Array.from(document.querySelectorAll('a[href]')).find((anchor) => /View .* Auctions/i.test(anchor.textContent ?? ''));
        const agencyName = agencyLink
            ? (agencyLink.textContent ?? '').replace(/^\[?View\s+/i, '').replace(/\s+Auctions\]?$/i, '').trim()
            : '';

        const photo = Array.from(document.querySelectorAll('img'))
            .map((img) => img.getAttribute('data-src') || img.getAttribute('src') || '')
            .find((src) => /cloudfront|docviewer|thumb/i.test(src));

        return {
            title,
            currentBid,
            location,
            state,
            auctionEndTime: findLineValue('Auction Ends'),
            photoUrl: photo || null,
            description,
            agencyName,
            itemNumber,
        };
    });

    const bid = parseMoney(data.currentBid);
    const state = normalizeText(data.state).toUpperCase().slice(0, 2);
    const title = normalizeText(data.title);

    // Apply filters
    if (HIGH_RUST_STATES.has(state)) {
        log.debug(`Skipping high-rust state: ${state} - ${title}`);
        return;
    }
    if (bid < minBid || bid > maxBid) {
        log.debug(`Skipping out-of-range bid $${bid} - ${title}`);
        return;
    }
    if (!title) {
        log.debug(`Skipping listing with no title: ${request.url}`);
        return;
    }

    const vehicle = {
        title,
        current_bid: bid,
        buyer_premium: 0.10,
        doc_fee: 50,
        auction_end_time: parseAuctionDate(data.auctionEndTime),
        location: normalizeText(data.location),
        state,
        listing_url: request.url,
        item_number: normalizeText(data.itemNumber),
        photo_url: data.photoUrl || null,
        description: normalizeText(data.description),
        agency_name: normalizeText(data.agencyName),
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
