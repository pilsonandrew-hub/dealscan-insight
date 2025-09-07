import { describe, it, expect, test } from 'vitest';
import { validateAndSanitizeUrl, isInternalIP } from '../../utils/urlSecurity';

describe('URL Security & SSRF Protection', () => {
  // Test cases for allowed domains
  const allowedUrls = [
    'https://govdeals.com/some/path',
    'http://publicsurplus.com/auctions'
  ];

  // Test cases for disallowed domains and attack vectors
  const disallowedUrls = [
    'https://some-malicious-site.com', // Not in allowlist
    'ftp://govdeals.com', // Invalid protocol
    'https://127.0.0.1/admin', // Localhost IP
    'http://10.0.0.5/internal', // Private IP range
    'https://169.254.169.254/latest/meta-data/', // AWS metadata service
    'http://[::1]/', // Localhost IPv6
    'http://localhost:3000/api' // localhost string
  ];

  test.each(allowedUrls)('should allow and return valid URL: %s', (url) => {
    expect(validateAndSanitizeUrl(url)).toBe(url);
  });

  test.each(disallowedUrls)('should reject and return null for disallowed URL: %s', (url) => {
    expect(validateAndSanitizeUrl(url)).toBeNull();
  });

  it('should return null for malformed URL strings', () => {
    expect(validateAndSanitizeUrl('not-a-valid-url')).toBeNull();
    expect(validateAndSanitizeUrl('http://')).toBeNull();
  });

  describe('isInternalIP', () => {
    it('should correctly identify internal and private IP addresses', () => {
      expect(isInternalIP('192.168.1.1')).toBe(true);
      expect(isInternalIP('10.0.0.1')).toBe(true);
      expect(isInternalIP('172.16.0.1')).toBe(true);
      expect(isInternalIP('127.0.0.1')).toBe(true);
      expect(isInternalIP('localhost')).toBe(true);
      expect(isInternalIP('8.8.8.8')).toBe(false); // Google's DNS
    });
  });
});