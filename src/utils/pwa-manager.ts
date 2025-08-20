/**
 * PWA Manager for offline support and installation
 * Implements production-ready PWA features from v4.7 plan
 */

import { auditLogger } from './audit-logger';
import { performanceMonitor } from './performance-monitor';

export interface PWAManagerConfig {
  enableOfflineMode: boolean;
  enableInstallPrompt: boolean;
  enableBackgroundSync: boolean;
  offlinePages: string[];
  cacheStrategy: 'cache-first' | 'network-first' | 'stale-while-revalidate';
}

export interface PWAStatus {
  isInstalled: boolean;
  isInstallable: boolean;
  isOnline: boolean;
  hasUpdate: boolean;
  cacheStatus: 'loading' | 'ready' | 'error';
  backgroundSyncEnabled: boolean;
}

const DEFAULT_CONFIG: PWAManagerConfig = {
  enableOfflineMode: true,
  enableInstallPrompt: true,
  enableBackgroundSync: true,
  offlinePages: ['/', '/dashboard', '/opportunities'],
  cacheStrategy: 'stale-while-revalidate'
};

export class PWAManager {
  private static instance: PWAManager;
  private config: PWAManagerConfig;
  private swRegistration: ServiceWorkerRegistration | null = null;
  private deferredPrompt: any = null;
  private status: PWAStatus = {
    isInstalled: false,
    isInstallable: false,
    isOnline: navigator.onLine,
    hasUpdate: false,
    cacheStatus: 'loading',
    backgroundSyncEnabled: false
  };
  private listeners: Map<string, Set<Function>> = new Map();

  private constructor(config: Partial<PWAManagerConfig> = {}) {
    this.config = { ...DEFAULT_CONFIG, ...config };
    this.init();
  }

  static getInstance(config?: Partial<PWAManagerConfig>): PWAManager {
    if (!PWAManager.instance) {
      PWAManager.instance = new PWAManager(config);
    }
    return PWAManager.instance;
  }

  private async init() {
    // Register service worker
    if ('serviceWorker' in navigator && this.config.enableOfflineMode) {
      try {
        this.swRegistration = await navigator.serviceWorker.register('/sw.js');
        this.status.cacheStatus = 'ready';
        
        auditLogger.log(
          'pwa_service_worker_registered',
          'system',
          'info',
          { scope: this.swRegistration.scope }
        );

        // Listen for updates
        this.swRegistration.addEventListener('updatefound', () => {
          this.handleServiceWorkerUpdate();
        });

      } catch (error) {
        this.status.cacheStatus = 'error';
        auditLogger.logError(error as Error, 'pwa_service_worker_registration');
      }
    }

    // Check if app is already installed
    this.checkInstallationStatus();

    // Listen for install prompt
    if (this.config.enableInstallPrompt) {
      window.addEventListener('beforeinstallprompt', (e) => {
        e.preventDefault();
        this.deferredPrompt = e;
        this.status.isInstallable = true;
        this.emit('installable', true);
      });
    }

    // Listen for app installation
    window.addEventListener('appinstalled', () => {
      this.status.isInstalled = true;
      this.status.isInstallable = false;
      this.deferredPrompt = null;
      this.emit('installed', true);
      
      auditLogger.log('pwa_app_installed', 'user_action', 'info');
    });

    // Monitor online/offline status
    window.addEventListener('online', () => {
      this.status.isOnline = true;
      this.emit('online', true);
      this.syncPendingData();
    });

    window.addEventListener('offline', () => {
      this.status.isOnline = false;
      this.emit('offline', true);
    });

    // Background sync setup
    if (this.config.enableBackgroundSync && 'serviceWorker' in navigator) {
      this.setupBackgroundSync();
    }
  }

  /**
   * Install the PWA
   */
  async installApp(): Promise<boolean> {
    if (!this.deferredPrompt) {
      return false;
    }

    try {
      this.deferredPrompt.prompt();
      const { outcome } = await this.deferredPrompt.userChoice;
      
      auditLogger.log(
        'pwa_install_prompt_result',
        'user_action',
        'info',
        { outcome }
      );

      if (outcome === 'accepted') {
        this.deferredPrompt = null;
        return true;
      }
      
      return false;
    } catch (error) {
      auditLogger.logError(error as Error, 'pwa_install_prompt');
      return false;
    }
  }

  /**
   * Check for app updates
   */
  async checkForUpdates(): Promise<boolean> {
    if (!this.swRegistration) {
      return false;
    }

    try {
      await this.swRegistration.update();
      const hasUpdate = this.swRegistration.waiting !== null;
      
      this.status.hasUpdate = hasUpdate;
      if (hasUpdate) {
        this.emit('updateAvailable', true);
      }
      
      return hasUpdate;
    } catch (error) {
      auditLogger.logError(error as Error, 'pwa_update_check');
      return false;
    }
  }

  /**
   * Apply pending updates
   */
  async applyUpdate(): Promise<void> {
    if (!this.swRegistration) {
      return;
    }

    // Check if there's a waiting service worker
    if (this.swRegistration.waiting) {
      this.swRegistration.waiting.postMessage({ type: 'SKIP_WAITING' });
    }
    
    // Listen for controlling change
    navigator.serviceWorker.addEventListener('controllerchange', () => {
      window.location.reload();
    });
  }

  /**
   * Cache critical resources
   */
  async cacheResources(resources: string[]): Promise<void> {
    if (!('caches' in window)) {
      return;
    }

    try {
      const cache = await caches.open('dealerscope-v1');
      await cache.addAll(resources);
      
      auditLogger.log(
        'pwa_resources_cached',
        'system',
        'info',
        { resourceCount: resources.length }
      );
    } catch (error) {
      auditLogger.logError(error as Error, 'pwa_cache_resources');
    }
  }

  /**
   * Store data for background sync
   */
  async storeForSync(key: string, data: any): Promise<void> {
    if (!('indexedDB' in window)) {
      return;
    }

    try {
      const syncData = {
        key,
        data,
        timestamp: Date.now(),
        synced: false
      };

      // Store in IndexedDB for background sync
      await this.storeInIndexedDB('sync-queue', syncData);
      
      auditLogger.log(
        'pwa_data_queued_for_sync',
        'system',
        'info',
        { key, dataSize: JSON.stringify(data).length }
      );
    } catch (error) {
      auditLogger.logError(error as Error, 'pwa_store_for_sync');
    }
  }

  /**
   * Get PWA status
   */
  getStatus(): PWAStatus {
    return { ...this.status };
  }

  /**
   * Event subscription
   */
  on(event: string, callback: Function): () => void {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set());
    }
    
    this.listeners.get(event)!.add(callback);
    
    return () => {
      this.listeners.get(event)?.delete(callback);
    };
  }

  private emit(event: string, data: any) {
    this.listeners.get(event)?.forEach(callback => {
      try {
        callback(data);
      } catch (error) {
        console.error(`PWA event listener error for ${event}:`, error);
      }
    });
  }

  private checkInstallationStatus() {
    // Check if running in standalone mode (installed)
    this.status.isInstalled = window.matchMedia('(display-mode: standalone)').matches ||
                              (window.navigator as any).standalone === true;
  }

  private handleServiceWorkerUpdate() {
    this.status.hasUpdate = true;
    this.emit('updateAvailable', true);
    
    auditLogger.log('pwa_update_available', 'system', 'info');
  }

  private async setupBackgroundSync() {
    if (!this.swRegistration) {
      return;
    }

    try {
      // Check if background sync is supported
      if ('sync' in this.swRegistration) {
        await (this.swRegistration as any).sync.register('background-sync');
        this.status.backgroundSyncEnabled = true;
        
        auditLogger.log('pwa_background_sync_enabled', 'system', 'info');
      }
    } catch (error) {
      auditLogger.logError(error as Error, 'pwa_background_sync_setup');
    }
  }

  private async syncPendingData() {
    // Sync any pending data when coming back online
    try {
      const pendingData = await this.getAllFromIndexedDB('sync-queue');
      
      for (const item of pendingData) {
        if (!item.synced) {
          // Attempt to sync
          await this.syncDataItem(item);
        }
      }
    } catch (error) {
      auditLogger.logError(error as Error, 'pwa_sync_pending_data');
    }
  }

  private async syncDataItem(item: any): Promise<void> {
    // Implementation depends on your API structure
    // This is a placeholder for syncing logic
    performanceMonitor.recordMetric('pwa_sync_attempt', 1, { key: item.key });
  }

  private async storeInIndexedDB(storeName: string, data: any): Promise<void> {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open('dealerscope-pwa', 1);
      
      request.onerror = () => reject(request.error);
      request.onsuccess = () => {
        const db = request.result;
        const transaction = db.transaction([storeName], 'readwrite');
        const store = transaction.objectStore(storeName);
        
        store.add(data);
        transaction.oncomplete = () => resolve();
        transaction.onerror = () => reject(transaction.error);
      };
      
      request.onupgradeneeded = () => {
        const db = request.result;
        if (!db.objectStoreNames.contains(storeName)) {
          db.createObjectStore(storeName, { keyPath: 'id', autoIncrement: true });
        }
      };
    });
  }

  private async getAllFromIndexedDB(storeName: string): Promise<any[]> {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open('dealerscope-pwa', 1);
      
      request.onerror = () => reject(request.error);
      request.onsuccess = () => {
        const db = request.result;
        const transaction = db.transaction([storeName], 'readonly');
        const store = transaction.objectStore(storeName);
        const getAllRequest = store.getAll();
        
        getAllRequest.onsuccess = () => resolve(getAllRequest.result);
        getAllRequest.onerror = () => reject(getAllRequest.error);
      };
    });
  }
}

// Global instance
export const pwaManager = PWAManager.getInstance();

// React hook for PWA status
import { useState, useEffect } from 'react';

export function usePWAStatus() {
  const [status, setStatus] = useState<PWAStatus>(pwaManager.getStatus());
  
  useEffect(() => {
    const unsubscribers = [
      pwaManager.on('installable', () => setStatus(pwaManager.getStatus())),
      pwaManager.on('installed', () => setStatus(pwaManager.getStatus())),
      pwaManager.on('updateAvailable', () => setStatus(pwaManager.getStatus())),
      pwaManager.on('online', () => setStatus(pwaManager.getStatus())),
      pwaManager.on('offline', () => setStatus(pwaManager.getStatus()))
    ];
    
    return () => {
      unsubscribers.forEach(unsub => unsub());
    };
  }, []);
  
  return {
    ...status,
    installApp: pwaManager.installApp.bind(pwaManager),
    checkForUpdates: pwaManager.checkForUpdates.bind(pwaManager),
    applyUpdate: pwaManager.applyUpdate.bind(pwaManager)
  };
}