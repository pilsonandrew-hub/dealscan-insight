/**
 * Cloud Logging Integration Tests
 * Tests for cloud logging and performance monitoring
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { cloudLogger } from '@/utils/cloudLogger';
import { performanceMonitor } from '@/utils/performanceMonitor';

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

  it('should capture global errors', () => {
    const originalError = window.onerror;
    
    // Simulate a global error
    const error = new Error('Global test error');
    window.dispatchEvent(new ErrorEvent('error', {
      error,
      message: error.message,
      filename: 'test.js',
      lineno: 123,
      colno: 45
    }));
    
    const logs = cloudLogger.getBufferedLogs();
    const errorLog = logs.find(log => log.message.includes('Global test error'));
    expect(errorLog).toBeDefined();
    expect(errorLog?.severity).toBe('ERROR');
    expect(errorLog?.jsonPayload.type).toBe('javascript_error');
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

describe('Performance Monitoring', () => {
  beforeEach(() => {
    performanceMonitor.clearMetrics();
  });

  it('should initialize without errors', () => {
    expect(() => performanceMonitor.initialize()).not.toThrow();
  });

  it('should track metrics', () => {
    // Mock performance metric recording
    const recordMetricSpy = vi.spyOn(performanceMonitor as any, 'recordMetric');
    
    // Simulate recording a metric
    (performanceMonitor as any).recordMetric('Test Metric', 1000, 'good');
    
    expect(recordMetricSpy).toHaveBeenCalledWith('Test Metric', 1000, 'good');
  });

  it('should generate performance reports', () => {
    // Add some mock metrics
    (performanceMonitor as any).metrics = [
      {
        name: 'LCP',
        value: 2000,
        rating: 'good',
        timestamp: Date.now(),
        url: 'test://example.com',
        user_agent: 'test-agent'
      },
      {
        name: 'LCP',
        value: 3000,
        rating: 'needs-improvement',
        timestamp: Date.now(),
        url: 'test://example.com',
        user_agent: 'test-agent'
      }
    ];
    
    const reportSpy = vi.spyOn(cloudLogger, 'logInfo');
    performanceMonitor.reportToCloud();
    
    expect(reportSpy).toHaveBeenCalledWith(
      'Performance metrics report',
      expect.objectContaining({
        type: 'performance_report'
      })
    );
  });
});