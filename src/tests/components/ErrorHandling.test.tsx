/**
 * Error Handling Component Tests
 * Tests for centralized error handling functionality
 */

import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import { centralizedErrorHandler } from '@/lib/centralizedErrorHandling';

describe('Error Handling System', () => {
  it('should handle errors without crashing', () => {
    const TestComponent = () => {
      centralizedErrorHandler.handleError({
        error: new Error('Test error'),
        severity: 'low',
        category: 'system'
      });
      
      return <div>Error handled</div>;
    };

    const { getByText } = render(<TestComponent />);
    expect(getByText('Error handled')).toBeInTheDocument();
  });

  it('should track error statistics', () => {
    centralizedErrorHandler.clearErrorBuffer();
    
    centralizedErrorHandler.handleError({
      error: new Error('Test error 1'),
      severity: 'medium',
      category: 'network'
    });
    
    const stats = centralizedErrorHandler.getErrorStats();
    expect(stats.totalErrors).toBe(1);
    expect(stats.errorsByCategory.network).toBe(1);
  });
});