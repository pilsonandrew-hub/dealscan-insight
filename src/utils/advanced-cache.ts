/**
 * Advanced Caching System
 * Multi-tier caching with LRU, TTL, and performance optimization
 */

import { performanceMonitor } from './performance-monitor';

export interface CacheOptions {
  ttl?: number; // Time to live in milliseconds
  maxSize?: number; // Maximum cache size (LRU eviction)
  persistent?: boolean; // Use localStorage for persistence
  namespace?: string; // Cache namespace for separation
  onEviction?: (key: string, value: any) => void;
}

export interface CacheEntry<T> {
  value: T;
  timestamp: number;
  ttl: number;
  accessCount: number;
  lastAccessed: number;
}

export interface CacheStats {
  hits: number;
  misses: number;
  hitRate: number;
  size: number;
  maxSize: number;
  evictions: number;
}

class AdvancedCache<T = any> {
  private cache = new Map<string, CacheEntry<T>>();
  private stats: CacheStats = {
    hits: 0,
    misses: 0,
    hitRate: 0,
    size: 0,
    maxSize: 0,
    evictions: 0
  };
  private options: Required<CacheOptions>;

  constructor(options: CacheOptions = {}) {
    this.options = {
      ttl: options.ttl || 5 * 60 * 1000, // 5 minutes default
      maxSize: options.maxSize || 1000,
      persistent: options.persistent || false,
      namespace: options.namespace || 'default',
      onEviction: options.onEviction || (() => {})
    };

    this.stats.maxSize = this.options.maxSize;

    if (this.options.persistent) {
      this.loadFromStorage();
    }

    // Cleanup expired entries every minute
    setInterval(() => this.cleanup(), 60000);
  }

  public set(key: string, value: T, ttl?: number): void {
    const stopTiming = performanceMonitor.startTimer('cache_set');
    
    try {
      const entry: CacheEntry<T> = {
        value,
        timestamp: Date.now(),
        ttl: ttl || this.options.ttl,
        accessCount: 0,
        lastAccessed: Date.now()
      };

      // Check if we need to evict
      if (this.cache.size >= this.options.maxSize && !this.cache.has(key)) {
        this.evictLRU();
      }

      this.cache.set(key, entry);
      this.stats.size = this.cache.size;

      if (this.options.persistent) {
        this.saveToStorage();
      }
    } finally {
      stopTiming.end(true);
    }
  }

  public get(key: string): T | null {
    const stopTiming = performanceMonitor.startTimer('cache_get');
    
    try {
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
        this.stats.size = this.cache.size;
        this.updateHitRate();
        return null;
      }

      // Update access info
      entry.accessCount++;
      entry.lastAccessed = Date.now();
      
      this.stats.hits++;
      this.updateHitRate();
      
      return entry.value;
    } finally {
      stopTiming.end(true);
    }
  }

  public has(key: string): boolean {
    const entry = this.cache.get(key);
    return entry ? !this.isExpired(entry) : false;
  }

  public delete(key: string): boolean {
    const result = this.cache.delete(key);
    this.stats.size = this.cache.size;
    
    if (this.options.persistent) {
      this.saveToStorage();
    }
    
    return result;
  }

  public clear(): void {
    this.cache.clear();
    this.stats.size = 0;
    this.stats.hits = 0;
    this.stats.misses = 0;
    this.stats.evictions = 0;
    this.updateHitRate();

    if (this.options.persistent) {
      this.clearStorage();
    }
  }

  public getOrSet(key: string, factory: () => T | Promise<T>, ttl?: number): T | Promise<T> {
    const cached = this.get(key);
    if (cached !== null) {
      return cached;
    }

    const value = factory();
    
    if (value instanceof Promise) {
      return value.then(resolved => {
        this.set(key, resolved, ttl);
        return resolved;
      });
    } else {
      this.set(key, value, ttl);
      return value;
    }
  }

  public mget(keys: string[]): Map<string, T | null> {
    const stopTiming = performanceMonitor.startTimer('cache_mget');
    
    try {
      const result = new Map<string, T | null>();
      keys.forEach(key => {
        result.set(key, this.get(key));
      });
      return result;
    } finally {
      stopTiming.end(true);
    }
  }

  public mset(entries: Map<string, T>, ttl?: number): void {
    const stopTiming = performanceMonitor.startTimer('cache_mset');
    
    try {
      entries.forEach((value, key) => {
        this.set(key, value, ttl);
      });
    } finally {
      stopTiming.end(true);
    }
  }

  private isExpired(entry: CacheEntry<T>): boolean {
    return Date.now() - entry.timestamp > entry.ttl;
  }

  private evictLRU(): void {
    let lruKey: string | null = null;
    let lruTime = Date.now();

    for (const [key, entry] of this.cache.entries()) {
      if (entry.lastAccessed < lruTime) {
        lruTime = entry.lastAccessed;
        lruKey = key;
      }
    }

    if (lruKey) {
      const evicted = this.cache.get(lruKey);
      this.cache.delete(lruKey);
      this.stats.evictions++;
      
      if (evicted) {
        this.options.onEviction(lruKey, evicted.value);
      }
    }
  }

  private cleanup(): void {
    const now = Date.now();
    const keysToDelete: string[] = [];

    for (const [key, entry] of this.cache.entries()) {
      if (now - entry.timestamp > entry.ttl) {
        keysToDelete.push(key);
      }
    }

    keysToDelete.forEach(key => this.cache.delete(key));
    this.stats.size = this.cache.size;

    if (keysToDelete.length > 0 && this.options.persistent) {
      this.saveToStorage();
    }
  }

  private updateHitRate(): void {
    const total = this.stats.hits + this.stats.misses;
    this.stats.hitRate = total > 0 ? this.stats.hits / total : 0;
  }

  private loadFromStorage(): void {
    if (typeof window === 'undefined') return;

    try {
      const stored = localStorage.getItem(`cache_${this.options.namespace}`);
      if (stored) {
        const data = JSON.parse(stored);
        data.forEach((entry: CacheEntry<T>, key: string) => {
          if (!this.isExpired(entry)) {
            this.cache.set(key, entry);
          }
        });
        this.stats.size = this.cache.size;
      }
    } catch (error) {
      console.warn('Failed to load cache from storage:', error);
    }
  }

  private saveToStorage(): void {
    if (typeof window === 'undefined') return;

    try {
      const data = Array.from(this.cache.entries());
      localStorage.setItem(`cache_${this.options.namespace}`, JSON.stringify(data));
    } catch (error) {
      console.warn('Failed to save cache to storage:', error);
    }
  }

  private clearStorage(): void {
    if (typeof window === 'undefined') return;

    try {
      localStorage.removeItem(`cache_${this.options.namespace}`);
    } catch (error) {
      console.warn('Failed to clear cache storage:', error);
    }
  }

  public getStats(): CacheStats {
    return { ...this.stats };
  }

  public keys(): string[] {
    return Array.from(this.cache.keys());
  }

  public values(): T[] {
    return Array.from(this.cache.values()).map(entry => entry.value);
  }

  public entries(): Array<[string, T]> {
    return Array.from(this.cache.entries()).map(([key, entry]) => [key, entry.value]);
  }

  public size(): number {
    return this.cache.size;
  }
}

// Multi-tier cache system
class MultiTierCache {
  private l1Cache: AdvancedCache; // Memory cache (fast)
  private l2Cache: AdvancedCache; // Persistent cache (slower but persistent)

  constructor() {
    this.l1Cache = new AdvancedCache({
      maxSize: 500,
      ttl: 5 * 60 * 1000, // 5 minutes
      persistent: false,
      namespace: 'l1'
    });

    this.l2Cache = new AdvancedCache({
      maxSize: 2000,
      ttl: 30 * 60 * 1000, // 30 minutes
      persistent: true,
      namespace: 'l2'
    });
  }

  public get<T>(key: string): T | null {
    // Try L1 first
    let value = this.l1Cache.get(key);
    if (value !== null) {
      return value;
    }

    // Try L2
    value = this.l2Cache.get(key);
    if (value !== null) {
      // Promote to L1
      this.l1Cache.set(key, value);
      return value;
    }

    return null;
  }

  public set(key: string, value: any, ttl?: number): void {
    this.l1Cache.set(key, value, ttl);
    this.l2Cache.set(key, value, ttl ? ttl * 2 : undefined); // L2 lives longer
  }

  public getStats() {
    return {
      l1: this.l1Cache.getStats(),
      l2: this.l2Cache.getStats()
    };
  }

  public clear(): void {
    this.l1Cache.clear();
    this.l2Cache.clear();
  }
}

export { AdvancedCache, MultiTierCache };
export const globalCache = new MultiTierCache();