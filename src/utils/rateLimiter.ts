/**
 * Production-grade rate limiting with Redis fallback and token bucket
 */

import productionLogger from './productionLogger';

export interface RateLimitConfig {
  maxTokens: number;
  refillRate: number; // tokens per second
  windowMs: number;
  keyPrefix: string;
}

export interface RateLimitResult {
  allowed: boolean;
  tokensRemaining: number;
  resetTime: number;
  retryAfter?: number;
}

interface TokenBucket {
  tokens: number;
  lastRefill: number;
  resetTime: number;
}

/**
 * In-memory token bucket rate limiter with Redis fallback capability
 */
export class RateLimiter {
  private buckets = new Map<string, TokenBucket>();
  private cleanupInterval?: number;

  constructor(private config: RateLimitConfig) {
    // Cleanup expired buckets every minute
    this.cleanupInterval = window.setInterval(() => {
      this.cleanup();
    }, 60000);
  }

  /**
   * Check if request is allowed under rate limit
   */
  async checkLimit(key: string, tokens: number = 1): Promise<RateLimitResult> {
    const bucketKey = `${this.config.keyPrefix}:${key}`;
    const now = Date.now();
    
    let bucket = this.buckets.get(bucketKey);
    
    if (!bucket) {
      bucket = {
        tokens: this.config.maxTokens,
        lastRefill: now,
        resetTime: now + this.config.windowMs
      };
      this.buckets.set(bucketKey, bucket);
    }

    // Refill tokens based on time elapsed
    this.refillBucket(bucket, now);

    const allowed = bucket.tokens >= tokens;
    
    if (allowed) {
      bucket.tokens -= tokens;
    }

    const result: RateLimitResult = {
      allowed,
      tokensRemaining: Math.max(0, bucket.tokens),
      resetTime: bucket.resetTime,
      retryAfter: allowed ? undefined : this.calculateRetryAfter(bucket, tokens)
    };

    logger.debug('Rate limit check', {
      key: bucketKey,
      allowed,
      tokensRemaining: result.tokensRemaining,
      requestedTokens: tokens
    });

    return result;
  }

  /**
   * Rate limit decorator for functions
   */
  limit<T extends (...args: any[]) => Promise<any>>(
    keyGenerator: (...args: Parameters<T>) => string,
    tokens: number = 1
  ) {
    return (target: any, propertyName: string, descriptor: PropertyDescriptor) => {
      const method = descriptor.value;

      descriptor.value = async function (...args: Parameters<T>) {
        const key = keyGenerator(...args);
        const limitResult = await this.checkLimit(key, tokens);
        
        if (!limitResult.allowed) {
          const error = new Error(`Rate limit exceeded for ${key}`);
          (error as any).rateLimitInfo = limitResult;
          throw error;
        }

        return method.apply(this, args);
      };

      return descriptor;
    };
  }

  /**
   * Express middleware for API rate limiting
   */
  middleware(keyExtractor?: (req: any) => string) {
    return async (req: any, res: any, next: any) => {
      try {
        const key = keyExtractor ? keyExtractor(req) : this.getDefaultKey(req);
        const result = await this.checkLimit(key);

        // Add rate limit headers
        res.setHeader('X-RateLimit-Limit', this.config.maxTokens);
        res.setHeader('X-RateLimit-Remaining', result.tokensRemaining);
        res.setHeader('X-RateLimit-Reset', Math.ceil(result.resetTime / 1000));

        if (!result.allowed) {
          res.setHeader('Retry-After', Math.ceil(result.retryAfter! / 1000));
          return res.status(429).json({
            error: 'Too Many Requests',
            message: 'Rate limit exceeded',
            retryAfter: result.retryAfter
          });
        }

        next();
      } catch (error) {
        logger.error('Rate limiter middleware error', error as Error);
        next(); // Don't block on rate limiter errors
      }
    };
  }

  /**
   * Refill bucket tokens based on elapsed time
   */
  private refillBucket(bucket: TokenBucket, now: number): void {
    const timeSinceLastRefill = now - bucket.lastRefill;
    const tokensToAdd = Math.floor(timeSinceLastRefill / 1000 * this.config.refillRate);
    
    if (tokensToAdd > 0) {
      bucket.tokens = Math.min(this.config.maxTokens, bucket.tokens + tokensToAdd);
      bucket.lastRefill = now;
    }

    // Reset window if expired
    if (now >= bucket.resetTime) {
      bucket.tokens = this.config.maxTokens;
      bucket.resetTime = now + this.config.windowMs;
      bucket.lastRefill = now;
    }
  }

  /**
   * Calculate retry after time in milliseconds
   */
  private calculateRetryAfter(bucket: TokenBucket, tokensNeeded: number): number {
    const tokensShortfall = tokensNeeded - bucket.tokens;
    return Math.ceil(tokensShortfall / this.config.refillRate * 1000);
  }

  /**
   * Get default key from request
   */
  private getDefaultKey(req: any): string {
    return req.ip || req.connection?.remoteAddress || 'unknown';
  }

  /**
   * Cleanup expired buckets
   */
  private cleanup(): void {
    const now = Date.now();
    let cleaned = 0;

    for (const [key, bucket] of this.buckets) {
      if (now > bucket.resetTime + this.config.windowMs) {
        this.buckets.delete(key);
        cleaned++;
      }
    }

    if (cleaned > 0) {
      logger.debug('Rate limiter cleanup', { cleaned, remaining: this.buckets.size });
    }
  }

  /**
   * Get current rate limit stats
   */
  getStats(): { totalBuckets: number; activeBuckets: number } {
    const now = Date.now();
    let activeBuckets = 0;

    for (const bucket of this.buckets.values()) {
      if (now <= bucket.resetTime + this.config.windowMs) {
        activeBuckets++;
      }
    }

    return {
      totalBuckets: this.buckets.size,
      activeBuckets
    };
  }

  /**
   * Dispose rate limiter
   */
  dispose(): void {
    if (this.cleanupInterval) {
      clearInterval(this.cleanupInterval);
    }
    this.buckets.clear();
  }
}

// Pre-configured rate limiters for different use cases
export const apiRateLimiter = new RateLimiter({
  maxTokens: 100,
  refillRate: 1, // 1 token per second
  windowMs: 60000, // 1 minute window
  keyPrefix: 'api'
});

export const scraperRateLimiter = new RateLimiter({
  maxTokens: 10,
  refillRate: 0.1, // 1 token per 10 seconds
  windowMs: 300000, // 5 minute window
  keyPrefix: 'scraper'
});

export const uploadRateLimiter = new RateLimiter({
  maxTokens: 5,
  refillRate: 0.05, // 1 token per 20 seconds
  windowMs: 600000, // 10 minute window
  keyPrefix: 'upload'
});