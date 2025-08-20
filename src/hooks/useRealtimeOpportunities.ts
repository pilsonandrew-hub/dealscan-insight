/**
 * Real-time opportunities hook
 * Manages live opportunity updates via WebSocket
 */

import { useState, useEffect, useCallback } from 'react';
import { useWebSocket } from './useWebSocket';
import { Opportunity } from '@/types/dealerscope';
import { useToast } from '@/hooks/use-toast';

interface OpportunityUpdate {
  type: 'new' | 'updated' | 'removed';
  opportunity: Opportunity;
}

interface PipelineUpdate {
  status: string;
  stage: string;
  progress: number;
  opportunities_found: number;
  estimated_completion?: string;
}

const WS_BASE_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000';

export function useRealtimeOpportunities(initialOpportunities: Opportunity[] = []) {
  const [opportunities, setOpportunities] = useState<Opportunity[]>(initialOpportunities);
  const [pipelineStatus, setPipelineStatus] = useState<PipelineUpdate | null>(null);
  const [newOpportunitiesCount, setNewOpportunitiesCount] = useState(0);
  
  const { toast } = useToast();

  const ws = useWebSocket({
    url: `${WS_BASE_URL}/ws/opportunities`,
    autoReconnect: true,
    maxReconnectAttempts: 5,
    reconnectInterval: 3000
  });

  // Handle new opportunities
  const handleOpportunityUpdate = useCallback((data: OpportunityUpdate) => {
    const { type, opportunity } = data;
    
    setOpportunities(prev => {
      switch (type) {
        case 'new':
          // Check if opportunity already exists
          if (prev.some(op => op.id === opportunity.id)) {
            return prev;
          }
          
          setNewOpportunitiesCount(count => count + 1);
          
          // Show toast for high-value opportunities
          if (opportunity.profit > 5000) {
            toast({
              title: "🎯 High-Value Opportunity!",
              description: `${opportunity.vehicle.year} ${opportunity.vehicle.make} ${opportunity.vehicle.model} - $${opportunity.profit.toLocaleString()} profit`,
              duration: 5000,
            });
          }
          
          return [opportunity, ...prev];
          
        case 'updated':
          return prev.map(op => 
            op.id === opportunity.id ? { ...op, ...opportunity } : op
          );
          
        case 'removed':
          return prev.filter(op => op.id !== opportunity.id);
          
        default:
          return prev;
      }
    });
  }, [toast]);

  // Handle pipeline status updates
  const handlePipelineUpdate = useCallback((data: PipelineUpdate) => {
    setPipelineStatus(data);
    
    // Show progress notifications for major milestones
    if (data.progress === 100 && data.opportunities_found > 0) {
      toast({
        title: "Pipeline Complete",
        description: `Found ${data.opportunities_found} new opportunities`,
        duration: 4000,
      });
    }
  }, [toast]);

  // Handle market alerts
  const handleMarketAlert = useCallback((data: any) => {
    toast({
      title: "Market Alert",
      description: data.message,
      variant: data.severity === 'high' ? 'destructive' : 'default',
      duration: 6000,
    });
  }, [toast]);

  // Subscribe to WebSocket events
  useEffect(() => {
    const unsubscribeOpportunities = ws.subscribe('opportunity_update', handleOpportunityUpdate);
    const unsubscribePipeline = ws.subscribe('pipeline_status', handlePipelineUpdate);
    const unsubscribeAlerts = ws.subscribe('market_alert', handleMarketAlert);

    return () => {
      unsubscribeOpportunities();
      unsubscribePipeline();
      unsubscribeAlerts();
    };
  }, [ws.subscribe, handleOpportunityUpdate, handlePipelineUpdate, handleMarketAlert]);

  // Update opportunities when initial data changes
  useEffect(() => {
    if (initialOpportunities.length > 0) {
      setOpportunities(initialOpportunities);
    }
  }, [initialOpportunities]);

  const clearNewCount = useCallback(() => {
    setNewOpportunitiesCount(0);
  }, []);

  const requestPipelineStatus = useCallback(() => {
    ws.sendMessage({ type: 'get_pipeline_status' });
  }, [ws]);

  const pausePipeline = useCallback(() => {
    ws.sendMessage({ type: 'pause_pipeline' });
  }, [ws]);

  const resumePipeline = useCallback(() => {
    ws.sendMessage({ type: 'resume_pipeline' });
  }, [ws]);

  return {
    opportunities,
    pipelineStatus,
    newOpportunitiesCount,
    connectionStatus: ws.status,
    isConnected: ws.isConnected,
    isReconnecting: ws.isReconnecting,
    connectionError: ws.connectionError,
    
    // Actions
    clearNewCount,
    requestPipelineStatus,
    pausePipeline,
    resumePipeline,
    
    // Connection management
    connect: ws.connect,
    disconnect: ws.disconnect
  };
}