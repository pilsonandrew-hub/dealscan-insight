/**
 * Data validation pipeline
 * Inspired by the title filtering and data validation in the bootstrap script
 */

import { VINValidator } from './vin-validator';
import { auditLogger } from './audit-logger';
import { performanceMonitor } from './performance-monitor';

export interface ValidationRule<T = any> {
  name: string;
  description: string;
  severity: 'error' | 'warning' | 'info';
  validate: (data: T, context?: ValidationContext) => ValidationResult;
}

export interface ValidationResult {
  valid: boolean;
  message?: string;
  details?: Record<string, any>;
  correctedValue?: any;
}

export interface ValidationContext {
  rowIndex?: number;
  fieldName?: string;
  metadata?: Record<string, any>;
}

export interface ValidationReport {
  totalRecords: number;
  validRecords: number;
  invalidRecords: number;
  warningRecords: number;
  errors: ValidationError[];
  warnings: ValidationWarning[];
  summary: {
    overallValid: boolean;
    validationScore: number;
    criticalErrors: number;
    recommendations: string[];
  };
}

export interface ValidationError {
  rowIndex: number;
  field: string;
  rule: string;
  message: string;
  severity: 'error' | 'warning';
  originalValue: any;
  suggestedValue?: any;
}

export interface ValidationWarning extends ValidationError {
  severity: 'warning';
}

// Common validation rules
export const commonValidationRules = {
  // VIN validation
  vin: {
    name: 'vin_format',
    description: 'Validates VIN format and check digit',
    severity: 'error' as const,
    validate: (vin: string) => {
      if (!vin || typeof vin !== 'string') {
        return { valid: false, message: 'VIN is required' };
      }

      const result = VINValidator.validate(vin.trim().toUpperCase());
      return {
        valid: result.isValid,
        message: result.errors.join(', ') || 'Valid VIN',
        details: {
          wmi: result.wmi,
          year: result.year,
          manufacturer: VINValidator.getManufacturer(result.wmi)
        },
        correctedValue: vin.trim().toUpperCase()
      };
    }
  },

  // Price validation
  price: {
    name: 'price_range',
    description: 'Validates price is within reasonable range',
    severity: 'warning' as const,
    validate: (price: number, context?: ValidationContext) => {
      if (typeof price !== 'number' || isNaN(price)) {
        return { valid: false, message: 'Price must be a valid number' };
      }

      if (price <= 0) {
        return { valid: false, message: 'Price must be positive' };
      }

      if (price < 1000) {
        return { 
          valid: true, 
          message: 'Price seems unusually low for a vehicle',
          details: { suggestedMinimum: 1000 }
        };
      }

      if (price > 200000) {
        return { 
          valid: true, 
          message: 'Price seems unusually high - verify if this is a luxury/specialty vehicle',
          details: { suggestedMaximum: 200000 }
        };
      }

      return { valid: true, message: 'Price is within normal range' };
    }
  },

  // Year validation
  year: {
    name: 'model_year',
    description: 'Validates model year is reasonable',
    severity: 'error' as const,
    validate: (year: number) => {
      const currentYear = new Date().getFullYear();
      const minYear = 1980;
      const maxYear = currentYear + 2;

      if (typeof year !== 'number' || isNaN(year)) {
        return { valid: false, message: 'Year must be a valid number' };
      }

      if (year < minYear) {
        return { 
          valid: false, 
          message: `Year ${year} is too old (minimum: ${minYear})` 
        };
      }

      if (year > maxYear) {
        return { 
          valid: false, 
          message: `Year ${year} is too far in the future (maximum: ${maxYear})` 
        };
      }

      return { valid: true, message: 'Valid model year' };
    }
  },

  // Mileage validation
  mileage: {
    name: 'mileage_range',
    description: 'Validates mileage is reasonable for vehicle age',
    severity: 'warning' as const,
    validate: (mileage: number, context?: ValidationContext) => {
      if (typeof mileage !== 'number' || isNaN(mileage)) {
        return { valid: false, message: 'Mileage must be a valid number' };
      }

      if (mileage < 0) {
        return { valid: false, message: 'Mileage cannot be negative' };
      }

      if (mileage > 500000) {
        return { 
          valid: true, 
          message: 'Extremely high mileage - verify accuracy',
          details: { suggestedMaximum: 300000 }
        };
      }

      // Check against vehicle age if available
      if (context?.metadata?.year) {
        const vehicleAge = new Date().getFullYear() - context.metadata.year;
        const expectedMaxMileage = vehicleAge * 15000; // 15k miles per year
        
        if (mileage > expectedMaxMileage * 2) {
          return {
            valid: true,
            message: `High mileage for ${vehicleAge} year old vehicle`,
            details: { 
              expectedRange: `0-${expectedMaxMileage.toLocaleString()}`,
              actualMileage: mileage.toLocaleString()
            }
          };
        }
      }

      return { valid: true, message: 'Mileage appears reasonable' };
    }
  },

  // State validation
  state: {
    name: 'state_code',
    description: 'Validates US state code',
    severity: 'error' as const,
    validate: (state: string) => {
      if (!state || typeof state !== 'string') {
        return { valid: false, message: 'State is required' };
      }

      const validStates = [
        'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
        'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
        'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
        'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
        'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY', 'DC'
      ];

      const normalizedState = state.trim().toUpperCase();
      
      if (validStates.includes(normalizedState)) {
        return { 
          valid: true, 
          message: 'Valid state code',
          correctedValue: normalizedState
        };
      }

      return { 
        valid: false, 
        message: `Invalid state code: ${state}`,
        details: { validStates: validStates.slice(0, 10).concat(['...']) }
      };
    }
  },

  // Title status validation (inspired by title_filter.py)
  titleStatus: {
    name: 'title_status',
    description: 'Validates title status and flags problematic titles',
    severity: 'warning' as const,
    validate: (title: string) => {
      if (!title || typeof title !== 'string') {
        return { valid: true, message: 'No title status provided' };
      }

      const problematicTerms = [
        'salvage', 'flood', 'junk', 'lemon', 'rebuilt', 'reconstructed',
        'fire', 'hail', 'theft', 'vandalism', 'collision'
      ];

      const titleLower = title.toLowerCase();
      const foundProblems = problematicTerms.filter(term => 
        titleLower.includes(term)
      );

      if (foundProblems.length > 0) {
        return {
          valid: true,
          message: `Title has potential issues: ${foundProblems.join(', ')}`,
          details: { 
            problematicTerms: foundProblems,
            recommendation: 'Review carefully - may affect resale value'
          }
        };
      }

      return { valid: true, message: 'Title appears clean' };
    }
  }
};

export class DataValidator {
  private rules: Map<string, ValidationRule> = new Map();

  constructor() {
    // Register common rules
    Object.entries(commonValidationRules).forEach(([key, rule]) => {
      this.registerRule(key, rule);
    });
  }

  // Register a validation rule
  registerRule(field: string, rule: ValidationRule) {
    this.rules.set(field, rule);
    auditLogger.log(
      'validation_rule_registered',
      'system',
      'info',
      { field, ruleName: rule.name }
    );
  }

  // Validate a single record
  validateRecord(record: Record<string, any>, rowIndex?: number): ValidationError[] {
    const errors: ValidationError[] = [];

    Object.entries(record).forEach(([field, value]) => {
      const rule = this.rules.get(field);
      if (!rule) return;

      const context: ValidationContext = {
        rowIndex,
        fieldName: field,
        metadata: record
      };

      try {
        const result = rule.validate(value, context);
        
        if (!result.valid || (result.valid && result.message && result.message !== `Valid ${field}` && !result.message.includes('appears reasonable') && !result.message.includes('is within normal range') && !result.message.includes('Valid'))) {
          errors.push({
            rowIndex: rowIndex || 0,
            field,
            rule: rule.name,
            message: result.message || 'Validation failed',
            severity: result.valid ? 'warning' : (rule.severity === 'info' ? 'warning' : rule.severity),
            originalValue: value,
            suggestedValue: result.correctedValue
          });
        }
      } catch (error) {
        errors.push({
          rowIndex: rowIndex || 0,
          field,
          rule: rule.name,
          message: `Validation rule failed: ${error instanceof Error ? error.message : 'Unknown error'}`,
          severity: 'error',
          originalValue: value
        });
      }
    });

    return errors;
  }

  // Validate multiple records
  async validateDataset(records: Record<string, any>[]): Promise<ValidationReport> {
    const timer = performanceMonitor.startTimer('data_validation');
    
    auditLogger.log(
      'dataset_validation_start',
      'data',
      'info',
      { recordCount: records.length, rulesCount: this.rules.size }
    );

    const allErrors: ValidationError[] = [];
    let validCount = 0;

    records.forEach((record, index) => {
      const recordErrors = this.validateRecord(record, index);
      allErrors.push(...recordErrors);
      
      const hasErrors = recordErrors.some(e => e.severity === 'error');
      if (!hasErrors) validCount++;
    });

    const errors = allErrors.filter(e => e.severity === 'error');
    const warnings = allErrors.filter(e => e.severity === 'warning') as ValidationWarning[];
    
    const validationScore = records.length > 0 ? 
      Math.round((validCount / records.length) * 100) : 100;

    const recommendations = this.generateRecommendations(errors, warnings);

    const report: ValidationReport = {
      totalRecords: records.length,
      validRecords: validCount,
      invalidRecords: records.length - validCount,
      warningRecords: warnings.length,
      errors,
      warnings,
      summary: {
        overallValid: errors.length === 0,
        validationScore,
        criticalErrors: errors.length,
        recommendations
      }
    };

    timer.end(errors.length === 0);
    
    auditLogger.log(
      'dataset_validation_complete',
      'data',
      errors.length === 0 ? 'info' : 'warning',
      {
        totalRecords: records.length,
        validRecords: validCount,
        errorCount: errors.length,
        warningCount: warnings.length,
        validationScore
      }
    );

    return report;
  }

  private generateRecommendations(errors: ValidationError[], warnings: ValidationWarning[]): string[] {
    const recommendations: string[] = [];

    // Group errors by type
    const errorsByRule = errors.reduce((acc, error) => {
      acc[error.rule] = (acc[error.rule] || 0) + 1;
      return acc;
    }, {} as Record<string, number>);

    // Generate recommendations based on common errors
    Object.entries(errorsByRule).forEach(([rule, count]) => {
      if (count > 1) {
        switch (rule) {
          case 'vin_format':
            recommendations.push(`${count} VIN format errors found - verify VIN data source`);
            break;
          case 'price_range':
            recommendations.push(`${count} price validation issues - check pricing data accuracy`);
            break;
          case 'model_year':
            recommendations.push(`${count} invalid model years - verify year field mapping`);
            break;
          case 'state_code':
            recommendations.push(`${count} invalid state codes - standardize state format`);
            break;
        }
      }
    });

    // Add warnings-based recommendations
    if (warnings.length > errors.length * 2) {
      recommendations.push('High number of warnings - consider reviewing data quality standards');
    }

    return recommendations;
  }

  // Get validation statistics
  getStats() {
    return {
      rulesRegistered: this.rules.size,
      availableRules: Array.from(this.rules.keys())
    };
  }
}

// Global validator instance
export const dataValidator = new DataValidator();