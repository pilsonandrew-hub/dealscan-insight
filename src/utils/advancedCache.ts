/**
 * Advanced caching system with hit/miss tracking
 * Improved cache for system evaluation
 */

interface CacheEntry<T> {
  data: T;
  timestamp: number;
  ttl: number;
  accessCount: number;
}

interface CacheStats {
  size: number;
  maxSize: number;
  entries: string[];
  hits: number;
  misses: number;
  hitRate: number;
}

export class AdvancedCache {
  private cache = new Map<string, CacheEntry<any>>();
  private accessOrder: string[] = [];
  private stats = { hits: 0, misses: 0 };

  constructor(
    private config = {
      defaultTTL: 5 * 60 * 1000, // 5 minutes
      maxSize: 100,
      enableLogging: false
    }
  ) {}

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
          console.log(`Cache evicted: ${oldestKey}`);
        }
      }
    }

    this.cache.set(key, {
      data,
      timestamp: Date.now(),
      ttl,
      accessCount: 0
    });
    
    this.accessOrder.push(key);
    
    if (this.config.enableLogging) {
      console.log(`Cache set: ${key}, TTL: ${ttl}ms`);
    }
  }

  get<T>(key: string): T | null {
    const entry = this.cache.get(key);
    
    if (!entry) {
      this.stats.misses++;
      if (this.config.enableLogging) {
        console.log(`Cache miss: ${key}`);
      }
      return null;
    }

    // Check if expired
    if (Date.now() - entry.timestamp > entry.ttl) {
      this.cache.delete(key);
      this.accessOrder = this.accessOrder.filter(k => k !== key);
      this.stats.misses++;
      if (this.config.enableLogging) {
        console.log(`Cache expired: ${key}`);
      }
      return null;
    }

    // Update access stats
    entry.accessCount++;
    this.stats.hits++;

    // Update access order for LRU
    this.accessOrder = this.accessOrder.filter(k => k !== key);
    this.accessOrder.push(key);

    if (this.config.enableLogging) {
      console.log(`Cache hit: ${key}`);
    }
    
    return entry.data;
  }

  invalidate(keyPattern?: string): void {
    if (!keyPattern) {
      this.cache.clear();
      this.accessOrder = [];
      if (this.config.enableLogging) {
        console.log('Cache cleared completely');
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
      console.log(`Cache invalidated pattern: ${keyPattern}, deleted: ${keysToDelete.length}`);
    }
  }

  getStats(): CacheStats {
    const total = this.stats.hits + this.stats.misses;
    const hitRate = total > 0 ? (this.stats.hits / total) * 100 : 0;
    
    return {
      size: this.cache.size,
      maxSize: this.config.maxSize,
      entries: Array.from(this.cache.keys()),
      hits: this.stats.hits,
      misses: this.stats.misses,
      hitRate: Math.round(hitRate * 100) / 100
    };
  }

  // Reset stats (useful for testing)
  resetStats(): void {
    this.stats = { hits: 0, misses: 0 };
  }
}

// Global enhanced cache instance
export const advancedCache = new AdvancedCache({
  defaultTTL: 5 * 60 * 1000, // 5 minutes
  maxSize: 100,
  enableLogging: process.env.NODE_ENV === 'development'
});