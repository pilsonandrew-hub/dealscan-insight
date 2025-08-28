/**
 * ScraperOrchestrator - Main coordinator for multi-site scraping operations
 * Manages scraping jobs, site coordination, and result aggregation
 * 
 * @fileoverview This file is large (276 lines) and should be refactored into smaller modules:
 * - ScraperManager: Core orchestration logic
 * - BatchProcessor: Batch processing utilities  
 * - ResultHandler: Result storage and processing
 * - StatsUpdater: Site statistics management
 */

import { supabase } from '@/integrations/supabase/client';
import { logger } from '@/lib/logger';
import { ScraperSite, ScrapingResult, ProxyConfig } from './types';
import { ProxyManager } from './ProxyManager';
import { ContentParser } from './ContentParser';
import { ScraperConfig } from './ScraperConfig';

export class ScraperOrchestrator {
  private proxyManager: ProxyManager;
  private contentParser: ContentParser;
  private config: ScraperConfig;
  private sites: Map<string, ScraperSite> = new Map();
  private isRunning = false;

  constructor() {
    this.proxyManager = new ProxyManager();
    this.contentParser = new ContentParser(); 
    this.config = new ScraperConfig();
    this.initializeSites();
  }

  private async initializeSites(): Promise<void> {
    try {
      const { data: sites, error } = await supabase
        .from('scraper_sites')
        .select('*')
        .eq('enabled', true);

      if (error) throw error;

      this.sites.clear();
      sites?.forEach(site => {
        this.sites.set(site.id, {
          id: site.id,
          name: site.name,
          baseUrl: site.base_url,
          enabled: site.enabled,
          lastScrape: site.last_scrape,
          vehiclesFound: site.vehicles_found,
          status: site.status as 'active' | 'blocked' | 'maintenance' | 'error',
          category: site.category as 'federal' | 'state' | 'local' | 'insurance' | 'dealer'
        });
      });

      logger.info(`Initialized ${this.sites.size} scraper sites`);
    } catch (error) {
      logger.error('Failed to initialize scraper sites', error);
      throw error;
    }
  }

  async startScraping(targetSites?: string[]): Promise<Map<string, ScrapingResult>> {
    if (this.isRunning) {
      throw new Error('Scraping is already in progress');
    }

    this.isRunning = true;
    const results = new Map<string, ScrapingResult>();
    const sitesToScrape = targetSites ? 
      Array.from(this.sites.values()).filter(site => targetSites.includes(site.id)) :
      Array.from(this.sites.values());

    logger.info(`Starting scraping for ${sitesToScrape.length} sites`);

    try {
      // Process sites in batches to avoid overwhelming servers
      const batchSize = this.config.getConcurrentScrapingLimit();
      for (let i = 0; i < sitesToScrape.length; i += batchSize) {
        const batch = sitesToScrape.slice(i, i + batchSize);
        const batchPromises = batch.map(site => this.scrapeSite(site));
        
        const batchResults = await Promise.allSettled(batchPromises);
        
        batchResults.forEach((result, index) => {
          const site = batch[index];
          if (result.status === 'fulfilled') {
            results.set(site.id, result.value);
          } else {
            results.set(site.id, {
              site: site.id,
              success: false,
              vehiclesFound: 0,
              errors: [result.reason?.message || 'Unknown error'],
              blocked: false,
              timeElapsed: 0
            });
          }
        });

        // Wait between batches to respect rate limits
        if (i + batchSize < sitesToScrape.length) {
          await new Promise(resolve => setTimeout(resolve, this.config.getBatchDelay()));
        }
      }

      await this.updateScrapingSummary(results);
      return results;

    } finally {
      this.isRunning = false;
    }
  }

  private async scrapeSite(site: ScraperSite): Promise<ScrapingResult> {
    const startTime = Date.now();
    const result: ScrapingResult = {
      site: site.id,
      success: false,
      vehiclesFound: 0,
      errors: [],
      blocked: false,
      timeElapsed: 0
    };

    try {
      logger.info(`Starting scraping for site: ${site.name}`);

      // Get proxy for this site
      const proxy = await this.proxyManager.getNextProxy(site.id);
      if (proxy) {
        result.proxyUsed = `${proxy.ip}:${proxy.port}`;
      }

      // Perform the actual scraping
      const scrapingConfig = await this.config.getConfigForSite(site.id);
      const rawData = await this.performHttpScraping(site, proxy, scrapingConfig);
      
      // Parse the content
      const parsedListings = await this.contentParser.parseContent(rawData, site.id);
      
      result.success = true;
      result.vehiclesFound = parsedListings.length;
      
      // Store results in database
      if (parsedListings.length > 0) {
        await this.storeListings(parsedListings);
      }

      // Update site statistics
      await this.updateSiteStats(site.id, true, parsedListings.length);

    } catch (error: any) {
      result.errors.push(error.message);
      result.blocked = error.name === 'BlockedError';
      
      // Update proxy status if blocked
      if (result.blocked && result.proxyUsed) {
        await this.proxyManager.markProxyBlocked(result.proxyUsed);
      }

      // Update site statistics
      await this.updateSiteStats(site.id, false, 0);
      
      logger.error(`Scraping failed for site ${site.name}:`, { error: error.message, site: site.name });
    }

    result.timeElapsed = Date.now() - startTime;
    return result;
  }

  private async performHttpScraping(
    site: ScraperSite, 
    proxy: ProxyConfig | null,
    config: any
  ): Promise<string> {
    const headers = {
      'User-Agent': this.config.getRandomUserAgent(),
      'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
      'Accept-Language': 'en-US,en;q=0.5',
      'Accept-Encoding': 'gzip, deflate',
      'Connection': 'keep-alive',
      'Upgrade-Insecure-Requests': '1',
      ...config.headers
    };

    const fetchOptions: RequestInit = {
      method: 'GET',
      headers,
      signal: AbortSignal.timeout(config.timeout || 30000)
    };

    // Add proxy configuration if available
    if (proxy) {
      // Note: In a real implementation, you'd configure the proxy here
      // This is a simplified example
    }

    const response = await fetch(site.baseUrl, fetchOptions);
    
    if (!response.ok) {
      if (response.status === 403 || response.status === 429) {
        const error = new Error(`Site blocked scraping: ${response.status}`);
        error.name = 'BlockedError';
        throw error;
      }
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    return await response.text();
  }

  private async storeListings(listings: any[]): Promise<void> {
    // Store in batches to avoid overwhelming the database
    const batchSize = 100;
    for (let i = 0; i < listings.length; i += batchSize) {
      const batch = listings.slice(i, i + batchSize);
      
      const { error } = await supabase
        .from('public_listings')
        .upsert(batch, { 
          onConflict: 'listing_url',
          ignoreDuplicates: false 
        });

      if (error) {
        logger.error(`Failed to store listings batch ${i}:`, { 
          error: error.message, 
          batch: i, 
          code: error.code 
        });
      }
    }
  }

  private async updateSiteStats(
    siteId: string, 
    success: boolean, 
    vehiclesFound: number
  ): Promise<void> {
    try {
      const updates = {
        last_scrape: new Date().toISOString(),
        vehicles_found: vehiclesFound,
        status: success ? 'active' : 'error'
      };

      await supabase
        .from('scraper_sites')
        .update(updates)
        .eq('id', siteId);

    } catch (error) {
      logger.error(`Failed to update site stats for ${siteId}:`, error);
    }
  }

  private async updateScrapingSummary(results: Map<string, ScrapingResult>): Promise<void> {
    const summary = {
      total_sites: results.size,
      successful_sites: Array.from(results.values()).filter(r => r.success).length,
      total_vehicles: Array.from(results.values()).reduce((sum, r) => sum + r.vehiclesFound, 0),
      blocked_sites: Array.from(results.values()).filter(r => r.blocked).length,
      average_time: Array.from(results.values()).reduce((sum, r) => sum + r.timeElapsed, 0) / results.size
    };

    logger.info('Scraping summary:', summary);
  }

  async stopScraping(): Promise<void> {
    this.isRunning = false;
    logger.info('Scraping stopped by user request');
  }

  getScrapingStatus(): boolean {
    return this.isRunning;
  }

  async refreshSites(): Promise<void> {
    await this.initializeSites();
  }
}