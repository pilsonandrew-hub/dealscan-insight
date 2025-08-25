/**
 * ScraperConfig - Configuration management for scraping operations
 * Handles site-specific settings, rate limits, and scraping parameters
 */

import { supabase } from '@/integrations/supabase/client';
import { logger } from '@/lib/logger';

export interface SiteConfig {
  siteId: string;
  headers: Record<string, string>;
  timeout: number;
  rateLimit: number;
  maxPages: number;
  selectors: Record<string, string>;
  enabled: boolean;
}

export class ScraperConfig {
  private configs = new Map<string, SiteConfig>();
  private userAgents: string[] = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0'
  ];

  constructor() {
    this.initializeConfigs();
  }

  private async initializeConfigs(): Promise<void> {
    try {
      const { data: configs, error } = await supabase
        .from('scraper_configs')
        .select('*')
        .eq('is_enabled', true);

      if (error) throw error;

      this.configs.clear();
      configs?.forEach(config => {
        this.configs.set(config.site_name, {
          siteId: config.site_name,
          headers: (config.headers as Record<string, string>) || {},
          timeout: 30000,
          rateLimit: config.rate_limit_seconds || 3,
          maxPages: config.max_pages || 50,
          selectors: (config.selectors as Record<string, string>) || {},
          enabled: config.is_enabled
        });
      });

      // Add default configs for sites without database entries
      this.addDefaultConfigs();

      logger.info(`Loaded ${this.configs.size} scraper configurations`);
    } catch (error) {
      logger.error('Failed to load scraper configs:', error);
      this.addDefaultConfigs();
    }
  }

  private addDefaultConfigs(): void {
    const defaultConfigs: SiteConfig[] = [
      {
        siteId: 'govdeals',
        headers: {
          'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
          'Accept-Language': 'en-US,en;q=0.9',
          'Cache-Control': 'no-cache'
        },
        timeout: 30000,
        rateLimit: 5,
        maxPages: 25,
        selectors: {
          listingContainer: '.auction-item',
          title: '.title, h3',
          price: '.current-bid, .price',
          location: '.location',
          endTime: '.end-time, .auction-end'
        },
        enabled: true
      },
      {
        siteId: 'publicsurplus',
        headers: {
          'Accept': 'text/html,application/xhtml+xml',
          'Accept-Language': 'en-US,en;q=0.9'
        },
        timeout: 25000,
        rateLimit: 4,
        maxPages: 20,
        selectors: {
          listingContainer: '.item, .listing',
          title: '.item-title, h2',
          price: '.bid-amount, .current-bid',
          location: '.item-location'
        },
        enabled: true
      },
      {
        siteId: 'liquidation',
        headers: {
          'Accept': 'application/json, text/html',
          'Accept-Encoding': 'gzip, deflate, br'
        },
        timeout: 35000,
        rateLimit: 6,
        maxPages: 30,
        selectors: {
          listingContainer: '.lot, .auction-lot',
          title: '.lot-title',
          price: '.current-bid, .bid-price',
          description: '.lot-description'
        },
        enabled: true
      }
    ];

    defaultConfigs.forEach(config => {
      if (!this.configs.has(config.siteId)) {
        this.configs.set(config.siteId, config);
      }
    });
  }

  async getConfigForSite(siteId: string): Promise<SiteConfig> {
    let config = this.configs.get(siteId);
    
    if (!config) {
      // Create basic config for unknown sites
      config = {
        siteId,
        headers: {
          'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
          'Accept-Language': 'en-US,en;q=0.9'
        },
        timeout: 30000,
        rateLimit: 5,
        maxPages: 10,
        selectors: {},
        enabled: true
      };
      
      this.configs.set(siteId, config);
      logger.debug(`Created default config for site: ${siteId}`);
    }

    return { ...config }; // Return copy to avoid mutations
  }

  getRandomUserAgent(): string {
    const randomIndex = Math.floor(Math.random() * this.userAgents.length);
    return this.userAgents[randomIndex];
  }

  getConcurrentScrapingLimit(): number {
    return 3; // Process 3 sites concurrently
  }

  getBatchDelay(): number {
    return 2000; // 2 second delay between batches
  }

  getGlobalRateLimit(): number {
    return 1000; // Global minimum delay between requests
  }

  async updateConfigForSite(siteId: string, updates: Partial<SiteConfig>): Promise<void> {
    const existingConfig = await this.getConfigForSite(siteId);
    const updatedConfig = { ...existingConfig, ...updates };
    
    this.configs.set(siteId, updatedConfig);
    
    try {
      // Update in database
      const { error } = await supabase
        .from('scraper_configs')
        .upsert({
          site_name: siteId,
          site_url: `https://${siteId}.com`, // Basic fallback URL
          category: 'government', // Default category
          headers: updatedConfig.headers,
          rate_limit_seconds: updatedConfig.rateLimit,
          max_pages: updatedConfig.maxPages,
          selectors: updatedConfig.selectors,
          is_enabled: updatedConfig.enabled
        });

      if (error) throw error;
      
      logger.info(`Updated config for site: ${siteId}`);
    } catch (error) {
      logger.error(`Failed to update config for ${siteId}:`, error);
    }
  }

  async disableSite(siteId: string): Promise<void> {
    await this.updateConfigForSite(siteId, { enabled: false });
  }

  async enableSite(siteId: string): Promise<void> {
    await this.updateConfigForSite(siteId, { enabled: true });
  }

  getEnabledSites(): string[] {
    return Array.from(this.configs.entries())
      .filter(([_, config]) => config.enabled)
      .map(([siteId, _]) => siteId);
  }

  getAllConfigs(): Map<string, SiteConfig> {
    return new Map(this.configs);
  }

  async refreshConfigs(): Promise<void> {
    await this.initializeConfigs();
  }

  // Security settings
  getSecurityHeaders(): Record<string, string> {
    return {
      'DNT': '1',
      'Sec-Fetch-Dest': 'document',
      'Sec-Fetch-Mode': 'navigate',
      'Sec-Fetch-Site': 'none',
      'Upgrade-Insecure-Requests': '1'
    };
  }

  // Performance settings
  getPerformanceSettings() {
    return {
      maxConcurrent: this.getConcurrentScrapingLimit(),
      requestTimeout: 30000,
      retryAttempts: 3,
      retryDelay: 1000,
      connectionPoolSize: 10
    };
  }
}