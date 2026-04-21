/**
 * Cloud Logging Integration Tests
 * Tests only behavior that still exists in the live cloud logger.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { cloudLogger } from '@/utils/cloudLogger';

describe('Cloud Logging Integration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    cloudLogger.clearBuffer();
    cloudLogger.enable();
  });

  afterEach(() => {
    cloudLogger.clearBuffer();
  });

  it('should log messages to buffer', () => {
    cloudLogger.logInfo('Test message', { test: 'data' });

    const logs = cloudLogger.getBufferedLogs();
    expect(logs).toHaveLength(1);
    expect(logs[0].message).toBe('Test message');
    expect(logs[0].severity).toBe('INFO');
    expect(logs[0].jsonPayload.test).toBe('data');
  });

  it('should sanitize sensitive information', () => {
    cloudLogger.logError('Login failed with password=secret123', {
      token: 'sensitive-token',
      normal: 'data'
    });

    const logs = cloudLogger.getBufferedLogs();
    expect(logs[0].message).toContain('[REDACTED]');
    expect(logs[0].message).not.toContain('secret123');
    expect(logs[0].jsonPayload.token).toBe('[REDACTED]');
    expect(logs[0].jsonPayload.normal).toBe('data');
  });

  it('should flush logs immediately on critical errors', () => {
    const flushSpy = vi.spyOn(cloudLogger as any, 'flushLogs');

    cloudLogger.logCritical('Critical system error');

    expect(flushSpy).toHaveBeenCalled();
  });

  it('should disable and enable logging', () => {
    cloudLogger.disable();
    cloudLogger.logInfo('Should not be logged');

    expect(cloudLogger.getBufferedLogs()).toHaveLength(0);

    cloudLogger.enable();
    cloudLogger.logInfo('Should be logged');

    expect(cloudLogger.getBufferedLogs()).toHaveLength(1);
  });
});
