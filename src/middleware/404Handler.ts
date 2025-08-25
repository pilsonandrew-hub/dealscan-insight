/**
 * 404 Handler Middleware - Phase 1 Core Fix
 * Ensures unknown routes return proper 404 JSON responses
 */

import productionLogger from '@/utils/productionLogger';

interface NotFoundResponse {
  error: string;
  message: string;
  statusCode: number;
  timestamp: string;
  path: string;
}

/**
 * Create standardized 404 response
 */
export function create404Response(path: string, message?: string): NotFoundResponse {
  return {
    error: 'Not Found',
    message: message || `The requested resource '${path}' was not found`,
    statusCode: 404,
    timestamp: new Date().toISOString(),
    path
  };
}

/**
 * Handle API 404 responses
 */
export function handleAPI404(path: string): Response {
  const response = create404Response(path, `API endpoint '${path}' not found`);
  
  productionLogger.warn('API 404 response', {
    path,
    type: 'api_404'
  });
  
  return new Response(JSON.stringify(response), {
    status: 404,
    headers: {
      'Content-Type': 'application/json',
      'Cache-Control': 'no-cache'
    }
  });
}

/**
 * Handle frontend 404 responses (for SPAs)
 */
export function handleFrontend404(path: string): Response {
  const response = create404Response(path, `Page '${path}' not found`);
  
  productionLogger.warn('Frontend 404 response', {
    path,
    type: 'frontend_404'
  });
  
  // For SPAs, we might want to return the index.html instead
  // But for API consistency, return JSON
  return new Response(JSON.stringify(response), {
    status: 404,
    headers: {
      'Content-Type': 'application/json',
      'Cache-Control': 'no-cache'
    }
  });
}

/**
 * Middleware function for handling 404s in Express-like environments
 */
export function notFoundMiddleware(req: Request): Response {
  const url = new URL(req.url);
  const path = url.pathname;
  
  // Determine if this is an API request
  const isAPIRequest = path.startsWith('/api/');
  
  if (isAPIRequest) {
    return handleAPI404(path);
  } else {
    return handleFrontend404(path);
  }
}

/**
 * React Router 404 component props
 */
export interface NotFoundProps {
  path?: string;
}

/**
 * Utility to check if a route should return 404
 */
export function shouldReturn404(path: string, validRoutes: string[]): boolean {
  // Exact matches
  if (validRoutes.includes(path)) {
    return false;
  }
  
  // Pattern matches (for dynamic routes)
  for (const route of validRoutes) {
    if (route.includes(':') || route.includes('*')) {
      // Simple pattern matching - could be enhanced
      const pattern = route.replace(/:[^/]+/g, '[^/]+').replace(/\*/g, '.*');
      const regex = new RegExp(`^${pattern}$`);
      if (regex.test(path)) {
        return false;
      }
    }
  }
  
  return true;
}

/**
 * Log 404 events for monitoring
 */
export function log404Event(path: string, userAgent?: string, referer?: string): void {
  productionLogger.warn('404 event', {
    path,
    user_agent: userAgent,
    referer,
    type: '404_event'
  });
}

/**
 * Get 404 statistics for monitoring
 */
let notFoundStats = {
  total: 0,
  api: 0,
  frontend: 0,
  lastReset: Date.now()
};

export function increment404Stats(type: 'api' | 'frontend'): void {
  notFoundStats.total++;
  notFoundStats[type]++;
}

export function get404Stats(): typeof notFoundStats {
  return { ...notFoundStats };
}

export function reset404Stats(): void {
  notFoundStats = {
    total: 0,
    api: 0,
    frontend: 0,
    lastReset: Date.now()
  };
}

/**
 * Express.js compatible 404 handler
 */
export function expressNotFoundHandler(req: any, res: any, next: any): void {
  const path = req.path || req.url;
  const response = create404Response(path);
  
  increment404Stats(path.startsWith('/api/') ? 'api' : 'frontend');
  log404Event(path, req.get('User-Agent'), req.get('Referer'));
  
  res.status(404).json(response);
}

/**
 * Fetch API compatible 404 handler
 */
export function fetchNotFoundHandler(path: string): Response {
  const response = create404Response(path);
  
  increment404Stats(path.startsWith('/api/') ? 'api' : 'frontend');
  log404Event(path);
  
  return new Response(JSON.stringify(response), {
    status: 404,
    headers: {
      'Content-Type': 'application/json'
    }
  });
}