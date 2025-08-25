/**
 * MemoryManager - Memory optimization and leak detection utilities
 * Provides memory monitoring and cleanup mechanisms
 */

import React, { useEffect, useRef, useCallback, useState } from 'react';
import { logger } from '@/utils/secureLogger';

export interface MemoryStats {
  usedJSHeapSize: number;
  totalJSHeapSize: number;
  jsHeapSizeLimit: number;
  usedMB: number;
  totalMB: number;
  limitMB: number;
  usagePercentage: number;
}

export class MemoryManager {
  private static instance: MemoryManager;
  private observers: Set<(stats: MemoryStats) => void> = new Set();
  private monitoringInterval: NodeJS.Timeout | null = null;
  private memoryPressureThreshold = 0.8; // 80% of limit
  private cleanupCallbacks: Set<() => void> = new Set();

  private constructor() {
    this.startMonitoring();
  }

  static getInstance(): MemoryManager {
    if (!MemoryManager.instance) {
      MemoryManager.instance = new MemoryManager();
    }
    return MemoryManager.instance;
  }

  getCurrentMemoryStats(): MemoryStats | null {
    if ('memory' in performance) {
      const memory = (performance as any).memory;
      return {
        usedJSHeapSize: memory.usedJSHeapSize,
        totalJSHeapSize: memory.totalJSHeapSize,
        jsHeapSizeLimit: memory.jsHeapSizeLimit,
        usedMB: Math.round(memory.usedJSHeapSize / 1024 / 1024),
        totalMB: Math.round(memory.totalJSHeapSize / 1024 / 1024),
        limitMB: Math.round(memory.jsHeapSizeLimit / 1024 / 1024),
        usagePercentage: memory.usedJSHeapSize / memory.jsHeapSizeLimit
      };
    }
    return null;
  }

  private startMonitoring(): void {
    if (this.monitoringInterval) return;

    this.monitoringInterval = setInterval(() => {
      const stats = this.getCurrentMemoryStats();
      if (stats) {
        this.notifyObservers(stats);
        this.checkMemoryPressure(stats);
      }
    }, 5000); // Check every 5 seconds
  }

  private stopMonitoring(): void {
    if (this.monitoringInterval) {
      clearInterval(this.monitoringInterval);
      this.monitoringInterval = null;
    }
  }

  private notifyObservers(stats: MemoryStats): void {
    this.observers.forEach(callback => {
      try {
        callback(stats);
      } catch (error) {
        logger.error('Error in memory stats observer:', error);
      }
    });
  }

  private checkMemoryPressure(stats: MemoryStats): void {
    if (stats.usagePercentage > this.memoryPressureThreshold) {
      logger.warn(`High memory pressure detected: ${Math.round(stats.usagePercentage * 100)}%`, {
        used: stats.usedMB,
        total: stats.totalMB,
        limit: stats.limitMB
      });
      
      this.triggerGarbageCollection();
    }
  }

  private triggerGarbageCollection(): void {
    // Trigger cleanup callbacks
    this.cleanupCallbacks.forEach(callback => {
      try {
        callback();
      } catch (error) {
        logger.error('Error in cleanup callback:', error);
      }
    });

    // Force garbage collection if available (development only)
    if ('gc' in window && typeof (window as any).gc === 'function') {
      (window as any).gc();
    }
  }

  addMemoryObserver(callback: (stats: MemoryStats) => void): () => void {
    this.observers.add(callback);
    return () => this.observers.delete(callback);
  }

  addCleanupCallback(callback: () => void): () => void {
    this.cleanupCallbacks.add(callback);
    return () => this.cleanupCallbacks.delete(callback);
  }

  setMemoryPressureThreshold(threshold: number): void {
    this.memoryPressureThreshold = Math.max(0.1, Math.min(0.95, threshold));
  }

  // Utility methods for memory optimization
  createWeakCache<K extends object, V>(): WeakMap<K, V> {
    return new WeakMap();
  }

  createLRUCache<K, V>(maxSize: number): Map<K, V> & { cleanup: () => void } {
    const cache = new Map<K, V>();
    const cleanup = () => {
      if (cache.size > maxSize) {
        const entriesToDelete = cache.size - maxSize;
        const keys = Array.from(cache.keys()).slice(0, entriesToDelete);
        keys.forEach(key => cache.delete(key));
      }
    };

    return Object.assign(cache, { cleanup });
  }

  // Memory leak detection
  detectPotentialLeaks(): string[] {
    const issues: string[] = [];
    
    // Check for excessive event listeners
    const listenerCount = (document as any)._eventListeners?.length || 0;
    if (listenerCount > 100) {
      issues.push(`High number of event listeners: ${listenerCount}`);
    }

    // Check for large objects in global scope
    const globalKeys = Object.keys(window).length;
    if (globalKeys > 200) {
      issues.push(`High number of global variables: ${globalKeys}`);
    }

    return issues;
  }
}

// React hooks for memory management  
export const useMemoryMonitor = () => {
  const [memoryStats, setMemoryStats] = useState<MemoryStats | null>(null);
  const manager = MemoryManager.getInstance();

  useEffect(() => {
    const unsubscribe = manager.addMemoryObserver(setMemoryStats);
    return unsubscribe;
  }, [manager]);

  return memoryStats;
};

export const useMemoryCleanup = (cleanupFn: () => void) => {
  const manager = MemoryManager.getInstance();

  useEffect(() => {
    const unsubscribe = manager.addCleanupCallback(cleanupFn);
    return unsubscribe;
  }, [manager, cleanupFn]);
};

export const useWeakRef = <T extends object>(obj: T | null): React.MutableRefObject<WeakRef<T> | null> => {
  const weakRef = useRef<WeakRef<T> | null>(null);

  useEffect(() => {
    if (obj) {
      weakRef.current = new WeakRef(obj);
    } else {
      weakRef.current = null;
    }
  }, [obj]);

  return weakRef;
};

// Memory-efficient data structure hooks
export const useLRUCache = <K, V>(maxSize: number = 100) => {
  const cache = useRef<Map<K, V> & { cleanup: () => void }>();
  const manager = MemoryManager.getInstance();

  if (!cache.current) {
    cache.current = manager.createLRUCache<K, V>(maxSize);
  }

  const set = useCallback((key: K, value: V) => {
    cache.current!.set(key, value);
    cache.current!.cleanup();
  }, []);

  const get = useCallback((key: K) => {
    return cache.current!.get(key);
  }, []);

  const clear = useCallback(() => {
    cache.current!.clear();
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      cache.current?.clear();
    };
  }, []);

  return { set, get, clear, cache: cache.current };
};

export const memoryManager = MemoryManager.getInstance();

export default memoryManager;