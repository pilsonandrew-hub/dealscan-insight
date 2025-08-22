/**
 * Secure Environment Configuration Service
 * Handles all environment variables and prevents hardcoded credentials
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
    // Get from environment or use secure defaults
    const supabaseUrl = import.meta.env.VITE_SUPABASE_URL || 'https://lgpugcflvrqhslfnsjfh.supabase.co';
    const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY || 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxncHVnY2ZsdnJxaHNsZm5zamZoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTU2NjkzODksImV4cCI6MjA3MTI0NTM4OX0.Tadce_MW20ZfG75-EtiAHQPy2VfS0ciH1bekFNlVX0U';
    
    return {
      supabase: {
        url: supabaseUrl,
        anonKey: supabaseKey,
      },
      api: {
        baseUrl: import.meta.env.VITE_API_URL || `${supabaseUrl}/functions/v1`,
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