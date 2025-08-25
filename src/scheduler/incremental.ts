/**
 * Incremental Crawl Scheduler - ROI + change-probability scoring
 * Replaces flat batch crawls with intelligent priority queuing
 */

import { logger } from '@/lib/logger';

export interface CrawlItem {
  url: string;
  siteId: string;
  lastChange?: number;
  predictedProfit?: number;
  sitePriority: number;
  contentHash?: string;
  etag?: string;
  lastModified?: string;
  successRate?: number;
  avgExtractionTime?: number;
  lastError?: string;
  retryCount?: number;
  metadata?: Record<string, unknown>;
}

export interface SchedulerMetrics {
  totalItems: number;
  highPriorityItems: number;
  mediumPriorityItems: number;
  lowPriorityItems: number;
  avgScore: number;
  oldestItem: number;
  newestItem: number;
}

/**
 * Calculate priority score for crawl item
 * Formula: 0.6*profit + 0.3*recency + 0.1*sitePriority
 */
export function score(item: CrawlItem): number {
  // Recency factor (recent changes get higher priority)
  const now = Date.now();
  const lastChange = item.lastChange ?? now - (7 * 24 * 60 * 60 * 1000); // Default to 7 days ago
  const hoursSinceChange = Math.max(1, (now - lastChange) / (1000 * 60 * 60));
  const recencyScore = Math.min(1, 1 / Math.log10(hoursSinceChange + 1));

  // Profit factor (normalized to 0-1 scale)
  const profitScore = Math.min(1, Math.max(0, (item.predictedProfit ?? 0) / 10000));

  // Site priority factor (0-10 scale normalized to 0-1)
  const priorityScore = Math.min(1, item.sitePriority / 10);

  // Success rate factor (boost items that historically succeed)
  const successScore = item.successRate ?? 0.5;

  // Speed factor (faster extractions get slight boost)
  const avgTime = item.avgExtractionTime ?? 5000;
  const speedScore = Math.min(1, 1 / (avgTime / 1000));

  // Error penalty (items with recent errors get lower priority)
  const errorPenalty = item.lastError ? 0.8 : 1.0;

  // Retry penalty (heavily penalize items that keep failing)
  const retryPenalty = Math.max(0.1, 1 - ((item.retryCount ?? 0) * 0.2));

  const finalScore = (
    0.35 * profitScore +     // Primary: expected profit
    0.25 * recencyScore +    // Secondary: freshness
    0.15 * priorityScore +   // Tertiary: site importance
    0.10 * successScore +    // Historical success
    0.10 * speedScore +      // Extraction speed
    0.05 * errorPenalty      // Error history
  ) * retryPenalty;

  return Math.max(0, Math.min(1, finalScore));
}

/**
 * Schedule crawl items by priority score
 */
export function schedule(queue: CrawlItem[]): CrawlItem[] {
  const scoredItems = queue.map(item => ({
    ...item,
    score: score(item)
  }));

  // Sort by score (highest first)
  const sorted = scoredItems.sort((a, b) => b.score - a.score);

  logger.info('Scheduled crawl queue', {
    totalItems: queue.length,
    highPriority: sorted.filter(i => i.score >= 0.7).length,
    mediumPriority: sorted.filter(i => i.score >= 0.4 && i.score < 0.7).length,
    lowPriority: sorted.filter(i => i.score < 0.4).length,
    avgScore: (sorted.reduce((sum, i) => sum + i.score, 0) / sorted.length).toFixed(3)
  });

  return sorted;
}

/**
 * Filter items that need crawling (based on content hash, etag, etc.)
 */
export function filterStaleItems(items: CrawlItem[], maxAge = 24 * 60 * 60 * 1000): CrawlItem[] {
  const now = Date.now();
  
  return items.filter(item => {
    // Always crawl if no last change time
    if (!item.lastChange) return true;

    // Always crawl if older than max age
    if ((now - item.lastChange) > maxAge) return true;

    // Skip if we have a content hash (unchanged content)
    if (item.contentHash) return false;

    // Skip if we have fresh etag/lastModified headers
    if (item.etag || item.lastModified) {
      // These would be checked via conditional GET
      return false;
    }

    return true;
  });
}

/**
 * Batch items for efficient processing
 */
export function batchItems(items: CrawlItem[], batchSize = 10, maxConcurrent = 3): CrawlItem[][] {
  const batches: CrawlItem[][] = [];
  
  // Group by site for rate limiting
  const itemsBySite = new Map<string, CrawlItem[]>();
  for (const item of items) {
    if (!itemsBySite.has(item.siteId)) {
      itemsBySite.set(item.siteId, []);
    }
    itemsBySite.get(item.siteId)!.push(item);
  }

  // Create balanced batches
  const siteQueues = Array.from(itemsBySite.values());
  let batchIndex = 0;

  while (siteQueues.some(queue => queue.length > 0)) {
    if (!batches[batchIndex]) {
      batches[batchIndex] = [];
    }

    let addedToBatch = 0;
    
    for (const queue of siteQueues) {
      if (queue.length > 0 && addedToBatch < batchSize) {
        const item = queue.shift()!;
        batches[batchIndex].push(item);
        addedToBatch++;
      }
    }

    if (addedToBatch === 0) break;
    batchIndex++;
  }

  logger.info('Created batches for processing', {
    totalItems: items.length,
    batchCount: batches.length,
    avgBatchSize: (items.length / batches.length).toFixed(1),
    maxConcurrent
  });

  return batches;
}

/**
 * Get scheduler metrics
 */
export function getSchedulerMetrics(items: CrawlItem[]): SchedulerMetrics {
  const scores = items.map(score);
  const changes = items.map(i => i.lastChange ?? 0).filter(c => c > 0);

  return {
    totalItems: items.length,
    highPriorityItems: scores.filter(s => s >= 0.7).length,
    mediumPriorityItems: scores.filter(s => s >= 0.4 && s < 0.7).length,
    lowPriorityItems: scores.filter(s => s < 0.4).length,
    avgScore: scores.reduce((sum, s) => sum + s, 0) / scores.length,
    oldestItem: changes.length > 0 ? Math.min(...changes) : 0,
    newestItem: changes.length > 0 ? Math.max(...changes) : 0
  };
}

/**
 * Update crawl item after processing
 */
export function updateCrawlItem(
  item: CrawlItem,
  result: {
    success: boolean;
    contentHash?: string;
    etag?: string;
    lastModified?: string;
    extractionTime?: number;
    error?: string;
    extractedData?: Record<string, unknown>;
  }
): CrawlItem {
  const now = Date.now();
  
  const updated: CrawlItem = {
    ...item,
    lastChange: now,
    contentHash: result.contentHash || item.contentHash,
    etag: result.etag || item.etag,
    lastModified: result.lastModified || item.lastModified,
    avgExtractionTime: result.extractionTime || item.avgExtractionTime,
    lastError: result.success ? undefined : result.error,
    retryCount: result.success ? 0 : (item.retryCount ?? 0) + 1,
    successRate: updateSuccessRate(item.successRate, result.success),
    metadata: {
      ...item.metadata,
      lastProcessed: now,
      processingResult: result.success ? 'success' : 'failed',
      ...(result.extractedData && { lastExtraction: result.extractedData })
    }
  };

  return updated;
}

/**
 * Update success rate using exponential moving average
 */
function updateSuccessRate(currentRate: number | undefined, success: boolean): number {
  const alpha = 0.1; // Smoothing factor
  const newRate = success ? 1 : 0;
  
  if (currentRate === undefined) {
    return newRate;
  }
  
  return alpha * newRate + (1 - alpha) * currentRate;
}

/**
 * Create crawl item from listing URL
 */
export function createCrawlItem(
  url: string,
  siteId: string,
  options: Partial<CrawlItem> = {}
): CrawlItem {
  return {
    url,
    siteId,
    sitePriority: 5, // Default medium priority
    lastChange: Date.now(),
    successRate: 0.5, // Default 50% success rate
    retryCount: 0,
    ...options
  };
}
