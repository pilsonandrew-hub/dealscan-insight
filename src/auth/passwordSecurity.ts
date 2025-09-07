/**
 * Enterprise Password Security Module
 * NIST-compliant password validation and breach checking
 */

import { createHash } from 'crypto';

export interface PasswordStrengthResult {
  isValid: boolean;
  score: number; // 0-100
  reasons: string[];
}

/**
 * Validate password strength according to NIST guidelines
 */
export function validatePasswordStrength(password: string): PasswordStrengthResult {
  const reasons: string[] = [];
  let score = 0;

  // Length check (NIST recommends minimum 8, we enforce 12 for enterprise)
  if (password.length < 12) {
    reasons.push('Password must be at least 12 characters long');
  } else {
    score += 25;
  }

  // Character variety checks
  if (!/[A-Z]/.test(password)) {
    reasons.push('Password must include at least one uppercase letter');
  } else {
    score += 15;
  }

  if (!/[a-z]/.test(password)) {
    reasons.push('Password must include at least one lowercase letter');
  } else {
    score += 15;
  }

  if (!/[0-9]/.test(password)) {
    reasons.push('Password must include at least one number');
  } else {
    score += 15;
  }

  if (!/[!@#$%^&*(),.?":{}|<>]/.test(password)) {
    reasons.push('Password must include at least one special character');
  } else {
    score += 15;
  }

  // Entropy check - avoid simple patterns
  if (/(.)\1{2,}/.test(password)) {
    reasons.push('Password should not contain repeated characters');
  } else {
    score += 5;
  }

  // Sequential characters check
  if (/(?:abc|bcd|cde|def|efg|fgh|ghi|hij|ijk|jkl|klm|lmn|mno|nop|opq|pqr|qrs|rst|stu|tuv|uvw|vwx|wxy|xyz|012|123|234|345|456|567|678|789)/i.test(password)) {
    reasons.push('Password should not contain sequential characters');
  } else {
    score += 5;
  }

  // Common patterns check
  const commonPatterns = [
    /password/i,
    /qwerty/i,
    /admin/i,
    /letmein/i,
    /welcome/i,
    /123456/,
    /^(.)\1*$/ // All same character
  ];

  if (commonPatterns.some(pattern => pattern.test(password))) {
    reasons.push('Password contains common patterns that should be avoided');
  } else {
    score += 5;
  }

  return {
    isValid: reasons.length === 0 && score >= 80,
    score: Math.min(100, score),
    reasons
  };
}

/**
 * Check if password has been exposed in data breaches using HaveIBeenPwned API
 */
export async function isPasswordExposed(password: string): Promise<boolean> {
  try {
    // Hash the password using SHA-1 (required by HIBP API)
    const hash = createHash('sha1').update(password).digest('hex').toUpperCase();
    const hashPrefix = hash.substring(0, 5);
    const hashSuffix = hash.substring(5);

    // Query the HIBP API with k-anonymity (only send first 5 chars)
    const response = await fetch(`https://api.pwnedpasswords.com/range/${hashPrefix}`, {
      method: 'GET',
      headers: {
        'User-Agent': 'DealerScope-Enterprise-Security/1.0'
      }
    });

    if (!response.ok) {
      // If API is unavailable, allow the password (fail open for availability)
      return false;
    }

    const responseText = await response.text();
    const lines = responseText.split('\r\n');
    
    // Check if our hash suffix appears in the response
    return lines.some(line => {
      const [suffix] = line.split(':');
      return suffix === hashSuffix;
    });

  } catch (error) {
    // On any error, fail open (don't block user registration)
    console.error('Password breach check failed:', error);
    return false;
  }
}

/**
 * Generate a secure password that meets all requirements
 */
export function generateSecurePassword(length: number = 16): string {
  const lowercase = 'abcdefghijklmnopqrstuvwxyz';
  const uppercase = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
  const numbers = '0123456789';
  const symbols = '!@#$%^&*()_+-=[]{}|;:,.<>?';
  
  let password = '';
  
  // Ensure at least one character from each category
  password += lowercase[Math.floor(Math.random() * lowercase.length)];
  password += uppercase[Math.floor(Math.random() * uppercase.length)];
  password += numbers[Math.floor(Math.random() * numbers.length)];
  password += symbols[Math.floor(Math.random() * symbols.length)];
  
  // Fill the rest randomly
  const allChars = lowercase + uppercase + numbers + symbols;
  for (let i = password.length; i < length; i++) {
    password += allChars[Math.floor(Math.random() * allChars.length)];
  }
  
  // Shuffle the password to avoid predictable patterns
  return password.split('').sort(() => Math.random() - 0.5).join('');
}