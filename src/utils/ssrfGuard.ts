/**
 * SSRF Protection Utilities
 * Prevents Server-Side Request Forgery by validating URLs and blocking private networks
 */

// Private network ranges (RFC 1918, RFC 4193, RFC 3927)
const PRIVATE_RANGES = [
  /^127\./,                    // Loopback
  /^10\./,                     // Private Class A
  /^172\.(1[6-9]|2[0-9]|3[0-1])\./,  // Private Class B
  /^192\.168\./,               // Private Class C
  /^169\.254\./,               // Link-local
  /^::1$/,                     // IPv6 loopback
  /^fe80:/,                    // IPv6 link-local
  /^fc00:/,                    // IPv6 unique local
  /^fd00:/,                    // IPv6 unique local
];

// Allowed domains for scraping (production allowlist)
const ALLOWED_DOMAINS = new Set([
  // Federal auction sites
  'gsaauctions.gov',
  'govdeals.com',
  'publicsurplus.com',
  'municibid.com',
  'allsurplus.com',
  
  // Commercial auction sites
  'hibid.com',
  'proxibid.com',
  'equipmentfacts.com',
  'govplanet.com',
  'govliquidation.com',
  'usgovbid.com',
  
  // Vehicle auction sites
  'iaai.com',
  'copart.com',
  'manheim.com',
  'adesa.com',
  
  // State auction portals (examples - expand as needed)
  'california.gov',
  'texas.gov',
  'florida.gov',
  'newyork.gov',
]);

export interface SSRFValidationResult {
  allowed: boolean;
  reason?: string;
  sanitizedUrl?: string;
}

export class SSRFGuard {
  private static readonly MAX_REDIRECTS = 3;
  private static readonly TIMEOUT_MS = 10000;
  private static readonly MAX_RESPONSE_SIZE = 10 * 1024 * 1024; // 10MB

  /**
   * Validates a URL for SSRF protection
   */
  static validateUrl(url: string): SSRFValidationResult {
    try {
      const parsed = new URL(url);
      
      // Only allow HTTP/HTTPS
      if (!['http:', 'https:'].includes(parsed.protocol)) {
        return {
          allowed: false,
          reason: `Protocol ${parsed.protocol} not allowed`
        };
      }

      // Check if domain is in allowlist
      const hostname = parsed.hostname.toLowerCase();
      const isAllowed = ALLOWED_DOMAINS.has(hostname) || 
                       Array.from(ALLOWED_DOMAINS).some(domain => 
                         hostname.endsWith('.' + domain));

      if (!isAllowed) {
        return {
          allowed: false,
          reason: `Domain ${hostname} not in allowlist`
        };
      }

      // Check for private IP ranges
      if (this.isPrivateIP(hostname)) {
        return {
          allowed: false,
          reason: `Private IP or internal network access blocked: ${hostname}`
        };
      }

      // Sanitize URL (remove auth, normalize)
      const sanitized = new URL(parsed.href);
      sanitized.username = '';
      sanitized.password = '';

      return {
        allowed: true,
        sanitizedUrl: sanitized.href
      };

    } catch (error) {
      return {
        allowed: false,
        reason: `Invalid URL: ${error instanceof Error ? error.message : 'Unknown error'}`
      };
    }
  }

  /**
   * Checks if a hostname resolves to a private IP
   */
  private static isPrivateIP(hostname: string): boolean {
    // Check if hostname is already an IP
    const ipv4Regex = /^(\d{1,3}\.){3}\d{1,3}$/;
    const ipv6Regex = /^([0-9a-f]{0,4}:){2,7}[0-9a-f]{0,4}$/i;

    if (ipv4Regex.test(hostname) || ipv6Regex.test(hostname)) {
      return PRIVATE_RANGES.some(range => range.test(hostname));
    }

    // For domain names, we'll rely on DNS resolution in the edge function
    // This client-side check focuses on obvious private addresses
    return false;
  }

  /**
   * Safe fetch with SSRF protection and resource limits
   */
  static async safeFetch(url: string, options: RequestInit = {}): Promise<Response> {
    const validation = this.validateUrl(url);
    
    if (!validation.allowed) {
      throw new Error(`SSRF Protection: ${validation.reason}`);
    }

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.TIMEOUT_MS);

    try {
      const response = await fetch(validation.sanitizedUrl!, {
        ...options,
        signal: controller.signal,
        redirect: 'manual', // Handle redirects manually for validation
        headers: {
          'User-Agent': 'DealerScope-Bot/1.0',
          ...options.headers,
        },
      });

      // Handle redirects manually to validate each redirect URL
      if (response.status >= 300 && response.status < 400) {
        const location = response.headers.get('location');
        if (!location) {
          throw new Error('Redirect without location header');
        }

        const redirectValidation = this.validateUrl(location);
        if (!redirectValidation.allowed) {
          throw new Error(`Redirect blocked: ${redirectValidation.reason}`);
        }

        // Limit redirect chains
        const redirectCount = Number(options.headers?.['X-Redirect-Count'] || 0);
        if (redirectCount >= this.MAX_REDIRECTS) {
          throw new Error('Too many redirects');
        }

        return this.safeFetch(redirectValidation.sanitizedUrl!, {
          ...options,
          headers: {
            ...options.headers,
            'X-Redirect-Count': String(redirectCount + 1),
          },
        });
      }

      return response;

    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        throw new Error(`Request timeout after ${this.TIMEOUT_MS}ms`);
      }
      throw error;
    } finally {
      clearTimeout(timeout);
    }
  }

  /**
   * Validates and reads response with size limits
   */
  static async readSafeResponse(response: Response): Promise<string> {
    const contentLength = response.headers.get('content-length');
    if (contentLength && parseInt(contentLength) > this.MAX_RESPONSE_SIZE) {
      throw new Error(`Response too large: ${contentLength} bytes`);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error('No response body');
    }

    let bytesRead = 0;
    const chunks: Uint8Array[] = [];

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        bytesRead += value.length;
        if (bytesRead > this.MAX_RESPONSE_SIZE) {
          throw new Error(`Response too large: exceeded ${this.MAX_RESPONSE_SIZE} bytes`);
        }

        chunks.push(value);
      }

      const combined = new Uint8Array(bytesRead);
      let offset = 0;
      for (const chunk of chunks) {
        combined.set(chunk, offset);
        offset += chunk.length;
      }

      return new TextDecoder().decode(combined);

    } finally {
      reader.releaseLock();
    }
  }

  /**
   * Add a domain to the allowlist (for testing/configuration)
   */
  static addAllowedDomain(domain: string): void {
    ALLOWED_DOMAINS.add(domain.toLowerCase());
  }

  /**
   * Remove a domain from the allowlist
   */
  static removeAllowedDomain(domain: string): void {
    ALLOWED_DOMAINS.delete(domain.toLowerCase());
  }

  /**
   * Get current allowlist (for debugging)
   */
  static getAllowedDomains(): string[] {
    return Array.from(ALLOWED_DOMAINS);
  }
}

export default SSRFGuard;