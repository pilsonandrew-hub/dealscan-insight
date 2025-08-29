/**
 * Sample component demonstrating proper logger usage
 * Shows how to replace console.* calls with unified logger
 */

import React, { useState } from 'react';
import { logger } from '../core/UnifiedLogger';
import { performanceKit } from '../core/PerformanceEmergencyKit';
import { ComponentErrorBoundary } from '../core/ErrorBoundary';

// Example of updating a component that had console.* calls
const DealScoringPanel = () => {
  const [isScoring, setIsScoring] = useState(false);

  const handleStartScoring = async () => {
    try {
      setIsScoring(true);
      logger.setContext('business').info('Starting deal scoring process');
      
      // Simulate scoring with performance monitoring
      await performanceKit.deduplicateRequest('deal_scoring', async () => {
        // Simulated scoring logic
        await new Promise(resolve => setTimeout(resolve, 2000));
        return { success: true, score: 85 };
      });
      
      logger.setContext('business').info('Deal scoring completed successfully');
    } catch (error) {
      // Replaced: console.error('Error starting scoring:', error);
      logger.setContext('business').error('Deal scoring failed', { error: error });
    } finally {
      setIsScoring(false);
    }
  };

  return (
    <ComponentErrorBoundary context="deal-scoring-panel">
      <div className="p-4 bg-card rounded-lg border">
        <h3 className="text-lg font-semibold mb-4">Deal Scoring</h3>
        <button
          onClick={handleStartScoring}
          disabled={isScoring}
          className="px-4 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90 disabled:opacity-50"
        >
          {isScoring ? 'Scoring...' : 'Start Scoring'}
        </button>
      </div>
    </ComponentErrorBoundary>
  );
};

export default DealScoringPanel;