/**
 * Client-side rate limiting utilities
 * Inspired by the slowapi middleware in the bootstrap script
 */

export interface RateLimitConfig {
  maxRequests: number;
  windowMs: number;
  identifier?: string;
}

export interface RateLimitState {
  requests: number[];
  blocked: boolean;
  resetTime: number;
}

class RateLimiter {
  private limits: Map<string, RateLimitState> = new Map();
  private defaultConfig: RateLimitConfig = {
    maxRequests: 60,
    windowMs: 60000, // 1 minute
  };

  // Check if request is allowed
  isAllowed(key: string, config?: Partial<RateLimitConfig>): boolean {
    const finalConfig = { ...this.defaultConfig, ...config };
    const now = Date.now();
    
    if (!this.limits.has(key)) {
      this.limits.set(key, {
        requests: [],
        blocked: false,
        resetTime: now + finalConfig.windowMs
      });
    }

    const state = this.limits.get(key)!;
    
    // Clean old requests
    state.requests = state.requests.filter(time => 
      now - time < finalConfig.windowMs
    );

    // Check if within limit
    if (state.requests.length >= finalConfig.maxRequests) {
      state.blocked = true;
      state.resetTime = now + finalConfig.windowMs;
      return false;
    }

    // Record this request
    state.requests.push(now);
    state.blocked = false;
    
    return true;
  }

  // Get current rate limit status
  getStatus(key: string): {
    remaining: number;
    resetTime: number;
    blocked: boolean;
    total: number;
  } {
    const state = this.limits.get(key);
    if (!state) {
      return {
        remaining: this.defaultConfig.maxRequests,
        resetTime: Date.now() + this.defaultConfig.windowMs,
        blocked: false,
        total: this.defaultConfig.maxRequests
      };
    }

    const remaining = Math.max(0, this.defaultConfig.maxRequests - state.requests.length);
    
    return {
      remaining,
      resetTime: state.resetTime,
      blocked: state.blocked,
      total: this.defaultConfig.maxRequests
    };
  }

  // Wait until rate limit resets
  async waitForReset(key: string): Promise<void> {
    const state = this.limits.get(key);
    if (!state || !state.blocked) return;

    const waitTime = Math.max(0, state.resetTime - Date.now());
    if (waitTime > 0) {
      await new Promise(resolve => setTimeout(resolve, waitTime));
    }
  }

  // Clear rate limit for key
  reset(key: string) {
    this.limits.delete(key);
  }

  // Clear all rate limits
  resetAll() {
    this.limits.clear();
  }

  // Cleanup expired entries
  cleanup() {
    const now = Date.now();
    
    this.limits.forEach((state, key) => {
      // Clean old requests
      state.requests = state.requests.filter(time => 
        now - time < this.defaultConfig.windowMs
      );
      
      // Remove empty entries
      if (state.requests.length === 0 && !state.blocked) {
        this.limits.delete(key);
      }
    });
  }
}

// Global rate limiter instance
export const rateLimiter = new RateLimiter();

// Auto-cleanup every 2 minutes
setInterval(() => {
  rateLimiter.cleanup();
}, 120000);

// Rate limiting decorator for functions
export function rateLimit(config: RateLimitConfig) {
  return function<T extends (...args: any[]) => any>(
    target: any,
    propertyName: string,
    descriptor: TypedPropertyDescriptor<T>
  ) {
    const method = descriptor.value!;
    
    descriptor.value = function(this: any, ...args: any[]) {
      const key = config.identifier || `${target.constructor.name}.${propertyName}`;
      
      if (!rateLimiter.isAllowed(key, config)) {
        const status = rateLimiter.getStatus(key);
        throw new Error(
          `Rate limit exceeded. Try again in ${Math.ceil((status.resetTime - Date.now()) / 1000)} seconds.`
        );
      }
      
      return method.apply(this, args);
    } as T;
    
    return descriptor;
  };
}

// Rate limiting hook for React components
export function useRateLimit(key: string, config?: Partial<RateLimitConfig>) {
  const checkLimit = () => rateLimiter.isAllowed(key, config);
  const getStatus = () => rateLimiter.getStatus(key);
  const reset = () => rateLimiter.reset(key);
  const waitForReset = () => rateLimiter.waitForReset(key);
  
  return {
    checkLimit,
    getStatus,
    reset,
    waitForReset,
    isAllowed: checkLimit(),
    status: getStatus()
  };
}

// Rate-limited fetch wrapper
export async function rateLimitedFetch(
  url: string, 
  options?: RequestInit,
  rateLimitConfig?: RateLimitConfig
): Promise<Response> {
  const key = `fetch_${new URL(url, window.location.origin).pathname}`;
  
  if (!rateLimiter.isAllowed(key, rateLimitConfig)) {
    const status = rateLimiter.getStatus(key);
    throw new Error(
      `Rate limit exceeded for ${url}. Reset in ${Math.ceil((status.resetTime - Date.now()) / 1000)}s`
    );
  }
  
  return fetch(url, options);
}