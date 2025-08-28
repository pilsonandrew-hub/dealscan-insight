/**
 * BatchProcessor - Handles batch processing of scraping operations
 * Extracted from ScraperOrchestrator for better modularity
 */

import { logger } from '@/lib/logger';
import { ScraperSite, ScrapingResult } from './types';
import { ScraperConfig } from './ScraperConfig';

export class BatchProcessor {
  private config: ScraperConfig;

  constructor(config: ScraperConfig) {
    this.config = config;
  }

  async processBatch(
    sites: ScraperSite[],
    scrapeFn: (site: ScraperSite) => Promise<ScrapingResult>
  ): Promise<Map<string, ScrapingResult>> {
    const results = new Map<string, ScrapingResult>();
    const batchSize = this.config.getConcurrentScrapingLimit();

    logger.info(`Processing ${sites.length} sites in batches of ${batchSize}`);

    for (let i = 0; i < sites.length; i += batchSize) {
      const batch = sites.slice(i, i + batchSize);
      const batchPromises = batch.map(site => scrapeFn(site));
      
      const batchResults = await Promise.allSettled(batchPromises);
      
      this.processBatchResults(batch, batchResults, results);

      // Wait between batches to respect rate limits
      if (i + batchSize < sites.length) {
        await this.waitBetweenBatches();
      }
    }

    return results;
  }

  private processBatchResults(
    batch: ScraperSite[],
    batchResults: PromiseSettledResult<ScrapingResult>[],
    results: Map<string, ScrapingResult>
  ): void {
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
        
        logger.error(`Batch processing failed for site ${site.name}:`, result.reason);
      }
    });
  }

  private async waitBetweenBatches(): Promise<void> {
    const delay = this.config.getBatchDelay();
    await new Promise(resolve => setTimeout(resolve, delay));
  }
}