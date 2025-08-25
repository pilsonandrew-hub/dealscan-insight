import { Page, Browser, chromium } from 'playwright';

export interface HeadlessConfig {
  timeout?: number;
  waitUntil?: 'networkidle' | 'domcontentloaded' | 'load';
  blockResources?: string[];
  userAgent?: string;
  viewport?: { width: number; height: number };
}

export interface HeadlessResult {
  html: string;
  screenshots?: Buffer[];
  performance?: {
    loadTime: number;
    requestCount: number;
    blockedCount: number;
  };
  error?: string;
}

/**
 * Optimized headless browser with request blocking and performance budgets
 * Blocks non-essential resources to improve speed and reduce costs
 */
export class HeadlessOptimizer {
  private static readonly DEFAULT_CONFIG: Required<HeadlessConfig> = {
    timeout: 12000,
    waitUntil: 'networkidle',
    blockResources: ['image', 'font', 'media', 'stylesheet'],
    userAgent: 'DealerScope-Bot/1.0 (Headless)',
    viewport: { width: 1280, height: 720 }
  };

  private static readonly BLOCKED_EXTENSIONS = [
    '.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg',
    '.woff', '.woff2', '.ttf', '.otf',
    '.mp4', '.avi', '.mov', '.wmv',
    '.css', '.scss', '.less'
  ];

  private static readonly BLOCKED_DOMAINS = [
    'googletagmanager.com',
    'google-analytics.com',
    'facebook.com',
    'twitter.com',
    'linkedin.com',
    'instagram.com',
    'youtube.com',
    'doubleclick.net',
    'googlesyndication.com'
  ];

  /**
   * Fetch page content using optimized headless browser
   */
  static async fetchHeadless(
    url: string,
    config: HeadlessConfig = {}
  ): Promise<HeadlessResult> {
    const finalConfig = { ...this.DEFAULT_CONFIG, ...config };
    let browser: Browser | null = null;
    let requestCount = 0;
    let blockedCount = 0;
    const startTime = Date.now();

    try {
      // Launch browser with minimal resources
      browser = await chromium.launch({
        headless: true,
        args: [
          '--no-sandbox',
          '--disable-setuid-sandbox',
          '--disable-dev-shm-usage',
          '--disable-gpu',
          '--disable-web-security',
          '--disable-background-timer-throttling',
          '--disable-backgrounding-occluded-windows',
          '--disable-renderer-backgrounding'
        ]
      });

      const context = await browser.newContext({
        userAgent: finalConfig.userAgent,
        viewport: finalConfig.viewport,
        javaScriptEnabled: true,
        // Disable images by default for faster loading
        extraHTTPHeaders: {
          'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
        }
      });

      const page = await context.newPage();

      // Set timeouts
      page.setDefaultTimeout(finalConfig.timeout);

      // Block unwanted resources
      await page.route('**/*', (route) => {
        const request = route.request();
        const url = request.url();
        const resourceType = request.resourceType();

        requestCount++;

        // Block by resource type
        if (finalConfig.blockResources.includes(resourceType)) {
          blockedCount++;
          return route.abort();
        }

        // Block by file extension
        if (this.BLOCKED_EXTENSIONS.some(ext => url.toLowerCase().includes(ext))) {
          blockedCount++;
          return route.abort();
        }

        // Block by domain
        if (this.BLOCKED_DOMAINS.some(domain => url.includes(domain))) {
          blockedCount++;
          return route.abort();
        }

        // Block ads and tracking
        if (this.isAdOrTracking(url)) {
          blockedCount++;
          return route.abort();
        }

        route.continue();
      });

      // Navigate with performance monitoring
      await page.goto(url, {
        waitUntil: finalConfig.waitUntil,
        timeout: finalConfig.timeout
      });

      // Wait for dynamic content to load
      if (finalConfig.waitUntil === 'networkidle') {
        await page.waitForLoadState('networkidle', { timeout: finalConfig.timeout });
      }

      // Extract HTML content
      const html = await page.content();
      const loadTime = Date.now() - startTime;

      return {
        html,
        performance: {
          loadTime,
          requestCount,
          blockedCount
        }
      };

    } catch (error) {
      return {
        html: '',
        error: error instanceof Error ? error.message : 'Unknown headless error',
        performance: {
          loadTime: Date.now() - startTime,
          requestCount,
          blockedCount
        }
      };
    } finally {
      if (browser) {
        await browser.close();
      }
    }
  }

  /**
   * Check if URL is likely an ad or tracking resource
   */
  private static isAdOrTracking(url: string): boolean {
    const adPatterns = [
      /\/ads?\//,
      /\/analytics?\//,
      /\/tracking?\//,
      /\/pixel\//,
      /\/beacon\//,
      /gtm\.js/,
      /gtag/,
      /fbevents/,
      /\.ads\./,
      /\.advertising\./
    ];

    return adPatterns.some(pattern => pattern.test(url.toLowerCase()));
  }

  /**
   * Get performance budget recommendations based on site type
   */
  static getPerformanceBudget(siteType: 'auction' | 'government' | 'commercial'): {
    maxLoadTime: number;
    maxRequests: number;
    maxBlockedRatio: number;
  } {
    const budgets = {
      auction: { maxLoadTime: 15000, maxRequests: 50, maxBlockedRatio: 0.7 },
      government: { maxLoadTime: 20000, maxRequests: 30, maxBlockedRatio: 0.8 },
      commercial: { maxLoadTime: 12000, maxRequests: 80, maxBlockedRatio: 0.6 }
    };

    return budgets[siteType] || budgets.commercial;
  }

  /**
   * Validate if performance is within budget
   */
  static validatePerformanceBudget(
    result: HeadlessResult,
    budget: ReturnType<typeof HeadlessOptimizer.getPerformanceBudget>
  ): {
    withinBudget: boolean;
    violations: string[];
  } {
    const violations: string[] = [];

    if (!result.performance) {
      return { withinBudget: false, violations: ['No performance data available'] };
    }

    const { loadTime, requestCount, blockedCount } = result.performance;
    const blockedRatio = requestCount > 0 ? blockedCount / requestCount : 0;

    if (loadTime > budget.maxLoadTime) {
      violations.push(`Load time ${loadTime}ms exceeds budget ${budget.maxLoadTime}ms`);
    }

    if (requestCount > budget.maxRequests) {
      violations.push(`Request count ${requestCount} exceeds budget ${budget.maxRequests}`);
    }

    if (blockedRatio < budget.maxBlockedRatio) {
      violations.push(`Blocked ratio ${blockedRatio.toFixed(2)} below target ${budget.maxBlockedRatio}`);
    }

    return {
      withinBudget: violations.length === 0,
      violations
    };
  }
}

export default HeadlessOptimizer;