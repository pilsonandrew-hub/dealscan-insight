/**
 * SRE Console - Production monitoring dashboard
 */

import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { RefreshCw, AlertTriangle, CheckCircle, XCircle, Clock } from 'lucide-react';
import { productionCache } from '@/utils/productionCache';
import { circuitBreakerManager } from '@/utils/circuitBreakerEnhanced';
import { apiRateLimiter, scraperRateLimiter } from '@/utils/rateLimiter';
import { memoryManager } from '@/utils/memoryManager';
import { performanceMonitor } from '@/utils/performance-monitor';
import productionLogger from '@/utils/productionLogger';

interface SLOMetric {
  name: string;
  value: number;
  threshold: number;
  unit: string;
  status: 'healthy' | 'warning' | 'critical';
  description: string;
}

interface ServiceHealth {
  name: string;
  status: 'up' | 'down' | 'degraded';
  responseTime?: number;
  errorRate?: number;
  lastCheck: number;
}

export const SREConsole: React.FC = () => {
  const [metrics, setMetrics] = useState<SLOMetric[]>([]);
  const [services, setServices] = useState<ServiceHealth[]>([]);
  const [alerts, setAlerts] = useState<any[]>([]);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const refreshMetrics = async () => {
    setIsRefreshing(true);
    try {
      // Cache metrics
      const cacheStats = productionCache.getStats();
      
      // Circuit breaker metrics
      const circuitStats = circuitBreakerManager.getAllStats();
      
      // Rate limiter metrics
      const apiLimiterStats = apiRateLimiter.getStats();
      const scraperLimiterStats = scraperRateLimiter.getStats();
      
      // Memory metrics
      const memoryReport = memoryManager.getMemoryReport();
      
      // Performance metrics
      const perfStats = performanceMonitor.getStats();

      const updatedMetrics: SLOMetric[] = [
        {
          name: 'Cache Hit Rate',
          value: cacheStats.hitRate * 100,
          threshold: 70,
          unit: '%',
          status: cacheStats.hitRate >= 0.7 ? 'healthy' : cacheStats.hitRate >= 0.5 ? 'warning' : 'critical',
          description: 'Percentage of cache hits vs total requests'
        },
        {
          name: 'Memory Usage',
          value: memoryReport.current,
          threshold: 120,
          unit: 'MB',
          status: memoryReport.status === 'healthy' ? 'healthy' : memoryReport.status === 'warning' ? 'warning' : 'critical',
          description: 'Current memory consumption'
        },
        {
          name: 'API Response Time (P95)',
          value: perfStats.operations.find(op => op.name === 'getOpportunities')?.p95Duration || 0,
          threshold: 200,
          unit: 'ms',
          status: (perfStats.operations.find(op => op.name === 'getOpportunities')?.p95Duration || 0) <= 200 ? 'healthy' : 'warning',
          description: '95th percentile API response time'
        },
        {
          name: 'Error Rate',
          value: (perfStats.operations.find(op => op.name === 'getOpportunities')?.errorCount || 0) / Math.max(1, perfStats.operations.find(op => op.name === 'getOpportunities')?.count || 1) * 100,
          threshold: 0.1,
          unit: '%',
          status: ((perfStats.operations.find(op => op.name === 'getOpportunities')?.errorCount || 0) / Math.max(1, perfStats.operations.find(op => op.name === 'getOpportunities')?.count || 1)) <= 0.001 ? 'healthy' : 'critical',
          description: 'Percentage of failed requests'
        }
      ];

      const updatedServices: ServiceHealth[] = [
        {
          name: 'API Gateway',
          status: Object.values(circuitStats).some(s => s.state === 'open') ? 'down' : Object.values(circuitStats).some(s => s.state === 'half_open') ? 'degraded' : 'up',
          errorRate: circuitStats.api?.failureRate || 0,
          lastCheck: Date.now()
        },
        {
          name: 'Scraper Service',
          status: circuitStats.scraper?.state === 'open' ? 'down' : circuitStats.scraper?.state === 'half_open' ? 'degraded' : 'up',
          errorRate: circuitStats.scraper?.failureRate || 0,
          lastCheck: Date.now()
        },
        {
          name: 'Cache Layer',
          status: cacheStats.hitRate >= 0.5 ? 'up' : cacheStats.hitRate >= 0.2 ? 'degraded' : 'down',
          lastCheck: Date.now()
        }
      ];

      setMetrics(updatedMetrics);
      setServices(updatedServices);

      // Check for SLO breaches and create alerts
      const newAlerts = updatedMetrics
        .filter(metric => metric.status === 'critical' || metric.status === 'warning')
        .map(metric => ({
          id: `slo-${metric.name}`,
          type: metric.status === 'critical' ? 'error' : 'warning',
          title: `SLO Breach: ${metric.name}`,
          message: `${metric.name} is ${metric.value}${metric.unit}, threshold is ${metric.threshold}${metric.unit}`,
          timestamp: Date.now()
        }));

      setAlerts(newAlerts);

      productionLogger.info('SRE metrics refreshed', {
        metricsCount: updatedMetrics.length,
        servicesCount: updatedServices.length,
        alertsCount: newAlerts.length
      });
    } catch (error) {
      productionLogger.error('Failed to refresh SRE metrics', error as Error);
    } finally {
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    refreshMetrics();
    const interval = setInterval(refreshMetrics, 30000); // Refresh every 30 seconds
    return () => clearInterval(interval);
  }, []);

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'healthy':
      case 'up':
        return <CheckCircle className="h-4 w-4 text-green-500" />;
      case 'warning':
      case 'degraded':
        return <AlertTriangle className="h-4 w-4 text-yellow-500" />;
      case 'critical':
      case 'down':
        return <XCircle className="h-4 w-4 text-red-500" />;
      default:
        return <Clock className="h-4 w-4 text-gray-500" />;
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'healthy':
      case 'up':
        return 'bg-green-500';
      case 'warning':
      case 'degraded':
        return 'bg-yellow-500';
      case 'critical':
      case 'down':
        return 'bg-red-500';
      default:
        return 'bg-gray-500';
    }
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold">SRE Console</h1>
          <p className="text-muted-foreground">Production monitoring and observability</p>
        </div>
        <Button onClick={refreshMetrics} disabled={isRefreshing}>
          <RefreshCw className={`h-4 w-4 mr-2 ${isRefreshing ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      {alerts.length > 0 && (
        <Alert>
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription>
            {alerts.length} SLO breach(es) detected. Review metrics below.
          </AlertDescription>
        </Alert>
      )}

      <Tabs defaultValue="metrics" className="space-y-4">
        <TabsList>
          <TabsTrigger value="metrics">SLO Metrics</TabsTrigger>
          <TabsTrigger value="services">Service Health</TabsTrigger>
          <TabsTrigger value="performance">Performance</TabsTrigger>
          <TabsTrigger value="alerts">Alerts</TabsTrigger>
        </TabsList>

        <TabsContent value="metrics" className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {metrics.map((metric) => (
              <Card key={metric.name}>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium">{metric.name}</CardTitle>
                  {getStatusIcon(metric.status)}
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold">
                    {metric.value.toFixed(1)}{metric.unit}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Threshold: {metric.threshold}{metric.unit}
                  </p>
                  <Badge className={`mt-2 ${getStatusColor(metric.status)}`}>
                    {metric.status}
                  </Badge>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="services" className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {services.map((service) => (
              <Card key={service.name}>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium">{service.name}</CardTitle>
                  {getStatusIcon(service.status)}
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    <Badge className={getStatusColor(service.status)}>
                      {service.status}
                    </Badge>
                    {service.responseTime && (
                      <div className="text-sm">
                        Response: {service.responseTime}ms
                      </div>
                    )}
                    {service.errorRate !== undefined && (
                      <div className="text-sm">
                        Error Rate: {(service.errorRate * 100).toFixed(2)}%
                      </div>
                    )}
                    <div className="text-xs text-muted-foreground">
                      Last Check: {new Date(service.lastCheck).toLocaleTimeString()}
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="performance" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Performance Overview</CardTitle>
              <CardDescription>
                Key performance indicators and trends
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <div className="grid grid-cols-3 gap-4">
                  <div className="text-center">
                    <div className="text-2xl font-bold text-green-600">
                      {productionCache.getStats().hitRate.toFixed(1)}%
                    </div>
                    <div className="text-sm text-muted-foreground">Cache Hit Rate</div>
                  </div>
                  <div className="text-center">
                    <div className="text-2xl font-bold text-blue-600">
                      {memoryManager.getMemoryReport().current}MB
                    </div>
                    <div className="text-sm text-muted-foreground">Memory Usage</div>
                  </div>
                  <div className="text-center">
                    <div className="text-2xl font-bold text-purple-600">
                      {performanceMonitor.getStats().operations.length}
                    </div>
                    <div className="text-sm text-muted-foreground">Tracked Operations</div>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="alerts" className="space-y-4">
          {alerts.length === 0 ? (
            <Card>
              <CardContent className="flex items-center justify-center h-32">
                <div className="text-center">
                  <CheckCircle className="h-8 w-8 text-green-500 mx-auto mb-2" />
                  <p className="text-muted-foreground">No active alerts</p>
                </div>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-2">
              {alerts.map((alert) => (
                <Alert key={alert.id} className={alert.type === 'error' ? 'border-red-500' : 'border-yellow-500'}>
                  <AlertTriangle className="h-4 w-4" />
                  <AlertDescription>
                    <div className="flex justify-between items-start">
                      <div>
                        <div className="font-medium">{alert.title}</div>
                        <div className="text-sm">{alert.message}</div>
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {new Date(alert.timestamp).toLocaleTimeString()}
                      </div>
                    </div>
                  </AlertDescription>
                </Alert>
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
};