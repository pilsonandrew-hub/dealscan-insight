/**
 * Enterprise Data Validation Framework
 * Type-safe validation with comprehensive error reporting
 */

import Ajv, { Schema, ValidateFunction } from 'ajv';
import addFormats from 'ajv-formats';

// Global AJV instance with enterprise configuration
const ajv = new Ajv({
  allErrors: true,
  removeAdditional: true, // Remove extra properties for security
  coerceTypes: false,     // Strict type checking
  strict: true,          // Strict mode for production
});

addFormats(ajv);

export interface ValidationError {
  field: string;
  message: string;
  value?: any;
}

export class ValidationException extends Error {
  public readonly errors: ValidationError[];

  constructor(errors: ValidationError[]) {
    const message = `Validation failed: ${errors.map(e => `${e.field}: ${e.message}`).join(', ')}`;
    super(message);
    this.name = 'ValidationException';
    this.errors = errors;
  }
}

/**
 * Validate data against schema and throw on failure
 */
export function validateOrThrow<T>(data: any, schema: Schema): T {
  const validate = ajv.compile(schema);
  const isValid = validate(data);
  
  if (!isValid) {
    const errors: ValidationError[] = (validate.errors || []).map(error => ({
      field: error.instancePath || error.schemaPath || 'unknown',
      message: error.message || 'Validation error',
      value: error.data
    }));
    
    throw new ValidationException(errors);
  }

  return data as T;
}

/**
 * Validate data and return result without throwing
 */
export function validateSafe<T>(data: any, schema: Schema): {
  isValid: boolean;
  data?: T;
  errors?: ValidationError[];
} {
  try {
    const validatedData = validateOrThrow<T>(data, schema);
    return { isValid: true, data: validatedData };
  } catch (error) {
    if (error instanceof ValidationException) {
      return { isValid: false, errors: error.errors };
    }
    return { 
      isValid: false, 
      errors: [{ field: 'unknown', message: error instanceof Error ? error.message : 'Unknown validation error' }] 
    };
  }
}

/**
 * Create a reusable validator function
 */
export function createValidator<T>(schema: Schema): ValidateFunction<T> {
  return ajv.compile(schema);
}

export { ajv };