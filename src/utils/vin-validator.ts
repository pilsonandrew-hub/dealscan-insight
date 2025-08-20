/**
 * Comprehensive VIN validation following ISO 3779 standard
 * Includes check digit validation and decoding capabilities
 */

interface VINDecoded {
  isValid: boolean;
  wmi: string;        // World Manufacturer Identifier
  vds: string;        // Vehicle Descriptor Section  
  vis: string;        // Vehicle Identifier Section
  year?: number;
  errors: string[];
}

export class VINValidator {
  private static readonly VIN_LENGTH = 17;
  private static readonly INVALID_CHARS = /[IOQ]/i;
  private static readonly VALID_CHARS = /^[A-HJ-NPR-Z0-9]+$/i;

  // Check digit calculation weights
  private static readonly WEIGHTS = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2];
  
  // Character to numeric value mapping
  private static readonly CHAR_VALUES: { [key: string]: number } = {
    'A': 1, 'B': 2, 'C': 3, 'D': 4, 'E': 5, 'F': 6, 'G': 7, 'H': 8,
    'J': 1, 'K': 2, 'L': 3, 'M': 4, 'N': 5, 'P': 7, 'R': 9,
    'S': 2, 'T': 3, 'U': 4, 'V': 5, 'W': 6, 'X': 7, 'Y': 8, 'Z': 9,
    '0': 0, '1': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9
  };

  // Model year mapping for 10th position
  private static readonly YEAR_CODES: { [key: string]: number } = {
    'A': 2010, 'B': 2011, 'C': 2012, 'D': 2013, 'E': 2014, 'F': 2015, 'G': 2016, 'H': 2017,
    'J': 2018, 'K': 2019, 'L': 2020, 'M': 2021, 'N': 2022, 'P': 2023, 'R': 2024, 'S': 2025,
    'T': 2026, 'U': 2027, 'V': 2028, 'W': 2029, 'X': 2030, 'Y': 2031, 'Z': 2032,
    '1': 2001, '2': 2002, '3': 2003, '4': 2004, '5': 2005, '6': 2006, '7': 2007, '8': 2008, '9': 2009
  };

  static validate(vin: string): VINDecoded {
    const errors: string[] = [];
    const vinUpper = vin.toUpperCase().trim();

    // Basic format validation
    if (vinUpper.length !== this.VIN_LENGTH) {
      errors.push(`VIN must be exactly ${this.VIN_LENGTH} characters`);
    }

    if (this.INVALID_CHARS.test(vinUpper)) {
      errors.push('VIN cannot contain letters I, O, or Q');
    }

    if (!this.VALID_CHARS.test(vinUpper)) {
      errors.push('VIN contains invalid characters');
    }

    if (errors.length > 0) {
      return {
        isValid: false,
        wmi: '',
        vds: '',
        vis: '',
        errors
      };
    }

    // Check digit validation
    const isCheckDigitValid = this.validateCheckDigit(vinUpper);
    if (!isCheckDigitValid) {
      errors.push('Invalid check digit - VIN may be corrupted');
    }

    // Extract components
    const wmi = vinUpper.substring(0, 3);    // World Manufacturer Identifier
    const vds = vinUpper.substring(3, 9);    // Vehicle Descriptor Section
    const vis = vinUpper.substring(9, 17);   // Vehicle Identifier Section

    // Decode model year
    const yearChar = vinUpper.charAt(9);
    const year = this.YEAR_CODES[yearChar];

    return {
      isValid: errors.length === 0,
      wmi,
      vds, 
      vis,
      year,
      errors
    };
  }

  private static validateCheckDigit(vin: string): boolean {
    let sum = 0;
    
    for (let i = 0; i < 17; i++) {
      const char = vin.charAt(i);
      const value = this.CHAR_VALUES[char] || 0;
      sum += value * this.WEIGHTS[i];
    }

    const remainder = sum % 11;
    const checkDigit = remainder === 10 ? 'X' : remainder.toString();
    
    return checkDigit === vin.charAt(8);
  }

  static getManufacturer(wmi: string): string {
    // Basic manufacturer mapping - can be expanded
    const manufacturers: { [key: string]: string } = {
      '1FT': 'Ford',
      '1GC': 'Chevrolet', 
      '1HD': 'Harley-Davidson',
      'JHM': 'Honda',
      'KMH': 'Hyundai',
      'WBA': 'BMW',
      'WVW': 'Volkswagen'
    };

    return manufacturers[wmi] || 'Unknown';
  }

  static isGovAuctionVIN(vin: string): boolean {
    const decoded = this.validate(vin);
    if (!decoded.isValid) return false;

    // Government fleet vehicles often have specific WMI patterns
    const govPatterns = [
      '1FT', // Ford trucks (common in gov fleets)
      '1GC', // Chevrolet (common in gov fleets) 
      '2C3'  // Chrysler (common in police fleets)
    ];

    return govPatterns.some(pattern => decoded.wmi.startsWith(pattern));
  }
}