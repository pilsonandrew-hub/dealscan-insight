/**
 * Input Sanitization Utilities
 * Comprehensive input validation and sanitization for DealerScope
 */

// XSS prevention patterns
const XSS_PATTERNS = [
  /<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi,
  /<iframe\b[^<]*(?:(?!<\/iframe>)<[^<]*)*<\/iframe>/gi,
  /<object\b[^<]*(?:(?!<\/object>)<[^<]*)*<\/object>/gi,
  /<embed\b[^>]*>/gi,
  /<applet\b[^<]*(?:(?!<\/applet>)<[^<]*)*<\/applet>/gi,
  /javascript:/gi,
  /data:text\/html/gi,
  /vbscript:/gi,
  /on\w+\s*=/gi
];

// SQL injection patterns
const SQL_PATTERNS = [
  /(\b(select|insert|update|delete|union|drop|create|alter|exec|execute)\b)/gi,
  /(--|\/\*|\*\/|;)/g,
  /(\bor\b|\band\b)\s+\w+\s*=\s*\w+/gi,
  /\b(null|true|false)\b.*[=<>]/gi
];

// Path traversal patterns
const PATH_TRAVERSAL_PATTERNS = [
  /\.\.[\/\\]/g,
  /%2e%2e[\/\\]/gi,
  /\.\.[%2f%5c]/gi,
  /%252e%252e/gi
];

// Command injection patterns
const COMMAND_INJECTION_PATTERNS = [
  /[;&|`$(){}[\]]/g,
  /\b(cmd|powershell|bash|sh|eval|exec|system)\b/gi,
  /[<>]/g
];

export interface SanitizationOptions {
  allowHtml?: boolean;
  maxLength?: number;
  trimWhitespace?: boolean;
  preventSql?: boolean;
  preventXss?: boolean;
  preventPathTraversal?: boolean;
  preventCommandInjection?: boolean;
}

export function sanitizeInput(
  input: string,
  options: SanitizationOptions = {}
): string {
  if (typeof input !== 'string') {
    return String(input);
  }

  const {
    allowHtml = false,
    maxLength = 10000,
    trimWhitespace = true,
    preventSql = true,
    preventXss = true,
    preventPathTraversal = true,
    preventCommandInjection = true
  } = options;

  let sanitized = input;

  // Trim whitespace
  if (trimWhitespace) {
    sanitized = sanitized.trim();
  }

  // Length validation
  if (sanitized.length > maxLength) {
    sanitized = sanitized.substring(0, maxLength);
  }

  // XSS prevention
  if (preventXss && !allowHtml) {
    XSS_PATTERNS.forEach(pattern => {
      sanitized = sanitized.replace(pattern, '');
    });
    
    // HTML entity encoding for remaining special characters
    sanitized = sanitized
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#x27;');
  }

  // SQL injection prevention
  if (preventSql) {
    SQL_PATTERNS.forEach(pattern => {
      sanitized = sanitized.replace(pattern, '');
    });
  }

  // Path traversal prevention
  if (preventPathTraversal) {
    PATH_TRAVERSAL_PATTERNS.forEach(pattern => {
      sanitized = sanitized.replace(pattern, '');
    });
  }

  // Command injection prevention
  if (preventCommandInjection) {
    COMMAND_INJECTION_PATTERNS.forEach(pattern => {
      sanitized = sanitized.replace(pattern, '');
    });
  }

  return sanitized;
}

/**
 * Validates if input is safe for database operations
 */
export function validateSafeInput(input: string): {
  isValid: boolean;
  issues: string[];
  sanitized: string;
} {
  const issues: string[] = [];
  
  // Check for XSS patterns
  if (XSS_PATTERNS.some(pattern => pattern.test(input))) {
    issues.push('Potential XSS content detected');
  }

  // Check for SQL injection
  if (SQL_PATTERNS.some(pattern => pattern.test(input))) {
    issues.push('Potential SQL injection detected');
  }

  // Check for path traversal
  if (PATH_TRAVERSAL_PATTERNS.some(pattern => pattern.test(input))) {
    issues.push('Path traversal attempt detected');
  }

  // Check for command injection
  if (COMMAND_INJECTION_PATTERNS.some(pattern => pattern.test(input))) {
    issues.push('Command injection attempt detected');
  }

  const sanitized = sanitizeInput(input);

  return {
    isValid: issues.length === 0,
    issues,
    sanitized
  };
}

/**
 * Sanitizes object properties recursively
 */
export function sanitizeObject<T extends Record<string, any>>(
  obj: T,
  options?: SanitizationOptions
): T {
  const sanitized: any = { ...obj };

  for (const [key, value] of Object.entries(sanitized)) {
    if (typeof value === 'string') {
      sanitized[key] = sanitizeInput(value, options);
    } else if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
      sanitized[key] = sanitizeObject(value, options);
    } else if (Array.isArray(value)) {
      sanitized[key] = value.map(item => 
        typeof item === 'string' 
          ? sanitizeInput(item, options)
          : typeof item === 'object' && item !== null
            ? sanitizeObject(item, options)
            : item
      );
    }
  }

  return sanitized as T;
}

/**
 * Rate limiting for input validation
 */
class InputRateLimiter {
  private attempts = new Map<string, { count: number; timestamp: number }>();
  private readonly maxAttempts: number;
  private readonly windowMs: number;

  constructor(maxAttempts = 10, windowMs = 60000) {
    this.maxAttempts = maxAttempts;
    this.windowMs = windowMs;
  }

  isAllowed(identifier: string): boolean {
    const now = Date.now();
    const record = this.attempts.get(identifier);

    if (!record) {
      this.attempts.set(identifier, { count: 1, timestamp: now });
      return true;
    }

    if (now - record.timestamp > this.windowMs) {
      this.attempts.set(identifier, { count: 1, timestamp: now });
      return true;
    }

    if (record.count >= this.maxAttempts) {
      return false;
    }

    record.count++;
    return true;
  }

  reset(identifier: string): void {
    this.attempts.delete(identifier);
  }

  cleanup(): void {
    const now = Date.now();
    for (const [key, record] of this.attempts.entries()) {
      if (now - record.timestamp > this.windowMs) {
        this.attempts.delete(key);
      }
    }
  }
}

export const inputRateLimiter = new InputRateLimiter();

// Cleanup rate limiter every 5 minutes
setInterval(() => inputRateLimiter.cleanup(), 5 * 60 * 1000);