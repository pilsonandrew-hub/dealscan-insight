/**
 * OpenTelemetry Integration - Temporarily Disabled
 * Will be re-enabled once dependencies are properly configured
 */

import { createLogger } from '@/utils/productionLogger';

const logger = createLogger('OpenTelemetry');

export class TelemetryService {
  initialize(): void {
    logger.info('OpenTelemetry temporarily disabled');
  }
  createSpan(): any { return null; }
  recordMetric(): void {}
  recordHistogram(): void {}
}

export const telemetryService = new TelemetryService();