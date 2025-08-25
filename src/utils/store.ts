/**
 * Database Store Utilities - Phase 1 Core Fix
 * Atomic upsert operations with proper error handling
 */

import { supabase } from '@/integrations/supabase/client';
import productionLogger from '@/utils/productionLogger';
import type { Json } from '@/integrations/supabase/types';

interface PublicListing {
  id?: string;
  vin: string;
  title: string;
  current_price: number;
  year?: number;
  make?: string;
  model?: string;
  mileage?: number;
  location?: string;
  listing_url: string;
  source_site: string;
  content_hash: string;
  ingested_at?: string;
  auction_end?: string;
  raw_data?: Json;
  extraction_metadata?: Json;
}

interface UpsertResult {
  success: boolean;
  id?: string;
  error?: string;
  conflictResolution?: 'inserted' | 'updated' | 'ignored';
}

/**
 * Atomic upsert for public listings with proper conflict resolution
 */
export async function upsertPublicListing(listing: PublicListing): Promise<UpsertResult> {
  const startTime = Date.now();
  
  try {
    productionLogger.info('Upserting public listing', {
      vin: listing.vin,
      content_hash: listing.content_hash,
      source_site: listing.source_site
    });
    
    // Prepare data with defaults
    const listingData = {
      ...listing,
      ingested_at: listing.ingested_at || new Date().toISOString(),
      raw_data: listing.raw_data || {},
      extraction_metadata: listing.extraction_metadata || {}
    };
    
    // Use upsert with conflict resolution on content_hash
    const { data, error } = await supabase
      .from('public_listings')
      .upsert(listingData, {
        onConflict: 'content_hash',
        ignoreDuplicates: false
      })
      .select('id')
      .single();
    
    if (error) {
      productionLogger.error('Failed to upsert public listing', {
        error: error.message,
        code: error.code,
        vin: listing.vin,
        duration_ms: Date.now() - startTime
      });
      
      return {
        success: false,
        error: error.message
      };
    }
    
    productionLogger.info('Successfully upserted public listing', {
      id: data.id,
      vin: listing.vin,
      duration_ms: Date.now() - startTime
    });
    
    return {
      success: true,
      id: data.id,
      conflictResolution: 'updated' // Supabase upsert doesn't distinguish, assume update
    };
    
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : 'Unknown error';
    
    productionLogger.error('Exception during public listing upsert', {
      error: errorMessage,
      vin: listing.vin,
      duration_ms: Date.now() - startTime
    });
    
    return {
      success: false,
      error: errorMessage
    };
  }
}

/**
 * Batch upsert with transaction-like behavior
 */
export async function batchUpsertPublicListings(listings: PublicListing[]): Promise<{
  success: boolean;
  results: UpsertResult[];
  summary: {
    total: number;
    successful: number;
    failed: number;
  };
}> {
  const startTime = Date.now();
  const results: UpsertResult[] = [];
  
  productionLogger.info('Starting batch upsert', {
    count: listings.length
  });
  
  try {
    // Process in smaller batches to avoid timeout
    const batchSize = 50;
    let successful = 0;
    let failed = 0;
    
    for (let i = 0; i < listings.length; i += batchSize) {
      const batch = listings.slice(i, i + batchSize);
      
      // Prepare batch data
      const batchData = batch.map(listing => ({
        ...listing,
        ingested_at: listing.ingested_at || new Date().toISOString(),
        raw_data: listing.raw_data || {},
        extraction_metadata: listing.extraction_metadata || {}
      }));
      
      try {
        const { data, error } = await supabase
          .from('public_listings')
          .upsert(batchData, {
            onConflict: 'content_hash',
            ignoreDuplicates: false
          })
          .select('id');
        
        if (error) {
          // If batch fails, try individual upserts
          productionLogger.warn('Batch upsert failed, falling back to individual upserts', {
            error: error.message,
            batch_size: batch.length
          });
          
          for (const listing of batch) {
            const result = await upsertPublicListing(listing);
            results.push(result);
            
            if (result.success) {
              successful++;
            } else {
              failed++;
            }
          }
        } else {
          // Batch succeeded
          const batchResults: UpsertResult[] = (data || []).map((item, index) => ({
            success: true,
            id: item.id,
            conflictResolution: 'updated'
          }));
          
          results.push(...batchResults);
          successful += batchResults.length;
        }
        
      } catch (batchError) {
        productionLogger.error('Batch processing failed', {
          error: batchError instanceof Error ? batchError.message : 'Unknown error',
          batch_start: i,
          batch_size: batch.length
        });
        
        // Add failed results for this batch
        for (let j = 0; j < batch.length; j++) {
          results.push({
            success: false,
            error: batchError instanceof Error ? batchError.message : 'Unknown error'
          });
          failed++;
        }
      }
    }
    
    const summary = {
      total: listings.length,
      successful,
      failed
    };
    
    productionLogger.info('Completed batch upsert', {
      ...summary,
      duration_ms: Date.now() - startTime
    });
    
    return {
      success: failed === 0,
      results,
      summary
    };
    
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : 'Unknown error';
    
    productionLogger.error('Exception during batch upsert', {
      error: errorMessage,
      count: listings.length,
      duration_ms: Date.now() - startTime
    });
    
    return {
      success: false,
      results: listings.map(() => ({ success: false, error: errorMessage })),
      summary: {
        total: listings.length,
        successful: 0,
        failed: listings.length
      }
    };
  }
}

/**
 * Check for duplicate content by hash
 */
export async function checkDuplicateContent(contentHash: string): Promise<{
  exists: boolean;
  existingId?: string;
  lastSeen?: string;
}> {
  try {
    const { data, error } = await supabase
      .from('public_listings')
      .select('id, ingested_at')
      .eq('content_hash', contentHash)
      .single();
    
    if (error && error.code !== 'PGRST116') { // PGRST116 = no rows returned
      productionLogger.error('Error checking duplicate content', {
        error: error.message,
        content_hash: contentHash
      });
      return { exists: false };
    }
    
    return {
      exists: !!data,
      existingId: data?.id,
      lastSeen: data?.ingested_at
    };
    
  } catch (error) {
    productionLogger.error('Exception checking duplicate content', {
      error: error instanceof Error ? error.message : 'Unknown error',
      content_hash: contentHash
    });
    
    return { exists: false };
  }
}

/**
 * Get content statistics
 */
export async function getContentStats(): Promise<{
  total_listings: number;
  unique_vins: number;
  unique_sources: number;
  latest_ingestion: string | null;
}> {
  try {
    const [totalResult, vinResult, sourceResult, latestResult] = await Promise.all([
      supabase.from('public_listings').select('id', { count: 'exact', head: true }),
      supabase.from('public_listings').select('vin', { count: 'exact', head: true }).not('vin', 'is', null),
      supabase.from('public_listings').select('source_site', { count: 'exact', head: true }),
      supabase.from('public_listings').select('ingested_at').order('ingested_at', { ascending: false }).limit(1).single()
    ]);
    
    return {
      total_listings: totalResult.count || 0,
      unique_vins: vinResult.count || 0,
      unique_sources: sourceResult.count || 0,
      latest_ingestion: latestResult.data?.ingested_at || null
    };
    
  } catch (error) {
    productionLogger.error('Error getting content stats', {
      error: error instanceof Error ? error.message : 'Unknown error'
    });
    
    return {
      total_listings: 0,
      unique_vins: 0,
      unique_sources: 0,
      latest_ingestion: null
    };
  }
}

/**
 * Clean up old content based on retention policy
 */
export async function cleanupOldContent(retentionDays: number = 90): Promise<{
  success: boolean;
  deletedCount: number;
  error?: string;
}> {
  const cutoffDate = new Date();
  cutoffDate.setDate(cutoffDate.getDate() - retentionDays);
  
  try {
    productionLogger.info('Starting content cleanup', {
      retention_days: retentionDays,
      cutoff_date: cutoffDate.toISOString()
    });
    
    const { count, error } = await supabase
      .from('public_listings')
      .delete({ count: 'exact' })
      .lt('ingested_at', cutoffDate.toISOString());
    
    if (error) {
      productionLogger.error('Failed to cleanup old content', {
        error: error.message
      });
      
      return {
        success: false,
        deletedCount: 0,
        error: error.message
      };
    }
    
    productionLogger.info('Completed content cleanup', {
      deleted_count: count || 0
    });
    
    return {
      success: true,
      deletedCount: count || 0
    };
    
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : 'Unknown error';
    
    productionLogger.error('Exception during content cleanup', {
      error: errorMessage
    });
    
    return {
      success: false,
      deletedCount: 0,
      error: errorMessage
    };
  }
}