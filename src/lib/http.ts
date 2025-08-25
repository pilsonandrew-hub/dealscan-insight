/**
 * Unified HTTP Client with Error Handling
 * Replaces all ad-hoc fetch calls with standardized error handling
 */

export class ApiError extends Error {
  status?: number;
  code?: string;
  cause?: unknown;
  url?: string;

  constructor(message: string, options: Partial<ApiError> = {}) {
    super(message);
    this.name = 'ApiError';
    Object.assign(this, options);
  }
}

interface HttpOptions extends RequestInit {
  timeout?: number;
  retries?: number;
  retryDelay?: number;
}

/**
 * Production-grade HTTP client with SSRF protection, retries, and timeouts
 */
export async function http<T>(url: string, options: HttpOptions = {}): Promise<T> {
  const {
    timeout = 10000,
    retries = 2,
    retryDelay = 1000,
    ...fetchOptions
  } = options;

  // SSRF Protection
  validateUrl(url);

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);

  const fetchWithTimeout = async (): Promise<Response> => {
    try {
      const response = await fetch(url, {
        ...fetchOptions,
        signal: controller.signal,
        redirect: "manual"
      });
      return response;
    } finally {
      clearTimeout(timeoutId);
    }
  };

  let lastError: Error | null = null;

  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const response = await fetchWithTimeout();

      if (!response.ok) {
        const errorBody = await safeBody(response);
        throw new ApiError(
          `HTTP ${response.status}: ${response.statusText}`,
          {
            status: response.status,
            cause: errorBody,
            url
          }
        );
      }

      const data = await response.json();
      return data as T;
    } catch (error) {
      lastError = error as Error;

      // Don't retry on client errors (4xx) or AbortError
      if (error instanceof ApiError && error.status && error.status < 500) {
        throw error;
      }

      if (error instanceof Error && error.name === 'AbortError') {
        throw new ApiError('Request timeout', { cause: error, url });
      }

      // Wait before retrying
      if (attempt < retries) {
        await new Promise(resolve => setTimeout(resolve, retryDelay * (attempt + 1)));
      }
    }
  }

  throw new ApiError(
    `Request failed after ${retries + 1} attempts`,
    { cause: lastError, url }
  );
}

/**
 * Safe response body parsing
 */
async function safeBody(response: Response): Promise<unknown> {
  try {
    const text = await response.text();
    try {
      return JSON.parse(text);
    } catch {
      return text;
    }
  } catch {
    return null;
  }
}

/**
 * SSRF Protection - validates URLs to prevent internal network access
 */
function validateUrl(url: string): void {
  try {
    const urlObj = new URL(url);
    
    // Block internal networks
    const hostname = urlObj.hostname.toLowerCase();
    
    // Block localhost variations
    if (hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '::1') {
      throw new Error('Access to localhost is not allowed');
    }

    // Block private IP ranges
    if (isPrivateIP(hostname)) {
      throw new Error('Access to private IP ranges is not allowed');
    }

    // Block file:// protocol
    if (urlObj.protocol === 'file:') {
      throw new Error('File protocol is not allowed');
    }

    // Only allow HTTP/HTTPS
    if (!['http:', 'https:'].includes(urlObj.protocol)) {
      throw new Error('Only HTTP and HTTPS protocols are allowed');
    }

  } catch (error) {
    if (error instanceof Error) {
      throw new ApiError(`Invalid URL: ${error.message}`, { url });
    }
    throw new ApiError('Invalid URL format', { url });
  }
}

/**
 * Check if hostname is a private IP address
 */
function isPrivateIP(hostname: string): boolean {
  // Simple regex check for common private IP ranges
  const privateRanges = [
    /^10\./,                    // 10.0.0.0/8
    /^172\.(1[6-9]|2[0-9]|3[01])\./, // 172.16.0.0/12
    /^192\.168\./,              // 192.168.0.0/16
    /^169\.254\./,              // 169.254.0.0/16 (link-local)
  ];

  return privateRanges.some(range => range.test(hostname));
}

/**
 * Typed GET request
 */
export async function httpGet<T>(url: string, options?: Omit<HttpOptions, 'method'>): Promise<T> {
  return http<T>(url, { ...options, method: 'GET' });
}

/**
 * Typed POST request
 */
export async function httpPost<T>(
  url: string, 
  data?: unknown, 
  options?: Omit<HttpOptions, 'method' | 'body'>
): Promise<T> {
  return http<T>(url, {
    ...options,
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers
    },
    body: data ? JSON.stringify(data) : undefined
  });
}

/**
 * Typed PUT request
 */
export async function httpPut<T>(
  url: string, 
  data?: unknown, 
  options?: Omit<HttpOptions, 'method' | 'body'>
): Promise<T> {
  return http<T>(url, {
    ...options,
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers
    },
    body: data ? JSON.stringify(data) : undefined
  });
}

/**
 * Typed DELETE request
 */
export async function httpDelete<T>(url: string, options?: Omit<HttpOptions, 'method'>): Promise<T> {
  return http<T>(url, { ...options, method: 'DELETE' });
}