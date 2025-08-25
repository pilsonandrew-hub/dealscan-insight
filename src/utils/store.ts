/**
 * Database Store Utilities - Production-ready data persistence
 * Single source of truth for upsert operations with content hashing
 */

import { supabase } from '@/integrations/supabase/client';
import { contentHash } from './contentHash';
import { logger } from '@/lib/logger';

export interface PublicListing extends Record<string, unknown> {
  id?: string;
  content_hash?: string;
  vin: string;
  make?: string;
  model?: string;
  year?: number;
  mileage?: number;
  current_bid?: number;
  source_site: string;
  listing_url: string;
  location?: string;
  auction_end?: string;
  scrape_metadata?: Record<string, any>;
  created_at?: string;
  updated_at?: string;
}

/**
 * Upsert public listing with content hash deduplication
 * Single source of truth implementation
 */
export async function upsertPublicListing(item: PublicListing): Promise<void> {
  try {
    // Generate content hash for deduplication
    item.content_hash = await contentHash(item);
    
    const { error } = await supabase
      .from('public_listings')
      .upsert(item, {
        onConflict: 'content_hash',
        ignoreDuplicates: false
      });

    if (error) {
      logger.error('Failed to upsert public listing', { error, item: { vin: item.vin, source_site: item.source_site } });
      throw error;
    }

    logger.debug('Successfully upserted public listing', { 
      vin: item.vin, 
      source_site: item.source_site,
      content_hash: item.content_hash 
    });
  } catch (error) {
    logger.error('Upsert operation failed', { error, item });
    throw error;
  }
}

/**
 * Batch upsert with proper error handling and deduplication
 */
export async function batchUpsertPublicListings(items: PublicListing[]): Promise<{
  successful: number;
  failed: number;
  duplicates: number;
}> {
  const results = { successful: 0, failed: 0, duplicates: 0 };
  
  // Add content hashes
  const itemsWithHashes = await Promise.all(
    items.map(async (item) => ({
      ...item,
      content_hash: await contentHash(item)
    }))
  );

  // Deduplicate by content hash
  const uniqueItems = new Map<string, PublicListing>();
  for (const item of itemsWithHashes) {
    if (item.content_hash && uniqueItems.has(item.content_hash)) {
      results.duplicates++;
    } else if (item.content_hash) {
      uniqueItems.set(item.content_hash, item);
    }
  }

  // Batch upsert unique items
  const uniqueItemsArray = Array.from(uniqueItems.values());
  
  try {
    const { error, count } = await supabase
      .from('public_listings')
      .upsert(uniqueItemsArray, {
        onConflict: 'content_hash',
        ignoreDuplicates: false,
        count: 'exact'
      });

    if (error) {
      logger.error('Batch upsert failed', { error, itemCount: uniqueItemsArray.length });
      results.failed = uniqueItemsArray.length;
    } else {
      results.successful = count || uniqueItemsArray.length;
    }
  } catch (error) {
    logger.error('Batch upsert operation failed', { error });
    results.failed = uniqueItemsArray.length;
  }

  logger.info('Batch upsert completed', results);
  return results;
}

/**
 * Check if listing exists by content hash
 */
export async function listingExists(item: PublicListing): Promise<boolean> {
  try {
    const hash = await contentHash(item);
    const { data, error } = await supabase
      .from('public_listings')
      .select('id')
      .eq('content_hash', hash)
      .single();

    if (error && error.code !== 'PGRST116') {
      logger.error('Failed to check listing existence', { error, hash });
      return false;
    }

    return !!data;
  } catch (error) {
    logger.error('Listing existence check failed', { error });
    return false;
  }
}