/**
 * Unified State Management System
 * Consolidates multiple state management approaches into a single source of truth
 */

import { logger } from './UnifiedLogger';
import { configService } from './UnifiedConfigService';

type StateChangeListener<T = any> = (newState: T, oldState: T, action: Action) => void;
type StateSelector<T, R> = (state: T) => R;

interface Action {
  type: string;
  payload?: any;
  meta?: {
    timestamp: number;
    userId?: string;
    sessionId?: string;
  };
}

interface StateSlice<T = any> {
  name: string;
  initialState: T;
  reducer: (state: T, action: Action) => T;
  middleware?: StateMiddleware<T>[];
}

interface StateMiddleware<T = any> {
  name: string;
  execute: (state: T, action: Action, next: (action: Action) => T) => T;
}

interface PersistenceConfig {
  enabled: boolean;
  key: string;
  storage: 'localStorage' | 'sessionStorage' | 'indexedDB';
  whitelist?: string[]; // Only persist these slices
  blacklist?: string[]; // Never persist these slices
}

class UnifiedStateManager {
  private static instance: UnifiedStateManager;
  private state: Record<string, any> = {};
  private slices = new Map<string, StateSlice>();
  private listeners = new Map<string, Set<StateChangeListener>>();
  private globalListeners = new Set<StateChangeListener>();
  private middleware: StateMiddleware[] = [];
  private persistenceConfig: PersistenceConfig;
  private isHydrated = false;

  private constructor() {
    this.persistenceConfig = {
      enabled: true,
      key: 'dealerscope_state',
      storage: 'localStorage',
      blacklist: ['auth'], // Don't persist sensitive auth data
    };

    this.setupMiddleware();
    this.hydrateFromStorage();
    this.setupStorageSync();
  }

  static getInstance(): UnifiedStateManager {
    if (!UnifiedStateManager.instance) {
      UnifiedStateManager.instance = new UnifiedStateManager();
    }
    return UnifiedStateManager.instance;
  }

  private setupMiddleware(): void {
    // Logging middleware
    this.middleware.push({
      name: 'logger',
      execute: (state, action, next) => {
        const startTime = performance.now();
        logger.debug('State action dispatched', {
          type: action.type,
          payload: action.payload,
          timestamp: action.meta?.timestamp,
        });

        const newState = next(action);
        const endTime = performance.now();

        logger.performance('State update completed', {
          action: action.type,
          duration: endTime - startTime,
          stateSize: JSON.stringify(newState).length,
        });

        return newState;
      },
    });

    // Validation middleware
    this.middleware.push({
      name: 'validator',
      execute: (state, action, next) => {
        // Validate action structure
        if (!action.type) {
          throw new Error('Action must have a type');
        }

        // Validate against known action types in development
        if (configService.isDevelopment) {
          this.validateAction(action);
        }

        return next(action);
      },
    });

    // Performance middleware
    this.middleware.push({
      name: 'performance',
      execute: (state, action, next) => {
        const memoryBefore = this.getMemoryUsage();
        const result = next(action);
        const memoryAfter = this.getMemoryUsage();

        if (memoryAfter - memoryBefore > 1024 * 1024) { // 1MB increase
          logger.warn('Large memory increase detected', {
            action: action.type,
            memoryIncrease: memoryAfter - memoryBefore,
          });
        }

        return result;
      },
    });
  }

  private getMemoryUsage(): number {
    if ('memory' in performance) {
      return (performance as any).memory.usedJSHeapSize;
    }
    return 0;
  }

  private validateAction(action: Action): void {
    // Basic action validation
    if (typeof action.type !== 'string') {
      throw new Error('Action type must be a string');
    }

    // Check for potential serialization issues
    try {
      JSON.stringify(action);
    } catch (error) {
      throw new Error('Action must be serializable');
    }
  }

  private async hydrateFromStorage(): Promise<void> {
    if (!this.persistenceConfig.enabled) {
      this.isHydrated = true;
      return;
    }

    try {
      const storage = this.getStorage();
      const persistedState = storage.getItem(this.persistenceConfig.key);
      
      if (persistedState) {
        const parsed = JSON.parse(persistedState);
        
        // Only restore non-blacklisted slices
        for (const [sliceName, sliceState] of Object.entries(parsed)) {
          if (!this.isBlacklisted(sliceName)) {
            this.state[sliceName] = sliceState;
          }
        }

        logger.info('State hydrated from storage', {
          slices: Object.keys(parsed),
          size: persistedState.length,
        });
      }
    } catch (error) {
      logger.error('Failed to hydrate state from storage', { error });
    }

    this.isHydrated = true;
  }

  private getStorage(): Storage {
    switch (this.persistenceConfig.storage) {
      case 'sessionStorage':
        return sessionStorage;
      case 'localStorage':
      default:
        return localStorage;
    }
  }

  private isBlacklisted(sliceName: string): boolean {
    const { whitelist, blacklist } = this.persistenceConfig;
    
    if (whitelist && !whitelist.includes(sliceName)) {
      return true;
    }
    
    if (blacklist && blacklist.includes(sliceName)) {
      return true;
    }
    
    return false;
  }

  private setupStorageSync(): void {
    // Debounced persistence
    let persistTimer: NodeJS.Timeout;
    
    this.addGlobalListener(() => {
      if (!this.persistenceConfig.enabled || !this.isHydrated) {
        return;
      }

      clearTimeout(persistTimer);
      persistTimer = setTimeout(() => {
        this.persistToStorage();
      }, 1000); // Debounce by 1 second
    });

    // Listen for storage changes in other tabs
    window.addEventListener('storage', (event) => {
      if (event.key === this.persistenceConfig.key && event.newValue) {
        try {
          const newState = JSON.parse(event.newValue);
          
          // Merge changes from other tabs
          for (const [sliceName, sliceState] of Object.entries(newState)) {
            if (!this.isBlacklisted(sliceName)) {
              this.state[sliceName] = sliceState;
            }
          }

          logger.info('State synchronized from other tab');
          this.notifyGlobalListeners({ type: 'SYNC_FROM_STORAGE' }, {}, {});
        } catch (error) {
          logger.error('Failed to sync state from storage', { error });
        }
      }
    });
  }

  private persistToStorage(): void {
    try {
      const stateToPersist: Record<string, any> = {};
      
      for (const [sliceName, sliceState] of Object.entries(this.state)) {
        if (!this.isBlacklisted(sliceName)) {
          stateToPersist[sliceName] = sliceState;
        }
      }

      const storage = this.getStorage();
      storage.setItem(this.persistenceConfig.key, JSON.stringify(stateToPersist));
      
      logger.debug('State persisted to storage', {
        slices: Object.keys(stateToPersist),
      });
    } catch (error) {
      logger.error('Failed to persist state to storage', { error });
    }
  }

  // Public API
  registerSlice<T>(slice: StateSlice<T>): void {
    if (this.slices.has(slice.name)) {
      throw new Error(`Slice '${slice.name}' is already registered`);
    }

    this.slices.set(slice.name, slice);
    
    // Initialize state if not already present
    if (!(slice.name in this.state)) {
      this.state[slice.name] = slice.initialState;
    }

    logger.info('State slice registered', { slice: slice.name });
  }

  dispatch(action: Action): void {
    // Add metadata to action
    const enrichedAction: Action = {
      ...action,
      meta: {
        timestamp: Date.now(),
        userId: this.state.auth?.user?.id,
        sessionId: this.state.auth?.sessionId,
        ...action.meta,
      },
    };

    // Apply global middleware
    const execute = (currentAction: Action): void => {
      const oldState = { ...this.state };
      
      // Apply slice reducers
      for (const [sliceName, slice] of this.slices.entries()) {
        const oldSliceState = this.state[sliceName];
        let newSliceState = oldSliceState;

        // Apply slice middleware
        if (slice.middleware && slice.middleware.length > 0) {
          newSliceState = this.applySliceMiddleware(
            slice.middleware,
            oldSliceState,
            currentAction,
            slice.reducer
          );
        } else {
          newSliceState = slice.reducer(oldSliceState, currentAction);
        }

        // Update state if changed
        if (newSliceState !== oldSliceState) {
          this.state[sliceName] = newSliceState;
          this.notifySliceListeners(sliceName, newSliceState, oldSliceState, currentAction);
        }
      }

      // Notify global listeners
      this.notifyGlobalListeners(currentAction, this.state, oldState);
    };

    // Apply global middleware chain
    this.applyGlobalMiddleware(this.state, enrichedAction, execute);
  }

  private applyGlobalMiddleware(
    state: any,
    action: Action,
    execute: (action: Action) => void
  ): void {
    let index = 0;
    
    const next = (currentAction: Action): void => {
      if (index >= this.middleware.length) {
        execute(currentAction);
        return;
      }
      
      const middleware = this.middleware[index++];
      middleware.execute(state, currentAction, next);
    };
    
    next(action);
  }

  private applySliceMiddleware<T>(
    middleware: StateMiddleware<T>[],
    state: T,
    action: Action,
    reducer: (state: T, action: Action) => T
  ): T {
    let index = 0;
    
    const next = (currentAction: Action): T => {
      if (index >= middleware.length) {
        return reducer(state, currentAction);
      }
      
      const mw = middleware[index++];
      return mw.execute(state, currentAction, next);
    };
    
    return next(action);
  }

  select<T, R>(sliceName: string, selector?: StateSelector<T, R>): R | T {
    const sliceState = this.state[sliceName];
    
    if (selector) {
      return selector(sliceState);
    }
    
    return sliceState;
  }

  subscribe<T>(sliceName: string, listener: StateChangeListener<T>): () => void {
    if (!this.listeners.has(sliceName)) {
      this.listeners.set(sliceName, new Set());
    }
    
    this.listeners.get(sliceName)!.add(listener);
    
    // Return unsubscribe function
    return () => {
      this.listeners.get(sliceName)?.delete(listener);
    };
  }

  addGlobalListener(listener: StateChangeListener): () => void {
    this.globalListeners.add(listener);
    
    return () => {
      this.globalListeners.delete(listener);
    };
  }

  private notifySliceListeners<T>(
    sliceName: string,
    newState: T,
    oldState: T,
    action: Action
  ): void {
    const listeners = this.listeners.get(sliceName);
    if (listeners) {
      listeners.forEach(listener => {
        try {
          listener(newState, oldState, action);
        } catch (error) {
          logger.error('State listener error', { sliceName, error });
        }
      });
    }
  }

  private notifyGlobalListeners(action: Action, newState: any, oldState: any): void {
    this.globalListeners.forEach(listener => {
      try {
        listener(newState, oldState, action);
      } catch (error) {
        logger.error('Global state listener error', { error });
      }
    });
  }

  // Utility methods
  getState(): Record<string, any> {
    return { ...this.state };
  }

  clearState(): void {
    this.state = {};
    
    // Reinitialize with default states
    for (const [sliceName, slice] of this.slices.entries()) {
      this.state[sliceName] = slice.initialState;
    }

    logger.info('State cleared and reinitialized');
  }

  // For debugging
  getDebugInfo() {
    return {
      slices: Array.from(this.slices.keys()),
      listeners: Object.fromEntries(
        Array.from(this.listeners.entries()).map(([key, value]) => [key, value.size])
      ),
      globalListeners: this.globalListeners.size,
      middleware: this.middleware.map(mw => mw.name),
      isHydrated: this.isHydrated,
      stateSize: JSON.stringify(this.state).length,
    };
  }
}

export const stateManager = UnifiedStateManager.getInstance();
export type { Action, StateSlice, StateMiddleware, StateChangeListener, StateSelector };