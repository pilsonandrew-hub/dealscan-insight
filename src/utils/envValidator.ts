/**
 * Environment Validation - Prevent runtime crashes in staging/production
 * Validates required environment variables and configuration
 */

import { logger } from '@/lib/logger';

export interface EnvConfig {
  required: string[];
  optional?: string[];
  development?: string[];
  production?: string[];
}

/**
 * Validate required environment variables
 * Throws error with clear message if any are missing
 */
export function validateRequiredEnv(requiredVars: string[]): void {
  const missing = requiredVars.filter(varName => {
    const value = import.meta.env[varName] || process.env[varName];
    return !value || value.trim() === '';
  });
  
  if (missing.length > 0) {
    const errorMsg = `Missing required environment variables: ${missing.join(', ')}`;
    logger.error(errorMsg);
    console.error(`🚨 Environment Validation Failed: ${errorMsg}`);
    throw new Error(errorMsg);
  }
  
  logger.info('Environment validation passed', { required: requiredVars });
}

/**
 * Comprehensive environment validation for different deployment contexts
 */
export function validateEnvironment(config: EnvConfig): void {
  const isDevelopment = import.meta.env.DEV;
  const isProduction = import.meta.env.PROD;
  
  // Always validate required variables
  validateRequiredEnv(config.required);
  
  // Environment-specific validation
  if (isDevelopment && config.development) {
    const missing = config.development.filter(varName => {
      const value = import.meta.env[varName] || process.env[varName];
      return !value;
    });
    
    if (missing.length > 0) {
      logger.warn('Missing development environment variables', { missing });
      console.warn(`⚠️ Missing dev env vars: ${missing.join(', ')}`);
    }
  }
  
  if (isProduction && config.production) {
    validateRequiredEnv(config.production);
  }
  
  // Log optional variables status
  if (config.optional) {
    const optionalStatus = config.optional.map(varName => ({
      name: varName,
      configured: !!(import.meta.env[varName] || process.env[varName])
    }));
    
    logger.debug('Optional environment variables status', { optionalStatus });
  }
}

/**
 * DealerScope specific environment validation
 */
export function validateDealerScopeEnv(): void {
  validateEnvironment({
    required: [
      'VITE_SUPABASE_URL',
      'VITE_SUPABASE_ANON_KEY'
    ],
    optional: [
      'VITE_ANALYTICS_ID',
      'VITE_SENTRY_DSN'
    ],
    development: [
      'VITE_DEV_MODE'
    ],
    production: [
      'VITE_SUPABASE_URL',
      'VITE_SUPABASE_ANON_KEY'
    ]
  });
}

/**
 * Validate Supabase configuration
 */
export function validateSupabaseEnv(): boolean {
  try {
    const url = import.meta.env.VITE_SUPABASE_URL;
    const key = import.meta.env.VITE_SUPABASE_ANON_KEY;
    
    if (!url || !key) {
      logger.error('Supabase configuration missing');
      return false;
    }
    
    // Basic URL validation
    if (!url.startsWith('https://') || !url.includes('.supabase.co')) {
      logger.error('Invalid Supabase URL format', { url });
      return false;
    }
    
    // Basic key validation (should be a long base64-like string)
    if (key.length < 100) {
      logger.error('Invalid Supabase anon key format');
      return false;
    }
    
    logger.info('Supabase environment validation passed');
    return true;
  } catch (error) {
    logger.error('Supabase environment validation failed', { error });
    return false;
  }
}

/**
 * Get environment variable with fallback and type conversion
 */
export function getEnvVar<T = string>(
  name: string,
  fallback?: T,
  converter?: (value: string) => T
): T {
  const value = import.meta.env[name] || process.env[name];
  
  if (!value) {
    if (fallback !== undefined) {
      return fallback;
    }
    throw new Error(`Environment variable ${name} is required but not set`);
  }
  
  if (converter) {
    try {
      return converter(value);
    } catch (error) {
      logger.error(`Failed to convert env var ${name}`, { value, error });
      if (fallback !== undefined) {
        return fallback;
      }
      throw error;
    }
  }
  
  return value as T;
}

/**
 * Environment variable type converters
 */
export const EnvConverters = {
  boolean: (value: string): boolean => {
    const lowered = value.toLowerCase();
    return lowered === 'true' || lowered === '1' || lowered === 'yes';
  },
  
  number: (value: string): number => {
    const num = Number(value);
    if (isNaN(num)) {
      throw new Error(`Invalid number: ${value}`);
    }
    return num;
  },
  
  array: (value: string, separator = ','): string[] => {
    return value.split(separator).map(s => s.trim()).filter(Boolean);
  },
  
  json: <T>(value: string): T => {
    try {
      return JSON.parse(value);
    } catch (error) {
      throw new Error(`Invalid JSON: ${value}`);
    }
  }
};

/**
 * Environment health check for monitoring
 */
export function checkEnvironmentHealth(): {
  healthy: boolean;
  issues: string[];
  config: Record<string, boolean>;
} {
  const issues: string[] = [];
  const config: Record<string, boolean> = {};
  
  // Check critical variables
  const critical = ['VITE_SUPABASE_URL', 'VITE_SUPABASE_ANON_KEY'];
  for (const varName of critical) {
    const value = import.meta.env[varName] || process.env[varName];
    config[varName] = !!value;
    if (!value) {
      issues.push(`Missing critical env var: ${varName}`);
    }
  }
  
  // Check optional but recommended
  const recommended = ['VITE_ANALYTICS_ID'];
  for (const varName of recommended) {
    const value = import.meta.env[varName] || process.env[varName];
    config[varName] = !!value;
  }
  
  return {
    healthy: issues.length === 0,
    issues,
    config
  };
}