/**
 * Headless Browser Pool - Phase 2 Security & Performance
 * Managed pool of Playwright contexts with resource limits and request blocking
 */

import { chromium, Browser, BrowserContext, Page } from 'playwright';
import productionLogger from '@/utils/productionLogger';
import { isFeatureEnabled, getFeatureValue } from '@/config/featureFlags';

interface BrowserPoolConfig {
  maxContexts: number;
  maxPagesPerContext: number;
  maxPageLifetime: number; // milliseconds
  contextTimeout: number;
  enableRequestBlocking: boolean;
  blockedResourceTypes: string[];
  userAgent: string;
  viewport: { width: number; height: number };
}

interface PoolContext {
  context: BrowserContext;
  pages: Set<Page>;
  createdAt: number;
  lastUsed: number;
  requestCount: number;
}

interface BrowserPoolStats {
  totalContexts: number;
  activePages: number;
  avgRequestsPerContext: number;
  oldestContextAge: number;
  poolUtilization: number;
}

const DEFAULT_CONFIG: BrowserPoolConfig = {
  maxContexts: getFeatureValue('MAX_BROWSER_CONTEXTS'),
  maxPagesPerContext: 3,
  maxPageLifetime: 300000, // 5 minutes
  contextTimeout: 30000, // 30 seconds
  enableRequestBlocking: true,
  blockedResourceTypes: [
    'image',
    'media', 
    'font',
    'texttrack',
    'object',
    'beacon',
    'csp_report',
    'imageset'
  ],
  userAgent: 'DealerScope-Bot/5.0 (+https://dealerscope.com/bot)',
  viewport: { width: 1920, height: 1080 }
};

export class BrowserPool {
  private browser: Browser | null = null;
  private contexts: Map<string, PoolContext> = new Map();
  private config: BrowserPoolConfig;
  private isInitialized = false;
  private cleanupInterval: NodeJS.Timeout | null = null;

  constructor(config: Partial<BrowserPoolConfig> = {}) {
    this.config = { ...DEFAULT_CONFIG, ...config };
  }

  /**
   * Initialize browser pool
   */
  async initialize(): Promise<void> {
    if (this.isInitialized) return;

    if (!isFeatureEnabled('ENABLE_BROWSER_POOL')) {
      productionLogger.info('Browser pool disabled by feature flag');
      return;
    }

    try {
      productionLogger.info('Initializing browser pool', {
        maxContexts: this.config.maxContexts,
        maxPagesPerContext: this.config.maxPagesPerContext
      });

      this.browser = await chromium.launch({
        headless: true,
        args: [
          '--no-sandbox',
          '--disable-dev-shm-usage',
          '--disable-background-timer-throttling',
          '--disable-backgrounding-occluded-windows',
          '--disable-renderer-backgrounding',
          '--disable-web-security',
          '--disable-features=TranslateUI',
          '--disable-extensions'
        ]
      });

      // Start cleanup interval
      this.cleanupInterval = setInterval(() => {
        this.cleanupExpiredContexts().catch(error => {
          productionLogger.error('Browser pool cleanup failed', {}, error as Error);
        });
      }, 60000); // Cleanup every minute

      this.isInitialized = true;
      productionLogger.info('Browser pool initialized successfully');

    } catch (error) {
      productionLogger.error('Failed to initialize browser pool', {}, error as Error);
      throw error;
    }
  }

  /**
   * Get or create browser context
   */
  async getContext(): Promise<{ context: BrowserContext; contextId: string }> {
    if (!this.isInitialized) {
      await this.initialize();
    }

    if (!this.browser) {
      throw new Error('Browser pool not initialized');
    }

    // Try to find available context
    let selectedContext = this.findAvailableContext();
    let contextId: string;

    if (!selectedContext) {
      // Create new context if under limit
      if (this.contexts.size >= this.config.maxContexts) {
        // Force cleanup and try again
        await this.cleanupExpiredContexts();
        selectedContext = this.findAvailableContext();

        if (!selectedContext) {
          throw new Error('Browser pool at capacity');
        }
      } else {
        const result = await this.createContext();
        selectedContext = result.context;
        contextId = result.contextId;
      }
    }

    if (!contextId!) {
      contextId = this.getContextId(selectedContext);
    }

    // Update usage tracking
    const poolContext = this.contexts.get(contextId);
    if (poolContext) {
      poolContext.lastUsed = Date.now();
      poolContext.requestCount++;
    }

    return { context: selectedContext, contextId };
  }

  /**
   * Create new browser page with configuration
   */
  async createPage(contextId?: string): Promise<Page> {
    let context: BrowserContext;
    let actualContextId: string;

    if (contextId && this.contexts.has(contextId)) {
      const poolContext = this.contexts.get(contextId)!;
      context = poolContext.context;
      actualContextId = contextId;
    } else {
      const result = await this.getContext();
      context = result.context;
      actualContextId = result.contextId;
    }

    const poolContext = this.contexts.get(actualContextId)!;

    // Check page limit
    if (poolContext.pages.size >= this.config.maxPagesPerContext) {
      throw new Error(`Context ${actualContextId} at page capacity`);
    }

    try {
      const page = await context.newPage();

      // Configure page
      await page.setViewportSize(this.config.viewport);
      await page.setUserAgent(this.config.userAgent);

      // Setup request blocking
      if (this.config.enableRequestBlocking) {
        await this.setupRequestBlocking(page);
      }

      // Track page
      poolContext.pages.add(page);

      // Setup page cleanup
      page.on('close', () => {
        poolContext.pages.delete(page);
      });

      productionLogger.debug('Browser page created', {
        contextId: actualContextId,
        totalPages: poolContext.pages.size
      });

      return page;

    } catch (error) {
      productionLogger.error('Failed to create browser page', {
        contextId: actualContextId
      }, error as Error);
      throw error;
    }
  }

  /**
   * Setup request blocking for performance
   */
  private async setupRequestBlocking(page: Page): Promise<void> {
    await page.route('**/*', (route) => {
      const request = route.request();
      const resourceType = request.resourceType();

      // Block unwanted resource types
      if (this.config.blockedResourceTypes.includes(resourceType)) {
        route.abort();
        return;
      }

      // Block known ad/tracking domains
      const url = request.url();
      const blockedDomains = [
        'googleadservices.com',
        'googlesyndication.com',
        'googletagmanager.com',
        'doubleclick.net',
        'facebook.com',
        'twitter.com',
        'linkedin.com'
      ];

      if (blockedDomains.some(domain => url.includes(domain))) {
        route.abort();
        return;
      }

      // Continue with request
      route.continue();
    });
  }

  /**
   * Release browser page
   */
  async releasePage(page: Page): Promise<void> {
    try {
      if (!page.isClosed()) {
        await page.close();
      }
    } catch (error) {
      productionLogger.warn('Error closing browser page', {}, error as Error);
    }
  }

  /**
   * Create new browser context
   */
  private async createContext(): Promise<{ context: BrowserContext; contextId: string }> {
    if (!this.browser) {
      throw new Error('Browser not initialized');
    }

    const contextId = `ctx_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

    try {
      const context = await this.browser.newContext({
        userAgent: this.config.userAgent,
        viewport: this.config.viewport,
        ignoreHTTPSErrors: true,
        extraHTTPHeaders: {
          'Accept-Language': 'en-US,en;q=0.9'
        }
      });

      // Set timeout
      context.setDefaultTimeout(this.config.contextTimeout);

      const poolContext: PoolContext = {
        context,
        pages: new Set(),
        createdAt: Date.now(),
        lastUsed: Date.now(),
        requestCount: 0
      };

      this.contexts.set(contextId, poolContext);

      productionLogger.debug('Browser context created', {
        contextId,
        totalContexts: this.contexts.size
      });

      return { context, contextId };

    } catch (error) {
      productionLogger.error('Failed to create browser context', {
        contextId
      }, error as Error);
      throw error;
    }
  }

  /**
   * Find available context with capacity
   */
  private findAvailableContext(): BrowserContext | null {
    for (const [contextId, poolContext] of this.contexts) {
      if (poolContext.pages.size < this.config.maxPagesPerContext) {
        // Check if context is not expired
        const age = Date.now() - poolContext.createdAt;
        if (age < this.config.maxPageLifetime) {
          return poolContext.context;
        }
      }
    }
    return null;
  }

  /**
   * Get context ID from context instance
   */
  private getContextId(context: BrowserContext): string {
    for (const [contextId, poolContext] of this.contexts) {
      if (poolContext.context === context) {
        return contextId;
      }
    }
    throw new Error('Context not found in pool');
  }

  /**
   * Cleanup expired contexts
   */
  private async cleanupExpiredContexts(): Promise<void> {
    const now = Date.now();
    const toRemove: string[] = [];

    for (const [contextId, poolContext] of this.contexts) {
      const age = now - poolContext.createdAt;
      const idle = now - poolContext.lastUsed;

      // Mark for removal if expired or idle too long
      if (age > this.config.maxPageLifetime || idle > this.config.maxPageLifetime) {
        toRemove.push(contextId);
      }
    }

    // Remove expired contexts
    for (const contextId of toRemove) {
      await this.removeContext(contextId);
    }

    if (toRemove.length > 0) {
      productionLogger.debug('Browser contexts cleaned up', {
        removed: toRemove.length,
        remaining: this.contexts.size
      });
    }
  }

  /**
   * Remove specific context
   */
  private async removeContext(contextId: string): Promise<void> {
    const poolContext = this.contexts.get(contextId);
    if (!poolContext) return;

    try {
      // Close all pages in context
      for (const page of Array.from(poolContext.pages)) {
        try {
          if (!page.isClosed()) {
            await page.close();
          }
        } catch (error) {
          productionLogger.warn('Error closing page during context cleanup', {
            contextId
          }, error as Error);
        }
      }

      // Close context
      await poolContext.context.close();
      this.contexts.delete(contextId);

    } catch (error) {
      productionLogger.error('Error removing browser context', {
        contextId
      }, error as Error);
    }
  }

  /**
   * Get pool statistics
   */
  getStats(): BrowserPoolStats {
    let totalPages = 0;
    let totalRequests = 0;
    let oldestAge = 0;

    const now = Date.now();

    for (const poolContext of this.contexts.values()) {
      totalPages += poolContext.pages.size;
      totalRequests += poolContext.requestCount;
      
      const age = now - poolContext.createdAt;
      if (age > oldestAge) {
        oldestAge = age;
      }
    }

    return {
      totalContexts: this.contexts.size,
      activePages: totalPages,
      avgRequestsPerContext: this.contexts.size > 0 ? totalRequests / this.contexts.size : 0,
      oldestContextAge: oldestAge,
      poolUtilization: (this.contexts.size / this.config.maxContexts) * 100
    };
  }

  /**
   * Shutdown browser pool
   */
  async shutdown(): Promise<void> {
    productionLogger.info('Shutting down browser pool');

    // Clear cleanup interval
    if (this.cleanupInterval) {
      clearInterval(this.cleanupInterval);
      this.cleanupInterval = null;
    }

    // Close all contexts
    const contextIds = Array.from(this.contexts.keys());
    await Promise.all(contextIds.map(id => this.removeContext(id)));

    // Close browser
    if (this.browser) {
      await this.browser.close();
      this.browser = null;
    }

    this.isInitialized = false;
    productionLogger.info('Browser pool shutdown complete');
  }
}

// Global instance
export const browserPool = new BrowserPool();