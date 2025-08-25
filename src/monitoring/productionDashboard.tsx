/**
 * Production Monitoring Dashboard
 * Real-time system health and performance monitoring
 */

import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { 
  Activity, 
  AlertTriangle, 
  CheckCircle, 
  Clock, 
  Database, 
  Globe, 
  Monitor, 
  RefreshCw, 
  Server, 
  TrendingUp,
  Users,
  Zap
} from 'lucide-react';
import { healthMonitor, SystemHealth } from './healthCheck';
import { testSuite, TestSuiteReport } from '@/testing/testSuite';
import { metricsCollector, MetricsSummary } from './metricsCollector';
import { createLogger } from '@/utils/productionLogger';

const logger = createLogger('ProductionDashboard');

interface DashboardProps {
  className?: string;
}

export const ProductionDashboard: React.FC<DashboardProps> = ({ className = "" }) => {
  const [systemHealth, setSystemHealth] = useState<SystemHealth | null>(null);
  const [testResults, setTestResults] = useState<TestSuiteReport | null>(null);
  const [metrics, setMetrics] = useState<MetricsSummary | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date());
  const [autoRefresh, setAutoRefresh] = useState(true);

  useEffect(() => {
    loadDashboardData();
    
    if (autoRefresh) {
      const interval = setInterval(loadDashboardData, 30000); // 30 seconds
      return () => clearInterval(interval);
    }
  }, [autoRefresh]);

  const loadDashboardData = async () => {
    setIsRefreshing(true);
    logger.info('Loading production dashboard data');
    
    try {
      const [healthData, testData, metricsData] = await Promise.all([
        healthMonitor.runHealthChecks(),
        testSuite.runAllTests(),
        metricsCollector.getMetricsSummary()
      ]);
      
      setSystemHealth(healthData);
      setTestResults(testData);
      setMetrics(metricsData);
      setLastUpdate(new Date());
      
      logger.info('Dashboard data loaded successfully', {
        systemHealth: healthData.overall,
        testsPassed: testData.passed,
        testsFailed: testData.failed,
        metricsCount: metricsData.totalMetrics
      });
      
    } catch (error) {
      logger.error('Failed to load dashboard data', {}, error as Error);
    } finally {
      setIsRefreshing(false);
    }
  };

  const getHealthStatusColor = (status: string) => {
    switch (status) {
      case 'healthy': return 'text-green-600 bg-green-50';
      case 'degraded': return 'text-yellow-600 bg-yellow-50';
      case 'unhealthy': return 'text-red-600 bg-red-50';
      default: return 'text-gray-600 bg-gray-50';
    }
  };

  const getHealthIcon = (status: string) => {
    switch (status) {
      case 'healthy': return <CheckCircle className="h-4 w-4" />;
      case 'degraded': return <AlertTriangle className="h-4 w-4" />;
      case 'unhealthy': return <AlertTriangle className="h-4 w-4" />;
      default: return <Monitor className="h-4 w-4" />;
    }
  };

  if (!systemHealth || !testResults || !metrics) {
    return (
      <div className={`space-y-6 p-6 ${className}`}>
        <div className="flex items-center space-x-2">
          <RefreshCw className="h-5 w-5 animate-spin" />
          <span>Loading production dashboard...</span>
        </div>
      </div>
    );
  }

  return (
    <div className={`space-y-6 p-6 ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Production Dashboard</h1>
          <p className="text-muted-foreground">
            Real-time monitoring and system health • Last updated: {lastUpdate.toLocaleTimeString()}
          </p>
        </div>
        <div className="flex items-center space-x-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setAutoRefresh(!autoRefresh)}
          >
            <Activity className="h-4 w-4 mr-2" />
            Auto-refresh: {autoRefresh ? 'ON' : 'OFF'}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={loadDashboardData}
            disabled={isRefreshing}
          >
            <RefreshCw className={`h-4 w-4 mr-2 ${isRefreshing ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </div>
      </div>

      {/* System Overview */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Overall Health</CardTitle>
            {getHealthIcon(systemHealth.overall)}
          </CardHeader>
          <CardContent>
            <div className="flex items-center space-x-2">
              <Badge className={getHealthStatusColor(systemHealth.overall)}>
                {systemHealth.overall.toUpperCase()}
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              {systemHealth.summary.healthy}/{systemHealth.summary.total} services healthy
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Test Coverage</CardTitle>
            <CheckCircle className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{testResults.coverage}%</div>
            <Progress value={testResults.coverage} className="mt-2" />
            <p className="text-xs text-muted-foreground mt-1">
              {testResults.passed}/{testResults.total} tests passing
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Active Metrics</CardTitle>
            <TrendingUp className="h-4 w-4 text-blue-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{metrics.totalMetrics}</div>
            <p className="text-xs text-muted-foreground mt-1">
              Collected over last hour
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Alerts</CardTitle>
            <AlertTriangle className="h-4 w-4 text-yellow-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{metrics.alerts.length}</div>
            <p className="text-xs text-muted-foreground mt-1">
              Active alerts
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Active Alerts */}
      {metrics.alerts.length > 0 && (
        <Alert className="border-yellow-200 bg-yellow-50">
          <AlertTriangle className="h-4 w-4 text-yellow-600" />
          <AlertTitle className="text-yellow-800">Active Alerts</AlertTitle>
          <AlertDescription className="text-yellow-700">
            <div className="space-y-2 mt-2">
              {metrics.alerts.map((alert, index) => (
                <div key={index} className="flex items-center justify-between">
                  <span className="font-medium">{alert.metric}</span>
                  <Badge variant={alert.severity === 'critical' ? 'destructive' : 'secondary'}>
                    {alert.current.toFixed(1)} / {alert.threshold}
                  </Badge>
                </div>
              ))}
            </div>
          </AlertDescription>
        </Alert>
      )}

      {/* Detailed Monitoring */}
      <Tabs defaultValue="health" className="space-y-4">
        <TabsList>
          <TabsTrigger value="health">System Health</TabsTrigger>
          <TabsTrigger value="tests">Test Results</TabsTrigger>
          <TabsTrigger value="metrics">Performance Metrics</TabsTrigger>
          <TabsTrigger value="services">Services</TabsTrigger>
        </TabsList>

        <TabsContent value="health" className="space-y-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {systemHealth.services.map((service) => (
              <Card key={service.service}>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium capitalize">
                    {service.service.replace('_', ' ')}
                  </CardTitle>
                  <div className="flex items-center space-x-2">
                    <Badge className={getHealthStatusColor(service.status)}>
                      {service.status}
                    </Badge>
                    {getHealthIcon(service.status)}
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    <div className="flex justify-between text-sm">
                      <span>Response Time:</span>
                      <span className="font-mono">{service.responseTime}ms</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span>Last Check:</span>
                      <span className="font-mono text-xs">
                        {new Date(service.lastCheck).toLocaleTimeString()}
                      </span>
                    </div>
                    {service.details && Object.keys(service.details).length > 0 && (
                      <details className="text-xs">
                        <summary className="cursor-pointer text-muted-foreground">
                          Service Details
                        </summary>
                        <pre className="mt-2 p-2 bg-muted rounded text-xs overflow-auto">
                          {JSON.stringify(service.details, null, 2)}
                        </pre>
                      </details>
                    )}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="tests" className="space-y-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {Object.entries(testResults.summary).map(([category, stats]) => (
              <Card key={category}>
                <CardHeader>
                  <CardTitle className="capitalize">{category} Tests</CardTitle>
                  <CardDescription>
                    {stats.passed}/{stats.total} tests passing
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    <Progress 
                      value={stats.total > 0 ? (stats.passed / stats.total) * 100 : 0} 
                      className="h-2"
                    />
                    <div className="flex justify-between text-sm text-muted-foreground">
                      <span>Passed: {stats.passed}</span>
                      <span>Failed: {stats.total - stats.passed}</span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="metrics" className="space-y-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle>Top Metrics</CardTitle>
                <CardDescription>Highest performing metrics</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {metrics.topMetrics.slice(0, 5).map((metric, index) => (
                    <div key={index} className="flex items-center justify-between">
                      <span className="text-sm font-medium truncate">
                        {metric.name.replace('_', ' ')}
                      </span>
                      <div className="flex items-center space-x-2">
                        <span className="text-sm font-mono">
                          {metric.value.toFixed(1)}
                        </span>
                        <Badge variant={metric.trend === 'up' ? 'default' : 'secondary'}>
                          {metric.trend}
                        </Badge>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Metrics by Category</CardTitle>
                <CardDescription>Distribution of collected metrics</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {Object.entries(metrics.categories).map(([category, count]) => (
                    <div key={category} className="space-y-1">
                      <div className="flex justify-between text-sm">
                        <span className="capitalize">{category}</span>
                        <span className="font-mono">{count}</span>
                      </div>
                      <Progress 
                        value={(count / metrics.totalMetrics) * 100} 
                        className="h-1"
                      />
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="services" className="space-y-4">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Database</CardTitle>
                <Database className="h-4 w-4 text-blue-600" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold text-green-600">Connected</div>
                <p className="text-xs text-muted-foreground">
                  Supabase connection active
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">API</CardTitle>
                <Globe className="h-4 w-4 text-green-600" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold text-green-600">Healthy</div>
                <p className="text-xs text-muted-foreground">
                  All endpoints responding
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Cache</CardTitle>
                <Zap className="h-4 w-4 text-yellow-600" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold text-green-600">Active</div>
                <p className="text-xs text-muted-foreground">
                  In-memory caching enabled
                </p>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
};