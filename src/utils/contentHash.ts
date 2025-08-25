/**
 * Content Hash Utilities - Bandwidth killer feature
 * Compute stable hashes for deduplication and conditional GET
 */

import { logger } from '@/lib/logger';

/**
 * Compute stable content hash for vehicle data
 * Formula: sha256(year||vin||price||mileage||title||location)
 */
export async function contentHash(data: Record<string, unknown>): Promise<string> {
  try {
    // Extract key fields in stable order
    const keyFields = [
      'year',
      'vin', 
      'make',
      'model',
      'price',
      'current_bid',
      'mileage',
      'title',
      'location',
      'auction_end',
      'condition',
      'description'
    ];

    // Build stable string representation
    const stableData: Record<string, string> = {};
    for (const field of keyFields) {
      const value = data[field];
      if (value !== undefined && value !== null) {
        stableData[field] = String(value).trim().toLowerCase();
      }
    }

    // Create deterministic JSON string
    const stableString = JSON.stringify(stableData, Object.keys(stableData).sort());
    
    // Compute SHA-256 hash
    const encoder = new TextEncoder();
    const dataBuffer = encoder.encode(stableString);
    const hashBuffer = await crypto.subtle.digest('SHA-256', dataBuffer);
    
    // Convert to hex string
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    const hashHex = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
    
    logger.debug('Content hash computed', {
      fields: Object.keys(stableData),
      hashLength: hashHex.length,
      hash: hashHex.substring(0, 8) + '...' // Log first 8 chars only
    });
    
    return hashHex;
  } catch (error) {
    logger.error('Failed to compute content hash', { 
      dataType: typeof data,
      dataLength: JSON.stringify(data).length 
    }, error as Error);
    throw new Error('Content hash computation failed');
  }
}

/**
 * Compute hash for HTML content (for page change detection)
 */
export async function htmlContentHash(html: string): Promise<string> {
  try {
    // Normalize HTML content
    const normalized = normalizeHtml(html);
    
    const encoder = new TextEncoder();
    const dataBuffer = encoder.encode(normalized);
    const hashBuffer = await crypto.subtle.digest('SHA-256', dataBuffer);
    
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    const hashHex = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
    
    return hashHex;
  } catch (error) {
    logger.error('Failed to compute HTML content hash', error);
    throw new Error('HTML content hash computation failed');
  }
}

/**
 * Normalize HTML content for stable hashing
 */
function normalizeHtml(html: string): string {
  return html
    // Remove timestamps and dynamic content
    .replace(/\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[Z\d\-\+:.]*/g, 'TIMESTAMP')
    .replace(/\d{13,}/g, 'TIMESTAMP_MS') // Millisecond timestamps
    .replace(/\d{10}/g, 'TIMESTAMP_S')   // Second timestamps
    
    // Remove session IDs and tokens
    .replace(/[a-f0-9]{32,}/gi, 'TOKEN')
    .replace(/sess_[a-zA-Z0-9]+/g, 'SESSION')
    .replace(/token_[a-zA-Z0-9]+/g, 'TOKEN')
    
    // Remove dynamic IDs
    .replace(/id=["'][^"']*["']/g, 'id="DYNAMIC"')
    .replace(/data-id=["'][^"']*["']/g, 'data-id="DYNAMIC"')
    
    // Normalize whitespace
    .replace(/\s+/g, ' ')
    .trim()
    
    // Remove common dynamic elements
    .replace(/<script[^>]*>.*?<\/script>/gis, '')
    .replace(/<style[^>]*>.*?<\/style>/gis, '')
    .replace(/<!--.*?-->/gs, '')
    
    // Remove ads and tracking
    .replace(/google-?ads?/gi, 'ADS')
    .replace(/facebook|twitter|linkedin/gi, 'SOCIAL')
    .replace(/analytics?/gi, 'ANALYTICS');
}

/**
 * Compare two content hashes
 */
export function hashesEqual(hash1: string, hash2: string): boolean {
  return hash1 === hash2;
}

/**
 * Generate ETag from content hash
 */
export function generateETag(hash: string): string {
  return `"${hash.substring(0, 16)}"`;
}

/**
 * Parse ETag to get hash
 */
export function parseETag(etag: string): string | null {
  const match = etag.match(/^"([a-f0-9]+)"$/);
  return match ? match[1] : null;
}

/**
 * Check if content has changed using conditional headers
 */
export interface ConditionalCheckResult {
  hasChanged: boolean;
  shouldFetch: boolean;
  reason: string;
}

export function checkConditionalHeaders(
  currentHash: string,
  headers: {
    'if-none-match'?: string;
    'if-modified-since'?: string;
    'last-modified'?: string;
    'etag'?: string;
  }
): ConditionalCheckResult {
  // Check ETag
  if (headers['if-none-match'] && headers['etag']) {
    const clientETag = parseETag(headers['if-none-match']);
    const serverETag = parseETag(headers['etag']);
    
    if (clientETag && serverETag && clientETag === serverETag) {
      return {
        hasChanged: false,
        shouldFetch: false,
        reason: 'ETag match - content unchanged'
      };
    }
  }

  // Check Last-Modified
  if (headers['if-modified-since'] && headers['last-modified']) {
    const clientTime = new Date(headers['if-modified-since']).getTime();
    const serverTime = new Date(headers['last-modified']).getTime();
    
    if (serverTime <= clientTime) {
      return {
        hasChanged: false,
        shouldFetch: false,
        reason: 'Not modified since last fetch'
      };
    }
  }

  return {
    hasChanged: true,
    shouldFetch: true,
    reason: 'Content may have changed'
  };
}

/**
 * Deduplicate array of items by content hash
 */
export function deduplicateByHash<T extends { content_hash?: string }>(
  items: T[]
): { unique: T[]; duplicates: T[]; duplicateCount: number } {
  const seen = new Set<string>();
  const unique: T[] = [];
  const duplicates: T[] = [];

  for (const item of items) {
    if (!item.content_hash) {
      unique.push(item);
      continue;
    }

    if (seen.has(item.content_hash)) {
      duplicates.push(item);
    } else {
      seen.add(item.content_hash);
      unique.push(item);
    }
  }

  logger.info('Deduplication completed', {
    total: items.length,
    unique: unique.length,
    duplicates: duplicates.length,
    dedupeRate: ((duplicates.length / items.length) * 100).toFixed(1) + '%'
  });

  return {
    unique,
    duplicates,
    duplicateCount: duplicates.length
  };
}