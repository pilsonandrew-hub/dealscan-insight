/**
 * Environment Configuration Manager
 * Handles multi-environment setup for development, staging, and production
 */

export enum Environment {
  DEVELOPMENT = 'development',
  STAGING = 'staging',
  PRODUCTION = 'production'
}

export interface DatabaseConfig {
  url: string;
  anonKey: string;
  serviceRoleKey?: string;
  pooling?: boolean;
  ssl?: boolean;
}

export interface EnvironmentConfig {
  environment: Environment;
  database: DatabaseConfig;
  api: {
    baseUrl: string;
    timeout: number;
    retries: number;
  };
  features: {
    enableAnalytics: boolean;
    enableErrorReporting: boolean;
    enableDevTools: boolean;
    enablePerformanceMonitoring: boolean;
  };
  logging: {
    level: 'debug' | 'info' | 'warn' | 'error';
    enableConsole: boolean;
    enableRemote: boolean;
  };
  security: {
    enableCSP: boolean;
    enableSRI: boolean;
    enableHSTS: boolean;
  };
  performance: {
    enablePWA: boolean;
    enableServiceWorker: boolean;
    cacheStrategy: 'aggressive' | 'conservative' | 'disabled';
  };
}

class EnvironmentManager {
  private static instance: EnvironmentManager;
  private currentEnvironment: Environment;
  private config: EnvironmentConfig;

  private constructor() {
    this.currentEnvironment = this.detectEnvironment();
    this.config = this.loadConfiguration();
  }

  static getInstance(): EnvironmentManager {
    if (!EnvironmentManager.instance) {
      EnvironmentManager.instance = new EnvironmentManager();
    }
    return EnvironmentManager.instance;
  }

  /**
   * Detect current environment
   */
  private detectEnvironment(): Environment {
    // Check environment variables
    const viteMode = import.meta.env.MODE;
    const isProd = import.meta.env.PROD;
    
    // Check hostname patterns
    const hostname = typeof window !== 'undefined' ? window.location.hostname : '';
    
    if (isProd || hostname.includes('dealerscope.com')) {
      return Environment.PRODUCTION;
    }
    
    if (viteMode === 'staging' || hostname.includes('staging') || hostname.includes('preview')) {
      return Environment.STAGING;
    }
    
    return Environment.DEVELOPMENT;
  }

  /**
   * Load environment-specific configuration
   */
  private loadConfiguration(): EnvironmentConfig {
    switch (this.currentEnvironment) {
      case Environment.PRODUCTION:
        return this.getProductionConfig();
      case Environment.STAGING:
        return this.getStagingConfig();
      default:
        return this.getDevelopmentConfig();
    }
  }

  /**
   * Production configuration
   */
  private getProductionConfig(): EnvironmentConfig {
    return {
      environment: Environment.PRODUCTION,
      database: {
        url: import.meta.env.VITE_SUPABASE_URL || 'https://lgpugcflvrqhslfnsjfh.supabase.co',
        anonKey: import.meta.env.VITE_SUPABASE_ANON_KEY || 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxncHVnY2ZsdnJxaHNsZm5zamZoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTU2NjkzODksImV4cCI6MjA3MTI0NTM4OX0.Tadce_MW20ZfG75-EtiAHQPy2VfS0ciH1bekFNlVX0U',
        pooling: true,
        ssl: true
      },
      api: {
        baseUrl: 'https://api.dealerscope.com',
        timeout: 30000,
        retries: 3
      },
      features: {
        enableAnalytics: true,
        enableErrorReporting: true,
        enableDevTools: false,
        enablePerformanceMonitoring: true
      },
      logging: {
        level: 'warn',
        enableConsole: false,
        enableRemote: true
      },
      security: {
        enableCSP: true,
        enableSRI: true,
        enableHSTS: true
      },
      performance: {
        enablePWA: true,
        enableServiceWorker: true,
        cacheStrategy: 'aggressive'
      }
    };
  }

  /**
   * Staging configuration
   */
  private getStagingConfig(): EnvironmentConfig {
    return {
      environment: Environment.STAGING,
      database: {
        url: import.meta.env.VITE_SUPABASE_URL || 'https://lgpugcflvrqhslfnsjfh.supabase.co',
        anonKey: import.meta.env.VITE_SUPABASE_ANON_KEY || 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxncHVnY2ZsdnJxaHNsZm5zamZoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTU2NjkzODksImV4cCI6MjA3MTI0NTM4OX0.Tadce_MW20ZfG75-EtiAHQPy2VfS0ciH1bekFNlVX0U',
        pooling: true,
        ssl: true
      },
      api: {
        baseUrl: 'https://staging-api.dealerscope.com',
        timeout: 30000,
        retries: 2
      },
      features: {
        enableAnalytics: true,
        enableErrorReporting: true,
        enableDevTools: true,
        enablePerformanceMonitoring: true
      },
      logging: {
        level: 'info',
        enableConsole: true,
        enableRemote: true
      },
      security: {
        enableCSP: true,
        enableSRI: false,
        enableHSTS: false
      },
      performance: {
        enablePWA: false,
        enableServiceWorker: false,
        cacheStrategy: 'conservative'
      }
    };
  }

  /**
   * Development configuration
   */
  private getDevelopmentConfig(): EnvironmentConfig {
    return {
      environment: Environment.DEVELOPMENT,
      database: {
        url: import.meta.env.VITE_SUPABASE_URL || 'https://lgpugcflvrqhslfnsjfh.supabase.co',
        anonKey: import.meta.env.VITE_SUPABASE_ANON_KEY || 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxncHVnY2ZsdnJxaHNsZm5zamZoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTU2NjkzODksImV4cCI6MjA3MTI0NTM4OX0.Tadce_MW20ZfG75-EtiAHQPy2VfS0ciH1bekFNlVX0U',
        pooling: false,
        ssl: false
      },
      api: {
        baseUrl: 'http://localhost:8080',
        timeout: 10000,
        retries: 1
      },
      features: {
        enableAnalytics: false,
        enableErrorReporting: false,
        enableDevTools: true,
        enablePerformanceMonitoring: false
      },
      logging: {
        level: 'debug',
        enableConsole: true,
        enableRemote: false
      },
      security: {
        enableCSP: false,
        enableSRI: false,
        enableHSTS: false
      },
      performance: {
        enablePWA: false,
        enableServiceWorker: false,
        cacheStrategy: 'disabled'
      }
    };
  }

  /**
   * Get current environment
   */
  getEnvironment(): Environment {
    return this.currentEnvironment;
  }

  /**
   * Get current configuration
   */
  getConfig(): EnvironmentConfig {
    return this.config;
  }

  /**
   * Check if in production
   */
  isProduction(): boolean {
    return this.currentEnvironment === Environment.PRODUCTION;
  }

  /**
   * Check if in staging
   */
  isStaging(): boolean {
    return this.currentEnvironment === Environment.STAGING;
  }

  /**
   * Check if in development
   */
  isDevelopment(): boolean {
    return this.currentEnvironment === Environment.DEVELOPMENT;
  }

  /**
   * Get database configuration
   */
  getDatabaseConfig(): DatabaseConfig {
    return this.config.database;
  }

  /**
   * Get API configuration
   */
  getAPIConfig() {
    return this.config.api;
  }

  /**
   * Get feature flags
   */
  getFeatureFlags() {
    return this.config.features;
  }

  /**
   * Get logging configuration
   */
  getLoggingConfig() {
    return this.config.logging;
  }

  /**
   * Get security configuration
   */
  getSecurityConfig() {
    return this.config.security;
  }

  /**
   * Get performance configuration
   */
  getPerformanceConfig() {
    return this.config.performance;
  }

  /**
   * Check if feature is enabled
   */
  isFeatureEnabled(feature: keyof EnvironmentConfig['features']): boolean {
    return this.config.features[feature];
  }
}

// Singleton instance
export const environmentManager = EnvironmentManager.getInstance();

// Convenience exports
export const environment = environmentManager.getEnvironment();
export const config = environmentManager.getConfig();
export const isProduction = environmentManager.isProduction();
export const isDevelopment = environmentManager.isDevelopment();
export const isStaging = environmentManager.isStaging();

export default environmentManager;