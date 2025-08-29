/**
 * Unified Configuration Service
 * Consolidates all 8 config files into a single, type-safe configuration system
 */

interface DatabaseConfig {
  url: string;
  anonKey: string;
  connectionPool: {
    min: number;
    max: number;
    idleTimeoutMs: number;
  };
}

interface SecurityConfig {
  enableDebugMode: boolean;
  allowedOrigins: string[];
  rateLimit: {
    windowMs: number;
    maxRequests: number;
  };
  secrets: {
    jwtSecret: string;
    encryptionKey: string;
  };
}

interface PerformanceConfig {
  caching: {
    ttl: number;
    maxEntries: number;
  };
  monitoring: {
    enabled: boolean;
    samplingRate: number;
  };
  bundleOptimization: {
    enableCodeSplitting: boolean;
    enableTreeShaking: boolean;
  };
}

interface FeatureFlags {
  enableAIScoring: boolean;
  enableRealtimeUpdates: boolean;
  enableAdvancedAnalytics: boolean;
  enableChaosEngineering: boolean;
}

interface UnifiedAppConfig {
  environment: 'development' | 'staging' | 'production';
  database: DatabaseConfig;
  security: SecurityConfig;
  performance: PerformanceConfig;
  features: FeatureFlags;
  deployment: {
    version: string;
    buildHash: string;
    deployedAt: string;
  };
}

class UnifiedConfigService {
  private static instance: UnifiedConfigService;
  private config: UnifiedAppConfig;
  private isInitialized = false;

  private constructor() {
    this.config = this.buildConfiguration();
    this.validateConfiguration();
    this.isInitialized = true;
  }

  static getInstance(): UnifiedConfigService {
    if (!UnifiedConfigService.instance) {
      UnifiedConfigService.instance = new UnifiedConfigService();
    }
    return UnifiedConfigService.instance;
  }

  private buildConfiguration(): UnifiedAppConfig {
    const environment = this.getEnvironment();
    
    return {
      environment,
      database: this.buildDatabaseConfig(environment),
      security: this.buildSecurityConfig(environment),
      performance: this.buildPerformanceConfig(environment),
      features: this.buildFeatureFlags(environment),
      deployment: this.buildDeploymentConfig(),
    };
  }

  private getEnvironment(): 'development' | 'staging' | 'production' {
    const env = import.meta.env.MODE || 'development';
    if (env === 'production' || env === 'staging') {
      return env as 'production' | 'staging';
    }
    return 'development';
  }

  private buildDatabaseConfig(env: string): DatabaseConfig {
    return {
      url: import.meta.env.VITE_SUPABASE_URL || 'http://localhost:54321',
      anonKey: import.meta.env.VITE_SUPABASE_ANON_KEY || 'dev-key',
      connectionPool: {
        min: env === 'production' ? 5 : 2,
        max: env === 'production' ? 20 : 5,
        idleTimeoutMs: 30000,
      },
    };
  }

  private buildSecurityConfig(env: string): SecurityConfig {
    return {
      enableDebugMode: env === 'development',
      allowedOrigins: env === 'production' 
        ? ['https://your-domain.com']
        : ['http://localhost:5173', 'http://localhost:4173'],
      rateLimit: {
        windowMs: 15 * 60 * 1000, // 15 minutes
        maxRequests: env === 'production' ? 100 : 1000,
      },
      secrets: {
        jwtSecret: import.meta.env.VITE_JWT_SECRET || 'dev-secret',
        encryptionKey: import.meta.env.VITE_ENCRYPTION_KEY || 'dev-encryption-key',
      },
    };
  }

  private buildPerformanceConfig(env: string): PerformanceConfig {
    return {
      caching: {
        ttl: env === 'production' ? 300000 : 60000, // 5min prod, 1min dev
        maxEntries: env === 'production' ? 1000 : 100,
      },
      monitoring: {
        enabled: env !== 'development',
        samplingRate: env === 'production' ? 0.1 : 1.0,
      },
      bundleOptimization: {
        enableCodeSplitting: env === 'production',
        enableTreeShaking: env === 'production',
      },
    };
  }

  private buildFeatureFlags(env: string): FeatureFlags {
    return {
      enableAIScoring: env === 'production' ? false : true, // Disabled in prod until foundation is fixed
      enableRealtimeUpdates: true,
      enableAdvancedAnalytics: env !== 'development',
      enableChaosEngineering: env === 'development',
    };
  }

  private buildDeploymentConfig() {
    return {
      version: import.meta.env.VITE_APP_VERSION || '1.0.0',
      buildHash: import.meta.env.VITE_BUILD_HASH || 'dev-build',
      deployedAt: new Date().toISOString(),
    };
  }

  private validateConfiguration(): void {
    if (!this.config.database.url) {
      throw new Error('Database URL is required');
    }
    
    if (!this.config.database.anonKey) {
      throw new Error('Database anonymous key is required');
    }

    if (this.config.environment === 'production' && this.config.security.enableDebugMode) {
      throw new Error('Debug mode must be disabled in production');
    }

    // Validate connection pool settings
    if (this.config.database.connectionPool.min > this.config.database.connectionPool.max) {
      throw new Error('Connection pool min cannot be greater than max');
    }
  }

  // Public API
  get database(): DatabaseConfig {
    this.ensureInitialized();
    return this.config.database;
  }

  get security(): SecurityConfig {
    this.ensureInitialized();
    return this.config.security;
  }

  get performance(): PerformanceConfig {
    this.ensureInitialized();
    return this.config.performance;
  }

  get features(): FeatureFlags {
    this.ensureInitialized();
    return this.config.features;
  }

  get deployment() {
    this.ensureInitialized();
    return this.config.deployment;
  }

  get environment() {
    this.ensureInitialized();
    return this.config.environment;
  }

  get isProduction(): boolean {
    return this.environment === 'production';
  }

  get isDevelopment(): boolean {
    return this.environment === 'development';
  }

  private ensureInitialized(): void {
    if (!this.isInitialized) {
      throw new Error('UnifiedConfigService not initialized');
    }
  }

  // For testing and debugging
  getFullConfig(): UnifiedAppConfig {
    this.ensureInitialized();
    return { ...this.config };
  }

  // Update feature flag at runtime
  updateFeatureFlag(flag: keyof FeatureFlags, value: boolean): void {
    this.ensureInitialized();
    this.config.features[flag] = value;
  }
}

export const configService = UnifiedConfigService.getInstance();
export type { UnifiedAppConfig, DatabaseConfig, SecurityConfig, PerformanceConfig, FeatureFlags };