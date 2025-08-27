/**
 * Core Error Handling Tests
 * Tests for centralized error handling system
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { centralizedErrorHandler, handleError, handleNetworkError } from '@/lib/centralizedErrorHandling';

describe('Centralized Error Handling', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    centralizedErrorHandler.clearErrorBuffer();
  });

  it('should handle basic errors', () => {
    const error = new Error('Test error');
    const errorId = handleError(error);
    
    expect(errorId).toBeDefined();
    expect(centralizedErrorHandler.getErrorStats().totalErrors).toBe(1);
  });

  it('should handle network errors', () => {
    const error = new Error('Network failed');
    const errorId = handleNetworkError(error, 'https://api.example.com');
    
    expect(errorId).toBeDefined();
    const stats = centralizedErrorHandler.getErrorStats();
    expect(stats.errorsByCategory.network).toBe(1);
  });

  it('should sanitize sensitive information', () => {
    const error = new Error('Failed with password=secret123');
    handleError(error);
    
    const buffer = centralizedErrorHandler.getErrorBuffer();
    expect(buffer[0].message).not.toContain('secret123');
    expect(buffer[0].message).toContain('[REDACTED]');
  });
});