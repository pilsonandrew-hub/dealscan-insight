/**
 * Centralized configuration management
 * Inspired by the config.py in the bootstrap script
 */

interface DatabaseConfig {
  url: string;
  poolSize: number;
  maxOverflow: number;
  timeout: number;
}

interface CacheConfig {
  ttl: number;
  maxSize: number;
  enablePersistence: boolean;
}

interface SecurityConfig {
  maxFileSize: number;
  allowedFileTypes: string[];
  rateLimitWindow: number;
  rateLimitMax: number;
  enableAuditLogging: boolean;
}

interface ProcessingConfig {
  batchSize: number;
  maxWorkers: number;
  retries: number;
  timeout: number;
  enableParallel: boolean;
}

interface ApiConfig {
  baseUrl: string;
  timeout: number;
  retries: number;
  circuitBreakerThreshold: number;
  circuitBreakerTimeout: number;
}

export interface AppSettings {
  environment: 'development' | 'staging' | 'production';
  debug: boolean;
  
  // API Configuration
  api: ApiConfig;
  
  // Database Configuration
  database: DatabaseConfig;
  
  // Cache Configuration
  cache: CacheConfig;
  
  // Security Configuration
  security: SecurityConfig;
  
  // Processing Configuration
  processing: ProcessingConfig;
  
  // Feature Flags
  features: {
    realTimeUpdates: boolean;
    advancedMetrics: boolean;
    backgroundSync: boolean;
    experimentalFeatures: boolean;
  };
  
  // WebSocket Configuration
  websocket: {
    url: string;
    autoReconnect: boolean;
    maxReconnectAttempts: number;
    reconnectInterval: number;
  };
}

// Default configuration
const defaultSettings: AppSettings = {
  environment: import.meta.env.MODE as 'development' | 'staging' | 'production' || 'development',
  debug: import.meta.env.MODE === 'development',
  
  api: {
    baseUrl: import.meta.env.VITE_API_URL || 'http://localhost:8000',
    timeout: 30000,
    retries: 3,
    circuitBreakerThreshold: 5,
    circuitBreakerTimeout: 30000
  },
  
  database: {
    url: import.meta.env.VITE_DATABASE_URL || 'sqlite://dealerscope.db',
    poolSize: 10,
    maxOverflow: 20,
    timeout: 30000
  },
  
  cache: {
    ttl: 300000, // 5 minutes
    maxSize: 1000,
    enablePersistence: true
  },
  
  security: {
    maxFileSize: 50 * 1024 * 1024, // 50MB
    allowedFileTypes: ['text/csv', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'],
    rateLimitWindow: 60000, // 1 minute
    rateLimitMax: 60,
    enableAuditLogging: true
  },
  
  processing: {
    batchSize: 1000,
    maxWorkers: 8,
    retries: 3,
    timeout: 30000,
    enableParallel: true
  },
  
  features: {
    realTimeUpdates: true,
    advancedMetrics: import.meta.env.MODE !== 'development',
    backgroundSync: true,
    experimentalFeatures: import.meta.env.MODE === 'development'
  },
  
  websocket: {
    url: import.meta.env.VITE_WS_URL || 'ws://localhost:8000',
    autoReconnect: true,
    maxReconnectAttempts: 5,
    reconnectInterval: 3000
  }
};

// Environment-specific overrides
const environmentOverrides: Partial<Record<AppSettings['environment'], Partial<AppSettings>>> = {
  production: {
    debug: false,
    cache: {
      ttl: 600000, // 10 minutes in production
      maxSize: 5000,
      enablePersistence: true
    },
    security: {
      maxFileSize: 100 * 1024 * 1024, // 100MB in production
      allowedFileTypes: [
        'text/csv', 
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/vnd.ms-excel'
      ],
      rateLimitWindow: 60000,
      rateLimitMax: 120, // Higher limit in production
      enableAuditLogging: true
    },
    features: {
      realTimeUpdates: true,
      advancedMetrics: true,
      backgroundSync: true,
      experimentalFeatures: false
    }
  },
  
  staging: {
    debug: true,
    features: {
      realTimeUpdates: true,
      advancedMetrics: true,
      backgroundSync: true,
      experimentalFeatures: true
    }
  }
};

// Merge configuration
function createSettings(): AppSettings {
  const envOverride = environmentOverrides[defaultSettings.environment] || {};
  
  return {
    ...defaultSettings,
    ...envOverride,
    // Deep merge nested objects
    api: { ...defaultSettings.api, ...envOverride.api },
    database: { ...defaultSettings.database, ...envOverride.database },
    cache: { ...defaultSettings.cache, ...envOverride.cache },
    security: { ...defaultSettings.security, ...envOverride.security },
    processing: { ...defaultSettings.processing, ...envOverride.processing },
    features: { ...defaultSettings.features, ...envOverride.features },
    websocket: { ...defaultSettings.websocket, ...envOverride.websocket }
  };
}

// Global settings instance
export const settings = createSettings();

// Settings validation
export function validateSettings(config: AppSettings): string[] {
  const errors: string[] = [];
  
  if (!config.api.baseUrl) {
    errors.push('API base URL is required');
  }
  
  if (config.security.maxFileSize <= 0) {
    errors.push('Max file size must be positive');
  }
  
  if (config.processing.batchSize <= 0) {
    errors.push('Batch size must be positive');
  }
  
  if (config.cache.ttl <= 0) {
    errors.push('Cache TTL must be positive');
  }
  
  return errors;
}

// Environment info
export const environmentInfo = {
  isDevelopment: settings.environment === 'development',
  isStaging: settings.environment === 'staging',
  isProduction: settings.environment === 'production',
  version: import.meta.env.VITE_APP_VERSION || '4.8.0',
  buildTime: import.meta.env.VITE_BUILD_TIME || new Date().toISOString(),
  gitCommit: import.meta.env.VITE_GIT_COMMIT || 'unknown'
};

// Log configuration on startup
if (settings.debug) {
  console.log('DealerScope Configuration:', {
    environment: settings.environment,
    features: settings.features,
    api: { baseUrl: settings.api.baseUrl },
    cache: { ttl: settings.cache.ttl, maxSize: settings.cache.maxSize },
    websocket: { url: settings.websocket.url }
  });
  
  const validationErrors = validateSettings(settings);
  if (validationErrors.length > 0) {
    console.warn('Configuration validation errors:', validationErrors);
  }
}