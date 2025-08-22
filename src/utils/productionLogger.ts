/**
 * Security-Hardened Production Logger Replacement
 * Replaces ALL console.log statements to prevent information disclosure
 */

import { logger } from '@/utils/secureLogger';

// Replace global console methods in production
if (import.meta.env.MODE === 'production') {
  // Override console methods to use secure logger
  const originalConsole = {
    log: console.log,
    debug: console.debug,
    info: console.info,
    warn: console.warn,
    error: console.error
  };

  console.log = (...args: any[]) => {
    // In production, suppress general logs
    if (import.meta.env.MODE !== 'production') {
      originalConsole.log(...args);
    }
  };

  console.debug = (...args: any[]) => {
    // Debug logs completely disabled in production
    if (import.meta.env.MODE !== 'production') {
      originalConsole.debug(...args);
    }
  };

  console.info = (...args: any[]) => {
    // Info logs suppressed in production unless critical
    if (import.meta.env.MODE !== 'production') {
      originalConsole.info(...args);
    }
  };

  console.warn = (...args: any[]) => {
    // Warnings allowed but sanitized
    logger.warn(args.join(' '), 'SYSTEM');
  };

  console.error = (...args: any[]) => {
    // Errors allowed but sanitized
    logger.error(args.join(' '), 'SYSTEM');
  };
}

// Export secure logging functions
export const secureLog = {
  debug: (message: string, context?: string, data?: any) => {
    logger.debug(message, context, data);
  },
  info: (message: string, context?: string, data?: any) => {
    logger.info(message, context, data);
  },
  warn: (message: string, context?: string, data?: any) => {
    logger.warn(message, context, data);
  },
  error: (message: string, context?: string, error?: any) => {
    logger.error(message, context, error);
  }
};

export default secureLog;