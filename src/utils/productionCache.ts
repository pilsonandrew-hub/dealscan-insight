/**
 * Production-grade caching with ETag, TTL jitter, and single-flight
 */

import { logger } from './productionLogger';

export interface CacheConfig {
  maxSize: number;
  defaultTTL: number;
  enableJitter: boolean;
  enableSingleFlight: boolean;
}

export interface CacheEntry<T> {
  data: T;
  timestamp: number;
  ttl: number;
  etag?: string;
  accessCount: number;
  lastAccessed: number;
}

export interface CacheStats {
  size: number;
  hits: number;
  misses: number;
  hitRate: number;
  evictions: number;
  totalRequests: number;
}

/**
 * Production cache with LRU eviction, TTL jitter, and ETag support
 */
export class ProductionCache {
  private cache = new Map<string, CacheEntry<any>>();
  private stats: CacheStats = {
    size: 0,
    hits: 0,
    misses: 0,
    hitRate: 0,
    evictions: 0,
    totalRequests: 0
  };
  private singleFlightPromises = new Map<string, Promise<any>>();

  constructor(private config: CacheConfig) {}

  /**
   * Get item from cache with ETag support
   */
  get<T>(key: string, ifNoneMatch?: string): T | null {
    this.stats.totalRequests++;
    
    const entry = this.cache.get(key);
    if (!entry) {
      this.stats.misses++;
      this.updateHitRate();
      return null;
    }

    // Check if expired
    if (this.isExpired(entry)) {
      this.cache.delete(key);
      this.stats.misses++;
      this.stats.size--;
      this.updateHitRate();
      return null;
    }

    // ETag validation
    if (ifNoneMatch && entry.etag && ifNoneMatch === entry.etag) {
      // Return 304 equivalent - caller should handle
      this.stats.hits++;
      entry.accessCount++;
      entry.lastAccessed = Date.now();
      this.updateHitRate();
      return null;
    }

    this.stats.hits++;
    entry.accessCount++;
    entry.lastAccessed = Date.now();
    this.updateHitRate();
    
    return entry.data;
  }

  /**
   * Set item in cache with optional ETag
   */
  set<T>(key: string, data: T, customTTL?: number, etag?: string): void {
    const ttl = customTTL || this.config.defaultTTL;
    const jitteredTTL = this.config.enableJitter ? this.addJitter(ttl) : ttl;
    
    const entry: CacheEntry<T> = {
      data,
      timestamp: Date.now(),
      ttl: jitteredTTL,
      etag,
      accessCount: 1,
      lastAccessed: Date.now()
    };

    // Evict if at capacity
    if (this.cache.size >= this.config.maxSize && !this.cache.has(key)) {
      this.evictLRU();
    }

    this.cache.set(key, entry);
    if (!this.cache.has(key)) {
      this.stats.size++;
    }

    logger.debug('Cache set', { key, ttl: jitteredTTL, etag, size: this.stats.size });
  }

  /**
   * Single-flight pattern - prevent cache stampedes
   */
  async singleFlight<T>(
    key: string, 
    fetcher: () => Promise<T>,
    ttl?: number,
    etagGenerator?: (data: T) => string
  ): Promise<T> {
    if (!this.config.enableSingleFlight) {
      return this.executeWithCache(key, fetcher, ttl, etagGenerator);
    }

    // Check if already in flight
    const inFlight = this.singleFlightPromises.get(key);
    if (inFlight) {
      logger.debug('Single-flight hit', { key });
      return inFlight;
    }

    // Execute and cache the promise
    const promise = this.executeWithCache(key, fetcher, ttl, etagGenerator);
    this.singleFlightPromises.set(key, promise);

    try {
      const result = await promise;
      return result;
    } finally {
      this.singleFlightPromises.delete(key);
    }
  }

  /**
   * Execute fetcher and cache result
   */
  private async executeWithCache<T>(
    key: string,
    fetcher: () => Promise<T>,
    ttl?: number,
    etagGenerator?: (data: T) => string
  ): Promise<T> {
    try {
      const data = await fetcher();
      const etag = etagGenerator ? etagGenerator(data) : undefined;
      this.set(key, data, ttl, etag);
      return data;
    } catch (error) {
      logger.error('Cache fetcher failed', error as Error, { key });
      throw error;
    }
  }

  /**
   * Check conditional GET (304 Not Modified)
   */
  checkConditionalGet(key: string, ifNoneMatch?: string): { hit: boolean; etag?: string } {
    const entry = this.cache.get(key);
    if (!entry || this.isExpired(entry)) {
      return { hit: false };
    }

    if (ifNoneMatch && entry.etag && ifNoneMatch === entry.etag) {
      entry.accessCount++;
      entry.lastAccessed = Date.now();
      return { hit: true, etag: entry.etag };
    }

    return { hit: false, etag: entry.etag };
  }

  /**
   * Invalidate cache entries by pattern
   */
  invalidate(pattern?: string): void {
    if (!pattern) {
      const size = this.cache.size;
      this.cache.clear();
      this.singleFlightPromises.clear();
      this.stats.size = 0;
      this.stats.evictions += size;
      logger.info('Cache cleared', { evicted: size });
      return;
    }

    const regex = new RegExp(pattern);
    let evicted = 0;
    
    for (const [key] of this.cache) {
      if (regex.test(key)) {
        this.cache.delete(key);
        evicted++;
      }
    }
    
    this.stats.size -= evicted;
    this.stats.evictions += evicted;
    logger.info('Cache invalidated by pattern', { pattern, evicted });
  }

  /**
   * Get cache statistics
   */
  getStats(): CacheStats {
    return { ...this.stats };
  }

  /**
   * Cleanup expired entries
   */
  cleanup(): number {
    let cleaned = 0;
    const now = Date.now();
    
    for (const [key, entry] of this.cache) {
      if (this.isExpired(entry)) {
        this.cache.delete(key);
        cleaned++;
      }
    }
    
    this.stats.size -= cleaned;
    this.stats.evictions += cleaned;
    
    if (cleaned > 0) {
      logger.debug('Cache cleanup completed', { cleaned, remaining: this.stats.size });
    }
    
    return cleaned;
  }

  /**
   * Check if entry is expired
   */
  private isExpired(entry: CacheEntry<any>): boolean {
    return Date.now() - entry.timestamp > entry.ttl;
  }

  /**
   * Add TTL jitter to prevent synchronized expiry
   */
  private addJitter(ttl: number): number {
    const jitter = ttl * 0.15; // ±15% jitter
    return ttl + (Math.random() - 0.5) * 2 * jitter;
  }

  /**
   * Evict least recently used entry
   */
  private evictLRU(): void {
    let oldestKey: string | undefined;
    let oldestTime = Date.now();
    
    for (const [key, entry] of this.cache) {
      if (entry.lastAccessed < oldestTime) {
        oldestTime = entry.lastAccessed;
        oldestKey = key;
      }
    }
    
    if (oldestKey) {
      this.cache.delete(oldestKey);
      this.stats.size--;
      this.stats.evictions++;
      logger.debug('Cache LRU eviction', { key: oldestKey });
    }
  }

  /**
   * Update hit rate
   */
  private updateHitRate(): void {
    this.stats.hitRate = this.stats.totalRequests > 0 
      ? this.stats.hits / this.stats.totalRequests 
      : 0;
  }
}

// Global production cache instance
export const productionCache = new ProductionCache({
  maxSize: 2000,
  defaultTTL: 300_000, // 5 minutes
  enableJitter: true,
  enableSingleFlight: true
});

// ETag generation helpers
export const generateETag = (data: any): string => {
  // Simple hash-based ETag
  const str = JSON.stringify(data);
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash; // Convert to 32-bit integer
  }
  return `W/"${Math.abs(hash).toString(36)}"`;
};

export const generateContentHashETag = (contentHash: string): string => {
  return `"${contentHash}"`;
};