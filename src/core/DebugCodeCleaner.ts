/**
 * Debug Code Cleanup Utility
 * Removes all console.* statements and debug code from components
 */

import { logger } from '../core/UnifiedLogger';
import { configService } from '../core/UnifiedConfigService';

interface DebugCodePattern {
  pattern: RegExp;
  replacement: string;
  description: string;
}

class DebugCodeCleaner {
  private patterns: DebugCodePattern[] = [
    {
      pattern: /console\.(log|debug|info|warn|error)\([^)]*\);?\s*/g,
      replacement: '',
      description: 'Console statements'
    },
    {
      pattern: /\/\*\s*DEBUG:.*?\*\//gs,
      replacement: '',
      description: 'Debug comments'
    },
    {
      pattern: /\/\/\s*DEBUG:.*$/gm,
      replacement: '',
      description: 'Debug line comments'
    },
    {
      pattern: /if\s*\(\s*process\.env\.NODE_ENV\s*===\s*['"]development['"]\s*\)\s*\{[^}]*\}/g,
      replacement: '',
      description: 'Development-only code blocks'
    },
    {
      pattern: /\b__DEV__\s*&&[^;]+;?/g,
      replacement: '',
      description: '__DEV__ checks'
    },
    {
      pattern: /debugger;?\s*/g,
      replacement: '',
      description: 'Debugger statements'
    }
  ];

  cleanCode(sourceCode: string): { cleaned: string; removedCount: number; details: string[] } {
    let cleaned = sourceCode;
    let totalRemoved = 0;
    const details: string[] = [];

    for (const { pattern, replacement, description } of this.patterns) {
      const matches = cleaned.match(pattern);
      if (matches) {
        cleaned = cleaned.replace(pattern, replacement);
        totalRemoved += matches.length;
        details.push(`${description}: ${matches.length} instances`);
      }
    }

    // Clean up empty lines and excessive whitespace
    cleaned = cleaned
      .replace(/\n\s*\n\s*\n/g, '\n\n') // Remove excessive empty lines
      .replace(/[ \t]+$/gm, '') // Remove trailing whitespace
      .trim();

    return {
      cleaned,
      removedCount: totalRemoved,
      details
    };
  }

  // Safe console replacement for production
  static setupProductionConsole(): void {
    if (typeof window === 'undefined') return;

    const originalConsole = { ...console };

    // Replace console methods with logger equivalents
    console.log = (...args) => {
      if (configService.isDevelopment) {
        originalConsole.log(...args);
      }
      logger.debug(args.join(' '));
    };

    console.info = (...args) => {
      if (configService.isDevelopment) {
        originalConsole.info(...args);
      }
      logger.info(args.join(' '));
    };

    console.warn = (...args) => {
      if (configService.isDevelopment) {
        originalConsole.warn(...args);
      }
      logger.warn(args.join(' '));
    };

    console.error = (...args) => {
      if (configService.isDevelopment) {
        originalConsole.error(...args);
      }
      logger.error(args.join(' '));
    };

    console.debug = (...args) => {
      if (configService.isDevelopment) {
        originalConsole.debug(...args);
      }
      logger.debug(args.join(' '));
    };

    // Store original for emergency use
    (window as any).__originalConsole = originalConsole;
  }

  // Analyze code for potential debug code
  analyzeDebugCode(sourceCode: string): {
    hasDebugCode: boolean;
    patterns: { [key: string]: number };
    recommendations: string[];
  } {
    const patterns: { [key: string]: number } = {};
    const recommendations: string[] = [];

    for (const { pattern, description } of this.patterns) {
      const matches = sourceCode.match(pattern);
      if (matches) {
        patterns[description] = matches.length;
      }
    }

    const hasDebugCode = Object.keys(patterns).length > 0;

    if (hasDebugCode) {
      recommendations.push('Replace console statements with logger calls');
      recommendations.push('Remove debugger statements before production');
      recommendations.push('Use conditional compilation for development code');
      recommendations.push('Implement proper error handling instead of console.error');
    }

    return {
      hasDebugCode,
      patterns,
      recommendations
    };
  }
}

// Initialize production console replacement
DebugCodeCleaner.setupProductionConsole();

export const debugCleaner = new DebugCodeCleaner();
export { DebugCodeCleaner };