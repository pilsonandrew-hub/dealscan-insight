/**
 * WebSocket hook for real-time data streaming
 * Provides automatic reconnection, connection status, and message handling
 */

import { useEffect, useRef, useState, useCallback } from 'react';
import { useToast } from '@/hooks/use-toast';
import { createLogger } from '@/utils/productionLogger';

const logger = createLogger('WebSocket');

export enum WebSocketStatus {
  CONNECTING = 'CONNECTING',
  CONNECTED = 'CONNECTED', 
  DISCONNECTED = 'DISCONNECTED',
  ERROR = 'ERROR',
  RECONNECTING = 'RECONNECTING'
}

interface WebSocketConfig {
  url: string;
  autoReconnect?: boolean;
  maxReconnectAttempts?: number;
  reconnectInterval?: number;
  enableLogging?: boolean;
}

interface WebSocketMessage {
  type: string;
  data: any;
  timestamp: string;
}

export function useWebSocket<T = any>(config: WebSocketConfig) {
  const [status, setStatus] = useState<WebSocketStatus>(WebSocketStatus.DISCONNECTED);
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout>();
  const messageHandlersRef = useRef<Map<string, (data: any) => void>>(new Map());
  
  const { toast } = useToast();

  const {
    url,
    autoReconnect = true,
    maxReconnectAttempts = 5,
    reconnectInterval = 3000,
    enableLogging = process.env.NODE_ENV === 'development'
  } = config;

  const log = useCallback((message: string, data?: any) => {
    if (enableLogging) {
      logger.debug('WebSocket', { message, data });
    }
  }, [enableLogging]);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    // Check if we're in development without backend
    if (import.meta.env.MODE === 'development' && url.includes('localhost:8000')) {
      log('Development mode: Backend not available, skipping WebSocket connection');
      setStatus(WebSocketStatus.DISCONNECTED);
      setConnectionError('Backend not deployed (development mode)');
      return;
    }

    try {
      setStatus(WebSocketStatus.CONNECTING);
      setConnectionError(null);
      
      log('Connecting to:', url);
      wsRef.current = new WebSocket(url);

      wsRef.current.onopen = () => {
        log('Connected successfully');
        setStatus(WebSocketStatus.CONNECTED);
        reconnectAttemptsRef.current = 0;
        
        toast({
          title: "Connected",
          description: "Real-time updates enabled",
          duration: 2000,
        });
      };

      wsRef.current.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data);
          log('Received message:', message);
          
          setLastMessage(message);
          
          // Call specific type handlers
          const handler = messageHandlersRef.current.get(message.type);
          if (handler) {
            handler(message.data);
          }
        } catch (error) {
          log('Error parsing message:', error);
        }
      };

      wsRef.current.onclose = (event) => {
        log('Connection closed', { code: event.code, reason: event.reason });
        setStatus(WebSocketStatus.DISCONNECTED);
        
        if (autoReconnect && reconnectAttemptsRef.current < maxReconnectAttempts) {
          setStatus(WebSocketStatus.RECONNECTING);
          reconnectAttemptsRef.current++;
          
          log(`Reconnecting... (${reconnectAttemptsRef.current}/${maxReconnectAttempts})`);
          
          reconnectTimeoutRef.current = setTimeout(() => {
            connect();
          }, reconnectInterval * reconnectAttemptsRef.current);
        } else if (reconnectAttemptsRef.current >= maxReconnectAttempts) {
          toast({
            title: "Connection Lost",
            description: "Unable to reconnect to real-time updates",
            variant: "destructive",
          });
        }
      };

      wsRef.current.onerror = (error) => {
        log('WebSocket error:', error);
        setStatus(WebSocketStatus.ERROR);
        setConnectionError('Connection failed');
      };

    } catch (error) {
      log('Connection error:', error);
      setStatus(WebSocketStatus.ERROR);
      setConnectionError(error instanceof Error ? error.message : 'Unknown error');
    }
  }, [url, autoReconnect, maxReconnectAttempts, reconnectInterval, toast, log]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }
    
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    
    setStatus(WebSocketStatus.DISCONNECTED);
    log('Disconnected');
  }, [log]);

  const sendMessage = useCallback((message: any) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      const payload = JSON.stringify(message);
      wsRef.current.send(payload);
      log('Sent message:', message);
      return true;
    }
    log('Cannot send message - not connected');
    return false;
  }, [log]);

  const subscribe = useCallback((messageType: string, handler: (data: any) => void) => {
    messageHandlersRef.current.set(messageType, handler);
    log(`Subscribed to message type: ${messageType}`);
    
    return () => {
      messageHandlersRef.current.delete(messageType);
      log(`Unsubscribed from message type: ${messageType}`);
    };
  }, [log]);

  // Auto-connect on mount
  useEffect(() => {
    connect();
    
    return () => {
      disconnect();
    };
  }, [connect, disconnect]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, []);

  return {
    status,
    lastMessage,
    connectionError,
    connect,
    disconnect,
    sendMessage,
    subscribe,
    isConnected: status === WebSocketStatus.CONNECTED,
    isConnecting: status === WebSocketStatus.CONNECTING,
    isReconnecting: status === WebSocketStatus.RECONNECTING
  };
}