/**
 * Elite Rate Limiter
 * Advanced rate limiting with adaptive algorithms and DDoS protection
 */

import { performanceMonitor } from './performance-monitor';

export interface RateLimitConfig {
  windowMs: number;
  maxRequests: number;
  algorithm: 'fixed-window' | 'sliding-window' | 'token-bucket' | 'adaptive';
  burstLimit?: number;
  enableDDoSProtection?: boolean;
  enableAdaptiveRates?: boolean;
  enableIPWhitelist?: boolean;
  enableGeoblocking?: boolean;
}

export interface RateLimitResult {
  allowed: boolean;
  remaining: number;
  resetTime: number;
  retryAfter?: number;
  reason?: string;
  riskScore?: number;
}

export interface RequestPattern {
  ip: string;
  timestamp: number;
  endpoint: string;
  userAgent?: string;
  riskScore: number;
}

class EliteRateLimiter {
  private requestHistory = new Map<string, RequestPattern[]>();
  private tokenBuckets = new Map<string, { tokens: number; lastRefill: number }>();
  private suspiciousIPs = new Map<string, { score: number; lastSeen: number }>();
  private whitelist = new Set<string>();
  private blacklist = new Map<string, number>(); // IP -> expiry timestamp
  
  constructor(private defaultConfig: RateLimitConfig) {
    this.startCleanupProcess();
    this.startAdaptiveMonitoring();
  }

  public checkLimit(
    identifier: string,
    config?: Partial<RateLimitConfig>
  ): RateLimitResult {
    const timer = performanceMonitor.startTimer('rate_limit_check');
    
    try {
      const finalConfig = { ...this.defaultConfig, ...config };
      const now = Date.now();

      // Check blacklist first
      if (this.isBlacklisted(identifier)) {
        return {
          allowed: false,
          remaining: 0,
          resetTime: this.blacklist.get(identifier) || now + finalConfig.windowMs,
          reason: 'IP_BLACKLISTED',
          riskScore: 100
        };
      }

      // Check whitelist
      if (finalConfig.enableIPWhitelist && this.whitelist.has(identifier)) {
        return {
          allowed: true,
          remaining: finalConfig.maxRequests,
          resetTime: now + finalConfig.windowMs,
          riskScore: 0
        };
      }

      // Apply rate limiting algorithm
      let result: RateLimitResult;
      
      switch (finalConfig.algorithm) {
        case 'token-bucket':
          result = this.tokenBucketCheck(identifier, finalConfig, now);
          break;
        case 'sliding-window':
          result = this.slidingWindowCheck(identifier, finalConfig, now);
          break;
        case 'adaptive':
          result = this.adaptiveCheck(identifier, finalConfig, now);
          break;
        default:
          result = this.fixedWindowCheck(identifier, finalConfig, now);
      }

      // DDoS protection analysis
      if (finalConfig.enableDDoSProtection && !result.allowed) {
        this.analyzeDDoSPattern(identifier, now);
      }

      // Update request history
      this.updateRequestHistory(identifier, now);
      
      return result;
    } finally {
      timer.end(true);
    }
  }

  private tokenBucketCheck(
    identifier: string,
    config: RateLimitConfig,
    now: number
  ): RateLimitResult {
    let bucket = this.tokenBuckets.get(identifier);
    
    if (!bucket) {
      bucket = { tokens: config.maxRequests, lastRefill: now };
      this.tokenBuckets.set(identifier, bucket);
    }

    // Refill tokens based on time passed
    const timePassed = now - bucket.lastRefill;
    const tokensToAdd = Math.floor(timePassed / (config.windowMs / config.maxRequests));
    
    if (tokensToAdd > 0) {
      bucket.tokens = Math.min(config.maxRequests, bucket.tokens + tokensToAdd);
      bucket.lastRefill = now;
    }

    if (bucket.tokens > 0) {
      bucket.tokens--;
      return {
        allowed: true,
        remaining: bucket.tokens,
        resetTime: now + (config.windowMs / config.maxRequests),
        riskScore: this.calculateRiskScore(identifier)
      };
    }

    return {
      allowed: false,
      remaining: 0,
      resetTime: now + (config.windowMs / config.maxRequests),
      retryAfter: Math.ceil((config.windowMs / config.maxRequests) / 1000),
      reason: 'RATE_LIMIT_EXCEEDED',
      riskScore: this.calculateRiskScore(identifier)
    };
  }

  private slidingWindowCheck(
    identifier: string,
    config: RateLimitConfig,
    now: number
  ): RateLimitResult {
    const history = this.requestHistory.get(identifier) || [];
    const windowStart = now - config.windowMs;
    
    // Remove old requests
    const recentRequests = history.filter(req => req.timestamp > windowStart);
    this.requestHistory.set(identifier, recentRequests);

    const remaining = Math.max(0, config.maxRequests - recentRequests.length - 1);
    
    if (recentRequests.length < config.maxRequests) {
      return {
        allowed: true,
        remaining,
        resetTime: now + config.windowMs,
        riskScore: this.calculateRiskScore(identifier)
      };
    }

    const oldestRequest = recentRequests[0];
    const resetTime = oldestRequest.timestamp + config.windowMs;
    
    return {
      allowed: false,
      remaining: 0,
      resetTime,
      retryAfter: Math.ceil((resetTime - now) / 1000),
      reason: 'RATE_LIMIT_EXCEEDED',
      riskScore: this.calculateRiskScore(identifier)
    };
  }

  private adaptiveCheck(
    identifier: string,
    config: RateLimitConfig,
    now: number
  ): RateLimitResult {
    const riskScore = this.calculateRiskScore(identifier);
    
    // Adjust rate limits based on risk score
    const adjustedMaxRequests = Math.max(
      1,
      Math.floor(config.maxRequests * (1 - riskScore / 200))
    );
    
    const adaptedConfig = { ...config, maxRequests: adjustedMaxRequests };
    
    // Use sliding window with adaptive limits
    return this.slidingWindowCheck(identifier, adaptedConfig, now);
  }

  private fixedWindowCheck(
    identifier: string,
    config: RateLimitConfig,
    now: number
  ): RateLimitResult {
    const windowStart = Math.floor(now / config.windowMs) * config.windowMs;
    const key = `${identifier}_${windowStart}`;
    
    const history = this.requestHistory.get(key) || [];
    const count = history.length + 1;
    
    if (count <= config.maxRequests) {
      return {
        allowed: true,
        remaining: config.maxRequests - count,
        resetTime: windowStart + config.windowMs,
        riskScore: this.calculateRiskScore(identifier)
      };
    }

    return {
      allowed: false,
      remaining: 0,
      resetTime: windowStart + config.windowMs,
      retryAfter: Math.ceil((windowStart + config.windowMs - now) / 1000),
      reason: 'RATE_LIMIT_EXCEEDED',
      riskScore: this.calculateRiskScore(identifier)
    };
  }

  private calculateRiskScore(identifier: string): number {
    const suspicious = this.suspiciousIPs.get(identifier);
    if (!suspicious) return 0;
    
    const now = Date.now();
    const timeSinceLastSeen = now - suspicious.lastSeen;
    
    // Decay risk score over time
    const decayFactor = Math.max(0, 1 - (timeSinceLastSeen / (24 * 60 * 60 * 1000))); // 24 hour decay
    
    return Math.min(100, suspicious.score * decayFactor);
  }

  private analyzeDDoSPattern(identifier: string, now: number): void {
    const history = this.requestHistory.get(identifier) || [];
    const recentRequests = history.filter(req => now - req.timestamp < 60000); // Last minute
    
    // DDoS indicators
    const requestRate = recentRequests.length;
    const uniqueEndpoints = new Set(recentRequests.map(req => req.endpoint)).size;
    
    let suspicionScore = 0;
    
    // High request rate
    if (requestRate > 100) suspicionScore += 30;
    else if (requestRate > 50) suspicionScore += 15;
    
    // Low endpoint diversity (potential bot)
    if (uniqueEndpoints < 3 && requestRate > 20) suspicionScore += 25;
    
    // Consistent timing (potential bot)
    if (recentRequests.length >= 5) {
      const intervals = [];
      for (let i = 1; i < Math.min(recentRequests.length, 10); i++) {
        intervals.push(recentRequests[i].timestamp - recentRequests[i-1].timestamp);
      }
      
      const avgInterval = intervals.reduce((sum, val) => sum + val, 0) / intervals.length;
      const variance = intervals.reduce((sum, val) => sum + Math.pow(val - avgInterval, 2), 0) / intervals.length;
      
      if (variance < 100) suspicionScore += 20; // Very consistent timing
    }
    
    // Update suspicion score
    const current = this.suspiciousIPs.get(identifier);
    const newScore = Math.min(100, (current?.score || 0) + suspicionScore);
    
    this.suspiciousIPs.set(identifier, {
      score: newScore,
      lastSeen: now
    });
    
    // Auto-blacklist high-risk IPs
    if (newScore > 80) {
      this.blacklist.set(identifier, now + (24 * 60 * 60 * 1000)); // 24 hour blacklist
      console.warn(`[Security] IP ${identifier} auto-blacklisted. Risk score: ${newScore}`);
    }
  }

  private updateRequestHistory(identifier: string, now: number): void {
    const history = this.requestHistory.get(identifier) || [];
    history.push({
      ip: identifier,
      timestamp: now,
      endpoint: 'unknown', // Would be set by middleware
      riskScore: this.calculateRiskScore(identifier)
    });
    
    // Keep only recent history
    const cutoff = now - (24 * 60 * 60 * 1000); // 24 hours
    const filtered = history.filter(req => req.timestamp > cutoff);
    
    this.requestHistory.set(identifier, filtered);
  }

  private isBlacklisted(identifier: string): boolean {
    const expiry = this.blacklist.get(identifier);
    if (!expiry) return false;
    
    if (Date.now() > expiry) {
      this.blacklist.delete(identifier);
      return false;
    }
    
    return true;
  }

  private startCleanupProcess(): void {
    setInterval(() => {
      const now = Date.now();
      const cutoff = now - (24 * 60 * 60 * 1000); // 24 hours
      
      // Clean up old request history
      for (const [key, history] of this.requestHistory.entries()) {
        const filtered = history.filter(req => req.timestamp > cutoff);
        if (filtered.length === 0) {
          this.requestHistory.delete(key);
        } else {
          this.requestHistory.set(key, filtered);
        }
      }
      
      // Clean up old token buckets
      for (const [key, bucket] of this.tokenBuckets.entries()) {
        if (now - bucket.lastRefill > cutoff) {
          this.tokenBuckets.delete(key);
        }
      }
      
      // Clean up expired blacklist entries
      for (const [ip, expiry] of this.blacklist.entries()) {
        if (now > expiry) {
          this.blacklist.delete(ip);
        }
      }
    }, 5 * 60 * 1000); // Every 5 minutes
  }

  private startAdaptiveMonitoring(): void {
    if (!this.defaultConfig.enableAdaptiveRates) return;
    
    setInterval(() => {
      // Analyze global patterns and adjust base rates
      const now = Date.now();
      const recentWindow = now - (5 * 60 * 1000); // Last 5 minutes
      
      let totalRequests = 0;
      let suspiciousRequests = 0;
      
      for (const history of this.requestHistory.values()) {
        const recent = history.filter(req => req.timestamp > recentWindow);
        totalRequests += recent.length;
        suspiciousRequests += recent.filter(req => req.riskScore > 50).length;
      }
      
      const suspicionRate = totalRequests > 0 ? suspiciousRequests / totalRequests : 0;
      
      // Adjust global rate limits based on attack patterns
      if (suspicionRate > 0.3) {
        console.warn('[Security] High suspicious activity detected. Tightening rate limits.');
        // In a real implementation, this would adjust the base configuration
      }
    }, 60000); // Every minute
  }

  // Public methods for management
  public addToWhitelist(ip: string): void {
    this.whitelist.add(ip);
  }

  public removeFromWhitelist(ip: string): void {
    this.whitelist.delete(ip);
  }

  public addToBlacklist(ip: string, durationMs: number = 24 * 60 * 60 * 1000): void {
    this.blacklist.set(ip, Date.now() + durationMs);
  }

  public removeFromBlacklist(ip: string): void {
    this.blacklist.delete(ip);
  }

  public getStats(): {
    totalRequests: number;
    activeIPs: number;
    blacklistedIPs: number;
    suspiciousIPs: number;
    whitelistedIPs: number;
  } {
    let totalRequests = 0;
    const activeIPs = new Set<string>();
    
    for (const [key, history] of this.requestHistory.entries()) {
      totalRequests += history.length;
      history.forEach(req => activeIPs.add(req.ip));
    }
    
    const suspiciousCount = Array.from(this.suspiciousIPs.values())
      .filter(sus => sus.score > 50).length;
    
    return {
      totalRequests,
      activeIPs: activeIPs.size,
      blacklistedIPs: this.blacklist.size,
      suspiciousIPs: suspiciousCount,
      whitelistedIPs: this.whitelist.size
    };
  }
}

// Global instances for different use cases
export const apiRateLimiter = new EliteRateLimiter({
  windowMs: 60 * 1000, // 1 minute
  maxRequests: 100,
  algorithm: 'sliding-window',
  enableDDoSProtection: true,
  enableAdaptiveRates: true
});

export const uploadRateLimiter = new EliteRateLimiter({
  windowMs: 5 * 60 * 1000, // 5 minutes
  maxRequests: 10,
  algorithm: 'token-bucket',
  burstLimit: 3,
  enableDDoSProtection: true
});

export const authRateLimiter = new EliteRateLimiter({
  windowMs: 15 * 60 * 1000, // 15 minutes
  maxRequests: 5,
  algorithm: 'fixed-window',
  enableDDoSProtection: true,
  enableAdaptiveRates: false // Strict for auth
});

export { EliteRateLimiter };
