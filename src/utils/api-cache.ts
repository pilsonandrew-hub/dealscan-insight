/**
 * Intelligent API response caching with TTL and memory management
 * Prevents expensive recalculations and reduces API load
 */

import { createLogger } from '@/utils/productionLogger';

const logger = createLogger('ApiCache');

interface CacheEntry<T> {
  data: T;
  timestamp: number;
  ttl: number;
}

interface CacheConfig {
  defaultTTL: number;
  maxSize: number;
  enableLogging: boolean;
}

export class APICache {
  private cache = new Map<string, CacheEntry<any>>();
  private accessOrder: string[] = [];

  constructor(private config: CacheConfig = {
    defaultTTL: 5 * 60 * 1000, // 5 minutes
    maxSize: 100,
    enableLogging: false
  }) {}

  set<T>(key: string, data: T, customTTL?: number): void {
    const ttl = customTTL || this.config.defaultTTL;
    
    // Remove if exists to update access order
    if (this.cache.has(key)) {
      this.accessOrder = this.accessOrder.filter(k => k !== key);
    }

    // Enforce max size with LRU eviction
    if (this.cache.size >= this.config.maxSize) {
      const oldestKey = this.accessOrder.shift();
      if (oldestKey) {
        this.cache.delete(oldestKey);
        if (this.config.enableLogging) {
          logger.info('Cache evicted oldest entry', { key: oldestKey });
        }
      }
    }

    this.cache.set(key, {
      data,
      timestamp: Date.now(),
      ttl
    });
    
    this.accessOrder.push(key);
    
    if (this.config.enableLogging) {
      logger.debug('Cache set', { key, ttl: `${ttl}ms` });
    }
  }

  get<T>(key: string): T | null {
    const entry = this.cache.get(key);
    
    if (!entry) {
      if (this.config.enableLogging) {
        logger.debug('Cache miss', { key });
      }
      return null;
    }

    // Check if expired
    if (Date.now() - entry.timestamp > entry.ttl) {
      this.cache.delete(key);
      this.accessOrder = this.accessOrder.filter(k => k !== key);
      if (this.config.enableLogging) {
        logger.debug('Cache expired', { key });
      }
      return null;
    }

    // Update access order for LRU
    this.accessOrder = this.accessOrder.filter(k => k !== key);
    this.accessOrder.push(key);

    if (this.config.enableLogging) {
      logger.debug('Cache hit', { key });
    }
    
    return entry.data;
  }

  invalidate(keyPattern?: string): void {
    if (!keyPattern) {
      this.cache.clear();
      this.accessOrder = [];
      if (this.config.enableLogging) {
        logger.info('Cache cleared completely');
      }
      return;
    }

    const keysToDelete = Array.from(this.cache.keys()).filter(key => 
      key.includes(keyPattern)
    );

    keysToDelete.forEach(key => {
      this.cache.delete(key);
      this.accessOrder = this.accessOrder.filter(k => k !== key);
    });

    if (this.config.enableLogging) {
      logger.info('Cache invalidated by pattern', { pattern: keyPattern, deletedCount: keysToDelete.length });
    }
  }

  getStats() {
    const totalHits = Array.from(this.cache.entries()).length;
    const totalMisses = this.accessOrder.length - totalHits;
    
    return {
      size: this.cache.size,
      maxSize: this.config.maxSize,
      entries: Array.from(this.cache.keys()),
      hits: totalHits,
      misses: Math.max(0, totalMisses),
      hitRate: totalHits > 0 ? (totalHits / (totalHits + totalMisses)) * 100 : 0
    };
  }
}

// Global cache instance
export const apiCache = new APICache({
  defaultTTL: 5 * 60 * 1000, // 5 minutes
  maxSize: 100,
  enableLogging: process.env.NODE_ENV === 'development'
});