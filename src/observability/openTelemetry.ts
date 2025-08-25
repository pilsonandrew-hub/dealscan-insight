/**
 * OpenTelemetry Integration - Temporarily Disabled
 * Will be re-enabled once dependencies are properly configured
 */

export class TelemetryService {
  initialize(): void {
    console.log('OpenTelemetry temporarily disabled');
  }
  createSpan(): any { return null; }
  recordMetric(): void {}
  recordHistogram(): void {}
}

export const telemetryService = new TelemetryService();