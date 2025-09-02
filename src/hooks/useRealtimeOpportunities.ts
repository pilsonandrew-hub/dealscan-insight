/**
 * Hook for managing real-time opportunities data
 * Simplified version without complex WebSocket connections for now
 */

import { useState, useEffect, useCallback } from 'react';
import { logger } from '@/core/UnifiedLogger';

interface Opportunity {
  id: string;
  make: string;
  model: string;
  year: number;
  current_bid: number;
  potential_profit: number;
  roi_percentage: number;
  confidence_score: number;
  risk_score: number;
  status: string;
  created_at: string;
}

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
  const [connectionStatus, setConnectionStatus] = useState<'connected' | 'disconnected' | 'connecting'>('connected');
  const [isConnected, setIsConnected] = useState(true);

  // Initialize with provided data
  useEffect(() => {
    if (initialData && initialData.length > 0) {
      setOpportunities(initialData);
      logger.setContext('system').info('Initialized opportunities', { count: initialData.length });
    }
  }, [initialData]);

  const clearNewCount = useCallback(() => {
    setNewOpportunitiesCount(0);
  }, []);

  const pausePipeline = useCallback(() => {
    setPipelineStatus(prev => ({ ...prev, status: 'paused' }));
    logger.setContext('system').info('Pipeline paused');
  }, []);

  const resumePipeline = useCallback(() => {
    setPipelineStatus(prev => ({ ...prev, status: 'running' }));
    logger.setContext('system').info('Pipeline resumed');
  }, []);

  const connect = useCallback(() => {
    setConnectionStatus('connected');
    setIsConnected(true);
    logger.setContext('system').info('Connection established');
  }, []);

  const disconnect = useCallback(() => {
    setConnectionStatus('disconnected');
    setIsConnected(false);
    logger.setContext('system').info('Connection disconnected');
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