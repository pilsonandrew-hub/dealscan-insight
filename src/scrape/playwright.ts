/**
 * Playwright Network Shaping - Fast headless scraping
 * Blocks unnecessary resources and optimizes for speed
 */

import { chromium, type Browser, type Page, type BrowserContext } from 'playwright';
import { logger } from '@/lib/logger';

interface PlaywrightOptions {
  headless?: boolean;
  timeout?: number;
  viewport?: { width: number; height: number };
  userAgent?: string;
  blockResources?: boolean;
  waitUntil?: 'load' | 'domcontentloaded' | 'networkidle';
  extraHeaders?: Record<string, string>;
  retries?: number;
}

interface ScrapingResult {
  html: string;
  url: string;
  title: string;
  loadTime: number;
  blockedRequests: number;
  totalRequests: number;
  errors: string[];
  metadata: {
    finalUrl: string;
    statusCode: number;
    responseHeaders: Record<string, string>;
    redirects: string[];
  };
}

class PlaywrightScraper {
  private browser: Browser | null = null;
  private context: BrowserContext | null = null;

  /**
   * Initialize browser instance
   */
  async initialize(): Promise<void> {
    if (this.browser) return;

    try {
      this.browser = await chromium.launch({
        headless: true,
        args: [
          '--no-sandbox',
          '--disable-setuid-sandbox',
          '--disable-dev-shm-usage',
          '--disable-accelerated-2d-canvas',
          '--no-first-run',
          '--no-zygote',
          '--disable-gpu',
          '--disable-web-security',
          '--disable-features=VizDisplayCompositor'
        ]
      });

      this.context = await this.browser.newContext({
        userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        viewport: { width: 1920, height: 1080 },
        ignoreHTTPSErrors: true
      });

      logger.info('Playwright browser initialized');
    } catch (error) {
      logger.error('Failed to initialize Playwright browser', error);
      throw error;
    }
  }

  /**
   * Scrape a single URL with optimizations
   */
  async scrape(url: string, options: PlaywrightOptions = {}): Promise<ScrapingResult> {
    const startTime = performance.now();
    let blockedRequests = 0;
    let totalRequests = 0;
    const errors: string[] = [];
    const redirects: string[] = [];

    const {
      headless = true,
      timeout = 12000,
      viewport = { width: 1920, height: 1080 },
      userAgent,
      blockResources = true,
      waitUntil = 'networkidle',
      extraHeaders = {},
      retries = 2
    } = options;

    await this.initialize();
    if (!this.browser || !this.context) {
      throw new Error('Browser not initialized');
    }

    let page: Page | null = null;
    let attempt = 0;

    while (attempt <= retries) {
      try {
        page = await this.context.newPage();

        // Set viewport and user agent
        await page.setViewportSize(viewport);
        if (userAgent) {
          await page.setExtraHTTPHeaders({
            'User-Agent': userAgent
          });
        }

        // Set extra headers
        if (Object.keys(extraHeaders).length > 0) {
          await page.setExtraHTTPHeaders(extraHeaders);
        }

        // Set default timeout
        page.setDefaultTimeout(timeout);

        // Resource blocking for performance
        if (blockResources) {
          await page.route('**/*', route => {
            const request = route.request();
            const resourceType = request.resourceType();
            const url = request.url();

            totalRequests++;

            // Block images, fonts, media, and ads
            if (
              resourceType === 'image' ||
              resourceType === 'font' ||
              resourceType === 'media' ||
              /\.(png|jpg|jpeg|gif|webp|svg|ico|woff|woff2|ttf|otf|mp4|mp3|avi)$/i.test(url) ||
              /google-?analytics|googletagmanager|facebook|twitter|linkedin|pinterest/i.test(url) ||
              /ads?[./]|doubleclick|googlesyndication|adsystem/i.test(url)
            ) {
              blockedRequests++;
              return route.abort();
            }

            route.continue();
          });
        }

        // Track redirects
        page.on('response', response => {
          if (response.status() >= 300 && response.status() < 400) {
            redirects.push(response.url());
          }
        });

        // Navigate to URL
        const response = await page.goto(url, { 
          waitUntil,
          timeout 
        });

        if (!response) {
          throw new Error('Navigation failed - no response');
        }

        const statusCode = response.status();
        if (statusCode >= 400) {
          throw new Error(`HTTP ${statusCode}: ${response.statusText()}`);
        }

        // Wait for content to stabilize
        await page.waitForLoadState('networkidle', { timeout: 5000 }).catch(() => {
          // Ignore timeout - content might still be loading
          logger.debug('Network idle timeout - continuing anyway');
        });

        // Extract data
        const html = await page.content();
        const title = await page.title();
        const finalUrl = page.url();
        const responseHeaders = response.headers();

        const loadTime = performance.now() - startTime;

        logger.info('Page scraped successfully', {
          url,
          finalUrl,
          statusCode,
          loadTime: `${loadTime.toFixed(2)}ms`,
          blockedRequests,
          totalRequests,
          htmlLength: html.length,
          title: title.substring(0, 100),
          attempt: attempt + 1
        });

        return {
          html,
          url: finalUrl,
          title,
          loadTime,
          blockedRequests,
          totalRequests,
          errors,
          metadata: {
            finalUrl,
            statusCode,
            responseHeaders,
            redirects
          }
        };

      } catch (error) {
        attempt++;
        const errorMessage = error instanceof Error ? error.message : 'Unknown error';
        errors.push(`Attempt ${attempt}: ${errorMessage}`);
        
        logger.warn('Scraping attempt failed', {
          url,
          attempt,
          error: errorMessage,
          willRetry: attempt <= retries
        });

        if (attempt > retries) {
          throw new Error(`Scraping failed after ${retries + 1} attempts: ${errors.join('; ')}`);
        }

        // Wait before retry
        await new Promise(resolve => setTimeout(resolve, 1000 * attempt));
      } finally {
        if (page) {
          await page.close().catch(() => {});
        }
      }
    }

    throw new Error('This should never be reached');
  }

  /**
   * Scrape multiple URLs in parallel with rate limiting
   */
  async scrapeMultiple(
    urls: string[],
    options: PlaywrightOptions & { concurrency?: number } = {}
  ): Promise<Array<{ url: string; result?: ScrapingResult; error?: string }>> {
    const { concurrency = 3, ...scrapeOptions } = options;

    const results: Array<{ url: string; result?: ScrapingResult; error?: string }> = [];
    
    // Process URLs in batches to control concurrency
    for (let i = 0; i < urls.length; i += concurrency) {
      const batch = urls.slice(i, i + concurrency);
      
      const batchPromises = batch.map(async (url) => {
        try {
          const result = await this.scrape(url, scrapeOptions);
          return { url, result };
        } catch (error) {
          const errorMessage = error instanceof Error ? error.message : 'Unknown error';
          logger.error('Failed to scrape URL in batch', { url }, error as Error);
          return { url, error: errorMessage };
        }
      });

      const batchResults = await Promise.all(batchPromises);
      results.push(...batchResults);

      // Rate limiting between batches
      if (i + concurrency < urls.length) {
        await new Promise(resolve => setTimeout(resolve, 1000));
      }
    }

    const successful = results.filter(r => r.result).length;
    const failed = results.filter(r => r.error).length;

    logger.info('Batch scraping completed', {
      total: urls.length,
      successful,
      failed,
      successRate: `${((successful / urls.length) * 100).toFixed(1)}%`
    });

    return results;
  }

  /**
   * Extract specific data using selectors
   */
  async extractData(
    url: string,
    selectors: Record<string, string>,
    options: PlaywrightOptions = {}
  ): Promise<{ data: Record<string, string | null>; metadata: ScrapingResult['metadata'] }> {
    await this.initialize();
    if (!this.browser || !this.context) {
      throw new Error('Browser not initialized');
    }

    const page = await this.context.newPage();

    try {
      // Configure page similar to scrape method
      const { timeout = 12000, blockResources = true } = options;
      page.setDefaultTimeout(timeout);

      if (blockResources) {
        await page.route('**/*', route => {
          const request = route.request();
          const resourceType = request.resourceType();
          
          if (['image', 'font', 'media'].includes(resourceType)) {
            return route.abort();
          }
          
          route.continue();
        });
      }

      const response = await page.goto(url, { waitUntil: 'networkidle' });
      if (!response) {
        throw new Error('Navigation failed');
      }

      // Extract data using selectors
      const data: Record<string, string | null> = {};
      
      for (const [field, selector] of Object.entries(selectors)) {
        try {
          const element = await page.$(selector);
          const value = element ? await element.textContent() : null;
          data[field] = value?.trim() || null;
        } catch (error) {
          logger.warn('Failed to extract field', { field, selector, error });
          data[field] = null;
        }
      }

      const metadata = {
        finalUrl: page.url(),
        statusCode: response.status(),
        responseHeaders: response.headers(),
        redirects: [] // Would need to track these like in scrape method
      };

      return { data, metadata };

    } finally {
      await page.close();
    }
  }

  /**
   * Clean up browser resources
   */
  async close(): Promise<void> {
    try {
      if (this.context) {
        await this.context.close();
        this.context = null;
      }
      if (this.browser) {
        await this.browser.close();
        this.browser = null;
      }
      logger.info('Playwright browser closed');
    } catch (error) {
      logger.error('Error closing Playwright browser', error);
    }
  }

  /**
   * Check if browser is running
   */
  isRunning(): boolean {
    return this.browser !== null && this.context !== null;
  }
}

// Singleton instance
const playwrightScraper = new PlaywrightScraper();

// Cleanup on process exit
process.on('exit', () => {
  playwrightScraper.close().catch(() => {});
});

process.on('SIGINT', async () => {
  await playwrightScraper.close();
  process.exit(0);
});

process.on('SIGTERM', async () => {
  await playwrightScraper.close();
  process.exit(0);
});

export { playwrightScraper };
export type { PlaywrightOptions, ScrapingResult };