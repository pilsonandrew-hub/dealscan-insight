/**
 * Distributed Rate Limiting Implementation
 * Prevents abuse with per-user and per-IP limits
 */

interface RateLimitConfig {
  windowMs: number;      // Time window in milliseconds
  maxRequests: number;   // Max requests per window
  keyPrefix: string;     // Redis key prefix
}

interface RateLimitResult {
  allowed: boolean;
  remaining: number;
  resetTime: number;
  retryAfter?: number;
}

export class DistributedRateLimit {
  private config: RateLimitConfig;

  constructor(config: RateLimitConfig) {
    this.config = config;
  }

  // For production, use Redis. For now, in-memory fallback
  private static store = new Map<string, { count: number; resetTime: number }>();

  async checkLimit(identifier: string): Promise<RateLimitResult> {
    const key = `${this.config.keyPrefix}:${identifier}`;
    const now = Date.now();
    
    const record = DistributedRateLimit.store.get(key);
    
    if (!record || now > record.resetTime) {
      // Reset or create new window
      DistributedRateLimit.store.set(key, {
        count: 1,
        resetTime: now + this.config.windowMs
      });
      
      return {
        allowed: true,
        remaining: this.config.maxRequests - 1,
        resetTime: now + this.config.windowMs
      };
    }
    
    if (record.count >= this.config.maxRequests) {
      return {
        allowed: false,
        remaining: 0,
        resetTime: record.resetTime,
        retryAfter: Math.ceil((record.resetTime - now) / 1000)
      };
    }
    
    // Increment counter
    record.count++;
    DistributedRateLimit.store.set(key, record);
    
    return {
      allowed: true,
      remaining: this.config.maxRequests - record.count,
      resetTime: record.resetTime
    };
  }

  // Clean expired entries (call periodically)
  static cleanup() {
    const now = Date.now();
    for (const [key, record] of DistributedRateLimit.store.entries()) {
      if (now > record.resetTime) {
        DistributedRateLimit.store.delete(key);
      }
    }
  }
}

// Pre-configured rate limiters
export const authRateLimit = new DistributedRateLimit({
  windowMs: 60000,    // 1 minute
  maxRequests: 5,     // 5 auth attempts per minute
  keyPrefix: 'auth'
});

export const scraperRateLimit = new DistributedRateLimit({
  windowMs: 60000,    // 1 minute  
  maxRequests: 3,     // 3 scraping jobs per minute
  keyPrefix: 'scraper'
});

export const apiRateLimit = new DistributedRateLimit({
  windowMs: 60000,    // 1 minute
  maxRequests: 100,   // 100 API calls per minute
  keyPrefix: 'api'
});

// Cleanup every 5 minutes
setInterval(() => {
  DistributedRateLimit.cleanup();
}, 5 * 60 * 1000);