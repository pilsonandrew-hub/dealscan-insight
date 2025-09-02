/**
 * Comprehensive Input Sanitization and Validation
 * Prevents XSS, injection attacks, and malicious input
 */

export interface SanitizationConfig {
  allowHTML?: boolean;
  maxLength?: number;
  allowSpecialChars?: boolean;
  preventSQLInjection?: boolean;
  preventXSS?: boolean;
}

export interface ValidationResult {
  isValid: boolean;
  sanitized: string;
  threats: string[];
  riskLevel: 'low' | 'medium' | 'high';
}

class InputSanitizer {
  private readonly SQL_INJECTION_PATTERNS = [
    /(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|UNION|SCRIPT)\b)/gi,
    /('|''|"|""|\-\-|#|\/\*)/gi,
    /(\b(OR|AND)\b\s*\=)/gi,
    /(\b(WAITFOR|DELAY)\b)/gi,
    /(xp_|sp_)/gi,
  ];

  private readonly XSS_PATTERNS = [
    /<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi,
    /javascript:/gi,
    /on\w+\s*=/gi,
    /<iframe\b[^>]*>/gi,
    /<object\b[^>]*>/gi,
    /<embed\b[^>]*>/gi,
    /<form\b[^>]*>/gi,
    /expression\s*\(/gi,
    /vbscript:/gi,
    /data:text\/html/gi,
  ];

  private readonly DANGEROUS_CHARS = [
    '&lt;', '&gt;', '&amp;', '&quot;', '&#x27;', '&#x2F;', '&#96;'
  ];

  private readonly HTML_ENTITIES: Record<string, string> = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#x27;',
    '/': '&#x2F;',
    '`': '&#96;'
  };

  /**
   * Sanitize and validate input string
   */
  sanitize(input: string, config: SanitizationConfig = {}): ValidationResult {
    const {
      allowHTML = false,
      maxLength = 10000,
      allowSpecialChars = true,
      preventSQLInjection = true,
      preventXSS = true
    } = config;

    const threats: string[] = [];
    let riskLevel: 'low' | 'medium' | 'high' = 'low';
    let sanitized = input;

    // Basic validation
    if (input.length > maxLength) {
      threats.push(`Input exceeds maximum length of ${maxLength} characters`);
      sanitized = sanitized.substring(0, maxLength);
      riskLevel = 'medium';
    }

    // SQL Injection Detection
    if (preventSQLInjection) {
      for (const pattern of this.SQL_INJECTION_PATTERNS) {
        if (pattern.test(sanitized)) {
          threats.push('Potential SQL injection detected');
          sanitized = sanitized.replace(pattern, '');
          riskLevel = 'high';
        }
      }
    }

    // XSS Detection and Prevention
    if (preventXSS) {
      for (const pattern of this.XSS_PATTERNS) {
        if (pattern.test(sanitized)) {
          threats.push('Potential XSS attack detected');
          sanitized = sanitized.replace(pattern, '');
          riskLevel = 'high';
        }
      }

      // HTML Entity Encoding (if HTML not allowed)
      if (!allowHTML) {
        sanitized = this.encodeHTMLEntities(sanitized);
      }
    }

    // Special character filtering
    if (!allowSpecialChars) {
      sanitized = sanitized.replace(/[<>'"&]/g, '');
      if (sanitized !== input) {
        threats.push('Special characters removed');
        riskLevel = riskLevel === 'high' ? 'high' : 'medium';
      }
    }

    // Normalize whitespace
    sanitized = sanitized.replace(/\s+/g, ' ').trim();

    return {
      isValid: threats.length === 0 || riskLevel !== 'high',
      sanitized,
      threats,
      riskLevel
    };
  }

  /**
   * Sanitize object with nested properties
   */
  sanitizeObject<T extends Record<string, any>>(
    obj: T, 
    config: SanitizationConfig = {}
  ): { sanitized: T; threats: string[]; isValid: boolean } {
    const threats: string[] = [];
    const sanitized = { ...obj } as T;

    for (const [key, value] of Object.entries(obj)) {
      if (typeof value === 'string') {
        const result = this.sanitize(value, config);
        (sanitized as any)[key] = result.sanitized;
        threats.push(...result.threats.map(t => `${key}: ${t}`));
      } else if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
        const result = this.sanitizeObject(value, config);
        (sanitized as any)[key] = result.sanitized;
        threats.push(...result.threats);
      } else if (Array.isArray(value)) {
        (sanitized as any)[key] = value.map(item => 
          typeof item === 'string' ? this.sanitize(item, config).sanitized : item
        );
      }
    }

    return {
      sanitized,
      threats,
      isValid: threats.length === 0
    };
  }

  /**
   * Validate email address
   */
  validateEmail(email: string): ValidationResult {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    const sanitized = email.toLowerCase().trim();
    
    const threats: string[] = [];
    let riskLevel: 'low' | 'medium' | 'high' = 'low';

    // Basic format validation
    if (!emailRegex.test(sanitized)) {
      threats.push('Invalid email format');
      riskLevel = 'medium';
    }

    // Check for dangerous patterns
    if (this.XSS_PATTERNS.some(pattern => pattern.test(sanitized))) {
      threats.push('Potentially malicious email address');
      riskLevel = 'high';
    }

    // Length validation
    if (sanitized.length > 254) {
      threats.push('Email address too long');
      riskLevel = 'medium';
    }

    return {
      isValid: threats.length === 0,
      sanitized,
      threats,
      riskLevel
    };
  }

  /**
   * Validate URL
   */
  validateURL(url: string): ValidationResult {
    const sanitized = url.trim();
    const threats: string[] = [];
    let riskLevel: 'low' | 'medium' | 'high' = 'low';

    try {
      const urlObj = new URL(sanitized);
      
      // Only allow HTTP/HTTPS
      if (!['http:', 'https:'].includes(urlObj.protocol)) {
        threats.push('Only HTTP and HTTPS protocols are allowed');
        riskLevel = 'high';
      }

      // Block internal networks
      const hostname = urlObj.hostname.toLowerCase();
      if (this.isPrivateIP(hostname)) {
        threats.push('Access to private networks is not allowed');
        riskLevel = 'high';
      }

      // Check for XSS in URL
      if (this.XSS_PATTERNS.some(pattern => pattern.test(sanitized))) {
        threats.push('Potentially malicious URL');
        riskLevel = 'high';
      }

    } catch (error) {
      threats.push('Invalid URL format');
      riskLevel = 'medium';
    }

    return {
      isValid: riskLevel !== 'high',
      sanitized,
      threats,
      riskLevel
    };
  }

  /**
   * Sanitize CSV data
   */
  sanitizeCSVData(data: string[][]): { sanitized: string[][]; threats: string[] } {
    const threats: string[] = [];
    const sanitized = data.map((row, rowIndex) => 
      row.map((cell, cellIndex) => {
        // Check for CSV injection (formulas)
        if (typeof cell === 'string' && /^[=+\-@]/.test(cell.trim())) {
          threats.push(`Row ${rowIndex + 1}, Column ${cellIndex + 1}: Potential CSV injection`);
          return `'${cell}`; // Prefix with single quote to prevent formula execution
        }

        // Sanitize the cell content
        const result = this.sanitize(cell.toString(), { 
          preventXSS: true, 
          preventSQLInjection: true 
        });
        
        if (result.threats.length > 0) {
          threats.push(`Row ${rowIndex + 1}, Column ${cellIndex + 1}: ${result.threats.join(', ')}`);
        }

        return result.sanitized;
      })
    );

    return { sanitized, threats };
  }

  private encodeHTMLEntities(str: string): string {
    return str.replace(/[&<>"'`]/g, match => this.HTML_ENTITIES[match] || match);
  }

  private isPrivateIP(hostname: string): boolean {
    const privateRanges = [
      /^10\./,
      /^172\.(1[6-9]|2[0-9]|3[01])\./,
      /^192\.168\./,
      /^169\.254\./,
      /^127\./,
      /^localhost$/i,
    ];

    return privateRanges.some(range => range.test(hostname));
  }
}

// Export singleton instance
export const inputSanitizer = new InputSanitizer();

// Helper functions for common use cases
export const sanitizeString = (input: string, config?: SanitizationConfig) => 
  inputSanitizer.sanitize(input, config);

export const sanitizeObject = <T extends Record<string, any>>(obj: T, config?: SanitizationConfig) => 
  inputSanitizer.sanitizeObject(obj, config);

export const validateEmail = (email: string) => 
  inputSanitizer.validateEmail(email);

export const validateURL = (url: string) => 
  inputSanitizer.validateURL(url);