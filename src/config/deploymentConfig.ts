/**
 * Production Deployment Configuration
 * Handles environment-specific settings and deployment requirements
 */

import { Environment } from '@/config/environmentManager';

export interface DeploymentConfig {
  environment: Environment;
  domain: string;
  ssl: boolean;
  cdn: {
    enabled: boolean;
    domain?: string;
    assets: string[];
  };
  database: {
    pooling: boolean;
    ssl: boolean;
    connectionLimit: number;
  };
  security: {
    csp: string;
    hsts: boolean;
    xssProtection: boolean;
    frameOptions: string;
  };
  monitoring: {
    healthCheckPath: string;
    metricsPath: string;
    logLevel: string;
  };
  performance: {
    compression: boolean;
    caching: {
      staticAssets: string;
      api: string;
    };
  };
}

export class DeploymentManager {
  private static readonly PRODUCTION_CONFIG: DeploymentConfig = {
    environment: Environment.PRODUCTION,
    domain: 'dealerscope.com',
    ssl: true,
    cdn: {
      enabled: true,
      domain: 'cdn.dealerscope.com',
      assets: ['*.js', '*.css', '*.png', '*.jpg', '*.svg', '*.woff2']
    },
    database: {
      pooling: true,
      ssl: true,
      connectionLimit: 20
    },
    security: {
      csp: "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; connect-src 'self' https://lgpugcflvrqhslfnsjfh.supabase.co wss://lgpugcflvrqhslfnsjfh.supabase.co;",
      hsts: true,
      xssProtection: true,
      frameOptions: 'DENY'
    },
    monitoring: {
      healthCheckPath: '/api/health',
      metricsPath: '/api/metrics',
      logLevel: 'warn'
    },
    performance: {
      compression: true,
      caching: {
        staticAssets: 'public, max-age=31536000, immutable',
        api: 'no-cache, no-store, must-revalidate'
      }
    }
  };

  private static readonly STAGING_CONFIG: DeploymentConfig = {
    ...DeploymentManager.PRODUCTION_CONFIG,
    environment: Environment.STAGING,
    domain: 'staging.dealerscope.com',
    cdn: {
      enabled: false,
      assets: []
    },
    security: {
      ...DeploymentManager.PRODUCTION_CONFIG.security,
      csp: "default-src 'self' 'unsafe-inline' 'unsafe-eval'; connect-src 'self' https://lgpugcflvrqhslfnsjfh.supabase.co wss://lgpugcflvrqhslfnsjfh.supabase.co;",
      hsts: false
    },
    monitoring: {
      ...DeploymentManager.PRODUCTION_CONFIG.monitoring,
      logLevel: 'info'
    }
  };

  private static readonly DEVELOPMENT_CONFIG: DeploymentConfig = {
    ...DeploymentManager.PRODUCTION_CONFIG,
    environment: Environment.DEVELOPMENT,
    domain: 'localhost:8080',
    ssl: false,
    cdn: {
      enabled: false,
      assets: []
    },
    database: {
      pooling: false,
      ssl: false,
      connectionLimit: 5
    },
    security: {
      csp: '',
      hsts: false,
      xssProtection: false,
      frameOptions: 'SAMEORIGIN'
    },
    monitoring: {
      ...DeploymentManager.PRODUCTION_CONFIG.monitoring,
      logLevel: 'debug'
    },
    performance: {
      compression: false,
      caching: {
        staticAssets: 'no-cache',
        api: 'no-cache'
      }
    }
  };

  /**
   * Get deployment configuration for environment
   */
  static getConfig(environment: Environment): DeploymentConfig {
    switch (environment) {
      case Environment.PRODUCTION:
        return this.PRODUCTION_CONFIG;
      case Environment.STAGING:
        return this.STAGING_CONFIG;
      default:
        return this.DEVELOPMENT_CONFIG;
    }
  }

  /**
   * Generate Content Security Policy header
   */
  static generateCSPHeader(config: DeploymentConfig): string {
    if (!config.security.csp) return '';
    
    return config.security.csp;
  }

  /**
   * Generate security headers for deployment
   */
  static generateSecurityHeaders(config: DeploymentConfig): Record<string, string> {
    const headers: Record<string, string> = {};

    if (config.security.csp) {
      headers['Content-Security-Policy'] = config.security.csp;
    }

    if (config.security.hsts) {
      headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload';
    }

    if (config.security.xssProtection) {
      headers['X-XSS-Protection'] = '1; mode=block';
      headers['X-Content-Type-Options'] = 'nosniff';
    }

    if (config.security.frameOptions) {
      headers['X-Frame-Options'] = config.security.frameOptions;
    }

    headers['Referrer-Policy'] = 'strict-origin-when-cross-origin';
    headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()';

    return headers;
  }

  /**
   * Generate cache headers for static assets
   */
  static generateCacheHeaders(
    config: DeploymentConfig,
    assetType: 'static' | 'api'
  ): Record<string, string> {
    const cacheControl = assetType === 'static' 
      ? config.performance.caching.staticAssets
      : config.performance.caching.api;

    return {
      'Cache-Control': cacheControl,
      'Vary': 'Accept-Encoding'
    };
  }

  /**
   * Validate deployment readiness
   */
  static validateDeployment(environment: Environment): {
    ready: boolean;
    issues: string[];
    warnings: string[];
  } {
    const issues: string[] = [];
    const warnings: string[] = [];

    // Check environment variables
    if (environment === Environment.PRODUCTION) {
      if (!process.env.SUPABASE_URL) {
        issues.push('SUPABASE_URL environment variable is required for production');
      }

      if (!process.env.SUPABASE_ANON_KEY) {
        issues.push('SUPABASE_ANON_KEY environment variable is required for production');
      }

      // Check for development artifacts
      if (process.env.NODE_ENV !== 'production') {
        warnings.push('NODE_ENV should be set to "production" for production deployment');
      }
    }

    // Validate SSL configuration
    const config = this.getConfig(environment);
    if (environment === Environment.PRODUCTION && !config.ssl) {
      issues.push('SSL must be enabled for production deployment');
    }

    // Check database configuration
    if (environment === Environment.PRODUCTION && !config.database.ssl) {
      warnings.push('Database SSL should be enabled for production');
    }

    return {
      ready: issues.length === 0,
      issues,
      warnings
    };
  }

  /**
   * Generate deployment manifest
   */
  static generateManifest(environment: Environment): {
    version: string;
    environment: Environment;
    buildTime: string;
    config: DeploymentConfig;
    validation: ReturnType<typeof DeploymentManager.validateDeployment>;
  } {
    const config = this.getConfig(environment);
    const validation = this.validateDeployment(environment);

    return {
      version: process.env.npm_package_version || '1.0.0',
      environment,
      buildTime: new Date().toISOString(),
      config,
      validation
    };
  }
}

// Health check endpoint configuration
export const HEALTH_CHECK_CONFIG = {
  path: '/api/health',
  timeout: 5000,
  services: ['database', 'storage', 'memory', 'network'],
  thresholds: {
    responseTime: 2000,
    memoryUsage: 80,
    errorRate: 5
  }
};

// Monitoring endpoints
export const MONITORING_CONFIG = {
  healthCheck: '/api/health',
  metrics: '/api/metrics',
  readiness: '/api/ready',
  liveness: '/api/live'
};

export default DeploymentManager;