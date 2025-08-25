/**
 * Data Contracts and Validation - Phase 3 Data Quality
 * AJV JSON Schema validation with VIN checksums and field validation
 */

import Ajv, { ValidateFunction } from 'ajv';
import addFormats from 'ajv-formats';
import productionLogger from '@/utils/productionLogger';
import { validators } from '@/utils/normalize';

// Vehicle listing data contract
interface VehicleListing {
  vin: string;
  year: number;
  make: string;
  model: string;
  mileage: number;
  price: number;
  location: string;
  condition?: 'excellent' | 'good' | 'fair' | 'poor' | 'salvage' | 'unknown';
  auction_end?: string;
  title_status?: 'clean' | 'salvage' | 'rebuilt' | 'lemon' | 'flood' | 'unknown';
  engine?: string;
  transmission?: 'automatic' | 'manual' | 'cvt' | 'unknown';
  drivetrain?: 'fwd' | 'rwd' | 'awd' | '4wd' | 'unknown';
  fuel_type?: 'gasoline' | 'diesel' | 'hybrid' | 'electric' | 'unknown';
  exterior_color?: string;
  interior_color?: string;
  features?: string[];
  damage?: string[];
  inspection_notes?: string;
  seller_type?: 'dealer' | 'government' | 'insurance' | 'individual';
  listing_source: string;
  listing_url: string;
  images?: string[];
  created_at: string;
  updated_at: string;
}

interface ValidationResult {
  valid: boolean;
  errors: Array<{
    field: string;
    message: string;
    value?: any;
    severity: 'error' | 'warning';
  }>;
  warnings: Array<{
    field: string;
    message: string;
    value?: any;
  }>;
  score: number; // 0-100, data quality score
}

interface ContractStats {
  totalValidations: number;
  passedValidations: number;
  failedValidations: number;
  passRate: number;
  commonErrors: Record<string, number>;
  averageScore: number;
}

// JSON Schema for VehicleListing  
const vehicleListingSchema = {
  type: 'object',
  properties: {
    vin: { 
      type: 'string', 
      pattern: '^[A-HJ-NPR-Z0-9]{17}$',
      description: 'Valid 17-character VIN'
    },
    year: { 
      type: 'integer', 
      minimum: 1900, 
      maximum: new Date().getFullYear() + 2,
      description: 'Vehicle year between 1900 and current year + 2'
    },
    make: { 
      type: 'string', 
      minLength: 1, 
      maxLength: 50,
      description: 'Vehicle manufacturer'
    },
    model: { 
      type: 'string', 
      minLength: 1, 
      maxLength: 50,
      description: 'Vehicle model'
    },
    mileage: { 
      type: 'integer', 
      minimum: 0, 
      maximum: 1000000,
      description: 'Vehicle mileage in miles'
    },
    price: { 
      type: 'number', 
      minimum: 0, 
      maximum: 10000000,
      description: 'Vehicle price in USD'
    },
    location: { 
      type: 'string', 
      minLength: 1, 
      maxLength: 200,
      description: 'Vehicle location'
    },
    condition: { 
      type: 'string', 
      enum: ['excellent', 'good', 'fair', 'poor', 'salvage', 'unknown'],
      nullable: true 
    },
    auction_end: { 
      type: 'string', 
      format: 'date-time',
      nullable: true 
    },
    title_status: { 
      type: 'string', 
      enum: ['clean', 'salvage', 'rebuilt', 'lemon', 'flood', 'unknown'],
      nullable: true 
    },
    engine: { type: 'string', maxLength: 100, nullable: true },
    transmission: { 
      type: 'string', 
      enum: ['automatic', 'manual', 'cvt', 'unknown'],
      nullable: true 
    },
    drivetrain: { 
      type: 'string', 
      enum: ['fwd', 'rwd', 'awd', '4wd', 'unknown'],
      nullable: true 
    },
    fuel_type: { 
      type: 'string', 
      enum: ['gasoline', 'diesel', 'hybrid', 'electric', 'unknown'],
      nullable: true 
    },
    exterior_color: { type: 'string', maxLength: 50, nullable: true },
    interior_color: { type: 'string', maxLength: 50, nullable: true },
    features: { 
      type: 'array', 
      items: { type: 'string', maxLength: 100 },
      maxItems: 50,
      nullable: true 
    },
    damage: { 
      type: 'array', 
      items: { type: 'string', maxLength: 200 },
      maxItems: 20,
      nullable: true 
    },
    inspection_notes: { type: 'string', maxLength: 5000, nullable: true },
    seller_type: { 
      type: 'string', 
      enum: ['dealer', 'government', 'insurance', 'individual'],
      nullable: true 
    },
    listing_source: { 
      type: 'string', 
      minLength: 1, 
      maxLength: 100,
      description: 'Source website or platform'
    },
    listing_url: { 
      type: 'string', 
      format: 'uri',
      description: 'URL to original listing'
    },
    images: { 
      type: 'array', 
      items: { type: 'string', format: 'uri' },
      maxItems: 50,
      nullable: true 
    },
    created_at: { 
      type: 'string', 
      format: 'date-time',
      description: 'ISO timestamp when record was created'
    },
    updated_at: { 
      type: 'string', 
      format: 'date-time',
      description: 'ISO timestamp when record was last updated'
    }
  },
  required: ['vin', 'year', 'make', 'model', 'mileage', 'price', 'location', 'listing_source', 'listing_url', 'created_at', 'updated_at'],
  additionalProperties: false
};

export class DataContractValidator {
  private ajv: Ajv;
  private vehicleValidator: ValidateFunction;
  private stats: ContractStats;

  constructor() {
    this.ajv = new Ajv({ allErrors: true, strict: false });
    addFormats(this.ajv);

    // Add custom VIN checksum validation
    this.ajv.addKeyword({
      keyword: 'vinChecksum',
      type: 'string',
      compile: () => (vin: string) => this.validateVINChecksum(vin)
    });

    this.vehicleValidator = this.ajv.compile(vehicleListingSchema);
    
    this.stats = {
      totalValidations: 0,
      passedValidations: 0,
      failedValidations: 0,
      passRate: 0,
      commonErrors: {},
      averageScore: 0
    };

    productionLogger.info('Data contract validator initialized');
  }

  /**
   * Validate vehicle listing against contract
   */
  async validateVehicleListing(data: any): Promise<ValidationResult> {
    this.stats.totalValidations++;
    
    const errors: ValidationResult['errors'] = [];
    const warnings: ValidationResult['warnings'] = [];
    let score = 100;

    try {
      // Basic schema validation
      const isValid = this.vehicleValidator(data);
      
      if (!isValid && this.vehicleValidator.errors) {
        for (const error of this.vehicleValidator.errors) {
          const field = error.instancePath.substring(1) || error.params?.missingProperty || 'root';
          const message = `${error.keyword}: ${error.message}`;
          
          errors.push({
            field,
            message,
            value: error.data,
            severity: 'error'
          });

          // Track common errors
          this.stats.commonErrors[message] = (this.stats.commonErrors[message] || 0) + 1;
          
          score -= 10; // Deduct points for schema violations
        }
      }

      // Advanced validations
      await this.performAdvancedValidations(data, errors, warnings);

      // Calculate final score
      score = Math.max(0, score - (warnings.length * 2)); // Deduct 2 points per warning
      score = Math.max(0, score - (errors.length * 10)); // Already deducted, but ensure consistency

      const result: ValidationResult = {
        valid: errors.length === 0,
        errors,
        warnings,
        score
      };

      // Update stats
      if (result.valid) {
        this.stats.passedValidations++;
      } else {
        this.stats.failedValidations++;
      }
      
      this.stats.passRate = (this.stats.passedValidations / this.stats.totalValidations) * 100;
      this.stats.averageScore = ((this.stats.averageScore * (this.stats.totalValidations - 1)) + score) / this.stats.totalValidations;

      productionLogger.debug('Vehicle listing validation completed', {
        valid: result.valid,
        errors: errors.length,
        warnings: warnings.length,
        score
      });

      return result;

    } catch (error) {
      productionLogger.error('Validation failed with exception', {
        vin: data?.vin
      }, error as Error);

      return {
        valid: false,
        errors: [{
          field: 'validation',
          message: 'Validation failed due to processing error',
          severity: 'error'
        }],
        warnings: [],
        score: 0
      };
    }
  }

  /**
   * Perform advanced validations beyond schema
   */
  private async performAdvancedValidations(
    data: any, 
    errors: ValidationResult['errors'], 
    warnings: ValidationResult['warnings']
  ): Promise<void> {
    
    // VIN checksum validation
    if (data.vin && !this.validateVINChecksum(data.vin)) {
      errors.push({
        field: 'vin',
        message: 'VIN checksum validation failed',
        value: data.vin,
        severity: 'error'
      });
    }

    // Year validation with make/model context
    if (data.year && data.make) {
      const yearValidation = this.validateYearForMake(data.year, data.make);
      if (!yearValidation.valid) {
        warnings.push({
          field: 'year',
          message: yearValidation.message,
          value: data.year
        });
      }
    }

    // Price reasonableness check
    if (data.price && data.year && data.mileage) {
      const priceValidation = this.validatePriceReasonableness(data.price, data.year, data.mileage, data.make);
      if (!priceValidation.valid) {
        warnings.push({
          field: 'price',
          message: priceValidation.message,
          value: data.price
        });
      }
    }

    // Mileage reasonableness
    if (data.mileage && data.year) {
      const mileageValidation = this.validateMileageReasonableness(data.mileage, data.year);
      if (!mileageValidation.valid) {
        warnings.push({
          field: 'mileage',
          message: mileageValidation.message,
          value: data.mileage
        });
      }
    }

    // Location format validation
    if (data.location && !this.validateLocationFormat(data.location)) {
      warnings.push({
        field: 'location',
        message: 'Location format may be inconsistent',
        value: data.location
      });
    }

    // URL accessibility check
    if (data.listing_url && !await this.validateUrlAccessibility(data.listing_url)) {
      warnings.push({
        field: 'listing_url',
        message: 'URL may not be accessible',
        value: data.listing_url
      });
    }
  }

  /**
   * Validate VIN checksum using standard algorithm
   */
  private validateVINChecksum(vin: string): boolean {
    if (!vin || vin.length !== 17) return false;

    // VIN character values
    const values: Record<string, number> = {
      'A': 1, 'B': 2, 'C': 3, 'D': 4, 'E': 5, 'F': 6, 'G': 7, 'H': 8,
      'J': 1, 'K': 2, 'L': 3, 'M': 4, 'N': 5, 'P': 7, 'R': 9,
      'S': 2, 'T': 3, 'U': 4, 'V': 5, 'W': 6, 'X': 7, 'Y': 8, 'Z': 9,
      '0': 0, '1': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9
    };

    // Position weights
    const weights = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2];
    
    let sum = 0;
    for (let i = 0; i < 17; i++) {
      if (i === 8) continue; // Skip check digit position
      
      const char = vin[i];
      const value = values[char];
      
      if (value === undefined) return false;
      
      sum += value * weights[i];
    }

    const checkDigit = sum % 11;
    const expectedCheckChar = checkDigit === 10 ? 'X' : checkDigit.toString();
    
    return vin[8] === expectedCheckChar;
  }

  /**
   * Validate year is reasonable for make
   */
  private validateYearForMake(year: number, make: string): { valid: boolean; message: string } {
    const makeFirstYears: Record<string, number> = {
      'TESLA': 2008,
      'RIVIAN': 2021,
      'LUCID': 2021,
      'FISKER': 2022
    };

    const makeUpper = make.toUpperCase();
    const firstYear = makeFirstYears[makeUpper];

    if (firstYear && year < firstYear) {
      return {
        valid: false,
        message: `${make} vehicles not produced before ${firstYear}`
      };
    }

    return { valid: true, message: '' };
  }

  /**
   * Validate price reasonableness
   */
  private validatePriceReasonableness(price: number, year: number, mileage: number, make?: string): { valid: boolean; message: string } {
    const currentYear = new Date().getFullYear();
    const age = currentYear - year;

    // Very rough price validation
    if (price < 500 && age < 20) {
      return {
        valid: false,
        message: 'Price unusually low for vehicle age'
      };
    }

    if (price > 500000 && (!make || !['FERRARI', 'LAMBORGHINI', 'MCLAREN', 'BUGATTI'].includes(make.toUpperCase()))) {
      return {
        valid: false,
        message: 'Price unusually high for make'
      };
    }

    return { valid: true, message: '' };
  }

  /**
   * Validate mileage reasonableness
   */
  private validateMileageReasonableness(mileage: number, year: number): { valid: boolean; message: string } {
    const currentYear = new Date().getFullYear();
    const age = currentYear - year;
    const avgMilesPerYear = 12000;
    const expectedMileage = age * avgMilesPerYear;

    if (mileage > expectedMileage * 3) {
      return {
        valid: false,
        message: 'Mileage unusually high for vehicle age'
      };
    }

    if (mileage < 1000 && age > 5) {
      return {
        valid: false,
        message: 'Mileage unusually low for vehicle age'
      };
    }

    return { valid: true, message: '' };
  }

  /**
   * Validate location format
   */
  private validateLocationFormat(location: string): boolean {
    // Check for common US location patterns
    const patterns = [
      /^[A-Za-z\s]+,\s*[A-Z]{2}$/,        // City, ST
      /^[A-Za-z\s]+,\s*[A-Z]{2}\s+\d{5}$/, // City, ST ZIP
      /^\d{5}$/                            // ZIP only
    ];

    return patterns.some(pattern => pattern.test(location.trim()));
  }

  /**
   * Validate URL accessibility (simplified)
   */
  private async validateUrlAccessibility(url: string): Promise<boolean> {
    try {
      // Simple URL format check for now
      new URL(url);
      return true;
    } catch {
      return false;
    }
  }

  /**
   * Get validation statistics
   */
  getStats(): ContractStats {
    return { ...this.stats };
  }

  /**
   * Reset statistics
   */
  resetStats(): void {
    this.stats = {
      totalValidations: 0,
      passedValidations: 0,
      failedValidations: 0,
      passRate: 0,
      commonErrors: {},
      averageScore: 0
    };
  }

  /**
   * Get top validation errors
   */
  getTopErrors(limit: number = 10): Array<{ error: string; count: number }> {
    return Object.entries(this.stats.commonErrors)
      .sort(([, a], [, b]) => b - a)
      .slice(0, limit)
      .map(([error, count]) => ({ error, count }));
  }
}

// Global validator instance
export const dataContractValidator = new DataContractValidator();