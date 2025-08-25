/**
 * SSRF Protection Guard - Phase 2 Security
 * Prevents Server-Side Request Forgery attacks with allowlists and private IP detection
 */

import productionLogger from '@/utils/productionLogger';

interface SSRFConfig {
  allowedDomains: string[];
  allowedPorts: number[];
  maxRedirects: number;
  requestTimeout: number;
  maxResponseSize: number;
  blockPrivateIPs: boolean;
  blockLoopback: boolean;
}

const DEFAULT_CONFIG: SSRFConfig = {
  allowedDomains: [
    'govdeals.com',
    'publicsurplus.com',
    'liquidation.com',
    'autoauctions.com',
    'copart.com',
    'iaai.com'
  ],
  allowedPorts: [80, 443, 8080, 8443],
  maxRedirects: 3,
  requestTimeout: 30000, // 30 seconds
  maxResponseSize: 50 * 1024 * 1024, // 50MB
  blockPrivateIPs: true,
  blockLoopback: true
};

interface ValidationResult {
  allowed: boolean;
  reason?: string;
  sanitizedUrl?: string;
}

export class SSRFGuard {
  private config: SSRFConfig;
  private redirectCount: Map<string, number> = new Map();

  constructor(config: Partial<SSRFConfig> = {}) {
    this.config = { ...DEFAULT_CONFIG, ...config };
    productionLogger.info('SSRF Guard initialized', {
      allowedDomains: this.config.allowedDomains.length,
      maxRedirects: this.config.maxRedirects,
      blockPrivate: this.config.blockPrivateIPs
    });
  }

  /**
   * Validate URL for SSRF protection
   */
  validateUrl(url: string, requestId?: string): ValidationResult {
    try {
      const parsedUrl = new URL(url);
      
      // Check protocol
      if (!['http:', 'https:'].includes(parsedUrl.protocol)) {
        return {
          allowed: false,
          reason: `Protocol ${parsedUrl.protocol} not allowed`
        };
      }

      // Check domain allowlist
      const domain = parsedUrl.hostname.toLowerCase();
      if (!this.isDomainAllowed(domain)) {
        productionLogger.logSecurityEvent('ssrf_blocked_domain', 'medium', {
          domain,
          url,
          requestId
        });
        
        return {
          allowed: false,
          reason: `Domain ${domain} not in allowlist`
        };
      }

      // Check for private IP addresses
      if (this.config.blockPrivateIPs && this.isPrivateIP(domain)) {
        productionLogger.logSecurityEvent('ssrf_blocked_private_ip', 'high', {
          domain,
          url,
          requestId
        });
        
        return {
          allowed: false,
          reason: `Private IP address detected: ${domain}`
        };
      }

      // Check for loopback addresses
      if (this.config.blockLoopback && this.isLoopbackAddress(domain)) {
        productionLogger.logSecurityEvent('ssrf_blocked_loopback', 'high', {
          domain,
          url,
          requestId
        });
        
        return {
          allowed: false,
          reason: `Loopback address detected: ${domain}`
        };
      }

      // Check port allowlist
      const port = parsedUrl.port ? parseInt(parsedUrl.port) : 
                   (parsedUrl.protocol === 'https:' ? 443 : 80);
      
      if (!this.config.allowedPorts.includes(port)) {
        return {
          allowed: false,
          reason: `Port ${port} not allowed`
        };
      }

      // Sanitize URL (remove dangerous fragments)
      const sanitizedUrl = this.sanitizeUrl(parsedUrl);

      return {
        allowed: true,
        sanitizedUrl
      };

    } catch (error) {
      productionLogger.warn('URL validation failed', {
        url,
        error: (error as Error).message,
        requestId
      });
      
      return {
        allowed: false,
        reason: 'Invalid URL format'
      };
    }
  }

  /**
   * Check if domain is in allowlist
   */
  private isDomainAllowed(domain: string): boolean {
    // Exact match
    if (this.config.allowedDomains.includes(domain)) {
      return true;
    }

    // Subdomain match (e.g., api.govdeals.com matches govdeals.com)
    return this.config.allowedDomains.some(allowedDomain => 
      domain.endsWith(`.${allowedDomain}`)
    );
  }

  /**
   * Check if IP is private (RFC 1918)
   */
  private isPrivateIP(address: string): boolean {
    // IPv4 private ranges
    const privateRanges = [
      /^10\./,                    // 10.0.0.0/8
      /^172\.(1[6-9]|2[0-9]|3[0-1])\./, // 172.16.0.0/12
      /^192\.168\./,              // 192.168.0.0/16
      /^169\.254\./,              // Link-local
      /^127\./,                   // Loopback
      /^0\./                      // This network
    ];

    return privateRanges.some(range => range.test(address));
  }

  /**
   * Check if address is loopback
   */
  private isLoopbackAddress(address: string): boolean {
    const loopbackPatterns = [
      'localhost',
      '127.0.0.1',
      '::1',
      /^127\./,
      /^0+\.0+\.0+\.0*1$/
    ];

    return loopbackPatterns.some(pattern => 
      typeof pattern === 'string' ? 
        address === pattern : 
        pattern.test(address)
    );
  }

  /**
   * Sanitize URL to remove dangerous components
   */
  private sanitizeUrl(url: URL): string {
    // Remove fragments that could be used for attacks
    url.hash = '';
    
    // Remove auth info
    url.username = '';
    url.password = '';
    
    // Normalize path
    url.pathname = url.pathname.replace(/\/+/g, '/');
    
    return url.toString();
  }

  /**
   * Track redirect count for URL
   */
  trackRedirect(originalUrl: string): boolean {
    const count = this.redirectCount.get(originalUrl) || 0;
    
    if (count >= this.config.maxRedirects) {
      productionLogger.logSecurityEvent('ssrf_max_redirects', 'medium', {
        url: originalUrl,
        redirectCount: count
      });
      return false;
    }

    this.redirectCount.set(originalUrl, count + 1);
    return true;
  }

  /**
   * Clear redirect tracking (call after request completes)
   */
  clearRedirectTracking(url: string): void {
    this.redirectCount.delete(url);
  }

  /**
   * Create fetch wrapper with SSRF protection
   */
  createProtectedFetch(requestId?: string) {
    return async (url: string, options: RequestInit = {}): Promise<Response> => {
      const validation = this.validateUrl(url, requestId);
      
      if (!validation.allowed) {
        throw new Error(`SSRF Protection: ${validation.reason}`);
      }

      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), this.config.requestTimeout);

      try {
        const response = await fetch(validation.sanitizedUrl!, {
          ...options,
          signal: controller.signal,
          redirect: 'manual' // Handle redirects manually for tracking
        });

        // Handle redirects with tracking
        if (response.status >= 300 && response.status < 400) {
          const location = response.headers.get('location');
          
          if (location && this.trackRedirect(url)) {
            // Recursively validate and fetch redirect
            return this.createProtectedFetch(requestId)(location, options);
          } else {
            throw new Error('Too many redirects or invalid redirect location');
          }
        }

        // Check response size if readable stream
        if (response.body) {
          const contentLength = response.headers.get('content-length');
          if (contentLength && parseInt(contentLength) > this.config.maxResponseSize) {
            throw new Error(`Response too large: ${contentLength} bytes`);
          }
        }

        return response;

      } finally {
        clearTimeout(timeoutId);
        this.clearRedirectTracking(url);
      }
    };
  }

  /**
   * Update configuration
   */
  updateConfig(newConfig: Partial<SSRFConfig>): void {
    this.config = { ...this.config, ...newConfig };
    productionLogger.info('SSRF Guard configuration updated', {
      allowedDomains: this.config.allowedDomains.length
    });
  }

  /**
   * Get current configuration
   */
  getConfig(): Readonly<SSRFConfig> {
    return { ...this.config };
  }
}

// Global instance
export const ssrfGuard = new SSRFGuard();

// Convenience function
export const protectedFetch = ssrfGuard.createProtectedFetch();