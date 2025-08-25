/**
 * Data Normalization Utilities - Consistent canonical forms
 * Fixes dedupe misses by ensuring consistent data representation
 */

/**
 * Normalize text to canonical form for consistent deduplication
 */
export function canonical(text: string | null | undefined): string {
  if (!text) return '';
  
  // Unicode normalization to canonical composition
  let normalized = text.normalize('NFKC').trim().toLowerCase();
  
  // Collapse multiple whitespace to single space
  normalized = normalized.replace(/\s+/g, ' ');
  
  // Normalize different dash types to standard hyphen
  normalized = normalized.replace(/[–—]/g, '-');
  
  // Remove common noise characters
  normalized = normalized.replace(/['"'""`]/g, '');
  
  // Normalize common abbreviations
  const abbreviations: Record<string, string> = {
    'w/': 'with',
    'w/o': 'without',
    '&': 'and',
    '+': 'plus',
    '#': 'number',
    '@': 'at'
  };
  
  for (const [abbrev, full] of Object.entries(abbreviations)) {
    normalized = normalized.replace(new RegExp(`\\b${abbrev.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b`, 'g'), full);
  }
  
  return normalized.trim();
}

/**
 * Normalize vehicle model name for consistent matching
 */
export function normalizeModel(model: string | null | undefined): string {
  const normalized = canonical(model);
  
  // Common model name normalizations
  const modelMappings: Record<string, string> = {
    'f-150': 'f150',
    'f-250': 'f250',
    'f-350': 'f350',
    'e-class': 'eclass',
    'c-class': 'cclass',
    's-class': 'sclass',
    'x-trail': 'xtrail',
    'x-terra': 'xterra'
  };
  
  let result = normalized;
  for (const [variant, standard] of Object.entries(modelMappings)) {
    result = result.replace(new RegExp(`\\b${variant}\\b`, 'g'), standard);
  }
  
  return result;
}

/**
 * Normalize VIN to uppercase, remove spaces/dashes
 */
export function normalizeVIN(vin: string | null | undefined): string {
  if (!vin) return '';
  return vin.replace(/[\s-]/g, '').toUpperCase();
}

/**
 * Normalize location string for consistent matching
 */
export function normalizeLocation(location: string | null | undefined): string {
  const normalized = canonical(location);
  
  // Common location abbreviations
  const locationMappings: Record<string, string> = {
    'st': 'street',
    'ave': 'avenue',
    'blvd': 'boulevard',
    'rd': 'road',
    'dr': 'drive',
    'ct': 'court',
    'pl': 'place',
    'n': 'north',
    's': 'south',
    'e': 'east',
    'w': 'west'
  };
  
  let result = normalized;
  for (const [abbrev, full] of Object.entries(locationMappings)) {
    result = result.replace(new RegExp(`\\b${abbrev}\\b`, 'g'), full);
  }
  
  return result;
}

/**
 * Normalize monetary amount (remove currency symbols, normalize decimals)
 */
export function normalizeAmount(amount: string | number | null | undefined): number {
  if (typeof amount === 'number') return amount;
  if (!amount) return 0;
  
  // Remove currency symbols and whitespace
  const cleaned = String(amount).replace(/[$,\s]/g, '');
  
  // Parse as float
  const parsed = parseFloat(cleaned);
  return isNaN(parsed) ? 0 : parsed;
}

/**
 * Normalize mileage (handle various formats)
 */
export function normalizeMileage(mileage: string | number | null | undefined): number {
  if (typeof mileage === 'number') return mileage;
  if (!mileage) return 0;
  
  // Remove common mileage suffixes and separators
  const cleaned = String(mileage)
    .toLowerCase()
    .replace(/[,\s]/g, '')
    .replace(/mi(les?)?$/, '')
    .replace(/k$/, '000');
  
  const parsed = parseFloat(cleaned);
  return isNaN(parsed) ? 0 : parsed;
}

/**
 * Comprehensive normalization for vehicle data
 */
export function normalizeVehicleData(data: Record<string, any>): Record<string, any> {
  return {
    ...data,
    vin: normalizeVIN(data.vin),
    make: canonical(data.make),
    model: normalizeModel(data.model),
    location: normalizeLocation(data.location),
    current_bid: normalizeAmount(data.current_bid),
    price: normalizeAmount(data.price),
    mileage: normalizeMileage(data.mileage),
    title: canonical(data.title),
    description: canonical(data.description),
    condition: canonical(data.condition)
  };
}