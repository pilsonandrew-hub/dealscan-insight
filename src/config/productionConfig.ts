/**
 * Production Configuration Management
 * Centralized configuration for production deployment
 */

import { createLogger } from '@/utils/productionLogger';

const logger = createLogger('ProductionConfig');

export interface ProductionConfig {
  app: {
    name: string;
    version: string;
    environment: 'development' | 'staging' | 'production';
    buildHash?: string;
    deployedAt?: string;
  };
  api: {
    baseUrl: string;
    timeout: number;
    retries: number;
    rateLimit: {
      enabled: boolean;
      requests: number;
      window: number;
    };
  };
  monitoring: {
    enabled: boolean;
    healthCheckInterval: number;
    metricsFlushInterval: number;
    errorReporting: boolean;
    performanceTracking: boolean;
  };
  features: {
    realTimeUpdates: boolean;
    advancedScoring: boolean;
    mlPredictions: boolean;
    auditLogging: boolean;
    maintenanceMode: boolean;
  };
  performance: {
    cacheEnabled: boolean;
    cacheTTL: number;
    maxConcurrentRequests: number;
    memoryLimit: number;
  };
  security: {
    csrfProtection: boolean;
    rateLimiting: boolean;
    inputSanitization: boolean;
    auditTrail: boolean;
  };
  supabase: {
    url: string;
    anonKey: string;
    enableRLS: boolean;
    connectionPooling: boolean;
  };
}

class ProductionConfigManager {
  private config: ProductionConfig;
  private initialized = false;

  constructor() {
    this.config = this.getDefaultConfig();
  }

  /**
   * Initialize configuration from environment variables
   */
  initialize(): void {
    if (this.initialized) return;

    try {
      // Load environment-specific configuration
      this.config = {
        ...this.config,
        app: {
          ...this.config.app,
          environment: this.getEnvironment(),
          buildHash: import.meta.env.VITE_BUILD_HASH || 'unknown',
          deployedAt: import.meta.env.VITE_DEPLOYED_AT || new Date().toISOString(),
        },
        supabase: {
          ...this.config.supabase,
          url: import.meta.env.VITE_SUPABASE_URL || 'https://lgpugcflvrqhslfnsjfh.supabase.co',
          anonKey: import.meta.env.VITE_SUPABASE_ANON_KEY || 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxncHVnY2ZsdnJxaHNsZm5zamZoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTU2NjkzODksImV4cCI6MjA3MTI0NTM4OX0.Tadce_MW20ZfG75-EtiAHQPy2VfS0ciH1bekFNlVX0U',
        },
        monitoring: {
          ...this.config.monitoring,
          enabled: this.isProduction(),
          errorReporting: this.isProduction(),
          performanceTracking: this.isProduction(),
        },
        performance: {
          ...this.config.performance,
          cacheEnabled: this.isProduction(),
        },
        security: {
          ...this.config.security,
          csrfProtection: this.isProduction(),
          rateLimiting: this.isProduction(),
          auditTrail: this.isProduction(),
        },
      };

      // Apply production-specific optimizations
      if (this.isProduction()) {
        this.applyProductionOptimizations();
      }

      this.validateConfig();
      this.initialized = true;

      logger.info('Production configuration initialized', {
        environment: this.config.app.environment,
        version: this.config.app.version,
        buildHash: this.config.app.buildHash?.substring(0, 8),
        featuresEnabled: Object.entries(this.config.features)
          .filter(([_, enabled]) => enabled)
          .map(([feature]) => feature),
      });

    } catch (error) {
      logger.error('Failed to initialize production configuration', {}, error as Error);
      throw new Error('Configuration initialization failed');
    }
  }

  /**
   * Get current configuration
   */
  getConfig(): ProductionConfig {
    if (!this.initialized) {
      this.initialize();
    }
    return { ...this.config };
  }

  /**
   * Update configuration at runtime
   */
  updateConfig(updates: Partial<ProductionConfig>): void {
    this.config = {
      ...this.config,
      ...updates,
    };

    logger.info('Configuration updated', { updates });
  }

  /**
   * Check if running in production
   */
  isProduction(): boolean {
    return this.getEnvironment() === 'production';
  }

  /**
   * Check if running in development
   */
  isDevelopment(): boolean {
    return this.getEnvironment() === 'development';
  }

  /**
   * Check if feature is enabled
   */
  isFeatureEnabled(feature: keyof ProductionConfig['features']): boolean {
    return this.config.features[feature];
  }

  /**
   * Get environment from various sources
   */
  private getEnvironment(): ProductionConfig['app']['environment'] {
    // Check environment variables
    const viteMode = import.meta.env.MODE;
    const nodeEnv = import.meta.env.NODE_ENV;
    
    // Check URL for staging/production indicators
    const hostname = typeof window !== 'undefined' ? window.location.hostname : '';
    
    if (hostname.includes('lovable.app') || viteMode === 'production') {
      return 'production';
    }
    
    if (hostname.includes('staging') || viteMode === 'staging') {
      return 'staging';
    }
    
    return 'development';
  }

  /**
   * Get default configuration
   */
  private getDefaultConfig(): ProductionConfig {
    return {
      app: {
        name: 'DealerScope',
        version: '5.0.0-production',
        environment: 'development',
      },
      api: {
        baseUrl: '/api',
        timeout: 10000,
        retries: 3,
        rateLimit: {
          enabled: false,
          requests: 100,
          window: 60000,
        },
      },
      monitoring: {
        enabled: false,
        healthCheckInterval: 60000,
        metricsFlushInterval: 30000,
        errorReporting: false,
        performanceTracking: false,
      },
      features: {
        realTimeUpdates: true,
        advancedScoring: true,
        mlPredictions: true,
        auditLogging: false,
        maintenanceMode: false,
      },
      performance: {
        cacheEnabled: false,
        cacheTTL: 300000,
        maxConcurrentRequests: 10,
        memoryLimit: 150,
      },
      security: {
        csrfProtection: false,
        rateLimiting: false,
        inputSanitization: true,
        auditTrail: false,
      },
      supabase: {
        url: '',
        anonKey: '',
        enableRLS: true,
        connectionPooling: true,
      },
    };
  }

  /**
   * Apply production-specific optimizations
   */
  private applyProductionOptimizations(): void {
    // Enable all production features
    this.config.features.auditLogging = true;
    this.config.performance.cacheEnabled = true;
    this.config.api.rateLimit.enabled = true;
    
    // Increase timeouts for production stability
    this.config.api.timeout = 15000;
    this.config.monitoring.healthCheckInterval = 30000;
    
    // Enable security features
    this.config.security.csrfProtection = true;
    this.config.security.rateLimiting = true;
    this.config.security.auditTrail = true;

    logger.info('Production optimizations applied');
  }

  /**
   * Validate configuration
   */
  private validateConfig(): void {
    const errors: string[] = [];

    // Validate required fields
    if (!this.config.supabase.url) {
      errors.push('Supabase URL is required');
    }

    if (!this.config.supabase.anonKey) {
      errors.push('Supabase anon key is required');
    }

    // Validate performance limits
    if (this.config.performance.memoryLimit < 50) {
      errors.push('Memory limit too low (minimum 50MB)');
    }

    if (this.config.api.timeout < 1000) {
      errors.push('API timeout too low (minimum 1000ms)');
    }

    // Production-specific validations
    if (this.isProduction()) {
      if (!this.config.monitoring.enabled) {
        logger.warn('Monitoring disabled in production');
      }

      if (!this.config.security.csrfProtection) {
        errors.push('CSRF protection required in production');
      }
    }

    if (errors.length > 0) {
      logger.error('Configuration validation failed', { errors });
      throw new Error(`Configuration validation failed: ${errors.join(', ')}`);
    }
  }

  /**
   * Get configuration summary for debugging
   */
  getConfigSummary(): Record<string, any> {
    return {
      environment: this.config.app.environment,
      version: this.config.app.version,
      monitoringEnabled: this.config.monitoring.enabled,
      cacheEnabled: this.config.performance.cacheEnabled,
      securityEnabled: {
        csrf: this.config.security.csrfProtection,
        rateLimit: this.config.security.rateLimiting,
        audit: this.config.security.auditTrail,
      },
      featuresEnabled: Object.entries(this.config.features)
        .filter(([_, enabled]) => enabled)
        .map(([feature]) => feature),
    };
  }
}

// Global configuration manager instance
export const productionConfig = new ProductionConfigManager();

// Initialize configuration on module load
productionConfig.initialize();