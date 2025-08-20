/**
 * Enhanced WebSocket hook with graceful degradation
 * Automatically falls back to polling when WebSocket is unavailable
 */

import { useEffect, useRef, useState, useCallback } from 'react';
import { useToast } from '@/hooks/use-toast';
import { useWebSocket, WebSocketStatus } from './useWebSocket';

interface GracefulWebSocketConfig {
  wsUrl: string;
  fallbackPollUrl?: string;
  pollInterval?: number;
  enableFallback?: boolean;
  maxConnectionAttempts?: number;
}

export function useGracefulWebSocket<T = any>(config: GracefulWebSocketConfig) {
  const {
    wsUrl,
    fallbackPollUrl,
    pollInterval = 30000, // 30 seconds
    enableFallback = true,
    maxConnectionAttempts = 3
  } = config;

  const [isUsingFallback, setIsUsingFallback] = useState(false);
  const [lastData, setLastData] = useState<T | null>(null);
  const connectionAttemptsRef = useRef(0);
  const pollIntervalRef = useRef<NodeJS.Timeout>();
  
  const { toast } = useToast();

  // Primary WebSocket connection
  const webSocket = useWebSocket({
    url: wsUrl,
    autoReconnect: true,
    maxReconnectAttempts: maxConnectionAttempts,
    enableLogging: import.meta.env.MODE === 'development'
  });

  // Fallback polling function
  const pollData = useCallback(async () => {
    if (!fallbackPollUrl || !enableFallback) return;

    try {
      const response = await fetch(fallbackPollUrl);
      if (response.ok) {
        const data = await response.json();
        setLastData(data);
      }
    } catch (error) {
      console.warn('Polling fallback failed:', error);
    }
  }, [fallbackPollUrl, enableFallback]);

  // Monitor WebSocket connection status
  useEffect(() => {
    if (webSocket.status === WebSocketStatus.CONNECTED) {
      // WebSocket connected successfully
      setIsUsingFallback(false);
      connectionAttemptsRef.current = 0;
      
      // Clear polling if active
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = undefined;
      }
    } else if (
      webSocket.status === WebSocketStatus.ERROR || 
      webSocket.status === WebSocketStatus.DISCONNECTED
    ) {
      connectionAttemptsRef.current++;
      
      // Switch to fallback after max attempts
      if (connectionAttemptsRef.current >= maxConnectionAttempts && enableFallback && fallbackPollUrl) {
        setIsUsingFallback(true);
        
        toast({
          title: "Real-time Connection Unavailable",
          description: "Using periodic updates instead",
          variant: "default",
        });

        // Start polling
        if (!pollIntervalRef.current) {
          pollData(); // Initial poll
          pollIntervalRef.current = setInterval(pollData, pollInterval);
        }
      }
    }
  }, [webSocket.status, maxConnectionAttempts, enableFallback, fallbackPollUrl, pollData, pollInterval, toast]);

  // Handle WebSocket messages
  useEffect(() => {
    if (webSocket.lastMessage && !isUsingFallback) {
      setLastData(webSocket.lastMessage.data);
    }
  }, [webSocket.lastMessage, isUsingFallback]);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, []);

  // Force reconnection attempt
  const reconnect = useCallback(() => {
    connectionAttemptsRef.current = 0;
    setIsUsingFallback(false);
    
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = undefined;
    }
    
    webSocket.connect();
  }, [webSocket]);

  return {
    // Connection status
    isConnected: webSocket.status === WebSocketStatus.CONNECTED,
    isUsingFallback,
    connectionStatus: webSocket.status,
    connectionError: webSocket.connectionError,
    
    // Data
    lastData,
    lastMessage: webSocket.lastMessage,
    
    // Methods
    sendMessage: webSocket.sendMessage,
    subscribe: webSocket.subscribe,
    reconnect,
    disconnect: webSocket.disconnect,
    
    // Fallback controls
    forceFallback: () => {
      setIsUsingFallback(true);
      webSocket.disconnect();
      if (enableFallback && fallbackPollUrl) {
        pollData();
        if (!pollIntervalRef.current) {
          pollIntervalRef.current = setInterval(pollData, pollInterval);
        }
      }
    },
    
    // Status helpers
    getConnectionType: () => isUsingFallback ? 'polling' : 'websocket',
    isRealtime: webSocket.status === WebSocketStatus.CONNECTED
  };
}