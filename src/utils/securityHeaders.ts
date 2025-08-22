/**
 * Security Headers Management
 * Implements CSP, HSTS, and other security headers
 */

import { logger } from '@/utils/secureLogger';

export interface SecurityHeaders {
  'Content-Security-Policy': string;
  'X-Content-Type-Options': string;
  'X-Frame-Options': string;
  'X-XSS-Protection': string;
  'Strict-Transport-Security': string;
  'Referrer-Policy': string;
  'Permissions-Policy': string;
}

class SecurityHeadersManager {
  private headers: SecurityHeaders;

  constructor() {
    this.headers = this.generateSecurityHeaders();
    this.applyHeaders();
  }

  private generateSecurityHeaders(): SecurityHeaders {
    const nonce = this.generateNonce();
    
    return {
      'Content-Security-Policy': [
        "default-src 'self'",
        `script-src 'self' 'nonce-${nonce}' https://cdn.jsdelivr.net`,
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
        "font-src 'self' https://fonts.gstatic.com",
        "img-src 'self' data: https:",
        "connect-src 'self' wss: https:",
        "media-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
        "upgrade-insecure-requests"
      ].join('; '),
      'X-Content-Type-Options': 'nosniff',
      'X-Frame-Options': 'DENY',
      'X-XSS-Protection': '1; mode=block',
      'Strict-Transport-Security': 'max-age=31536000; includeSubDomains; preload',
      'Referrer-Policy': 'strict-origin-when-cross-origin',
      'Permissions-Policy': [
        'geolocation=()',
        'microphone=()',
        'camera=()',
        'payment=()',
        'usb=()',
        'magnetometer=()',
        'gyroscope=()',
        'speaker=()'
      ].join(', ')
    };
  }

  private generateNonce(): string {
    const array = new Uint8Array(16);
    crypto.getRandomValues(array);
    return Array.from(array, byte => byte.toString(16).padStart(2, '0')).join('');
  }

  private applyHeaders(): void {
    // Apply meta tags for security headers that can be set via HTML
    this.setMetaTags();
    
    // Log security headers application
    logger.info('Security headers applied', 'SECURITY', {
      headersCount: Object.keys(this.headers).length
    });
  }

  private setMetaTags(): void {
    const head = document.head;
    
    // Add CSP meta tag
    const cspMeta = document.createElement('meta');
    cspMeta.setAttribute('http-equiv', 'Content-Security-Policy');
    cspMeta.setAttribute('content', this.headers['Content-Security-Policy']);
    head.appendChild(cspMeta);

    // Add X-Content-Type-Options
    const nosniffMeta = document.createElement('meta');
    nosniffMeta.setAttribute('http-equiv', 'X-Content-Type-Options');
    nosniffMeta.setAttribute('content', this.headers['X-Content-Type-Options']);
    head.appendChild(nosniffMeta);

    // Add referrer policy
    const referrerMeta = document.createElement('meta');
    referrerMeta.setAttribute('name', 'referrer');
    referrerMeta.setAttribute('content', this.headers['Referrer-Policy']);
    head.appendChild(referrerMeta);
  }

  public getHeaders(): SecurityHeaders {
    return { ...this.headers };
  }

  public updateCSP(additionalDirectives: string[]): void {
    const currentCSP = this.headers['Content-Security-Policy'];
    this.headers['Content-Security-Policy'] = currentCSP + '; ' + additionalDirectives.join('; ');
    this.applyHeaders();
  }
}

// Content sanitization utilities
class ContentSanitizer {
  private static readonly ALLOWED_TAGS = ['p', 'br', 'strong', 'em', 'u', 'ol', 'ul', 'li'];
  private static readonly ALLOWED_ATTRIBUTES: Record<string, string[]> = {};

  static sanitizeHTML(html: string): string {
    const div = document.createElement('div');
    div.innerHTML = html;
    
    this.removeDisallowedElements(div);
    this.removeDisallowedAttributes(div);
    
    return div.innerHTML;
  }

  private static removeDisallowedElements(element: Element): void {
    const walker = document.createTreeWalker(
      element,
      NodeFilter.SHOW_ELEMENT,
      {
        acceptNode: (node) => {
          const tagName = (node as Element).tagName.toLowerCase();
          return this.ALLOWED_TAGS.includes(tagName) 
            ? NodeFilter.FILTER_ACCEPT 
            : NodeFilter.FILTER_REJECT;
        }
      }
    );

    const nodesToRemove: Element[] = [];
    let node: Node | null;
    
    while (node = walker.nextNode()) {
      const element = node as Element;
      if (!this.ALLOWED_TAGS.includes(element.tagName.toLowerCase())) {
        nodesToRemove.push(element);
      }
    }

    nodesToRemove.forEach(node => node.remove());
  }

  private static removeDisallowedAttributes(element: Element): void {
    const walker = document.createTreeWalker(
      element,
      NodeFilter.SHOW_ELEMENT
    );

    let node: Node | null;
    while (node = walker.nextNode()) {
      const el = node as Element;
      const tagName = el.tagName.toLowerCase();
      const allowedAttrs = this.ALLOWED_ATTRIBUTES[tagName] || [];
      
      // Remove all attributes except allowed ones
      const attributesToRemove: string[] = [];
      for (let i = 0; i < el.attributes.length; i++) {
        const attr = el.attributes[i];
        if (!allowedAttrs.includes(attr.name)) {
          attributesToRemove.push(attr.name);
        }
      }
      
      attributesToRemove.forEach(attrName => el.removeAttribute(attrName));
    }
  }

  static sanitizeText(text: string): string {
    return text
      .replace(/[<>\"'&]/g, (match) => {
        const escapeMap: Record<string, string> = {
          '<': '&lt;',
          '>': '&gt;',
          '"': '&quot;',
          "'": '&#x27;',
          '&': '&amp;'
        };
        return escapeMap[match];
      });
  }

  static sanitizeURL(url: string): string {
    try {
      const parsedURL = new URL(url);
      // Only allow http and https protocols
      if (!['http:', 'https:'].includes(parsedURL.protocol)) {
        throw new Error('Invalid protocol');
      }
      return parsedURL.href;
    } catch {
      return '';
    }
  }
}

// Rate limiting for client-side requests
class ClientRateLimiter {
  private requests: Map<string, number[]> = new Map();
  private limits: Map<string, { count: number; window: number }> = new Map();

  setLimit(key: string, count: number, windowMs: number): void {
    this.limits.set(key, { count, window: windowMs });
  }

  canMakeRequest(key: string): boolean {
    const limit = this.limits.get(key);
    if (!limit) return true;

    const now = Date.now();
    const requests = this.requests.get(key) || [];
    
    // Clean old requests outside window
    const validRequests = requests.filter(time => now - time < limit.window);
    
    if (validRequests.length >= limit.count) {
      logger.warn('Rate limit exceeded', 'SECURITY', { key, count: validRequests.length });
      return false;
    }

    // Add current request
    validRequests.push(now);
    this.requests.set(key, validRequests);
    
    return true;
  }

  reset(key?: string): void {
    if (key) {
      this.requests.delete(key);
    } else {
      this.requests.clear();
    }
  }
}

// Initialize security headers
const securityManager = new SecurityHeadersManager();

export { securityManager, ContentSanitizer, ClientRateLimiter };
export default securityManager;