/**
 * Production API route handler with 404, compression, and monitoring
 */

import { logger } from '@/utils/productionLogger';
import { apiRateLimiter } from '@/utils/rateLimiter';
import { productionCache } from '@/utils/productionCache';

export interface APIResponse<T = any> {
  data?: T;
  error?: string;
  message?: string;
  timestamp: string;
  requestId: string;
}

export interface APIError extends Error {
  statusCode: number;
  code?: string;
}

/**
 * Create standardized API response
 */
export function createAPIResponse<T>(
  data?: T,
  error?: string,
  message?: string,
  requestId: string = generateRequestId()
): APIResponse<T> {
  return {
    data,
    error,
    message,
    timestamp: new Date().toISOString(),
    requestId
  };
}

/**
 * Create API error response
 */
export function createAPIError(
  statusCode: number,
  message: string,
  code?: string,
  requestId: string = generateRequestId()
): Response {
  const errorResponse = createAPIResponse(undefined, message, undefined, requestId);
  
  logger.warn('API error response', {
    statusCode,
    message,
    code,
    requestId
  });

  return new Response(JSON.stringify(errorResponse), {
    status: statusCode,
    headers: {
      'Content-Type': 'application/json',
      'X-Request-ID': requestId
    }
  });
}

/**
 * Handle API 404 responses
 */
export function handle404(path: string, requestId: string = generateRequestId()): Response {
  logger.info('API 404 response', { path, requestId });
  
  return createAPIError(404, `Endpoint not found: ${path}`, 'NOT_FOUND', requestId);
}

/**
 * Handle API route with error handling, rate limiting, and caching
 */
export async function handleAPIRoute(
  request: Request,
  handler: (request: Request) => Promise<Response>,
  options: {
    enableRateLimit?: boolean;
    enableCache?: boolean;
    cacheKey?: (request: Request) => string;
    cacheTTL?: number;
  } = {}
): Promise<Response> {
  const requestId = generateRequestId();
  const startTime = Date.now();
  
  try {
    // Add request ID to headers
    const url = new URL(request.url);
    logger.info('API request started', {
      method: request.method,
      path: url.pathname,
      requestId
    });

    // Rate limiting
    if (options.enableRateLimit) {
      const clientKey = getClientKey(request);
      const rateLimitResult = await apiRateLimiter.checkLimit(clientKey);
      
      if (!rateLimitResult.allowed) {
        return new Response(
          JSON.stringify(createAPIResponse(
            undefined, 
            'Rate limit exceeded', 
            'Please wait before making more requests',
            requestId
          )),
          {
            status: 429,
            headers: {
              'Content-Type': 'application/json',
              'X-Request-ID': requestId,
              'X-RateLimit-Limit': '100',
              'X-RateLimit-Remaining': rateLimitResult.tokensRemaining.toString(),
              'X-RateLimit-Reset': Math.ceil(rateLimitResult.resetTime / 1000).toString(),
              'Retry-After': rateLimitResult.retryAfter ? Math.ceil(rateLimitResult.retryAfter / 1000).toString() : '60'
            }
          }
        );
      }
    }

    // Caching for GET requests
    if (options.enableCache && request.method === 'GET' && options.cacheKey) {
      const cacheKey = options.cacheKey(request);
      const ifNoneMatch = request.headers.get('If-None-Match');
      
      const conditionalResult = productionCache.checkConditionalGet(cacheKey, ifNoneMatch || undefined);
      if (conditionalResult.hit) {
        logger.debug('Cache conditional GET hit', { cacheKey, requestId });
        return new Response(null, {
          status: 304,
          headers: {
            'ETag': conditionalResult.etag || '',
            'X-Request-ID': requestId,
            'Cache-Control': 'public, max-age=300'
          }
        });
      }
    }

    // Execute handler
    const response = await handler(request);
    
    // Add standard headers
    response.headers.set('X-Request-ID', requestId);
    response.headers.set('X-Response-Time', `${Date.now() - startTime}ms`);
    
    // Add cache headers for successful responses
    if (response.status === 200 && request.method === 'GET') {
      response.headers.set('Cache-Control', 'public, max-age=300, s-maxage=600');
    }

    logger.info('API request completed', {
      method: request.method,
      path: url.pathname,
      status: response.status,
      duration: Date.now() - startTime,
      requestId
    });

    return response;

  } catch (error) {
    const duration = Date.now() - startTime;
    logger.error('API request failed', error as Error, {
      method: request.method,
      path: new URL(request.url).pathname,
      duration,
      requestId
    });

    // Return appropriate error response
    if (error instanceof Error && 'statusCode' in error) {
      const apiError = error as APIError;
      return createAPIError(apiError.statusCode, apiError.message, apiError.code, requestId);
    }

    return createAPIError(500, 'Internal server error', 'INTERNAL_ERROR', requestId);
  }
}

/**
 * Generate unique request ID
 */
function generateRequestId(): string {
  return `req_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
}

/**
 * Extract client key for rate limiting
 */
function getClientKey(request: Request): string {
  // In a real app, you might use IP address, user ID, API key, etc.
  const userAgent = request.headers.get('User-Agent') || 'unknown';
  const origin = request.headers.get('Origin') || 'unknown';
  return `${origin}:${userAgent.slice(0, 50)}`;
}

/**
 * Setup API route handling with 404 fallback
 */
export function setupAPIRouteHandling() {
  // This would be used in a service worker or edge function
  // For now, we'll enhance the existing fetch override
  const originalFetch = window.fetch;
  
  window.fetch = async function(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    
    // Only handle API routes
    if (!url.includes('/api/')) {
      return originalFetch(input, init);
    }

    try {
      const response = await originalFetch(input, init);
      
      // If response is 404 and it's an API route, return proper JSON 404
      if (response.status === 404) {
        const path = new URL(url).pathname;
        return handle404(path);
      }
      
      return response;
    } catch (error) {
      logger.error('Fetch error for API route', error as Error, { url });
      return createAPIError(503, 'Service unavailable', 'FETCH_ERROR');
    }
  };
}

// Compression helper (would be used server-side)
export function shouldCompress(response: Response): boolean {
  const contentType = response.headers.get('Content-Type') || '';
  return contentType.includes('application/json') || 
         contentType.includes('text/') ||
         contentType.includes('application/javascript');
}