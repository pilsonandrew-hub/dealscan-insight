/**
 * Browser Pool Management - Temporarily Simplified
 */

import productionLogger from '@/utils/productionLogger';

export class BrowserPool {
  async getBrowser(): Promise<any> {
    productionLogger.info('Browser pool temporarily simplified');
    return null;
  }
  async releaseBrowser(): Promise<void> {}
  async cleanup(): Promise<void> {}
}

export const browserPool = new BrowserPool();