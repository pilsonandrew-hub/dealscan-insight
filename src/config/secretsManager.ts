/**
 * Secrets Management System
 * Addresses Issue #4: Production Configuration Issues
 * Secure handling of sensitive configuration data
 */

import { logger } from '@/utils/secureLogger';
import { centralizedErrorHandler } from '@/lib/centralizedErrorHandling';

interface SecretConfig {
  key: string;
  required: boolean;
  description: string;
  validationPattern?: RegExp;
  defaultValue?: string;
  environment?: 'development' | 'staging' | 'production' | 'all';
}

interface ValidationResult {
  isValid: boolean;
  errors: string[];
  warnings: string[];
}

/**
 * Centralized secrets management with validation and secure access
 */
class SecretsManager {
  private secrets: Map<string, string> = new Map();
  private secretConfigs: Map<string, SecretConfig> = new Map();
  private isInitialized = false;

  constructor() {
    this.defineSecretConfigs();
  }

  /**
   * Define all required secrets and their configurations
   */
  private defineSecretConfigs() {
    const configs: SecretConfig[] = [
      // Supabase Configuration
      {
        key: 'VITE_SUPABASE_URL',
        required: true,
        description: 'Supabase project URL',
        validationPattern: /^https:\/\/[a-z0-9]+\.supabase\.co$/,
        environment: 'all'
      },
      {
        key: 'VITE_SUPABASE_PUBLISHABLE_KEY',
        required: true,
        description: 'Supabase publishable (anon) key',
        validationPattern: /^eyJ[A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+\.?[A-Za-z0-9-_.+/=]*$/,
        environment: 'all'
      },
      {
        key: 'VITE_SUPABASE_PROJECT_ID',
        required: true,
        description: 'Supabase project ID',
        validationPattern: /^[a-z0-9]{20}$/,
        environment: 'all'
      },

      // Application Configuration
      {
        key: 'VITE_APP_NAME',
        required: false,
        description: 'Application name',
        defaultValue: 'DealerScope',
        environment: 'all'
      },
      {
        key: 'VITE_APP_VERSION',
        required: false,
        description: 'Application version',
        defaultValue: '1.0.0',
        environment: 'all'
      },
      {
        key: 'VITE_ENVIRONMENT',
        required: true,
        description: 'Deployment environment',
        validationPattern: /^(development|staging|production)$/,
        defaultValue: 'development',
        environment: 'all'
      },

      // Security Configuration
      {
        key: 'VITE_ENABLE_ANALYTICS',
        required: false,
        description: 'Enable analytics tracking',
        validationPattern: /^(true|false)$/,
        defaultValue: 'false',
        environment: 'all'
      },
      {
        key: 'VITE_API_BASE_URL',
        required: false,
        description: 'Base URL for API requests',
        validationPattern: /^https?:\/\/.+/,
        environment: 'all'
      },

      // External Service Keys
      {
        key: 'VITE_SENTRY_DSN',
        required: false,
        description: 'Sentry error monitoring DSN',
        validationPattern: /^https:\/\/[a-f0-9]+@[a-z0-9]+\.ingest\.sentry\.io\/[0-9]+$/,
        environment: 'production'
      },
      {
        key: 'VITE_GOOGLE_ANALYTICS_ID',
        required: false,
        description: 'Google Analytics tracking ID',
        validationPattern: /^G-[A-Z0-9]+$/,
        environment: 'production'
      }
    ];

    configs.forEach(config => {
      this.secretConfigs.set(config.key, config);
    });
  }

  /**
   * Initialize secrets manager with environment validation
   */
  public async initialize(): Promise<ValidationResult> {
    if (this.isInitialized) {
      return { isValid: true, errors: [], warnings: [] };
    }

    logger.info('Initializing secrets manager', 'SECRETS');

    try {
      // Load secrets from environment
      await this.loadSecretsFromEnvironment();

      // Validate all secrets
      const validation = await this.validateAllSecrets();

      // Log validation results
      if (validation.errors.length > 0) {
        logger.error('Secret validation failed', 'SECRETS', {
          errors: validation.errors,
          warnings: validation.warnings
        });
      } else if (validation.warnings.length > 0) {
        logger.warn('Secret validation warnings', 'SECRETS', {
          warnings: validation.warnings
        });
      } else {
        logger.info('All secrets validated successfully', 'SECRETS');
      }

      this.isInitialized = true;
      return validation;
    } catch (error) {
      const errorMsg = 'Failed to initialize secrets manager';
      logger.error(errorMsg, 'SECRETS', error);
      centralizedErrorHandler.handleError({
        error: error as Error,
        severity: 'critical',
        category: 'system',
        context: {
          component: 'SecretsManager',
          operation: 'initialize'
        }
      });

      return {
        isValid: false,
        errors: [errorMsg],
        warnings: []
      };
    }
  }

  /**
   * Load secrets from environment variables
   */
  private async loadSecretsFromEnvironment() {
    this.secretConfigs.forEach((config, key) => {
      const value = import.meta.env[key];
      
      if (value) {
        this.secrets.set(key, value);
      } else if (config.defaultValue) {
        this.secrets.set(key, config.defaultValue);
        logger.debug(`Using default value for ${key}`, 'SECRETS');
      }
    });
  }

  /**
   * Validate all loaded secrets
   */
  private async validateAllSecrets(): Promise<ValidationResult> {
    const errors: string[] = [];
    const warnings: string[] = [];
    const currentEnv = this.getCurrentEnvironment();

    this.secretConfigs.forEach((config, key) => {
      // Skip if not relevant for current environment
      if (config.environment !== 'all' && config.environment !== currentEnv) {
        return;
      }

      const value = this.secrets.get(key);

      // Check required secrets
      if (config.required && !value) {
        errors.push(`Required secret missing: ${key} - ${config.description}`);
        return;
      }

      // Validate pattern if value exists
      if (value && config.validationPattern && !config.validationPattern.test(value)) {
        errors.push(`Invalid format for ${key}: ${config.description}`);
      }

      // Environment-specific warnings
      if (currentEnv === 'production') {
        if (key.includes('DEV') || key.includes('TEST')) {
          warnings.push(`Development/test secret found in production: ${key}`);
        }
      }
    });

    // Additional security checks
    this.performSecurityChecks(errors, warnings);

    return {
      isValid: errors.length === 0,
      errors,
      warnings
    };
  }

  /**
   * Perform additional security validation
   */
  private performSecurityChecks(errors: string[], warnings: string[]) {
    const supabaseUrl = this.secrets.get('VITE_SUPABASE_URL');
    const supabaseKey = this.secrets.get('VITE_SUPABASE_PUBLISHABLE_KEY');

    // Check for localhost/development URLs in production
    if (this.getCurrentEnvironment() === 'production') {
      if (supabaseUrl?.includes('localhost')) {
        errors.push('Localhost URL detected in production environment');
      }
    }

    // Check key strength
    if (supabaseKey && supabaseKey.length < 100) {
      warnings.push('Supabase key appears to be shorter than expected');
    }

    // Check for common weak patterns
    this.secrets.forEach((value, key) => {
      if (value.includes('test') || value.includes('demo') || value.includes('example')) {
        warnings.push(`Possible test/demo value detected for ${key}`);
      }
    });
  }

  /**
   * Get current environment
   */
  private getCurrentEnvironment(): string {
    return this.secrets.get('VITE_ENVIRONMENT') || 'development';
  }

  /**
   * Securely get a secret value
   */
  public getSecret(key: string): string | undefined {
    if (!this.isInitialized) {
      logger.warn('Secrets manager not initialized', 'SECRETS');
      return undefined;
    }

    const value = this.secrets.get(key);
    
    if (!value) {
      logger.debug(`Secret not found: ${key}`, 'SECRETS');
    }

    return value;
  }

  /**
   * Get a required secret (throws if missing)
   */
  public getRequiredSecret(key: string): string {
    const value = this.getSecret(key);
    
    if (!value) {
      const error = new Error(`Required secret missing: ${key}`);
      centralizedErrorHandler.handleError({
        error,
        severity: 'critical',
        category: 'system',
        context: {
          component: 'SecretsManager',
          operation: 'getRequiredSecret',
          metadata: { key }
        }
      });
      throw error;
    }

    return value;
  }

  /**
   * Check if a secret exists
   */
  public hasSecret(key: string): boolean {
    return this.secrets.has(key) && Boolean(this.secrets.get(key));
  }

  /**
   * Get sanitized secrets info for debugging (without values)
   */
  public getSecretsInfo() {
    const info: Record<string, any> = {};
    
    this.secretConfigs.forEach((config, key) => {
      info[key] = {
        required: config.required,
        description: config.description,
        hasValue: this.hasSecret(key),
        environment: config.environment
      };
    });

    return info;
  }

  /**
   * Generate configuration report
   */
  public generateConfigReport(): string {
    const info = this.getSecretsInfo();
    const currentEnv = this.getCurrentEnvironment();
    
    let report = `\n=== Configuration Report (${currentEnv}) ===\n`;
    
    Object.entries(info).forEach(([key, config]) => {
      const status = config.hasValue ? '✅' : (config.required ? '❌' : '⚠️');
      report += `${status} ${key}: ${config.description}\n`;
    });
    
    return report;
  }

  /**
   * Validate runtime configuration
   */
  public async validateRuntimeConfig(): Promise<boolean> {
    try {
      const validation = await this.validateAllSecrets();
      
      if (!validation.isValid) {
        logger.error('Runtime configuration validation failed', 'SECRETS', {
          errors: validation.errors
        });
        return false;
      }

      return true;
    } catch (error) {
      logger.error('Runtime configuration validation error', 'SECRETS', error);
      return false;
    }
  }
}

// Create singleton instance
export const secretsManager = new SecretsManager();

// Convenience functions
export const getSecret = (key: string) => secretsManager.getSecret(key);
export const getRequiredSecret = (key: string) => secretsManager.getRequiredSecret(key);
export const hasSecret = (key: string) => secretsManager.hasSecret(key);

// Initialize on module load
secretsManager.initialize().then(result => {
  if (!result.isValid) {
    logger.error('Application configuration is invalid', 'SECRETS', {
      errors: result.errors,
      warnings: result.warnings
    });
  }
});

export default secretsManager;