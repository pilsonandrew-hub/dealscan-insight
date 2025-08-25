/**
 * OpenTelemetry Configuration - Phase 4 Observability
 * Distributed tracing with Prometheus metrics endpoints
 */

import { NodeSDK } from '@opentelemetry/sdk-node';
import { Resource } from '@opentelemetry/resources';
import { SemanticResourceAttributes } from '@opentelemetry/semantic-conventions';
import { getNodeAutoInstrumentations } from '@opentelemetry/auto-instrumentations-node';
import { PeriodicExportingMetricReader } from '@opentelemetry/sdk-metrics';
import { PrometheusExporter } from '@opentelemetry/exporter-prometheus';
import { trace, metrics, SpanStatusCode, SpanKind } from '@opentelemetry/api';
import productionLogger from '@/utils/productionLogger';

interface TraceConfig {
  serviceName: string;
  serviceVersion: string;
  environment: string;
  prometheusEndpoint: string;
  prometheusPort: number;
  enableAutoInstrumentation: boolean;
  sampleRate: number;
}

const DEFAULT_CONFIG: TraceConfig = {
  serviceName: 'dealerscope-v5',
  serviceVersion: '5.0.0',
  environment: process.env.NODE_ENV || 'development',
  prometheusEndpoint: '/metrics',
  prometheusPort: 9090,
  enableAutoInstrumentation: true,
  sampleRate: 0.1 // Sample 10% of traces in production
};

interface MetricLabels {
  [key: string]: string;
}

interface PerformanceMetrics {
  requestDuration: any;
  requestCount: any;
  errorCount: any;
  cacheHitRate: any;
  scrapingDuration: any;
  dbQueryDuration: any;
  mlInferenceDuration: any;
}

export class OpenTelemetryManager {
  private sdk: NodeSDK | null = null;
  private config: TraceConfig;
  private metrics: PerformanceMetrics;
  private prometheusExporter: PrometheusExporter;
  private isInitialized = false;

  constructor(config: Partial<TraceConfig> = {}) {
    this.config = { ...DEFAULT_CONFIG, ...config };
    
    // Initialize Prometheus exporter
    this.prometheusExporter = new PrometheusExporter({
      endpoint: this.config.prometheusEndpoint,
      port: this.config.prometheusPort
    });

    this.initializeMetrics();
  }

  /**
   * Initialize OpenTelemetry SDK
   */
  async initialize(): Promise<void> {
    if (this.isInitialized) return;

    try {
      productionLogger.info('Initializing OpenTelemetry', {
        service: this.config.serviceName,
        version: this.config.serviceVersion,
        environment: this.config.environment
      });

      // Define resource
      const resource = new Resource({
        [SemanticResourceAttributes.SERVICE_NAME]: this.config.serviceName,
        [SemanticResourceAttributes.SERVICE_VERSION]: this.config.serviceVersion,
        [SemanticResourceAttributes.DEPLOYMENT_ENVIRONMENT]: this.config.environment
      });

      // Configure SDK
      this.sdk = new NodeSDK({
        resource,
        instrumentations: this.config.enableAutoInstrumentation ? [
          getNodeAutoInstrumentations({
            '@opentelemetry/instrumentation-fs': {
              enabled: false // Disable filesystem instrumentation for performance
            },
            '@opentelemetry/instrumentation-http': {
              enabled: true,
              requestHook: (span, request) => {
                span.setAttributes({
                  'dealerscope.request.method': request.method,
                  'dealerscope.request.path': new URL(request.url!).pathname
                });
              }
            }
          })
        ] : [],
        metricReader: new PeriodicExportingMetricReader({
          exporter: this.prometheusExporter,
          exportIntervalMillis: 5000 // Export every 5 seconds
        })
      });

      // Start SDK
      await this.sdk.start();

      this.isInitialized = true;
      productionLogger.info('OpenTelemetry initialized successfully', {
        prometheusPort: this.config.prometheusPort
      });

    } catch (error) {
      productionLogger.error('Failed to initialize OpenTelemetry', {}, error as Error);
      throw error;
    }
  }

  /**
   * Initialize custom metrics
   */
  private initializeMetrics(): void {
    const meter = metrics.getMeter('dealerscope', '5.0.0');

    this.metrics = {
      requestDuration: meter.createHistogram('dealerscope_request_duration_seconds', {
        description: 'HTTP request duration in seconds',
        unit: 's'
      }),

      requestCount: meter.createCounter('dealerscope_requests_total', {
        description: 'Total number of HTTP requests'
      }),

      errorCount: meter.createCounter('dealerscope_errors_total', {
        description: 'Total number of errors'
      }),

      cacheHitRate: meter.createGauge('dealerscope_cache_hit_rate', {
        description: 'Cache hit rate percentage'
      }),

      scrapingDuration: meter.createHistogram('dealerscope_scraping_duration_seconds', {
        description: 'Scraping operation duration in seconds',
        unit: 's'
      }),

      dbQueryDuration: meter.createHistogram('dealerscope_db_query_duration_seconds', {
        description: 'Database query duration in seconds',
        unit: 's'
      }),

      mlInferenceDuration: meter.createHistogram('dealerscope_ml_inference_duration_seconds', {
        description: 'ML inference duration in seconds',
        unit: 's'
      })
    };
  }

  /**
   * Create traced function wrapper
   */
  traceFunction<T extends (...args: any[]) => any>(
    name: string,
    fn: T,
    options: {
      kind?: SpanKind;
      attributes?: Record<string, string | number | boolean>;
    } = {}
  ): T {
    return ((...args: Parameters<T>) => {
      const tracer = trace.getTracer('dealerscope');
      
      return tracer.startActiveSpan(name, {
        kind: options.kind || SpanKind.INTERNAL,
        attributes: options.attributes
      }, async (span) => {
        const startTime = performance.now();
        
        try {
          const result = await fn(...args);
          
          span.setStatus({ code: SpanStatusCode.OK });
          
          // Record success metrics
          const duration = (performance.now() - startTime) / 1000;
          this.recordMetric('success', name, duration, options.attributes);
          
          return result;
        } catch (error) {
          span.recordException(error as Error);
          span.setStatus({
            code: SpanStatusCode.ERROR,
            message: (error as Error).message
          });
          
          // Record error metrics
          const duration = (performance.now() - startTime) / 1000;
          this.recordMetric('error', name, duration, options.attributes);
          
          throw error;
        } finally {
          span.end();
        }
      });
    }) as T;
  }

  /**
   * Record custom metrics
   */
  recordMetric(
    type: 'success' | 'error' | 'duration' | 'counter',
    operation: string,
    value: number,
    labels: MetricLabels = {}
  ): void {
    const commonLabels = {
      operation,
      environment: this.config.environment,
      ...labels
    };

    switch (type) {
      case 'success':
      case 'error':
        this.metrics.requestDuration.record(value, commonLabels);
        this.metrics.requestCount.add(1, { ...commonLabels, status: type });
        if (type === 'error') {
          this.metrics.errorCount.add(1, commonLabels);
        }
        break;
        
      case 'duration':
        if (operation.includes('scraping')) {
          this.metrics.scrapingDuration.record(value, commonLabels);
        } else if (operation.includes('db') || operation.includes('database')) {
          this.metrics.dbQueryDuration.record(value, commonLabels);
        } else if (operation.includes('ml') || operation.includes('inference')) {
          this.metrics.mlInferenceDuration.record(value, commonLabels);
        }
        break;
        
      case 'counter':
        this.metrics.requestCount.add(value, commonLabels);
        break;
    }
  }

  /**
   * Record cache metrics
   */
  recordCacheMetrics(hitRate: number, operation: string): void {
    this.metrics.cacheHitRate.record(hitRate * 100, {
      operation,
      environment: this.config.environment
    });
  }

  /**
   * Record scraping metrics
   */
  recordScrapingMetrics(
    site: string,
    duration: number,
    vehiclesFound: number,
    success: boolean
  ): void {
    this.metrics.scrapingDuration.record(duration, {
      site,
      status: success ? 'success' : 'error',
      environment: this.config.environment
    });

    this.metrics.requestCount.add(1, {
      operation: 'scraping',
      site,
      status: success ? 'success' : 'error',
      environment: this.config.environment
    });

    if (!success) {
      this.metrics.errorCount.add(1, {
        operation: 'scraping',
        site,
        environment: this.config.environment
      });
    }
  }

  /**
   * Record ML inference metrics
   */
  recordMLMetrics(
    model: string,
    field: string,
    duration: number,
    confidence: number,
    success: boolean
  ): void {
    this.metrics.mlInferenceDuration.record(duration, {
      model,
      field,
      status: success ? 'success' : 'error',
      environment: this.config.environment
    });

    this.metrics.requestCount.add(1, {
      operation: 'ml_inference',
      model,
      field,
      status: success ? 'success' : 'error',
      confidence_bucket: this.getConfidenceBucket(confidence),
      environment: this.config.environment
    });
  }

  /**
   * Record database metrics
   */
  recordDatabaseMetrics(
    operation: string,
    table: string,
    duration: number,
    rowsAffected: number,
    success: boolean
  ): void {
    this.metrics.dbQueryDuration.record(duration, {
      operation,
      table,
      status: success ? 'success' : 'error',
      environment: this.config.environment
    });

    this.metrics.requestCount.add(1, {
      operation: `db_${operation}`,
      table,
      status: success ? 'success' : 'error',
      rows_bucket: this.getRowsBucket(rowsAffected),
      environment: this.config.environment
    });
  }

  /**
   * Get confidence bucket for metrics
   */
  private getConfidenceBucket(confidence: number): string {
    if (confidence >= 0.9) return 'high';
    if (confidence >= 0.7) return 'medium';
    if (confidence >= 0.5) return 'low';
    return 'very_low';
  }

  /**
   * Get rows affected bucket for metrics
   */
  private getRowsBucket(rows: number): string {
    if (rows === 0) return 'none';
    if (rows === 1) return 'single';
    if (rows <= 10) return 'small';
    if (rows <= 100) return 'medium';
    return 'large';
  }

  /**
   * Create span manually
   */
  createSpan(name: string, attributes: Record<string, string | number | boolean> = {}) {
    const tracer = trace.getTracer('dealerscope');
    return tracer.startSpan(name, { attributes });
  }

  /**
   * Get current trace context
   */
  getCurrentTraceId(): string | undefined {
    const span = trace.getActiveSpan();
    return span?.spanContext()?.traceId;
  }

  /**
   * Shutdown telemetry
   */
  async shutdown(): Promise<void> {
    if (this.sdk) {
      productionLogger.info('Shutting down OpenTelemetry');
      await this.sdk.shutdown();
      this.isInitialized = false;
    }
  }

  /**
   * Health check for telemetry system
   */
  healthCheck(): { status: 'healthy' | 'unhealthy'; details: any } {
    try {
      return {
        status: this.isInitialized ? 'healthy' : 'unhealthy',
        details: {
          initialized: this.isInitialized,
          service: this.config.serviceName,
          version: this.config.serviceVersion,
          environment: this.config.environment,
          prometheusPort: this.config.prometheusPort,
          traceId: this.getCurrentTraceId()
        }
      };
    } catch (error) {
      return {
        status: 'unhealthy',
        details: {
          error: (error as Error).message
        }
      };
    }
  }
}

// Global telemetry manager
export const telemetryManager = new OpenTelemetryManager();

// Convenience functions
export const traceFunction = telemetryManager.traceFunction.bind(telemetryManager);
export const recordMetric = telemetryManager.recordMetric.bind(telemetryManager);
export const createSpan = telemetryManager.createSpan.bind(telemetryManager);