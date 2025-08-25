/**
 * Data Validation Utilities
 * AJV-based validation for vehicle data and extraction outputs
 */

import Ajv from 'ajv';
import addFormats from 'ajv-formats';
import vehicleSchema from '../../schemas/vehicle.schema.json';
import provenanceSchema from '../../schemas/provenance.schema.json';

// Initialize AJV with formats
const ajv = new Ajv({ 
  allErrors: true,
  removeAdditional: true,
  useDefaults: true,
  coerceTypes: 'array'
});
addFormats(ajv);

// Compile schemas
const validateVehicle = ajv.compile(vehicleSchema);
const validateProvenance = ajv.compile(provenanceSchema);

export interface ValidationResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
  sanitized?: any;
}

export interface FieldValidationResult extends ValidationResult {
  confidence: number;
  anomalyScore: number;
}

/**
 * Vehicle Data Validator
 */
export class VehicleValidator {
  
  /**
   * Validates complete vehicle object
   */
  static validate(data: any): ValidationResult {
    const cloned = JSON.parse(JSON.stringify(data));
    const valid = validateVehicle(cloned);
    
    return {
      valid,
      errors: validateVehicle.errors?.map(err => 
        `${err.instancePath || 'root'}: ${err.message}`) || [],
      warnings: this.getWarnings(cloned),
      sanitized: valid ? cloned : undefined
    };
  }

  /**
   * Validates individual fields with business logic
   */
  static validateField(fieldName: string, value: any, context?: any): FieldValidationResult {
    const result: FieldValidationResult = {
      valid: true,
      errors: [],
      warnings: [],
      confidence: 1.0,
      anomalyScore: 0.0
    };

    switch (fieldName) {
      case 'vin':
        return this.validateVIN(value);
      
      case 'year':
        return this.validateYear(value);
      
      case 'mileage':
        return this.validateMileage(value, context?.year);
      
      case 'price':
        return this.validatePrice(value, context);
      
      case 'make':
      case 'model':
        return this.validateStringField(value, fieldName);
      
      default:
        return result;
    }
  }

  /**
   * VIN validation with checksum
   */
  private static validateVIN(vin: any): FieldValidationResult {
    const result: FieldValidationResult = {
      valid: true,
      errors: [],
      warnings: [],
      confidence: 1.0,
      anomalyScore: 0.0
    };

    if (!vin) {
      result.warnings.push('VIN is missing');
      result.confidence = 0.8;
      return result;
    }

    if (typeof vin !== 'string') {
      result.valid = false;
      result.errors.push('VIN must be a string');
      return result;
    }

    const vinRegex = /^[A-HJ-NPR-Z0-9]{17}$/;
    if (!vinRegex.test(vin)) {
      result.valid = false;
      result.errors.push('VIN must be exactly 17 characters (A-Z, 0-9, excluding I, O, Q)');
      return result;
    }

    // Basic checksum validation (simplified)
    const weights = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2];
    const values: { [key: string]: number } = {
      '0': 0, '1': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9,
      'A': 1, 'B': 2, 'C': 3, 'D': 4, 'E': 5, 'F': 6, 'G': 7, 'H': 8,
      'J': 1, 'K': 2, 'L': 3, 'M': 4, 'N': 5, 'P': 7, 'R': 9, 'S': 2,
      'T': 3, 'U': 4, 'V': 5, 'W': 6, 'X': 7, 'Y': 8, 'Z': 9
    };

    let sum = 0;
    for (let i = 0; i < 17; i++) {
      if (i === 8) continue; // Skip check digit position
      sum += (values[vin[i]] || 0) * weights[i];
    }

    const checkDigit = vin[8];
    const expectedCheck = sum % 11 === 10 ? 'X' : String(sum % 11);
    
    if (checkDigit !== expectedCheck) {
      result.warnings.push('VIN checksum validation failed');
      result.confidence = 0.7;
      result.anomalyScore = 0.3;
    }

    return result;
  }

  /**
   * Year validation with business rules
   */
  private static validateYear(year: any): FieldValidationResult {
    const result: FieldValidationResult = {
      valid: true,
      errors: [],
      warnings: [],
      confidence: 1.0,
      anomalyScore: 0.0
    };

    if (!year) {
      result.valid = false;
      result.errors.push('Year is required');
      return result;
    }

    const numYear = Number(year);
    if (!Number.isInteger(numYear)) {
      result.valid = false;
      result.errors.push('Year must be an integer');
      return result;
    }

    const currentYear = new Date().getFullYear();
    if (numYear < 1886) {
      result.valid = false;
      result.errors.push('Year cannot be before 1886 (first automobile)');
      return result;
    }

    if (numYear > currentYear + 2) {
      result.valid = false;
      result.errors.push(`Year cannot be more than 2 years in the future (${currentYear + 2})`);
      return result;
    }

    // Anomaly detection for very old or very new vehicles
    if (numYear < 1990) {
      result.warnings.push('Very old vehicle - verify accuracy');
      result.anomalyScore = Math.min(0.5, (1990 - numYear) / 50);
    }

    if (numYear > currentYear) {
      result.warnings.push('Future model year');
      result.confidence = 0.9;
    }

    return result;
  }

  /**
   * Mileage validation with year-based anomaly detection
   */
  private static validateMileage(mileage: any, year?: number): FieldValidationResult {
    const result: FieldValidationResult = {
      valid: true,
      errors: [],
      warnings: [],
      confidence: 1.0,
      anomalyScore: 0.0
    };

    if (mileage === null || mileage === undefined) {
      result.warnings.push('Mileage is missing');
      result.confidence = 0.8;
      return result;
    }

    const numMileage = Number(mileage);
    if (!Number.isInteger(numMileage) || numMileage < 0) {
      result.valid = false;
      result.errors.push('Mileage must be a non-negative integer');
      return result;
    }

    if (numMileage > 999999) {
      result.valid = false;
      result.errors.push('Mileage cannot exceed 999,999');
      return result;
    }

    // Anomaly detection based on age
    if (year) {
      const currentYear = new Date().getFullYear();
      const age = currentYear - year;
      const expectedMileage = age * 12000; // Average 12k miles/year
      const deviation = Math.abs(numMileage - expectedMileage) / expectedMileage;

      if (deviation > 2) { // More than 200% deviation
        result.anomalyScore = Math.min(0.8, deviation / 3);
        result.warnings.push(`Unusual mileage for ${year} vehicle (expected ~${expectedMileage.toLocaleString()})`);
      }

      if (numMileage < 100 && age > 1) {
        result.warnings.push('Extremely low mileage - verify accuracy');
        result.anomalyScore = Math.max(result.anomalyScore, 0.4);
      }
    }

    return result;
  }

  /**
   * Price validation with market-based anomaly detection
   */
  private static validatePrice(price: any, context?: any): FieldValidationResult {
    const result: FieldValidationResult = {
      valid: true,
      errors: [],
      warnings: [],
      confidence: 1.0,
      anomalyScore: 0.0
    };

    if (!price || typeof price !== 'object') {
      result.valid = false;
      result.errors.push('Price must be an object with amount and currency');
      return result;
    }

    const { amount, currency, type } = price;

    if (typeof amount !== 'number' || amount < 0) {
      result.valid = false;
      result.errors.push('Price amount must be a non-negative number');
      return result;
    }

    if (amount > 10000000) {
      result.valid = false;
      result.errors.push('Price amount cannot exceed $10,000,000');
      return result;
    }

    // Anomaly detection based on year and mileage
    if (context?.year && context?.make) {
      if (amount < 100) {
        result.warnings.push('Extremely low price - verify accuracy');
        result.anomalyScore = 0.6;
      }

      if (amount > 500000) {
        result.warnings.push('Very high price - verify accuracy');
        result.anomalyScore = Math.min(0.4, amount / 1000000);
      }

      // Year-based price validation
      const currentYear = new Date().getFullYear();
      const age = currentYear - context.year;
      
      if (age > 20 && amount > 100000) {
        result.warnings.push('High price for older vehicle');
        result.anomalyScore = Math.max(result.anomalyScore, 0.3);
      }
    }

    return result;
  }

  /**
   * String field validation
   */
  private static validateStringField(value: any, fieldName: string): FieldValidationResult {
    const result: FieldValidationResult = {
      valid: true,
      errors: [],
      warnings: [],
      confidence: 1.0,
      anomalyScore: 0.0
    };

    if (!value || typeof value !== 'string') {
      result.valid = false;
      result.errors.push(`${fieldName} must be a non-empty string`);
      return result;
    }

    if (value.trim().length === 0) {
      result.valid = false;
      result.errors.push(`${fieldName} cannot be empty`);
      return result;
    }

    // Check for suspicious patterns
    if (/[<>{}[\]"'\\]/.test(value)) {
      result.warnings.push(`${fieldName} contains unusual characters`);
      result.confidence = 0.8;
      result.anomalyScore = 0.2;
    }

    if (value.length > 100) {
      result.warnings.push(`${fieldName} is unusually long`);
      result.confidence = 0.9;
    }

    return result;
  }

  /**
   * Get business logic warnings
   */
  private static getWarnings(data: any): string[] {
    const warnings: string[] = [];

    // Check for missing optional but important fields
    if (!data.vin) warnings.push('VIN is missing - may limit verification');
    if (!data.mileage) warnings.push('Mileage is missing - affects valuation');
    if (!data.images?.length) warnings.push('No images available');
    if (!data.condition?.grade) warnings.push('Condition grade not specified');

    // Check for data consistency
    if (data.condition?.title_status === 'salvage' && data.price?.amount > 50000) {
      warnings.push('High price for salvage title vehicle');
    }

    if (data.year > 2020 && data.mileage > 100000) {
      warnings.push('High mileage for recent model year');
    }

    return warnings;
  }
}

/**
 * Provenance Data Validator
 */
export class ProvenanceValidator {
  
  static validate(data: any): ValidationResult {
    const cloned = JSON.parse(JSON.stringify(data));
    const valid = validateProvenance(cloned);
    
    return {
      valid,
      errors: validateProvenance.errors?.map(err => 
        `${err.instancePath || 'root'}: ${err.message}`) || [],
      warnings: this.getWarnings(cloned),
      sanitized: valid ? cloned : undefined
    };
  }

  private static getWarnings(data: any): string[] {
    const warnings: string[] = [];

    if (data.confidence < 0.7) {
      warnings.push('Low confidence extraction');
    }

    if (data.retries > 2) {
      warnings.push('Multiple retry attempts required');
    }

    if (data.limits_hit?.timeout) {
      warnings.push('Extraction hit timeout limit');
    }

    if (data.extraction_strategy === 'llm' && !data.costs?.llm_tokens) {
      warnings.push('LLM usage without cost tracking');
    }

    return warnings;
  }
}

/**
 * Batch validation utility
 */
export class BatchValidator {
  
  static validateVehicleBatch(vehicles: any[]): {
    valid: any[];
    invalid: { data: any; errors: string[] }[];
    summary: {
      total: number;
      valid: number;
      invalid: number;
      warnings: number;
    };
  } {
    const valid: any[] = [];
    const invalid: { data: any; errors: string[] }[] = [];
    let totalWarnings = 0;

    for (const vehicle of vehicles) {
      const result = VehicleValidator.validate(vehicle);
      
      if (result.valid && result.sanitized) {
        valid.push(result.sanitized);
        totalWarnings += result.warnings.length;
      } else {
        invalid.push({
          data: vehicle,
          errors: result.errors
        });
      }
    }

    return {
      valid,
      invalid,
      summary: {
        total: vehicles.length,
        valid: valid.length,
        invalid: invalid.length,
        warnings: totalWarnings
      }
    };
  }
}

export { validateVehicle, validateProvenance };