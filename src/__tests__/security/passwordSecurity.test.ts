import { describe, it, expect, vi, beforeEach } from 'vitest';
import { validatePasswordStrength, isPasswordExposed } from '../../auth/passwordSecurity';

// Mock the fetch call to HIBP API
global.fetch = vi.fn();

describe('Password Security Module', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('validatePasswordStrength', () => {
    it('should accept a strong password', () => {
      const result = validatePasswordStrength('StrongP@ssw0rd123');
      expect(result.isValid).toBe(true);
      expect(result.reasons).toHaveLength(0);
    });

    it('should reject passwords that are too short', () => {
      const result = validatePasswordStrength('Sh0rtp@ss');
      expect(result.isValid).toBe(false);
      expect(result.reasons).toContain('Password must be at least 12 characters long');
    });

    it('should reject passwords without an uppercase letter', () => {
      const result = validatePasswordStrength('nouppercasep@ssw0rd');
      expect(result.isValid).toBe(false);
      expect(result.reasons).toContain('Password must include at least one uppercase letter');
    });

    it('should reject passwords without a lowercase letter', () => {
      const result = validatePasswordStrength('NOLOWERCASEP@SSW0RD');
      expect(result.isValid).toBe(false);
      expect(result.reasons).toContain('Password must include at least one lowercase letter');
    });

    it('should reject passwords without a number', () => {
      const result = validatePasswordStrength('NoNumbersP@ssword');
      expect(result.isValid).toBe(false);
      expect(result.reasons).toContain('Password must include at least one number');
    });

    it('should reject passwords without special characters', () => {
      const result = validatePasswordStrength('NoSpecialChars123');
      expect(result.isValid).toBe(false);
      expect(result.reasons).toContain('Password must include at least one special character');
    });

    it('should reject passwords with common patterns', () => {
      const result = validatePasswordStrength('Password123!');
      expect(result.isValid).toBe(false);
      expect(result.reasons).toContain('Password contains common patterns that should be avoided');
    });
  });

  describe('isPasswordExposed', () => {
    it('should return true if the password hash is found in the HIBP database', async () => {
      // SHA-1 for "password" is 5BAA61E4C9B93F3F0682250B6CF8331B7EE68FD8
      const pwnedHashSuffix = 'A61E4C9B93F3F0682250B6CF8331B7EE68FD8';
      (fetch as any).mockResolvedValue({
        ok: true,
        text: () => Promise.resolve(`someotherhash:1\r\n${pwnedHashSuffix}:12345\r\nanotherhash:2`),
      });

      const result = await isPasswordExposed('password');
      expect(result).toBe(true);
      expect(fetch).toHaveBeenCalledWith(
        'https://api.pwnedpasswords.com/range/5BAA6',
        expect.any(Object)
      );
    });

    it('should return false if the password hash is not found', async () => {
      (fetch as any).mockResolvedValue({
        ok: true,
        text: () => Promise.resolve(`someotherhash:1\r\nanotherhash:2`),
      });

      const result = await isPasswordExposed('a-very-unique-and-safe-password');
      expect(result).toBe(false);
    });

    it('should return false if the API call fails', async () => {
      (fetch as any).mockResolvedValue({ ok: false });
      const result = await isPasswordExposed('password');
      expect(result).toBe(false);
    });
  });
});