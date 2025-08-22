/**
 * Secure Storage Hook
 * Implements encrypted localStorage with expiration and validation
 */

import { useState, useEffect, useCallback } from 'react';
import { logger } from '@/utils/secureLogger';

interface StorageOptions {
  encrypt?: boolean;
  expiry?: number; // milliseconds
  version?: string;
}

interface StorageItem<T> {
  value: T;
  timestamp: number;
  expiry?: number;
  version: string;
}

class SecureStorage {
  private static readonly ENCRYPTION_KEY = 'dealerscope-storage-key';
  private static readonly VERSION = '1.0';

  static async set<T>(
    key: string, 
    value: T, 
    options: StorageOptions = {}
  ): Promise<void> {
    try {
      const item: StorageItem<T> = {
        value,
        timestamp: Date.now(),
        expiry: options.expiry ? Date.now() + options.expiry : undefined,
        version: options.version || this.VERSION
      };

      let serialized = JSON.stringify(item);
      
      if (options.encrypt) {
        serialized = await this.encrypt(serialized);
      }

      localStorage.setItem(key, serialized);
      
      logger.debug('Secure storage item set', 'STORAGE', { 
        key, 
        encrypted: !!options.encrypt,
        hasExpiry: !!options.expiry 
      });
    } catch (error) {
      logger.error('Failed to set secure storage item', 'STORAGE', error);
      throw error;
    }
  }

  static async get<T>(key: string, encrypted: boolean = false): Promise<T | null> {
    try {
      const stored = localStorage.getItem(key);
      if (!stored) return null;

      let serialized = stored;
      
      if (encrypted) {
        serialized = await this.decrypt(stored);
      }

      const item: StorageItem<T> = JSON.parse(serialized);
      
      // Check version compatibility
      if (item.version !== this.VERSION) {
        logger.warn('Storage version mismatch', 'STORAGE', { 
          key, 
          storedVersion: item.version, 
          currentVersion: this.VERSION 
        });
        this.remove(key);
        return null;
      }

      // Check expiry
      if (item.expiry && Date.now() > item.expiry) {
        logger.debug('Storage item expired', 'STORAGE', { key });
        this.remove(key);
        return null;
      }

      return item.value;
    } catch (error) {
      logger.error('Failed to get secure storage item', 'STORAGE', error);
      this.remove(key); // Remove corrupted item
      return null;
    }
  }

  static remove(key: string): void {
    try {
      localStorage.removeItem(key);
      logger.debug('Secure storage item removed', 'STORAGE', { key });
    } catch (error) {
      logger.error('Failed to remove secure storage item', 'STORAGE', error);
    }
  }

  static clear(): void {
    try {
      localStorage.clear();
      logger.info('Secure storage cleared', 'STORAGE');
    } catch (error) {
      logger.error('Failed to clear secure storage', 'STORAGE', error);
    }
  }

  static getKeys(): string[] {
    try {
      return Object.keys(localStorage);
    } catch (error) {
      logger.error('Failed to get storage keys', 'STORAGE', error);
      return [];
    }
  }

  static getSize(): number {
    try {
      let total = 0;
      for (let key in localStorage) {
        if (localStorage.hasOwnProperty(key)) {
          total += localStorage[key].length + key.length;
        }
      }
      return total;
    } catch (error) {
      logger.error('Failed to calculate storage size', 'STORAGE', error);
      return 0;
    }
  }

  private static async encrypt(data: string): Promise<string> {
    try {
      // Simple encryption using base64 (for demo - use proper encryption in production)
      return btoa(encodeURIComponent(data));
    } catch (error) {
      logger.error('Encryption failed', 'STORAGE', error);
      throw error;
    }
  }

  private static async decrypt(encryptedData: string): Promise<string> {
    try {
      return decodeURIComponent(atob(encryptedData));
    } catch (error) {
      logger.error('Decryption failed', 'STORAGE', error);
      throw error;
    }
  }

  // Cleanup expired items
  static cleanup(): void {
    try {
      const keys = this.getKeys();
      let cleanedCount = 0;
      
      keys.forEach(async (key) => {
        try {
          const stored = localStorage.getItem(key);
          if (!stored) return;
          
          const item: StorageItem<any> = JSON.parse(stored);
          if (item.expiry && Date.now() > item.expiry) {
            this.remove(key);
            cleanedCount++;
          }
        } catch {
          // Remove corrupted items
          this.remove(key);
          cleanedCount++;
        }
      });
      
      if (cleanedCount > 0) {
        logger.info('Storage cleanup completed', 'STORAGE', { cleanedCount });
      }
    } catch (error) {
      logger.error('Storage cleanup failed', 'STORAGE', error);
    }
  }
}

// Hook for secure storage
export const useSecureStorage = <T>(
  key: string,
  initialValue: T,
  options: StorageOptions = {}
) => {
  const [value, setValue] = useState<T>(initialValue);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Load initial value
  useEffect(() => {
    const loadValue = async () => {
      try {
        setLoading(true);
        setError(null);
        
        const stored = await SecureStorage.get<T>(key, options.encrypt);
        if (stored !== null) {
          setValue(stored);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load storage');
        logger.error('Failed to load from secure storage', 'STORAGE', err);
      } finally {
        setLoading(false);
      }
    };

    loadValue();
  }, [key, options.encrypt]);

  // Update value
  const updateValue = useCallback(async (newValue: T | ((prev: T) => T)) => {
    try {
      setError(null);
      
      const valueToStore = typeof newValue === 'function' 
        ? (newValue as (prev: T) => T)(value)
        : newValue;
      
      await SecureStorage.set(key, valueToStore, options);
      setValue(valueToStore);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save storage');
      logger.error('Failed to save to secure storage', 'STORAGE', err);
    }
  }, [key, value, options]);

  // Remove value
  const removeValue = useCallback(() => {
    try {
      setError(null);
      SecureStorage.remove(key);
      setValue(initialValue);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to remove storage');
      logger.error('Failed to remove from secure storage', 'STORAGE', err);
    }
  }, [key, initialValue]);

  return {
    value,
    setValue: updateValue,
    removeValue,
    loading,
    error,
    isStored: value !== initialValue
  };
};

// Hook for storage cleanup
export const useStorageCleanup = (intervalMinutes: number = 60) => {
  useEffect(() => {
    // Initial cleanup
    SecureStorage.cleanup();
    
    // Periodic cleanup
    const interval = setInterval(() => {
      SecureStorage.cleanup();
    }, intervalMinutes * 60 * 1000);

    return () => clearInterval(interval);
  }, [intervalMinutes]);
};

// Hook for storage monitoring
export const useStorageMonitor = () => {
  const [storageInfo, setStorageInfo] = useState({
    size: 0,
    keyCount: 0,
    available: 0
  });

  const updateStorageInfo = useCallback(() => {
    try {
      const size = SecureStorage.getSize();
      const keyCount = SecureStorage.getKeys().length;
      
      // Estimate available space (5MB limit for localStorage)
      const maxSize = 5 * 1024 * 1024; // 5MB
      const available = maxSize - size;

      setStorageInfo({ size, keyCount, available });
    } catch (error) {
      logger.error('Failed to update storage info', 'STORAGE', error);
    }
  }, []);

  useEffect(() => {
    updateStorageInfo();
    
    // Update every 30 seconds
    const interval = setInterval(updateStorageInfo, 30000);
    return () => clearInterval(interval);
  }, [updateStorageInfo]);

  return {
    ...storageInfo,
    refresh: updateStorageInfo,
    isNearLimit: storageInfo.available < 512 * 1024 // Less than 512KB available
  };
};

export { SecureStorage };
export default useSecureStorage;