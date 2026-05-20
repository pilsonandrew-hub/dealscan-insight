/**
 * Production Logger facade
 * Thin compatibility wrapper over productionLogger for current live callers.
 */

import productionLogger from '@/utils/productionLogger';

export interface LogMeta {
  [key: string]: unknown;
}

export const logger = {
  debug: (message: string, meta?: LogMeta): void => {
    productionLogger.debug(message, {
      component: getCurrentComponent(),
      ...meta
    });
  },

  info: (message: string, meta?: LogMeta): void => {
    productionLogger.info(message, {
      component: getCurrentComponent(),
      ...meta
    });
  },

  warn: (message: string, meta?: LogMeta): void => {
    productionLogger.warn(message, {
      component: getCurrentComponent(),
      ...meta
    });
  },

  error: (message: string, context?: LogMeta, error?: Error): void => {
    productionLogger.error(message, {
      component: getCurrentComponent(),
      ...context
    }, error);
  },

  setCorrelationId: (correlationId: string): void => {
    productionLogger.setCorrelationId(correlationId);
  },

  newCorrelation: (): string => {
    return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }
};

function getCurrentComponent(): string {
  try {
    const stack = new Error().stack;
    if (!stack) return 'Unknown';

    const lines = stack.split('\n');
    for (let i = 2; i < lines.length; i++) {
      const line = lines[i];
      if (line && !line.includes('logger.ts') && !line.includes('productionLogger.ts')) {
        const match = line.match(/\/([^/]+)\.(tsx?|jsx?):/);
        if (match) {
          return match[1];
        }
      }
    }
    return 'Unknown';
  } catch {
    return 'Unknown';
  }
}

export default logger;
