import { supabase } from '@/integrations/supabase/client';

export interface CrawlTarget {
  url: string;
  siteName: string;
  lastChangeHours: number;
  sitePriority: number;
  predictedProfit: number;
  category: 'new' | 'changed' | 'stale';
  score: number;
}

export interface SchedulerConfig {
  recencyWeight: number;
  profitWeight: number;
  priorityWeight: number;
  maxQueueSize: number;
  staleThresholdHours: number;
}

/**
 * Incremental crawl scheduler with ROI and change-probability driven queues
 * Maintains separate queues for new, changed, and stale content
 */
export class IncrementalScheduler {
  private static readonly DEFAULT_CONFIG: SchedulerConfig = {
    recencyWeight: 0.4,
    profitWeight: 0.4,
    priorityWeight: 0.2,
    maxQueueSize: 1000,
    staleThresholdHours: 48
  };

  private newQueue: CrawlTarget[] = [];
  private changedQueue: CrawlTarget[] = [];
  private staleQueue: CrawlTarget[] = [];
  private config: SchedulerConfig;

  constructor(config?: Partial<SchedulerConfig>) {
    this.config = { ...IncrementalScheduler.DEFAULT_CONFIG, ...config };
  }

  /**
   * Calculate priority score for a crawl target
   */
  static scorePage(target: {
    lastChangeHours: number;
    sitePriority: number;
    predictedProfit: number;
  }, config: SchedulerConfig = IncrementalScheduler.DEFAULT_CONFIG): number {
    const { recencyWeight, profitWeight, priorityWeight } = config;
    
    // Recency score (higher for recent changes)
    const recencyScore = Math.exp(-target.lastChangeHours / 24) * recencyWeight;
    
    // Profit score (normalized to 0-1 range assuming max profit of $50k)
    const profitScore = Math.min(1, target.predictedProfit / 50000) * profitWeight;
    
    // Priority score (assuming 1-10 scale)
    const priorityScore = (target.sitePriority / 10) * priorityWeight;
    
    return recencyScore + profitScore + priorityScore;
  }

  /**
   * Add targets to appropriate queues based on their characteristics
   */
  async addTargets(targets: Omit<CrawlTarget, 'category' | 'score'>[]): Promise<void> {
    for (const target of targets) {
      const score = IncrementalScheduler.scorePage(target, this.config);
      const category = this.categorizeTarget(target);
      
      const crawlTarget: CrawlTarget = {
        ...target,
        category,
        score
      };

      // Add to appropriate queue
      switch (category) {
        case 'new':
          this.addToQueue(this.newQueue, crawlTarget);
          break;
        case 'changed':
          this.addToQueue(this.changedQueue, crawlTarget);
          break;
        case 'stale':
          this.addToQueue(this.staleQueue, crawlTarget);
          break;
      }
    }

    // Sort queues by score
    this.sortQueues();
  }

  /**
   * Get next batch of targets to crawl, prioritizing by queue and score
   */
  getNextBatch(batchSize: number = 10): CrawlTarget[] {
    const batch: CrawlTarget[] = [];
    
    // Prioritize new > changed > stale
    const queues = [
      { queue: this.newQueue, weight: 0.5 },
      { queue: this.changedQueue, weight: 0.3 },
      { queue: this.staleQueue, weight: 0.2 }
    ];

    for (const { queue, weight } of queues) {
      const queueBatchSize = Math.ceil(batchSize * weight);
      const queueTargets = queue.splice(0, queueBatchSize);
      batch.push(...queueTargets);
      
      if (batch.length >= batchSize) break;
    }

    return batch.slice(0, batchSize);
  }

  /**
   * Load targets from database based on site activity and predictions
   */
  async loadTargetsFromDatabase(): Promise<void> {
    try {
      // Load public listings with enriched data for scoring
      const { data: listings, error } = await supabase
        .from('public_listings')
        .select(`
          listing_url,
          source_site,
          created_at,
          updated_at,
          current_bid,
          auction_end
        `)
        .eq('is_active', true)
        .order('updated_at', { ascending: false })
        .limit(this.config.maxQueueSize * 2); // Load more than needed for filtering

      if (error) throw error;

      // Convert to crawl targets
      const targets = await Promise.all(
        (listings || []).map(async (listing) => {
          const lastChangeHours = this.calculateLastChangeHours(listing.updated_at);
          const sitePriority = await this.getSitePriority(listing.source_site);
          const predictedProfit = await this.predictProfit(listing);

          return {
            url: listing.listing_url,
            siteName: listing.source_site,
            lastChangeHours,
            sitePriority,
            predictedProfit
          };
        })
      );

      await this.addTargets(targets);
    } catch (error) {
      console.error('Failed to load targets from database:', error);
    }
  }

  /**
   * Categorize target based on age and change frequency
   */
  private categorizeTarget(target: Omit<CrawlTarget, 'category' | 'score'>): 'new' | 'changed' | 'stale' {
    if (target.lastChangeHours <= 1) {
      return 'new';
    } else if (target.lastChangeHours <= this.config.staleThresholdHours) {
      return 'changed';
    } else {
      return 'stale';
    }
  }

  /**
   * Add target to queue with size limit enforcement
   */
  private addToQueue(queue: CrawlTarget[], target: CrawlTarget): void {
    queue.push(target);
    
    // Enforce queue size limit by removing lowest-scored items
    if (queue.length > this.config.maxQueueSize / 3) { // Divide by 3 queues
      queue.sort((a, b) => b.score - a.score);
      queue.splice(Math.floor(this.config.maxQueueSize / 3));
    }
  }

  /**
   * Sort all queues by score (highest first)
   */
  private sortQueues(): void {
    this.newQueue.sort((a, b) => b.score - a.score);
    this.changedQueue.sort((a, b) => b.score - a.score);
    this.staleQueue.sort((a, b) => b.score - a.score);
  }

  /**
   * Calculate hours since last change
   */
  private calculateLastChangeHours(updatedAt: string): number {
    const now = Date.now();
    const updated = new Date(updatedAt).getTime();
    return (now - updated) / (1000 * 60 * 60); // Convert to hours
  }

  /**
   * Get site priority from configuration
   */
  private async getSitePriority(siteName: string): Promise<number> {
    try {
      const { data, error } = await supabase
        .from('scraper_sites')
        .select('priority')
        .eq('name', siteName)
        .single();

      if (error) throw error;
      return data?.priority || 5; // Default priority
    } catch (error) {
      return 5; // Default priority on error
    }
  }

  /**
   * Predict profit potential for a listing
   */
  private async predictProfit(listing: any): Promise<number> {
    // Simple profit prediction based on current bid and auction timing
    const currentBid = listing.current_bid || 0;
    const auctionEnd = listing.auction_end ? new Date(listing.auction_end) : null;
    
    if (!auctionEnd) return currentBid * 0.2; // 20% profit assumption
    
    const timeLeft = auctionEnd.getTime() - Date.now();
    const hoursLeft = timeLeft / (1000 * 60 * 60);
    
    // Higher profit potential for auctions ending soon (urgency factor)
    const urgencyMultiplier = hoursLeft <= 24 ? 1.5 : hoursLeft <= 72 ? 1.2 : 1.0;
    
    return currentBid * 0.2 * urgencyMultiplier;
  }

  /**
   * Get queue statistics for monitoring
   */
  getQueueStats(): {
    newCount: number;
    changedCount: number;
    staleCount: number;
    totalCount: number;
    avgScores: { new: number; changed: number; stale: number };
  } {
    const avgScore = (queue: CrawlTarget[]) =>
      queue.length > 0 ? queue.reduce((sum, t) => sum + t.score, 0) / queue.length : 0;

    return {
      newCount: this.newQueue.length,
      changedCount: this.changedQueue.length,
      staleCount: this.staleQueue.length,
      totalCount: this.newQueue.length + this.changedQueue.length + this.staleQueue.length,
      avgScores: {
        new: avgScore(this.newQueue),
        changed: avgScore(this.changedQueue),
        stale: avgScore(this.staleQueue)
      }
    };
  }

  /**
   * Clear all queues (for testing or reset)
   */
  clearQueues(): void {
    this.newQueue = [];
    this.changedQueue = [];
    this.staleQueue = [];
  }

  /**
   * Update configuration
   */
  updateConfig(newConfig: Partial<SchedulerConfig>): void {
    this.config = { ...this.config, ...newConfig };
    
    // Re-score and re-sort existing targets
    const allTargets = [...this.newQueue, ...this.changedQueue, ...this.staleQueue];
    this.clearQueues();
    
    // Re-add with new scoring
    allTargets.forEach(target => {
      target.score = IncrementalScheduler.scorePage(target, this.config);
      const category = this.categorizeTarget(target);
      target.category = category;
      
      switch (category) {
        case 'new': this.addToQueue(this.newQueue, target); break;
        case 'changed': this.addToQueue(this.changedQueue, target); break;
        case 'stale': this.addToQueue(this.staleQueue, target); break;
      }
    });
    
    this.sortQueues();
  }
}

export default IncrementalScheduler;