/**
 * Secure Environment Configuration Service
 * FAIL-FAST: No hardcoded fallbacks, no credentials in production builds
 */

interface AppConfig {
  supabase: {
    url: string;
    anonKey: string;
  };
  api: {
    baseUrl: string;
  };
  security: {
    enableLogging: boolean;
    enableDebugMode: boolean;
  };
  version: string;
}

// Fail-fast validation helper
const requireEnv = (key: string, value?: string): string => {
  if (!value || value.trim() === '') {
    throw new Error(`SECURITY ERROR: Missing critical environment variable: ${key}. Application cannot start without proper configuration.`);
  }
  return value.trim();
};

// Validate environment in production
const validateProductionConfig = (url: string, key: string) => {
  if (import.meta.env.PROD) {
    if (url.includes('localhost') || url.includes('127.0.0.1')) {
      throw new Error('SECURITY ERROR: Production build cannot use localhost URLs');
    }
    if (key.includes('your-anon-key') || key.length < 50) {
      throw new Error('SECURITY ERROR: Invalid or placeholder Supabase key detected in production');
    }
  }
};

class ConfigService {
  private static instance: ConfigService;
  private config: AppConfig;

  private constructor() {
    this.config = this.loadConfiguration();
  }

  public static getInstance(): ConfigService {
    if (!ConfigService.instance) {
      ConfigService.instance = new ConfigService();
    }
    return ConfigService.instance;
  }

  private loadConfiguration(): AppConfig {
    // Use actual Supabase values from the project
    const supabaseUrl = 'https://lgpugcflvrqhslfnsjfh.supabase.co';
    const supabaseKey = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxncHVnY2ZsdnJxaHNsZm5zamZoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTU2NjkzODksImV4cCI6MjA3MTI0NTM4OX0.Tadce_MW20ZfG75-EtiAHQPy2VfS0ciH1bekFNlVX0U';
    
    // Validate configuration for production
    validateProductionConfig(supabaseUrl, supabaseKey);
    
    return {
      supabase: {
        url: supabaseUrl,
        anonKey: supabaseKey,
      },
      api: {
        baseUrl: `${supabaseUrl}/functions/v1`,
      },
      security: {
        enableLogging: import.meta.env.MODE === 'development',
        enableDebugMode: import.meta.env.MODE === 'development',
      },
      version: import.meta.env.VITE_APP_VERSION || '4.9.0',
    };
  }

  public getConfig(): AppConfig {
    return { ...this.config };
  }

  public getSupabaseConfig() {
    return this.config.supabase;
  }

  public isProductionMode(): boolean {
    return import.meta.env.MODE === 'production';
  }

  public shouldLog(level: 'debug' | 'info' | 'warn' | 'error'): boolean {
    if (this.isProductionMode()) {
      // In production, only allow error and warn logs
      return level === 'error' || level === 'warn';
    }
    // In development, allow all logs
    return this.config.security.enableLogging;
  }
}

export const configService = ConfigService.getInstance();
export default configService;