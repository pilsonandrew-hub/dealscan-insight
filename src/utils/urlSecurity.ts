/**
 * URL Security & SSRF Protection Utilities
 * Enterprise-grade URL validation and security checks
 */

// Private IP ranges (RFC 1918, RFC 4193, RFC 3927)
const PRIVATE_IP_RANGES = [
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

// Enterprise-approved auction domains
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
  'bidspotter.com',
  'purplewave.com',
  'jjkane.com',
  
  // Vehicle auction sites
  'iaai.com',
  'copart.com',
  'manheim.com',
  'adesa.com',
  
  // State auction portals
  'california.gov',
  'texas.gov',
  'florida.gov',
  'newyork.gov',
]);

/**
 * Check if an IP address or hostname is internal/private
 */
export function isInternalIP(hostname: string): boolean {
  // Handle localhost variations
  if (['localhost', '127.0.0.1', '::1'].includes(hostname.toLowerCase())) {
    return true;
  }

  // Check private IP ranges
  return PRIVATE_IP_RANGES.some(range => range.test(hostname));
}

/**
 * Validate and sanitize URL for SSRF protection
 * Returns the sanitized URL if valid, null if invalid
 */
export function validateAndSanitizeUrl(url: string): string | null {
  try {
    const parsed = new URL(url);
    
    // Only allow HTTP/HTTPS protocols
    if (!['http:', 'https:'].includes(parsed.protocol)) {
      return null;
    }

    const hostname = parsed.hostname.toLowerCase();
    
    // Check if domain is in allowlist
    const isAllowed = ALLOWED_DOMAINS.has(hostname) || 
                     Array.from(ALLOWED_DOMAINS).some(domain => 
                       hostname.endsWith('.' + domain));
    
    if (!isAllowed) {
      return null;
    }

    // Check for private/internal IPs
    if (isInternalIP(hostname)) {
      return null;
    }

    // Remove credentials from URL for safety
    parsed.username = '';
    parsed.password = '';

    return parsed.href;

  } catch (error) {
    // Invalid URL format
    return null;
  }
}

/**
 * Safe fetch with SSRF protection
 */
export async function safeFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const validatedUrl = validateAndSanitizeUrl(url);
  
  if (!validatedUrl) {
    throw new Error('SSRF Protection: URL validation failed');
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10000); // 10s timeout

  try {
    const response = await fetch(validatedUrl, {
      ...options,
      signal: controller.signal,
      headers: {
        'User-Agent': 'DealerScope-Enterprise/1.0',
        ...options.headers,
      },
    });

    return response;

  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      throw new Error('Request timeout after 10 seconds');
    }
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

/**
 * Add domain to allowlist (for testing/configuration)
 */
export function addAllowedDomain(domain: string): void {
  ALLOWED_DOMAINS.add(domain.toLowerCase());
}

/**
 * Remove domain from allowlist
 */
export function removeAllowedDomain(domain: string): void {
  ALLOWED_DOMAINS.delete(domain.toLowerCase());
}

/**
 * Get current allowlist (for debugging)
 */
export function getAllowedDomains(): string[] {
  return Array.from(ALLOWED_DOMAINS);
}