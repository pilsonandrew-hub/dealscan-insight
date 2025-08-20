/**
 * CSV Security utilities to prevent formula injection attacks
 * Based on the Python CSVProcessor security measures
 */

// Dangerous prefixes that could be used for formula injection
const DANGEROUS_PREFIXES = ["=", "+", "-", "@", "\t", "\r"];

/**
 * Sanitize CSV cell value to prevent formula injection
 * Prefixes dangerous characters with a single quote
 */
export function sanitizeCSVValue(value: string): string {
  if (!value || typeof value !== 'string') {
    return value;
  }

  const trimmed = value.trim();
  
  // Check if value starts with any dangerous prefix
  for (const prefix of DANGEROUS_PREFIXES) {
    if (trimmed.startsWith(prefix)) {
      return "'" + trimmed;
    }
  }
  
  return trimmed;
}

/**
 * Validate that required vehicle data fields are present
 */
export function validateVehicleData(data: Record<string, string>): boolean {
  const required = ["VIN", "Make", "Model", "Year", "SalePrice", "Date"];
  return required.every(field => data[field] && data[field].trim() !== '');
}

/**
 * Check if file content might contain dangerous formulas
 */
export function detectDangerousFormulas(content: string): string[] {
  const lines = content.split('\n');
  const dangerous: string[] = [];
  
  lines.forEach((line, index) => {
    const cells = line.split(',');
    cells.forEach((cell, cellIndex) => {
      const trimmed = cell.trim().replace(/^["']|["']$/g, ''); // Remove quotes
      
      if (DANGEROUS_PREFIXES.some(prefix => trimmed.startsWith(prefix))) {
        dangerous.push(`Line ${index + 1}, Column ${cellIndex + 1}: Potential formula "${trimmed}"`);
      }
    });
  });
  
  return dangerous;
}

/**
 * Sanitize an entire CSV content string
 */
export function sanitizeCSVContent(content: string): string {
  const lines = content.split('\n');
  
  return lines.map(line => {
    const cells = line.split(',');
    return cells.map(cell => {
      // Handle quoted cells
      const hasQuotes = cell.startsWith('"') && cell.endsWith('"');
      const cleanCell = hasQuotes ? cell.slice(1, -1) : cell;
      const sanitized = sanitizeCSVValue(cleanCell);
      return hasQuotes ? `"${sanitized}"` : sanitized;
    }).join(',');
  }).join('\n');
}

/**
 * Validate file size and type restrictions
 */
export function validateFileUpload(file: File): { valid: boolean; error?: string } {
  const maxSize = 50 * 1024 * 1024; // 50MB
  const allowedExtensions = ['.csv', '.xlsx', '.xls'];
  const allowedMimeTypes = [
    'text/csv',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/csv'
  ];

  if (file.size > maxSize) {
    return {
      valid: false,
      error: `File size exceeds 50MB limit (${(file.size / 1024 / 1024).toFixed(1)}MB)`
    };
  }

  const extension = '.' + file.name.split('.').pop()?.toLowerCase();
  if (!allowedExtensions.includes(extension)) {
    return {
      valid: false,
      error: 'File type not supported. Please upload CSV or Excel files only.'
    };
  }

  // MIME type validation (can be empty for some files)
  if (file.type && !allowedMimeTypes.includes(file.type)) {
    return {
      valid: false,
      error: 'Invalid file type. Please upload CSV or Excel files only.'
    };
  }

  return { valid: true };
}