import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { 
  Activity, 
  CheckCircle, 
  AlertTriangle, 
  XCircle, 
  Clock, 
  Database, 
  Globe, 
  Shield,
  Zap,
  BarChart3,
  Settings
} from 'lucide-react';
import { healthCheckService, HealthStatus, type SystemHealth } from '@/services/healthCheck';
import { webVitalsMonitor, type PerformanceMetrics } from '@/services/webVitals';
import { globalErrorHandler } from '@/utils/globalErrorHandler';
import { environmentManager } from '@/config/environmentManager';
import DeploymentManager from '@/config/deploymentConfig';

/**
 * Production Status Dashboard
 * Comprehensive system health and performance monitoring
 */
export function ProductionStatus() {
  const [systemHealth, setSystemHealth] = useState<SystemHealth | null>(null);
  const [performanceMetrics, setPerformanceMetrics] = useState<PerformanceMetrics | null>(null);
  const [errorStats, setErrorStats] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [lastUpdate, setLastUpdate] = useState<string>('');

  useEffect(() => {
    loadSystemStatus();
    const interval = setInterval(loadSystemStatus, 30000); // Update every 30 seconds
    return () => clearInterval(interval);
  }, []);

  const loadSystemStatus = async () => {
    try {
      // Load system health
      const health = await healthCheckService.performHealthCheck();
      setSystemHealth(health);

      // Load performance metrics
      const performance = webVitalsMonitor.getPerformanceSummary();
      setPerformanceMetrics(performance);

      // Load error statistics
      const errors = globalErrorHandler.getErrorStats();
      setErrorStats(errors);

      setLastUpdate(new Date().toLocaleTimeString());
    } catch (error) {
      console.error('Failed to load system status:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const getStatusIcon = (status: HealthStatus) => {
    switch (status) {
      case HealthStatus.HEALTHY:
        return <CheckCircle className="h-5 w-5 text-green-500" />;
      case HealthStatus.DEGRADED:
        return <AlertTriangle className="h-5 w-5 text-yellow-500" />;
      case HealthStatus.UNHEALTHY:
        return <XCircle className="h-5 w-5 text-red-500" />;
      default:
        return <Clock className="h-5 w-5 text-gray-500" />;
    }
  };

  const getStatusColor = (status: HealthStatus) => {
    switch (status) {
      case HealthStatus.HEALTHY:
        return 'bg-green-500';
      case HealthStatus.DEGRADED:
        return 'bg-yellow-500';
      case HealthStatus.UNHEALTHY:
        return 'bg-red-500';
      default:
        return 'bg-gray-500';
    }
  };

  const getPerformanceRating = (value: number, thresholds: [number, number]) => {
    if (value <= thresholds[0]) return 'good';
    if (value <= thresholds[1]) return 'needs-improvement';
    return 'poor';
  };

  const getRatingColor = (rating: string) => {
    switch (rating) {
      case 'good': return 'text-green-600';
      case 'needs-improvement': return 'text-yellow-600';
      case 'poor': return 'text-red-600';
      default: return 'text-gray-600';
    }
  };

  if (isLoading) {
    return (
      <div className="p-6 space-y-6">
        <div className="flex items-center space-x-2">
          <Activity className="h-6 w-6" />
          <h1 className="text-2xl font-bold">Production Status</h1>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <Card key={i} className="animate-pulse">
              <CardHeader className="pb-2">
                <div className="h-4 bg-muted rounded w-3/4"></div>
              </CardHeader>
              <CardContent>
                <div className="h-8 bg-muted rounded w-1/2"></div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <Activity className="h-6 w-6" />
          <h1 className="text-2xl font-bold">Production Status</h1>
          <Badge variant={systemHealth?.overall === HealthStatus.HEALTHY ? 'default' : 'destructive'}>
            {environmentManager.getEnvironment().toUpperCase()}
          </Badge>
        </div>
        <div className="flex items-center space-x-4">
          <span className="text-sm text-muted-foreground">
            Last updated: {lastUpdate}
          </span>
          <Button variant="outline" size="sm" onClick={loadSystemStatus}>
            Refresh
          </Button>
        </div>
      </div>

      {/* System Overview */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-medium">Overall Status</CardTitle>
              {systemHealth && getStatusIcon(systemHealth.overall)}
            </div>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {systemHealth?.overall || 'Unknown'}
            </div>
            <p className="text-xs text-muted-foreground">
              {systemHealth?.services.length || 0} services monitored
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-medium">Uptime</CardTitle>
              <Clock className="h-4 w-4 text-muted-foreground" />
            </div>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {systemHealth ? Math.round(systemHealth.uptime / 1000 / 60) : 0}m
            </div>
            <p className="text-xs text-muted-foreground">
              Since last restart
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-medium">Error Rate</CardTitle>
              <AlertTriangle className="h-4 w-4 text-muted-foreground" />
            </div>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {errorStats ? ((errorStats.total - errorStats.resolved) / Math.max(errorStats.total, 1) * 100).toFixed(1) : 0}%
            </div>
            <p className="text-xs text-muted-foreground">
              {errorStats?.total || 0} total errors
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-medium">Performance</CardTitle>
              <Zap className="h-4 w-4 text-muted-foreground" />
            </div>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {webVitalsMonitor.isPerformanceGood() ? 'Good' : 'Poor'}
            </div>
            <p className="text-xs text-muted-foreground">
              Core Web Vitals
            </p>
          </CardContent>
        </Card>
      </div>

      <Tabs defaultValue="health" className="space-y-4">
        <TabsList>
          <TabsTrigger value="health">System Health</TabsTrigger>
          <TabsTrigger value="performance">Performance</TabsTrigger>
          <TabsTrigger value="errors">Error Tracking</TabsTrigger>
          <TabsTrigger value="deployment">Deployment Info</TabsTrigger>
        </TabsList>

        {/* System Health Tab */}
        <TabsContent value="health" className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {systemHealth?.services.map((service) => (
              <Card key={service.service}>
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-sm font-medium capitalize">
                      {service.service}
                    </CardTitle>
                    {getStatusIcon(service.status)}
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    <div className="flex justify-between text-sm">
                      <span>Status:</span>
                      <Badge variant={service.status === HealthStatus.HEALTHY ? 'default' : 'destructive'}>
                        {service.status}
                      </Badge>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span>Response Time:</span>
                      <span>{service.responseTime}ms</span>
                    </div>
                    {service.error && (
                      <Alert>
                        <AlertTriangle className="h-4 w-4" />
                        <AlertDescription className="text-xs">
                          {service.error}
                        </AlertDescription>
                      </Alert>
                    )}
                    {Object.keys(service.details).length > 0 && (
                      <div className="text-xs text-muted-foreground">
                        <strong>Details:</strong>
                        <pre className="mt-1 p-2 bg-muted rounded text-xs overflow-auto">
                          {JSON.stringify(service.details, null, 2)}
                        </pre>
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        {/* Performance Tab */}
        <TabsContent value="performance" className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {performanceMetrics && [
              { name: 'First Contentful Paint (FCP)', value: performanceMetrics.fcp, unit: 'ms', thresholds: [1800, 3000] as [number, number] },
              { name: 'Largest Contentful Paint (LCP)', value: performanceMetrics.lcp, unit: 'ms', thresholds: [2500, 4000] as [number, number] },
              { name: 'First Input Delay (FID)', value: performanceMetrics.fid, unit: 'ms', thresholds: [100, 300] as [number, number] },
              { name: 'Cumulative Layout Shift (CLS)', value: performanceMetrics.cls, unit: '', thresholds: [0.1, 0.25] as [number, number] },
              { name: 'Time to First Byte (TTFB)', value: performanceMetrics.ttfb, unit: 'ms', thresholds: [800, 1800] as [number, number] },
              { name: 'Interaction to Next Paint (INP)', value: performanceMetrics.inp, unit: 'ms', thresholds: [200, 500] as [number, number] }
            ].map((metric) => {
              const rating = getPerformanceRating(metric.value, metric.thresholds);
              return (
                <Card key={metric.name}>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium">{metric.name}</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2">
                      <div className={`text-2xl font-bold ${getRatingColor(rating)}`}>
                        {metric.value.toFixed(metric.unit ? 0 : 3)}{metric.unit}
                      </div>
                      <div className="space-y-1">
                        <div className="flex justify-between text-xs">
                          <span>Good</span>
                          <span>Poor</span>
                        </div>
                        <Progress 
                          value={Math.min(100, (metric.value / metric.thresholds[1]) * 100)} 
                          className="h-2"
                        />
                      </div>
                      <Badge variant={rating === 'good' ? 'default' : rating === 'needs-improvement' ? 'secondary' : 'destructive'}>
                        {rating.replace('-', ' ')}
                      </Badge>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </TabsContent>

        {/* Error Tracking Tab */}
        <TabsContent value="errors" className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card>
              <CardHeader>
                <CardTitle>Error Statistics</CardTitle>
                <CardDescription>Error breakdown by severity and category</CardDescription>
              </CardHeader>
              <CardContent>
                {errorStats ? (
                  <div className="space-y-4">
                    <div className="grid grid-cols-2 gap-4">
                      <div className="text-center">
                        <div className="text-2xl font-bold">{errorStats.total}</div>
                        <div className="text-sm text-muted-foreground">Total Errors</div>
                      </div>
                      <div className="text-center">
                        <div className="text-2xl font-bold text-green-600">{errorStats.resolved}</div>
                        <div className="text-sm text-muted-foreground">Resolved</div>
                      </div>
                    </div>
                    
                    <div className="space-y-2">
                      <h4 className="font-medium">By Severity</h4>
                      {Object.entries(errorStats.bySeverity).map(([severity, count]) => (
                        <div key={severity} className="flex justify-between">
                          <span className="capitalize">{severity}:</span>
                          <span>{count as number}</span>
                        </div>
                      ))}
                    </div>

                    <div className="space-y-2">
                      <h4 className="font-medium">By Category</h4>
                      {Object.entries(errorStats.byCategory).map(([category, count]) => (
                        <div key={category} className="flex justify-between">
                          <span className="capitalize">{category.replace('_', ' ')}:</span>
                          <span>{count as number}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="text-center text-muted-foreground">
                    No error data available
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Error Resolution Rate</CardTitle>
                <CardDescription>Percentage of errors automatically resolved</CardDescription>
              </CardHeader>
              <CardContent>
                {errorStats && (
                  <div className="space-y-4">
                    <div className="text-center">
                      <div className="text-3xl font-bold text-green-600">
                        {errorStats.total > 0 ? ((errorStats.resolved / errorStats.total) * 100).toFixed(1) : 100}%
                      </div>
                      <div className="text-sm text-muted-foreground">Resolution Rate</div>
                    </div>
                    <Progress 
                      value={errorStats.total > 0 ? (errorStats.resolved / errorStats.total) * 100 : 100} 
                      className="h-3"
                    />
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* Deployment Info Tab */}
        <TabsContent value="deployment" className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card>
              <CardHeader>
                <CardTitle>Environment Information</CardTitle>
                <CardDescription>Current deployment environment details</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  <div className="flex justify-between">
                    <span>Environment:</span>
                    <Badge>{environmentManager.getEnvironment()}</Badge>
                  </div>
                  <div className="flex justify-between">
                    <span>Version:</span>
                    <span>{systemHealth?.version || 'Unknown'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Build Time:</span>
                    <span>{import.meta.env.VITE_BUILD_TIME || 'Unknown'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Commit:</span>
                    <span className="font-mono text-xs">
                      {import.meta.env.VITE_COMMIT_SHA?.slice(0, 8) || 'Unknown'}
                    </span>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Configuration Status</CardTitle>
                <CardDescription>Deployment configuration validation</CardDescription>
              </CardHeader>
              <CardContent>
                {(() => {
                  const validation = DeploymentManager.validateDeployment(environmentManager.getEnvironment());
                  return (
                    <div className="space-y-4">
                      <div className="flex items-center space-x-2">
                        {validation.ready ? (
                          <CheckCircle className="h-5 w-5 text-green-500" />
                        ) : (
                          <XCircle className="h-5 w-5 text-red-500" />
                        )}
                        <span className="font-medium">
                          {validation.ready ? 'Ready for Production' : 'Issues Found'}
                        </span>
                      </div>
                      
                      {validation.issues.length > 0 && (
                        <div className="space-y-1">
                          <h4 className="font-medium text-red-600">Issues:</h4>
                          {validation.issues.map((issue, index) => (
                            <div key={index} className="text-sm text-red-600">• {issue}</div>
                          ))}
                        </div>
                      )}
                      
                      {validation.warnings.length > 0 && (
                        <div className="space-y-1">
                          <h4 className="font-medium text-yellow-600">Warnings:</h4>
                          {validation.warnings.map((warning, index) => (
                            <div key={index} className="text-sm text-yellow-600">• {warning}</div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })()}
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}

export default ProductionStatus;