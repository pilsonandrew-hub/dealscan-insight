/**
 * Safe Console Replacement for Components
 * Provides logger-compatible console methods that work in both dev and prod
 */

import { logger } from '../core/UnifiedLogger';
import { configService } from '../core/UnifiedConfigService';

// Create safe console methods that route to logger
export const safeConsole = {
  log: (...args: any[]) => {
    if (configService.isDevelopment) {
      // Allow console in development
      console.log(...args);
    }
    logger.debug(args.map(arg => typeof arg === 'string' ? arg : JSON.stringify(arg)).join(' '));
  },

  info: (...args: any[]) => {
    if (configService.isDevelopment) {
      console.info(...args);
    }
    logger.info(args.map(arg => typeof arg === 'string' ? arg : JSON.stringify(arg)).join(' '));
  },

  warn: (...args: any[]) => {
    if (configService.isDevelopment) {
      console.warn(...args);
    }
    logger.warn(args.map(arg => typeof arg === 'string' ? arg : JSON.stringify(arg)).join(' '));
  },

  error: (...args: any[]) => {
    if (configService.isDevelopment) {
      console.error(...args);
    }
    logger.error(args.map(arg => typeof arg === 'string' ? arg : JSON.stringify(arg)).join(' '));
  },

  debug: (...args: any[]) => {
    if (configService.isDevelopment) {
      console.debug(...args);
    }
    logger.debug(args.map(arg => typeof arg === 'string' ? arg : JSON.stringify(arg)).join(' '));
  },
};

// Context-specific loggers for better organization
export const componentLogger = logger.setContext('system');
export const apiLogger = logger.setContext('api');
export const errorLogger = logger.setContext('system');