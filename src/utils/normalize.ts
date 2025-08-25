/**
 * Data Normalization Utilities - Phase 1 Core Fix
 * Canonical normalization with proper regex handling
 */

// Alias mappings for common field variations
const FIELD_ALIASES: Record<string, string> = {
  // Vehicle identifiers
  'vin_number': 'vin',
  'vehicle_identification_number': 'vin',
  'chassis_number': 'vin',
  
  // Price fields
  'price': 'current_price',
  'asking_price': 'current_price',
  'listing_price': 'current_price',
  'sale_price': 'current_price',
  'current_bid': 'current_price',
  
  // Year fields
  'model_year': 'year',
  'year_made': 'year',
  'manufacture_year': 'year',
  
  // Mileage fields
  'odometer': 'mileage',
  'miles': 'mileage',
  'kilometers': 'mileage',
  'km': 'mileage',
  
  // Location fields
  'location': 'address',
  'city_state': 'address',
  'auction_location': 'address',
  
  // Title fields
  'vehicle_title': 'title',
  'listing_title': 'title',
  'vehicle_name': 'title',
  'description': 'title'
};

/**
 * Canonical string normalization
 * Handles whitespace, case, and special characters
 */
export function canonical(input: string): string {
  if (!input || typeof input !== 'string') {
    return '';
  }
  
  return input
    .trim()
    .replace(/\s+/g, ' ')  // Multiple whitespace to single space
    .replace(/[^\w\s-]/g, '') // Remove special chars except hyphens
    .toLowerCase()
    .replace(/\s/g, '-'); // Spaces to hyphens
}

/**
 * Normalize field names using alias mappings
 */
export function normalizeFieldName(fieldName: string): string {
  const canonical_name = canonical(fieldName);
  return FIELD_ALIASES[canonical_name] || canonical_name;
}

/**
 * Normalize VIN - uppercase, remove spaces/dashes
 */
export function normalizeVIN(vin: string): string {
  if (!vin) return '';
  
  return vin
    .toString()
    .replace(/[\s-]/g, '') // Remove spaces and dashes
    .toUpperCase()
    .substring(0, 17); // VIN is max 17 characters
}

/**
 * Normalize price values - extract numeric value
 */
export function normalizePrice(price: string | number): number {
  if (typeof price === 'number') return Math.max(0, price);
  if (!price) return 0;
  
  // Extract numeric value from string
  const numericString = price.toString().replace(/[^\d.]/g, '');
  const parsed = parseFloat(numericString);
  
  return isNaN(parsed) ? 0 : Math.max(0, parsed);
}

/**
 * Normalize year - ensure 4-digit year in valid range
 */
export function normalizeYear(year: string | number): number {
  const numYear = typeof year === 'number' ? year : parseInt(year?.toString() || '0');
  const currentYear = new Date().getFullYear();
  
  // Valid range: 1900 to current year + 2
  if (numYear >= 1900 && numYear <= currentYear + 2) {
    return numYear;
  }
  
  return 0; // Invalid year
}

/**
 * Normalize mileage - handle various units
 */
export function normalizeMileage(mileage: string | number, unit?: string): number {
  let numMileage = typeof mileage === 'number' ? mileage : 
                   parseFloat(mileage?.toString().replace(/[^\d.]/g, '') || '0');
  
  if (isNaN(numMileage) || numMileage < 0) return 0;
  
  // Convert kilometers to miles if needed
  const unitLower = unit?.toLowerCase() || '';
  if (unitLower.includes('km') || unitLower.includes('kilometer')) {
    numMileage = numMileage * 0.621371; // km to miles
  }
  
  return Math.round(numMileage);
}

/**
 * Normalize address - clean and standardize
 */
export function normalizeAddress(address: string): string {
  if (!address) return '';
  
  return address
    .trim()
    .replace(/\s+/g, ' ') // Multiple spaces to single
    .replace(/,\s*,/g, ',') // Remove double commas
    .replace(/^,|,$/, '') // Remove leading/trailing commas
    .toLowerCase()
    .split(' ')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1)) // Title case
    .join(' ');
}

/**
 * Extract and normalize vehicle make/model
 */
export function normalizeMakeModel(makeModel: string): { make: string; model: string } {
  if (!makeModel) return { make: '', model: '' };
  
  const parts = makeModel.trim().split(/\s+/);
  
  if (parts.length === 1) {
    return { make: parts[0], model: '' };
  }
  
  return {
    make: parts[0],
    model: parts.slice(1).join(' ')
  };
}

/**
 * Normalize data object with field aliasing
 */
export function normalizeDataObject(data: Record<string, any>): Record<string, any> {
  const normalized: Record<string, any> = {};
  
  for (const [key, value] of Object.entries(data)) {
    const normalizedKey = normalizeFieldName(key);
    
    // Apply field-specific normalization
    switch (normalizedKey) {
      case 'vin':
        normalized[normalizedKey] = normalizeVIN(value);
        break;
      case 'current_price':
        normalized[normalizedKey] = normalizePrice(value);
        break;
      case 'year':
        normalized[normalizedKey] = normalizeYear(value);
        break;
      case 'mileage':
        normalized[normalizedKey] = normalizeMileage(value);
        break;
      case 'address':
        normalized[normalizedKey] = normalizeAddress(value);
        break;
      default:
        normalized[normalizedKey] = value;
    }
  }
  
  return normalized;
}

/**
 * Validation helpers
 */
export const validators = {
  isValidVIN: (vin: string): boolean => {
    return /^[A-HJ-NPR-Z0-9]{17}$/.test(vin);
  },
  
  isValidYear: (year: number): boolean => {
    const currentYear = new Date().getFullYear();
    return year >= 1900 && year <= currentYear + 2;
  },
  
  isValidPrice: (price: number): boolean => {
    return price >= 0 && price <= 10000000; // Max $10M
  },
  
  isValidMileage: (mileage: number): boolean => {
    return mileage >= 0 && mileage <= 1000000; // Max 1M miles
  }
};