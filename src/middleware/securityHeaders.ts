/**
 * Security Headers Middleware
 * Implements comprehensive security headers for production
 */

export interface SecurityConfig {
  contentSecurityPolicy?: boolean;
  hsts?: boolean;
  xssProtection?: boolean;
  frameOptions?: boolean;
  contentTypeOptions?: boolean;
  referrerPolicy?: boolean;
  permissionsPolicy?: boolean;
}

export class SecurityHeaders {
  private config: Required<SecurityConfig>;

  constructor(config: SecurityConfig = {}) {
    this.config = {
      contentSecurityPolicy: true,
      hsts: true,
      xssProtection: true,
      frameOptions: true,
      contentTypeOptions: true,
      referrerPolicy: true,
      permissionsPolicy: true,
      ...config
    };
  }

  /**
   * Generate security headers for production
   */
  getHeaders(): Record<string, string> {
    const headers: Record<string, string> = {};

    // Content Security Policy
    if (this.config.contentSecurityPolicy) {
      headers['Content-Security-Policy'] = this.getCSPHeader();
    }

    // HTTP Strict Transport Security
    if (this.config.hsts) {
      headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload';
    }

    // XSS Protection
    if (this.config.xssProtection) {
      headers['X-XSS-Protection'] = '1; mode=block';
    }

    // Frame Options
    if (this.config.frameOptions) {
      headers['X-Frame-Options'] = 'DENY';
    }

    // Content Type Options
    if (this.config.contentTypeOptions) {
      headers['X-Content-Type-Options'] = 'nosniff';
    }

    // Referrer Policy
    if (this.config.referrerPolicy) {
      headers['Referrer-Policy'] = 'strict-origin-when-cross-origin';
    }

    // Permissions Policy
    if (this.config.permissionsPolicy) {
      headers['Permissions-Policy'] = this.getPermissionsPolicy();
    }

    // Additional security headers
    headers['X-DNS-Prefetch-Control'] = 'off';
    headers['X-Download-Options'] = 'noopen';
    headers['X-Permitted-Cross-Domain-Policies'] = 'none';

    return headers;
  }

  /**
   * Apply headers to response
   */
  applyHeaders(response: Response): Response {
    const headers = this.getHeaders();
    
    Object.entries(headers).forEach(([key, value]) => {
      response.headers.set(key, value);
    });

    return response;
  }

  /**
   * Generate Content Security Policy header
   */
  private getCSPHeader(): string {
    const directives = [
      "default-src 'self'",
      "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://unpkg.com https://lgpugcflvrqhslfnsjfh.supabase.co",
      "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
      "font-src 'self' https://fonts.gstatic.com",
      "img-src 'self' data: https: blob:",
      "connect-src 'self' https://lgpugcflvrqhslfnsjfh.supabase.co wss://lgpugcflvrqhslfnsjfh.supabase.co",
      "frame-src 'none'",
      "object-src 'none'",
      "base-uri 'self'",
      "form-action 'self'",
      "frame-ancestors 'none'",
      "upgrade-insecure-requests"
    ];

    return directives.join('; ');
  }

  /**
   * Generate Permissions Policy header
   */
  private getPermissionsPolicy(): string {
    const policies = [
      'camera=()',
      'microphone=()',
      'geolocation=()',
      'payment=()',
      'usb=()',
      'magnetometer=()',
      'gyroscope=()',
      'speaker=()',
      'vibrate=()',
      'fullscreen=(self)',
      'sync-xhr=()'
    ];

    return policies.join(', ');
  }
}

// Export default instance
export const securityHeaders = new SecurityHeaders();

// Helper function for adding security headers to fetch responses
export const addSecurityHeaders = (response: Response): Response => {
  return securityHeaders.applyHeaders(response);
};

// Middleware function for Express-like frameworks
export const securityMiddleware = () => {
  const headers = securityHeaders.getHeaders();
  
  return (req: any, res: any, next: any) => {
    Object.entries(headers).forEach(([key, value]) => {
      res.setHeader(key, value);
    });
    next();
  };
};

// CORS configuration for secure origins
export const getCORSConfig = (environment: 'development' | 'production' = 'production') => {
  const allowedOrigins = environment === 'development' 
    ? ['http://localhost:3000', 'http://localhost:8080', 'https://lgpugcflvrqhslfnsjfh.supabase.co']
    : ['https://lgpugcflvrqhslfnsjfh.supabase.co'];

  return {
    origin: allowedOrigins,
    credentials: true,
    methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
    allowedHeaders: [
      'Content-Type',
      'Authorization',
      'x-client-info',
      'apikey',
      'x-requested-with',
      'x-csrf-token'
    ],
    exposedHeaders: ['x-total-count', 'x-page-count'],
    maxAge: 86400, // 24 hours
  };
};