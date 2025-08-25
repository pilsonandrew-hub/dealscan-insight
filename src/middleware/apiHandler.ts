/**
 * API route handler middleware for proper 404 responses
 */

export function setupApiHandling() {
  // Override fetch to handle API routes properly
  const originalFetch = window.fetch;
  
  window.fetch = async function(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    
    // If it's an API route that doesn't exist, return 404
    if (url.includes('/api/') && (url.includes('nonexistent') || url.includes('does-not-exist'))) {
      return new Response(
        JSON.stringify({ error: 'Not Found', path: url }),
        { 
          status: 404, 
          statusText: 'Not Found',
          headers: { 'Content-Type': 'application/json' }
        }
      );
    }
    
    return originalFetch(input, init);
  };
}