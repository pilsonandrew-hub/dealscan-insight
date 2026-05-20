/**
 * Minimal CSV-focused input sanitization utility.
 * Current live surface is limited to UploadInterface CSV content checks.
 */

class InputSanitizer {
  private readonly SQL_INJECTION_PATTERNS = [
    /(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|UNION|SCRIPT)\b)/gi,
    /('|''|"|""|--|#|\/\*)/gi,
    /(\b(OR|AND)\b\s*=)/gi,
    /(\b(WAITFOR|DELAY)\b)/gi,
    /(xp_|sp_)/gi,
  ];

  private readonly XSS_PATTERNS = [
    /<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi,
    /javascript:/gi,
    /on\w+\s*=/gi,
    /<iframe\b[^>]*>/gi,
    /<object\b[^>]*>/gi,
    /<embed\b[^>]*>/gi,
    /<form\b[^>]*>/gi,
    /expression\s*\(/gi,
    /vbscript:/gi,
    /data:text\/html/gi,
  ];

  private readonly HTML_ENTITIES: Record<string, string> = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#x27;',
    '/': '&#x2F;',
    '`': '&#96;'
  };

  private sanitizeCell(input: string): { sanitized: string; threats: string[] } {
    const threats: string[] = [];
    let sanitized = input;

    for (const pattern of this.SQL_INJECTION_PATTERNS) {
      if (pattern.test(sanitized)) {
        threats.push('Potential SQL injection detected');
        sanitized = sanitized.replace(pattern, '');
      }
    }

    for (const pattern of this.XSS_PATTERNS) {
      if (pattern.test(sanitized)) {
        threats.push('Potential XSS attack detected');
        sanitized = sanitized.replace(pattern, '');
      }
    }

    sanitized = this.encodeHTMLEntities(sanitized);
    sanitized = sanitized.replace(/\s+/g, ' ').trim();

    return { sanitized, threats };
  }

  sanitizeCSVData(data: string[][]): { sanitized: string[][]; threats: string[] } {
    const threats: string[] = [];
    const sanitized = data.map((row, rowIndex) =>
      row.map((cell, cellIndex) => {
        if (typeof cell === 'string' && /^[=+\-@]/.test(cell.trim())) {
          threats.push(`Row ${rowIndex + 1}, Column ${cellIndex + 1}: Potential CSV injection`);
          return `'${cell}`;
        }

        const result = this.sanitizeCell(String(cell));

        if (result.threats.length > 0) {
          threats.push(`Row ${rowIndex + 1}, Column ${cellIndex + 1}: ${result.threats.join(', ')}`);
        }

        return result.sanitized;
      })
    );

    return { sanitized, threats };
  }

  private encodeHTMLEntities(str: string): string {
    return str.replace(/[&<>"'`/]/g, match => this.HTML_ENTITIES[match] || match);
  }
}

export const inputSanitizer = new InputSanitizer();
