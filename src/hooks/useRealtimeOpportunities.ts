/**
 * Hook for managing real-time opportunities data
 * Simplified version without complex WebSocket connections for now
 */

import { useState, useEffect, useCallback } from 'react';
import { logger } from '@/lib/logger';
import { Opportunity } from '@/types/dealerscope';

type RealtimeConnectionStatus = 'CONNECTED' | 'DISCONNECTED';

interface PipelineStatus {
  status: 'running' | 'paused' | 'stopped';
  lastUpdate: Date;
  processedCount: number;
}

export function useRealtimeOpportunities(initialData: Opportunity[] = []) {
  const [opportunities, setOpportunities] = useState<Opportunity[]>(initialData);
  const [pipelineStatus, setPipelineStatus] = useState<PipelineStatus>({
    status: 'running',
    lastUpdate: new Date(),
    processedCount: 0
  });
  const [newOpportunitiesCount, setNewOpportunitiesCount] = useState(0);
  const [connectionStatus, setConnectionStatus] = useState<RealtimeConnectionStatus>('CONNECTED');
  const [isConnected, setIsConnected] = useState(true);

  // Initialize with provided data
  useEffect(() => {
    if (initialData && initialData.length > 0) {
      setOpportunities(initialData);
      logger.info('Initialized opportunities', { count: initialData.length, context: 'system' });
    }
  }, [initialData]);

  const clearNewCount = useCallback(() => {
    setNewOpportunitiesCount(0);
  }, []);

  const pausePipeline = useCallback(() => {
    setPipelineStatus(prev => ({ ...prev, status: 'paused' }));
    logger.info('Pipeline paused', { context: 'system' });
  }, []);

  const resumePipeline = useCallback(() => {
    setPipelineStatus(prev => ({ ...prev, status: 'running' }));
    logger.info('Pipeline resumed', { context: 'system' });
  }, []);

  const connect = useCallback(() => {
    setConnectionStatus('CONNECTED');
    setIsConnected(true);
    logger.info('Connection established', { context: 'system' });
  }, []);

  const disconnect = useCallback(() => {
    setConnectionStatus('DISCONNECTED');
    setIsConnected(false);
    logger.info('Connection disconnected', { context: 'system' });
  }, []);

  return {
    opportunities,
    pipelineStatus,
    newOpportunitiesCount,
    connectionStatus,
    isConnected,
    clearNewCount,
    pausePipeline,
    resumePipeline,
    connect,
    disconnect
  };
}