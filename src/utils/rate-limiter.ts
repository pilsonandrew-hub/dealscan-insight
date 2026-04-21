/**
 * Minimal client-side upload rate limiting utility.
 * Current live surface is limited to UploadInterface security checks.
 */

export interface RateLimitConfig {
  maxRequests: number;
  windowMs: number;
}

interface RateLimitState {
  requests: number[];
}

class RateLimiter {
  private limits: Map<string, RateLimitState> = new Map();

  isAllowed(key: string, config: RateLimitConfig): boolean {
    const now = Date.now();
    const state = this.limits.get(key) || { requests: [] };

    state.requests = state.requests.filter(time => now - time < config.windowMs);

    if (state.requests.length >= config.maxRequests) {
      this.limits.set(key, state);
      return false;
    }

    state.requests.push(now);
    this.limits.set(key, state);
    return true;
  }

  cleanup(windowMs = 60000): void {
    const now = Date.now();

    this.limits.forEach((state, key) => {
      state.requests = state.requests.filter(time => now - time < windowMs);

      if (state.requests.length === 0) {
        this.limits.delete(key);
      }
    });
  }
}

export const rateLimiter = new RateLimiter();

setInterval(() => {
  rateLimiter.cleanup();
}, 120000);
