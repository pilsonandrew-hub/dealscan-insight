/**
 * Input Validation and Sanitization Service
 * Prevents XSS, SQL injection, and other input-based attacks
 */

interface ValidationRule {
  required?: boolean;
  minLength?: number;
  maxLength?: number;
  pattern?: RegExp;
  customValidator?: (value: string) => boolean;
  sanitize?: boolean;
}

interface ValidationResult {
  isValid: boolean;
  errors: string[];
  sanitizedValue?: string;
}

class InputValidator {
  private static instance: InputValidator;

  private constructor() {}

  public static getInstance(): InputValidator {
    if (!InputValidator.instance) {
      InputValidator.instance = new InputValidator();
    }
    return InputValidator.instance;
  }

  /**
   * Sanitize HTML to prevent XSS attacks
   */
  public sanitizeHtml(input: string): string {
    return input
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#x27;')
      .replace(/\//g, '&#x2F;');
  }

  /**
   * Sanitize SQL input to prevent injection
   */
  public sanitizeSql(input: string): string {
    return input
      .replace(/'/g, "''")
      .replace(/;/g, '')
      .replace(/--/g, '')
      .replace(/\/\*/g, '')
      .replace(/\*\//g, '');
  }

  /**
   * Validate VIN number
   */
  public validateVin(vin: string): ValidationResult {
    const errors: string[] = [];
    
    if (!vin) {
      errors.push('VIN is required');
    } else if (vin.length !== 17) {
      errors.push('VIN must be exactly 17 characters');
    } else if (!/^[A-HJ-NPR-Z0-9]{17}$/i.test(vin)) {
      errors.push('VIN contains invalid characters');
    } else {
      // Check VIN checksum (simplified)
      const checkDigit = this.calculateVinCheckDigit(vin);
      if (checkDigit !== vin[8]) {
        errors.push('Invalid VIN checksum');
      }
    }

    return {
      isValid: errors.length === 0,
      errors,
      sanitizedValue: vin.toUpperCase()
    };
  }

  /**
   * Validate email address
   */
  public validateEmail(email: string): ValidationResult {
    const errors: string[] = [];
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

    if (!email) {
      errors.push('Email is required');
    } else if (!emailRegex.test(email)) {
      errors.push('Invalid email format');
    } else if (email.length > 254) {
      errors.push('Email is too long');
    }

    return {
      isValid: errors.length === 0,
      errors,
      sanitizedValue: email.toLowerCase().trim()
    };
  }

  /**
   * Validate file upload
   */
  public validateFileUpload(file: File, allowedTypes: string[], maxSize: number): ValidationResult {
    const errors: string[] = [];

    if (!file) {
      errors.push('File is required');
      return { isValid: false, errors };
    }

    // Check file type
    if (!allowedTypes.includes(file.type)) {
      errors.push(`File type ${file.type} is not allowed. Allowed types: ${allowedTypes.join(', ')}`);
    }

    // Check file size
    if (file.size > maxSize) {
      errors.push(`File size ${(file.size / 1024 / 1024).toFixed(2)}MB exceeds maximum allowed size ${(maxSize / 1024 / 1024).toFixed(2)}MB`);
    }

    // Check file name for malicious patterns
    const dangerousPatterns = ['.exe', '.bat', '.cmd', '.scr', '.pif', '.jar', '.vbs', '.js'];
    if (dangerousPatterns.some(pattern => file.name.toLowerCase().includes(pattern))) {
      errors.push('File type is potentially dangerous');
    }

    return {
      isValid: errors.length === 0,
      errors
    };
  }

  /**
   * Generic string validation
   */
  public validateString(value: string, rules: ValidationRule): ValidationResult {
    const errors: string[] = [];
    let sanitizedValue = value;

    // Required check
    if (rules.required && (!value || value.trim().length === 0)) {
      errors.push('This field is required');
    }

    if (value) {
      // Length checks
      if (rules.minLength && value.length < rules.minLength) {
        errors.push(`Minimum length is ${rules.minLength} characters`);
      }

      if (rules.maxLength && value.length > rules.maxLength) {
        errors.push(`Maximum length is ${rules.maxLength} characters`);
      }

      // Pattern check
      if (rules.pattern && !rules.pattern.test(value)) {
        errors.push('Invalid format');
      }

      // Custom validator
      if (rules.customValidator && !rules.customValidator(value)) {
        errors.push('Custom validation failed');
      }

      // Sanitization
      if (rules.sanitize) {
        sanitizedValue = this.sanitizeHtml(value);
      }
    }

    return {
      isValid: errors.length === 0,
      errors,
      sanitizedValue
    };
  }

  /**
   * Validate number input
   */
  public validateNumber(value: number | string, min?: number, max?: number): ValidationResult {
    const errors: string[] = [];
    const numValue = typeof value === 'string' ? parseFloat(value) : value;

    if (isNaN(numValue)) {
      errors.push('Must be a valid number');
    } else {
      if (min !== undefined && numValue < min) {
        errors.push(`Minimum value is ${min}`);
      }

      if (max !== undefined && numValue > max) {
        errors.push(`Maximum value is ${max}`);
      }
    }

    return {
      isValid: errors.length === 0,
      errors,
      sanitizedValue: numValue.toString()
    };
  }

  private calculateVinCheckDigit(vin: string): string {
    const transliterationTable: { [key: string]: number } = {
      'A': 1, 'B': 2, 'C': 3, 'D': 4, 'E': 5, 'F': 6, 'G': 7, 'H': 8,
      'J': 1, 'K': 2, 'L': 3, 'M': 4, 'N': 5, 'P': 7, 'R': 9,
      'S': 2, 'T': 3, 'U': 4, 'V': 5, 'W': 6, 'X': 7, 'Y': 8, 'Z': 9
    };

    const weights = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2];
    let sum = 0;

    for (let i = 0; i < 17; i++) {
      let value = 0;
      const char = vin[i].toUpperCase();
      
      if (char >= '0' && char <= '9') {
        value = parseInt(char);
      } else {
        value = transliterationTable[char] || 0;
      }
      
      sum += value * weights[i];
    }

    const remainder = sum % 11;
    return remainder === 10 ? 'X' : remainder.toString();
  }
}

export const inputValidator = InputValidator.getInstance();
export default inputValidator;