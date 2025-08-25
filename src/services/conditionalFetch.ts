import crypto from 'crypto';
import SSRFGuard from '@/utils/ssrfGuard';

export interface ConditionalFetchResult {
  notModified?: boolean;
  status?: number;
  body?: string;
  etag?: string;
  lastModified?: string;
  contentHash?: string;
  error?: string;
}

export interface CacheHeaders {
  etag?: string;
  lastModified?: string;
}

/**
 * HTTP fetch with conditional GET support and content deduplication
 * Implements If-None-Match and If-Modified-Since headers for cache efficiency
 */
export class ConditionalFetcher {
  private static normalizeHtml(html: string): string {
    // Normalize whitespace and remove timestamps for content hashing
    return html
      .replace(/\s+/g, ' ')
      .replace(/<!--.*?-->/g, '') // Remove comments
      .replace(/\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/g, '') // Remove timestamps
      .trim();
  }

  private static generateContentHash(content: string): string {
    const normalized = this.normalizeHtml(content);
    return crypto.createHash('sha256').update(normalized, 'utf8').digest('hex');
  }

  /**
   * Fetch with conditional GET headers and content deduplication
   */
  static async fetchConditional(
    url: string, 
    cacheHeaders?: CacheHeaders,
    options: RequestInit = {}
  ): Promise<ConditionalFetchResult> {
    try {
      // Build conditional headers
      const headers: Record<string, string> = {
        'User-Agent': 'DealerScope-Bot/1.0',
        ...options.headers as Record<string, string>
      };

      if (cacheHeaders?.etag) {
        headers['If-None-Match'] = cacheHeaders.etag;
      }

      if (cacheHeaders?.lastModified) {
        headers['If-Modified-Since'] = cacheHeaders.lastModified;
      }

      // Use SSRF-protected fetch
      const response = await SSRFGuard.safeFetch(url, {
        ...options,
        headers
      });

      // Handle 304 Not Modified
      if (response.status === 304) {
        return { notModified: true };
      }

      // Handle other non-success responses
      if (!response.ok) {
        return {
          status: response.status,
          error: `HTTP ${response.status}: ${response.statusText}`
        };
      }

      // Read response with size protection
      const body = await SSRFGuard.readSafeResponse(response);
      
      // Generate content hash for deduplication
      const contentHash = this.generateContentHash(body);

      return {
        status: response.status,
        body,
        etag: response.headers.get('etag') || undefined,
        lastModified: response.headers.get('last-modified') || undefined,
        contentHash
      };

    } catch (error) {
      return {
        error: error instanceof Error ? error.message : 'Unknown fetch error'
      };
    }
  }

  /**
   * Check if content has changed based on hash comparison
   */
  static hasContentChanged(
    newHash: string, 
    existingHash?: string
  ): boolean {
    if (!existingHash) return true;
    return newHash !== existingHash;
  }

  /**
   * Extract cache-relevant headers from a previous response
   */
  static extractCacheHeaders(
    etag?: string | null,
    lastModified?: string | null
  ): CacheHeaders {
    return {
      etag: etag || undefined,
      lastModified: lastModified || undefined
    };
  }
}

export default ConditionalFetcher;