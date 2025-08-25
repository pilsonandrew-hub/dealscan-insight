/**
 * Feature Flags for Safe Production Rollout
 * Centralized feature flag management with environment overrides
 */

export interface FeatureFlagConfig {
  // Performance Features
  ENABLE_CURSOR_PAGINATION: boolean;
  ENABLE_PRODUCTION_CACHE: boolean;
  ENABLE_SINGLE_FLIGHT: boolean;
  ENABLE_TTL_JITTER: boolean;
  
  // Browser Pool Features
  ENABLE_BROWSER_POOL: boolean;
  MAX_BROWSER_CONTEXTS: number;
  BROWSER_POOL_TIMEOUT: number;
  
  // Cache Provider Selection
  CACHE_PROVIDER: 'memory' | 'redis' | 'hybrid';
  CACHE_TTL_MS: number;
  CACHE_MAX_SIZE: number;
  
  // API Features
  OPPS_CURSOR_API: boolean;
  LEGACY_PAGE_API: boolean;
  API_RATE_LIMITING: boolean;
  
  // Circuit Breaker Features
  ENABLE_CIRCUIT_BREAKERS: boolean;
  CB_FAILURE_THRESHOLD: number;
  CB_RECOVERY_TIMEOUT: number;
  
  // Monitoring Features
  ENABLE_SRE_CONSOLE: boolean;
  ENABLE_PERFORMANCE_MONITORING: boolean;
  ENABLE_AUDIT_LOGGING: boolean;
  
  // Security Features
  ENABLE_INPUT_VALIDATION: boolean;
  ENABLE_RATE_LIMITING: boolean;
  ENABLE_CSRF_PROTECTION: boolean;
  
  // Data Quality Features
  ENABLE_SCHEMA_VALIDATION: boolean;
  ENABLE_ANOMALY_DETECTION: boolean;
  ENABLE_PROVENANCE_TRACKING: boolean;
}

// Default feature flag configuration
const DEFAULT_FLAGS: FeatureFlagConfig = {
  // Performance - Gradual rollout
  ENABLE_CURSOR_PAGINATION: true,
  ENABLE_PRODUCTION_CACHE: true,
  ENABLE_SINGLE_FLIGHT: true,
  ENABLE_TTL_JITTER: true,
  
  // Browser Pool - Start with small limits
  ENABLE_BROWSER_POOL: false, // Start disabled
  MAX_BROWSER_CONTEXTS: 3,
  BROWSER_POOL_TIMEOUT: 30000,
  
  // Cache Provider - Start with memory, upgrade to Redis
  CACHE_PROVIDER: 'memory',
  CACHE_TTL_MS: 300000, // 5 minutes
  CACHE_MAX_SIZE: 1000,
  
  // API Features - Maintain backward compatibility
  OPPS_CURSOR_API: true,
  LEGACY_PAGE_API: true,
  API_RATE_LIMITING: true,
  
  // Circuit Breakers - Conservative settings
  ENABLE_CIRCUIT_BREAKERS: true,
  CB_FAILURE_THRESHOLD: 5,
  CB_RECOVERY_TIMEOUT: 30000,
  
  // Monitoring - Enable all
  ENABLE_SRE_CONSOLE: true,
  ENABLE_PERFORMANCE_MONITORING: true,
  ENABLE_AUDIT_LOGGING: true,
  
  // Security - Enable all
  ENABLE_INPUT_VALIDATION: true,
  ENABLE_RATE_LIMITING: true,
  ENABLE_CSRF_PROTECTION: true,
  
  // Data Quality - Gradual rollout
  ENABLE_SCHEMA_VALIDATION: true,
  ENABLE_ANOMALY_DETECTION: false, // Start disabled
  ENABLE_PROVENANCE_TRACKING: true,
};

/**
 * Environment-specific overrides
 */
const ENVIRONMENT_OVERRIDES: Record<string, Partial<FeatureFlagConfig>> = {
  development: {
    ENABLE_BROWSER_POOL: true, // Enable for testing
    CACHE_PROVIDER: 'memory',
    ENABLE_ANOMALY_DETECTION: true, // Test in dev
  },
  
  staging: {
    ENABLE_BROWSER_POOL: true,
    MAX_BROWSER_CONTEXTS: 5,
    CACHE_PROVIDER: 'redis',
    CACHE_MAX_SIZE: 2000,
    ENABLE_ANOMALY_DETECTION: true,
  },
  
  production: {
    ENABLE_BROWSER_POOL: false, // Gradual rollout
    MAX_BROWSER_CONTEXTS: 10,
    CACHE_PROVIDER: 'redis',
    CACHE_MAX_SIZE: 5000,
    CACHE_TTL_MS: 600000, // 10 minutes in prod
    ENABLE_ANOMALY_DETECTION: false, // Manual enable
  }
};

/**
 * Remote feature flag overrides (from config service/database)
 */
class FeatureFlagManager {
  private flags: FeatureFlagConfig;
  private overrides: Partial<FeatureFlagConfig> = {};
  
  constructor() {
    const env = process.env.NODE_ENV || 'development';
    this.flags = {
      ...DEFAULT_FLAGS,
      ...ENVIRONMENT_OVERRIDES[env],
      ...this.loadRemoteOverrides()
    };
  }
  
  /**
   * Get feature flag value
   */
  get<K extends keyof FeatureFlagConfig>(flag: K): FeatureFlagConfig[K] {
    // Check for runtime overrides first
    if (flag in this.overrides) {
      return this.overrides[flag] as FeatureFlagConfig[K];
    }
    
    // Check environment variables
    const envVar = `FF_${flag}`;
    const envValue = process.env[envVar];
    if (envValue !== undefined) {
      // Parse environment value based on flag type
      if (typeof this.flags[flag] === 'boolean') {
        return (envValue.toLowerCase() === 'true') as FeatureFlagConfig[K];
      }
      if (typeof this.flags[flag] === 'number') {
        return parseInt(envValue, 10) as FeatureFlagConfig[K];
      }
      return envValue as FeatureFlagConfig[K];
    }
    
    return this.flags[flag];
  }
  
  /**
   * Set runtime override (for A/B testing, canary releases)
   */
  set<K extends keyof FeatureFlagConfig>(flag: K, value: FeatureFlagConfig[K]): void {
    (this.overrides as any)[flag] = value;
    console.log(`Feature flag ${flag} overridden to:`, value);
  }
  
  /**
   * Check if feature is enabled (boolean flags)
   */
  isEnabled(flag: keyof FeatureFlagConfig): boolean {
    const value = this.get(flag);
    return Boolean(value);
  }
  
  /**
   * Get all current flag values
   */
  getAllFlags(): FeatureFlagConfig {
    const result = {} as FeatureFlagConfig;
    for (const flag of Object.keys(this.flags) as Array<keyof FeatureFlagConfig>) {
      (result as any)[flag] = this.get(flag);
    }
    return result;
  }
  
  /**
   * Load remote overrides from config service
   */
  private loadRemoteOverrides(): Partial<FeatureFlagConfig> {
    try {
      // In production, this would fetch from a config service
      const remoteConfig = localStorage.getItem('feature_flags_override');
      return remoteConfig ? JSON.parse(remoteConfig) : {};
    } catch {
      return {};
    }
  }
  
  /**
   * Update flags from remote config (for real-time updates)
   */
  async refreshFromRemote(): Promise<void> {
    try {
      // In production, this would be an API call to config service
      const response = await fetch('/api/config/feature-flags');
      if (response.ok) {
        const remoteFlags = await response.json();
        Object.assign(this.overrides, remoteFlags);
        console.log('Feature flags refreshed from remote config');
      }
    } catch (error) {
      console.warn('Failed to refresh feature flags from remote:', error);
    }
  }
}

// Global feature flag manager
export const featureFlags = new FeatureFlagManager();

// Convenience helpers
export const isFeatureEnabled = (flag: keyof FeatureFlagConfig): boolean => 
  featureFlags.isEnabled(flag);

export const getFeatureValue = <K extends keyof FeatureFlagConfig>(flag: K): FeatureFlagConfig[K] => 
  featureFlags.get(flag);

// Export for testing/debugging
export const debugFeatureFlags = (): void => {
  console.table(featureFlags.getAllFlags());
};