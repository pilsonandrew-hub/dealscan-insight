/**
 * ResultHandler - Manages scraping result storage and processing
 * Extracted from ScraperOrchestrator for better separation of concerns
 */

import { supabase } from '@/integrations/supabase/client';
import { logger } from '@/lib/logger';
import { ScrapingResult } from './types';

export class ResultHandler {
  async storeListings(listings: any[]): Promise<void> {
    if (listings.length === 0) return;

    // Store in batches to avoid overwhelming the database
    const batchSize = 100;
    let storedCount = 0;

    for (let i = 0; i < listings.length; i += batchSize) {
      const batch = listings.slice(i, i + batchSize);
      
      try {
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
        } else {
          storedCount += batch.length;
        }
      } catch (error) {
        logger.error(`Exception storing batch ${i}:`, error);
      }
    }

    logger.info(`Successfully stored ${storedCount}/${listings.length} listings`);
  }

  async updateSiteStats(
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

      const { error } = await supabase
        .from('scraper_sites')
        .update(updates)
        .eq('id', siteId);

        if (error) {
          logger.error(`Failed to update site stats for ${siteId}:`, { error: error.message });
        }
    } catch (error) {
      logger.error(`Exception updating site stats for ${siteId}:`, error);
    }
  }

  generateScrapingSummary(results: Map<string, ScrapingResult>): {
    total_sites: number;
    successful_sites: number;
    total_vehicles: number;
    blocked_sites: number;
    average_time: number;
  } {
    const summary = {
      total_sites: results.size,
      successful_sites: Array.from(results.values()).filter(r => r.success).length,
      total_vehicles: Array.from(results.values()).reduce((sum, r) => sum + r.vehiclesFound, 0),
      blocked_sites: Array.from(results.values()).filter(r => r.blocked).length,
      average_time: results.size > 0 
        ? Array.from(results.values()).reduce((sum, r) => sum + r.timeElapsed, 0) / results.size 
        : 0
    };

    logger.info('Scraping summary:', summary);
    return summary;
  }
}