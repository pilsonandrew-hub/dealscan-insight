// CSV security utilities retained only for the live upload-security path.

const DANGEROUS_PREFIXES = ['=', '+', '-', '@', '\t', '\r'];

/**
 * Check if file content might contain dangerous formulas
 */
export function detectDangerousFormulas(content: string): string[] {
  const lines = content.split('\n');
  const dangerous: string[] = [];

  lines.forEach((line, index) => {
    const cells = line.split(',');
    cells.forEach((cell, cellIndex) => {
      const trimmed = cell.trim().replace(/^["']|["']$/g, '');

      if (DANGEROUS_PREFIXES.some(prefix => trimmed.startsWith(prefix))) {
        dangerous.push(`Line ${index + 1}, Column ${cellIndex + 1}: Potential formula "${trimmed}"`);
      }
    });
  });

  return dangerous;
}

// Enhanced security check with the currently live upload validation.
export function validateCSVSecurity(file: File): {
  isSecure: boolean;
  issues: string[];
  riskLevel: 'low' | 'medium' | 'high';
} {
  const issues: string[] = [];
  let riskLevel: 'low' | 'medium' | 'high' = 'low';

  const MAX_FILE_SIZE = 50 * 1024 * 1024;
  if (file.size > MAX_FILE_SIZE) {
    issues.push('File size exceeds maximum allowed (50MB)');
    riskLevel = 'high';
  }

  const suspiciousPatterns = [
    /\.\./,
    /[<>:"|?*]/,
    /\.(exe|bat|sh|ps1|cmd)$/i,
  ];

  if (suspiciousPatterns.some(pattern => pattern.test(file.name))) {
    issues.push('Suspicious filename detected');
    riskLevel = 'high';
  }

  const allowedTypes = [
    'text/csv',
    'application/csv',
    'text/plain',
    'application/vnd.ms-excel',
  ];

  if (!allowedTypes.includes(file.type) && !file.name.toLowerCase().endsWith('.csv')) {
    issues.push('Invalid file type - only CSV files allowed');
    riskLevel = 'medium';
  }

  return {
    isSecure: issues.length === 0,
    issues,
    riskLevel,
  };
}
