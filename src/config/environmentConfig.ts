/**
 * Environment Configuration - Replaces VITE_* usage with proper config management
 * Provides type-safe environment variable access and validation
 */

export interface AppConfig {
  supabase: {
    url: string;
    anonKey: string;
  };
  api: {
    baseUrl: string;
    timeout: number;
  };
  websocket: {
    url: string;
    autoReconnect: boolean;
    reconnectDelay: number;
  };
  app: {
    version: string;
    buildTime: string;
    gitCommit: string;
    environment: 'development' | 'staging' | 'production';
  };
  features: {
    debugMode: boolean;
    analyticsEnabled: boolean;
    performanceMonitoring: boolean;
  };
}

class EnvironmentConfig {
  private config: AppConfig;

  constructor() {
    this.config = this.loadConfiguration();
    this.validateConfiguration();
  }

  private loadConfiguration(): AppConfig {
    return {
      supabase: {
        url: 'https://lgpugcflvrqhslfnsjfh.supabase.co',
        anonKey: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxncHVnY2ZsdnJxaHNsZm5zamZoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTU2NjkzODksImV4cCI6MjA3MTI0NTM4OX0.Tadce_MW20ZfG75-EtiAHQPy2VfS0ciH1bekFNlVX0U'
      },
      api: {
        baseUrl: process.env.NODE_ENV === 'production' 
          ? 'https://lgpugcflvrqhslfnsjfh.supabase.co/functions/v1'
          : 'http://localhost:8000',
        timeout: 30000
      },
      websocket: {
        url: process.env.NODE_ENV === 'production'
          ? 'wss://lgpugcflvrqhslfnsjfh.supabase.co/realtime/v1'
          : 'ws://localhost:8000',
        autoReconnect: true,
        reconnectDelay: 5000
      },
      app: {
        version: '5.0.1',
        buildTime: new Date().toISOString(),
        gitCommit: 'latest',
        environment: this.detectEnvironment()
      },
      features: {
        debugMode: process.env.NODE_ENV === 'development',
        analyticsEnabled: process.env.NODE_ENV === 'production',
        performanceMonitoring: true
      }
    };
  }

  private detectEnvironment(): 'development' | 'staging' | 'production' {
    if (process.env.NODE_ENV === 'production') return 'production';
    if (process.env.NODE_ENV === 'staging') return 'staging';
    return 'development';
  }

  private validateConfiguration(): void {
    const errors: string[] = [];

    // Validate Supabase config
    if (!this.config.supabase.url) {
      errors.push('Supabase URL is required');
    }
    if (!this.config.supabase.anonKey) {
      errors.push('Supabase anon key is required');
    }

    // Validate API config
    if (!this.config.api.baseUrl) {
      errors.push('API base URL is required');
    }

    // Validate WebSocket config
    if (!this.config.websocket.url) {
      errors.push('WebSocket URL is required');
    }

    if (errors.length > 0) {
      throw new Error(`Configuration validation failed: ${errors.join(', ')}`);
    }
  }

  // Public getters
  get supabase() {
    return { ...this.config.supabase };
  }

  get api() {
    return { ...this.config.api };
  }

  get websocket() {
    return { ...this.config.websocket };
  }

  get app() {
    return { ...this.config.app };
  }

  get features() {
    return { ...this.config.features };
  }

  get isProduction(): boolean {
    return this.config.app.environment === 'production';
  }

  get isDevelopment(): boolean {
    return this.config.app.environment === 'development';
  }

  get isStaging(): boolean {
    return this.config.app.environment === 'staging';
  }

  // Method to get complete config (for debugging)
  getFullConfig(): AppConfig {
    return JSON.parse(JSON.stringify(this.config));
  }

  // Method to override config for testing
  overrideConfig(overrides: Partial<AppConfig>): void {
    if (this.isDevelopment) {
      this.config = { ...this.config, ...overrides };
      this.validateConfiguration();
    } else {
      console.warn('Config override ignored in non-development environment');
    }
  }
}

// Export singleton instance
export const envConfig = new EnvironmentConfig();

// Export individual configs for convenience
export const supabaseConfig = envConfig.supabase;
export const apiConfig = envConfig.api;
export const websocketConfig = envConfig.websocket;
export const appConfig = envConfig.app;
export const featureConfig = envConfig.features;