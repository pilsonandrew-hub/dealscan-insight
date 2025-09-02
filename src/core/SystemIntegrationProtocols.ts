/**
 * System Integration Protocols - Investment Grade
 * Defines standardized protocols for inter-system communication
 * Ensures all sophisticated systems work together cohesively
 */

import { logger } from './UnifiedLogger';
import { configService } from './UnifiedConfigService';
import { stateManager } from './UnifiedStateManager';
import { enterpriseOrchestrator } from './EnterpriseSystemOrchestrator';

export interface IntegrationEventType {
  source: string;
  target: string;
  type: string;
  payload: any;
  timestamp: number;
  correlationId: string;
  priority: 'low' | 'medium' | 'high' | 'critical';
}

export interface ProtocolConfig {
  name: string;
  version: string;
  compatibility: string[];
  retryPolicy: {
    maxRetries: number;
    backoffMs: number;
    exponential: boolean;
  };
  timeout: number;
}

export interface SystemTransaction {
  id: string;
  systems: string[];
  operations: Array<{
    system: string;
    operation: string;
    payload: any;
    status: 'pending' | 'completed' | 'failed' | 'rolled_back';
    result?: any;
    error?: string;
  }>;
  status: 'in_progress' | 'completed' | 'failed' | 'rolled_back';
  createdAt: number;
  completedAt?: number;
}

class SystemIntegrationProtocols {
  private static instance: SystemIntegrationProtocols;
  private eventBus = new EventTarget();
  private protocolHandlers = new Map<string, ProtocolConfig>();
  private pendingTransactions = new Map<string, SystemTransaction>();
  private integrationMetrics = {
    totalEvents: 0,
    successfulTransactions: 0,
    failedTransactions: 0,
    averageTransactionTime: 0,
    systemCommunications: new Map<string, number>()
  };

  private constructor() {
    this.setupStandardProtocols();
    this.setupEventListeners();
    this.startMetricsCollection();
  }

  static getInstance(): SystemIntegrationProtocols {
    if (!SystemIntegrationProtocols.instance) {
      SystemIntegrationProtocols.instance = new SystemIntegrationProtocols();
    }
    return SystemIntegrationProtocols.instance;
  }

  /**
   * Setup standard integration protocols
   */
  private setupStandardProtocols(): void {
    // Configuration Change Protocol
    this.registerProtocolHandler({
      name: 'ConfigurationChange',
      version: '1.0.0',
      compatibility: ['UnifiedConfig', 'EnvironmentManager', 'UnifiedStateManager'],
      retryPolicy: {
        maxRetries: 3,
        backoffMs: 1000,
        exponential: true
      },
      timeout: 5000
    });

    // State Synchronization Protocol
    this.registerProtocolHandler({
      name: 'StateSynchronization',
      version: '1.0.0',
      compatibility: ['UnifiedStateManager', 'AdvancedMetricsCollector', 'PerformanceEmergencyKit'],
      retryPolicy: {
        maxRetries: 2,
        backoffMs: 500,
        exponential: false
      },
      timeout: 3000
    });

    // Performance Alert Protocol
    this.registerProtocolHandler({
      name: 'PerformanceAlert',
      version: '1.0.0',
      compatibility: ['PerformanceEmergencyKit', 'AdvancedMetricsCollector', 'UnifiedLogger'],
      retryPolicy: {
        maxRetries: 1,
        backoffMs: 100,
        exponential: false
      },
      timeout: 1000
    });

    // Health Check Protocol
    this.registerProtocolHandler({
      name: 'HealthCheck',
      version: '1.0.0',
      compatibility: ['*'], // All systems
      retryPolicy: {
        maxRetries: 2,
        backoffMs: 2000,
        exponential: true
      },
      timeout: 10000
    });

    logger.info('Standard integration protocols configured');
  }

  /**
   * Register a protocol handler
   */
  registerProtocolHandler(config: ProtocolConfig): void {
    this.protocolHandlers.set(config.name, config);
    logger.debug('Protocol handler registered', { name: config.name, version: config.version });
  }

  /**
   * Send integration event between systems
   */
  async sendIntegrationEvent(event: Omit<IntegrationEventType, 'timestamp' | 'correlationId'>): Promise<void> {
    const fullEvent: IntegrationEventType = {
      ...event,
      timestamp: Date.now(),
      correlationId: this.generateCorrelationId()
    };

    this.integrationMetrics.totalEvents++;
    this.updateCommunicationMetrics(event.source, event.target);

    logger.debug('Integration event sent', {
      source: fullEvent.source,
      target: fullEvent.target,
      type: fullEvent.type,
      correlationId: fullEvent.correlationId,
      priority: fullEvent.priority
    });

    // Dispatch event on the integration bus
    const customEvent = new CustomEvent('integration-event', { 
      detail: fullEvent 
    });
    this.eventBus.dispatchEvent(customEvent);

    // Handle based on priority
    if (fullEvent.priority === 'critical') {
      await this.handleCriticalEvent(fullEvent);
    }
  }

  /**
   * Subscribe to integration events
   */
  subscribeToIntegrationEvents(
    eventType: string | '*',
    handler: (event: IntegrationEventType) => Promise<void> | void
  ): () => void {
    const eventHandler = async (customEvent: Event) => {
      const integrationEvent = (customEvent as CustomEvent).detail as IntegrationEventType;
      
      // Filter by event type if specified
      if (eventType !== '*' && integrationEvent.type !== eventType) {
        return;
      }

      try {
        await handler(integrationEvent);
      } catch (error) {
        logger.error('Integration event handler failed', {
          eventType: integrationEvent.type,
          source: integrationEvent.source,
          target: integrationEvent.target,
          error
        });
      }
    };

    this.eventBus.addEventListener('integration-event', eventHandler);
    
    // Return unsubscribe function
    return () => {
      this.eventBus.removeEventListener('integration-event', eventHandler);
    };
  }

  /**
   * Execute cross-system transaction with rollback capability
   */
  async executeCrossSystemTransaction(
    systems: string[],
    operations: Array<{
      system: string;
      operation: string;
      payload: any;
    }>
  ): Promise<SystemTransaction> {
    const transactionId = this.generateTransactionId();
    const transaction: SystemTransaction = {
      id: transactionId,
      systems,
      operations: operations.map(op => ({ ...op, status: 'pending' })),
      status: 'in_progress',
      createdAt: Date.now()
    };

    this.pendingTransactions.set(transactionId, transaction);

    logger.info('Starting cross-system transaction', {
      transactionId,
      systems,
      operationsCount: operations.length
    });

    try {
      // Execute operations in sequence
      for (const operation of transaction.operations) {
        const result = await this.executeSystemOperation(operation);
        operation.result = result;
        operation.status = 'completed';
      }

      transaction.status = 'completed';
      transaction.completedAt = Date.now();
      this.integrationMetrics.successfulTransactions++;

      logger.info('Cross-system transaction completed successfully', {
        transactionId,
        duration: transaction.completedAt - transaction.createdAt
      });

    } catch (error) {
      logger.error('Cross-system transaction failed', {
        transactionId,
        error
      });

      transaction.status = 'failed';
      transaction.completedAt = Date.now();
      this.integrationMetrics.failedTransactions++;

      // Attempt rollback of completed operations
      await this.rollbackTransaction(transaction);
    }

    this.updateAverageTransactionTime(transaction);
    this.pendingTransactions.delete(transactionId);
    
    return transaction;
  }

  /**
   * Setup event listeners for system integration
   */
  private setupEventListeners(): void {
    // Listen for configuration changes
    this.subscribeToIntegrationEvents('configuration-changed', async (event) => {
      logger.info('Configuration change detected', {
        source: event.source,
        changes: event.payload
      });

      // Notify relevant systems
      await this.propagateConfigurationChange(event.payload);
    });

    // Listen for performance alerts
    this.subscribeToIntegrationEvents('performance-alert', async (event) => {
      logger.warn('Performance alert received', {
        source: event.source,
        alert: event.payload
      });

      // Trigger emergency procedures if critical
      if (event.priority === 'critical') {
        await this.triggerPerformanceEmergencyProtocol(event.payload);
      }
    });

    // Listen for state synchronization requests
    this.subscribeToIntegrationEvents('state-sync-request', async (event) => {
      logger.debug('State synchronization requested', {
        source: event.source,
        target: event.target,
        stateKey: event.payload.stateKey
      });

      await this.handleStateSynchronization(event);
    });

    // Listen for health check requests
    this.subscribeToIntegrationEvents('health-check-request', async (event) => {
      logger.debug('Health check requested', {
        source: event.source,
        target: event.target
      });

      await this.handleHealthCheckRequest(event);
    });

    logger.info('Integration event listeners configured');
  }

  /**
   * Start metrics collection for integration protocols
   */
  private startMetricsCollection(): void {
    setInterval(() => {
      const metrics = {
        ...this.integrationMetrics,
        pendingTransactions: this.pendingTransactions.size,
        systemCommunications: Object.fromEntries(this.integrationMetrics.systemCommunications)
      };

      logger.debug('Integration metrics', metrics);

      // Send metrics to advanced metrics collector
      this.sendIntegrationEvent({
        source: 'SystemIntegrationProtocols',
        target: 'AdvancedMetricsCollector',
        type: 'metrics-update',
        payload: metrics,
        priority: 'low'
      });

    }, 30000); // Every 30 seconds
  }

  /**
   * Handle critical integration events
   */
  private async handleCriticalEvent(event: IntegrationEventType): Promise<void> {
    logger.error('Critical integration event received', {
      source: event.source,
      target: event.target,
      type: event.type,
      payload: event.payload
    });

    // Immediate notification to enterprise orchestrator
    await enterpriseOrchestrator.getSystemReport().then(report => {
      if (report.overallHealth === 'critical') {
        logger.fatal('Multiple critical systems detected', {
          systemsInCriticalState: report.systemsStatus.filter(s => s.status === 'critical')
        });
      }
    });
  }

  /**
   * Propagate configuration changes to all systems
   */
  private async propagateConfigurationChange(changes: any): Promise<void> {
    const configUpdateTransaction = await this.executeCrossSystemTransaction(
      ['UnifiedStateManager', 'PerformanceEmergencyKit', 'AdvancedMetricsCollector'],
      [
        {
          system: 'UnifiedStateManager',
          operation: 'updateConfiguration',
          payload: { configChanges: changes }
        },
        {
          system: 'PerformanceEmergencyKit',
          operation: 'reconfigureThresholds',
          payload: { configChanges: changes }
        },
        {
          system: 'AdvancedMetricsCollector',
          operation: 'updateMetricsConfig',
          payload: { configChanges: changes }
        }
      ]
    );

    if (configUpdateTransaction.status === 'failed') {
      logger.error('Configuration propagation failed', {
        transactionId: configUpdateTransaction.id,
        failedOperations: configUpdateTransaction.operations.filter(op => op.status === 'failed')
      });
    }
  }

  /**
   * Trigger performance emergency protocols
   */
  private async triggerPerformanceEmergencyProtocol(alertPayload: any): Promise<void> {
    logger.error('Triggering performance emergency protocol', alertPayload);

    // Execute emergency procedures across systems
    const emergencyTransaction = await this.executeCrossSystemTransaction(
      ['PerformanceEmergencyKit', 'UnifiedStateManager', 'AdvancedMetricsCollector'],
      [
        {
          system: 'PerformanceEmergencyKit',
          operation: 'activateEmergencyMode',
          payload: alertPayload
        },
        {
          system: 'UnifiedStateManager',
          operation: 'enableEmergencyStateManagement',
          payload: { reason: 'performance_alert' }
        },
        {
          system: 'AdvancedMetricsCollector',
          operation: 'increaseMetricsFrequency',
          payload: { multiplier: 5 }
        }
      ]
    );

    if (emergencyTransaction.status === 'completed') {
      logger.info('Performance emergency protocol activated successfully');
    } else {
      logger.fatal('Performance emergency protocol failed to activate');
    }
  }

  /**
   * Handle state synchronization between systems
   */
  private async handleStateSynchronization(event: IntegrationEventType): Promise<void> {
    const { stateKey, targetSystem } = event.payload;
    
    try {
      const stateValue = stateManager.select(stateKey);
      
      await this.sendIntegrationEvent({
        source: 'SystemIntegrationProtocols',
        target: targetSystem,
        type: 'state-sync-response',
        payload: { stateKey, stateValue },
        priority: 'medium'
      });

    } catch (error) {
      logger.error('State synchronization failed', {
        stateKey,
        targetSystem,
        error
      });
    }
  }

  /**
   * Handle health check requests
   */
  private async handleHealthCheckRequest(event: IntegrationEventType): Promise<void> {
    try {
      const systemReport = await enterpriseOrchestrator.getSystemReport();
      
      await this.sendIntegrationEvent({
        source: 'SystemIntegrationProtocols',
        target: event.source,
        type: 'health-check-response',
        payload: { systemReport },
        priority: 'medium'
      });

    } catch (error) {
      logger.error('Health check request failed', {
        requestor: event.source,
        error
      });
    }
  }

  // Utility methods
  private async executeSystemOperation(operation: SystemTransaction['operations'][0]): Promise<any> {
    // This would integrate with actual system APIs
    logger.debug('Executing system operation', {
      system: operation.system,
      operation: operation.operation
    });

    // Simulate operation execution
    await new Promise(resolve => setTimeout(resolve, 100));
    return { success: true, timestamp: Date.now() };
  }

  private async rollbackTransaction(transaction: SystemTransaction): Promise<void> {
    logger.warn('Rolling back transaction', { transactionId: transaction.id });
    
    const completedOperations = transaction.operations.filter(op => op.status === 'completed');
    
    for (const operation of completedOperations.reverse()) {
      try {
        // Execute rollback operation
        await this.executeSystemOperation({
          ...operation,
          operation: `rollback_${operation.operation}`
        });
        operation.status = 'rolled_back';
      } catch (error) {
        logger.error('Rollback operation failed', {
          system: operation.system,
          operation: operation.operation,
          error
        });
      }
    }

    transaction.status = 'rolled_back';
  }

  private generateCorrelationId(): string {
    return `correlation_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  private generateTransactionId(): string {
    return `transaction_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  private updateCommunicationMetrics(source: string, target: string): void {
    const key = `${source}->${target}`;
    const current = this.integrationMetrics.systemCommunications.get(key) || 0;
    this.integrationMetrics.systemCommunications.set(key, current + 1);
  }

  private updateAverageTransactionTime(transaction: SystemTransaction): void {
    if (!transaction.completedAt) return;

    const duration = transaction.completedAt - transaction.createdAt;
    const totalTransactions = this.integrationMetrics.successfulTransactions + this.integrationMetrics.failedTransactions;
    const currentAverage = this.integrationMetrics.averageTransactionTime;
    
    this.integrationMetrics.averageTransactionTime = 
      (currentAverage * (totalTransactions - 1) + duration) / totalTransactions;
  }

  /**
   * Get integration metrics
   */
  getIntegrationMetrics() {
    return {
      ...this.integrationMetrics,
      pendingTransactions: this.pendingTransactions.size,
      systemCommunications: Object.fromEntries(this.integrationMetrics.systemCommunications),
      protocolHandlers: Array.from(this.protocolHandlers.keys())
    };
  }
}

// Create singleton instance
export const integrationProtocols = SystemIntegrationProtocols.getInstance();

export default SystemIntegrationProtocols;