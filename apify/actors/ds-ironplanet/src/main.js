import { Actor } from 'apify';
import { PlaywrightCrawler } from 'crawlee';

const HIGH_RUST_STATES = ['AK', 'ME', 'NH', 'VT', 'NY', 'MI', 'WI', 'MN', 'ND', 'SD', 'WV', 'OH', 'PA', 'MA', 'CT', 'RI', 'NJ', 'DE', 'MD'];
const MAX_MILEAGE = 50000;
const MAX_AGE_YEARS = 4;
const CURRENT_YEAR = new Date().getFullYear();

await Actor.init();

const proxyConfiguration = await Actor.createProxyConfiguration({
  groups: ['RESIDENTIAL'],
});

const crawler = new PlaywrightCrawler({
  proxyConfiguration,
  maxRequestsPerCrawl: 50,
  requestHandlerTimeoutSecs: 120,
  launchContext: {
    launchOptions: {
      headless: true,
    },
  },
  async requestHandler({ page, request, enqueueLinks, log }) {
    log.info(`Processing: ${request.url}`);

    await page.waitForLoadState('networkidle', { timeout: 60000 });

    // Extract listings
    const listings = await page.evaluate(() => {
      const items = [];
      const cards = document.querySelectorAll('[class*="item-card"], [class*="lot-card"], [class*="listing-card"], .search-result-item, [data-testid*="lot"], [class*="asset-card"]');

      cards.forEach(card => {
        try {
          const titleEl = card.querySelector('[class*="title"], h2, h3, [class*="name"]');
          const priceEl = card.querySelector('[class*="price"], [class*="bid"], [class*="amount"]');
          const locationEl = card.querySelector('[class*="location"], [class*="city"], [class*="state"]');
          const dateEl = card.querySelector('[class*="date"], [class*="end"], [class*="auction-date"], time');
          const linkEl = card.querySelector('a[href]');
          const mileageEl = card.querySelector('[class*="mileage"], [class*="meter"], [class*="odometer"]');
          const yearEl = card.querySelector('[class*="year"]');

          if (titleEl) {
            items.push({
              title: titleEl.textContent?.trim() || '',
              current_bid: priceEl?.textContent?.trim() || '',
              location: locationEl?.textContent?.trim() || '',
              end_date: dateEl?.textContent?.trim() || dateEl?.getAttribute('datetime') || '',
              listing_url: linkEl?.href || '',
              mileage_text: mileageEl?.textContent?.trim() || '',
              year_text: yearEl?.textContent?.trim() || '',
              source: 'ironplanet',
            });
          }
        } catch (e) {}
      });
      return items;
    });

    log.info(`Found ${listings.length} raw listings on page`);

    // Filter listings
    const filtered = listings.filter(item => {
      // Filter by HIGH_RUST states
      const locationUpper = item.location.toUpperCase();
      const stateMatch = locationUpper.match(/,\s*([A-Z]{2})(\s|$)/);
      if (stateMatch && HIGH_RUST_STATES.includes(stateMatch[1])) {
        return false;
      }

      // Filter by mileage
      const mileageMatch = item.mileage_text.replace(/,/g, '').match(/(\d+)/);
      if (mileageMatch) {
        const mileage = parseInt(mileageMatch[1]);
        if (mileage > MAX_MILEAGE) return false;
      }

      // Filter by age
      const yearMatch = (item.title + ' ' + item.year_text).match(/\b(20\d{2}|19\d{2})\b/);
      if (yearMatch) {
        const year = parseInt(yearMatch[1]);
        if (CURRENT_YEAR - year > MAX_AGE_YEARS) return false;
      }

      return true;
    });

    log.info(`${filtered.length} listings after filtering`);

    for (const item of filtered) {
      delete item.mileage_text;
      delete item.year_text;
      await Actor.pushData(item);
    }

    // Pagination - look for next page button
    const currentPage = request.userData.page || 1;
    if (currentPage < 10) {
      const nextPageExists = await page.evaluate((currentPage) => {
        // Try to find next page link or button
        const nextBtn = document.querySelector('[aria-label="Next page"], [class*="next"]:not([disabled]), [class*="pagination"] a[rel="next"]');
        if (nextBtn) return true;

        // Check URL-based pagination
        return false;
      }, currentPage);

      if (nextPageExists) {
        const nextUrl = new URL(request.url);
        // IronPlanet uses hash-based URLs, try page parameter
        const hash = nextUrl.hash;
        const newHash = hash.includes('page=')
          ? hash.replace(/page=\d+/, `page=${currentPage + 1}`)
          : hash + `&page=${currentPage + 1}`;
        nextUrl.hash = newHash;

        await crawler.addRequests([{
          url: nextUrl.toString(),
          userData: { page: currentPage + 1 },
        }]);
      }
    }
  },
  failedRequestHandler({ request, log }) {
    log.error(`Request failed: ${request.url}`);
  },
});

await crawler.run([{
  url: 'https://www.ironplanet.com/search#!?category=Trucks+%26+Trailers',
  userData: { page: 1 },
}]);

await Actor.exit();
