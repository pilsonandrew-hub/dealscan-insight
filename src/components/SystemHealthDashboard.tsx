
import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { AlertTriangle, CheckCircle, XCircle, RefreshCw, TrendingUp, TrendingDown } from 'lucide-react';
import { useAdvancedOptimizer } from '@/hooks/useAdvancedOptimizer';
import { ProfitDistributionChart } from '@/components/ProfitDistributionChart';

interface SystemHealth {
  overall: 'excellent' | 'good' | 'warning' | 'critical';
  score: number;
  components: {
    database: { status: string; responseTime: number; connections: number };
    api: { status: string; responseTime: number; errorRate: number };
    cache: { status: string; hitRate: number; memoryUsage: number };
    performance: { status: string; avgRenderTime: number; frameRate: number };
  };
  recommendations: string[];
}

export function SystemHealthDashboard() {
  const [healthData, setHealthData] = useState<SystemHealth | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const { metrics, measurePerformance, clearCache } = useAdvancedOptimizer();

  const fetchHealthData = measurePerformance(async () => {
    setIsRefreshing(true);
    
    // Simulate health check
    await new Promise(resolve => setTimeout(resolve, 1000));
    
    const mockHealth: SystemHealth = {
      overall: 'good',
      score: 85,
      components: {
        database: { status: 'healthy', responseTime: 120, connections: 15 },
        api: { status: 'healthy', responseTime: 89, errorRate: 0.2 },
        cache: { status: 'healthy', hitRate: metrics.cacheHitRate, memoryUsage: 45 },
        performance: { status: 'good', avgRenderTime: metrics.renderTime, frameRate: metrics.frameRate }
      },
      recommendations: [
        'Consider enabling database connection pooling',
        'API response time is optimal',
        'Cache performance is excellent',
        'Consider implementing service worker for offline capabilities'
      ]
    };
    
    setHealthData(mockHealth);
    setIsRefreshing(false);
  });

  useEffect(() => {
    fetchHealthData();
    const interval = setInterval(fetchHealthData, 30000); // Refresh every 30 seconds
    return () => clearInterval(interval);
  }, [fetchHealthData]);

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'healthy':
      case 'excellent':
      case 'good':
        return <CheckCircle className="h-4 w-4 text-green-500" />;
      case 'warning':
        return <AlertTriangle className="h-4 w-4 text-yellow-500" />;
      case 'critical':
        return <XCircle className="h-4 w-4 text-red-500" />;
      default:
        return <RefreshCw className="h-4 w-4 text-gray-500" />;
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'healthy':
      case 'excellent':
        return 'bg-green-500';
      case 'good':
        return 'bg-blue-500';
      case 'warning':
        return 'bg-yellow-500';
      case 'critical':
        return 'bg-red-500';
      default:
        return 'bg-gray-500';
    }
  };

  if (!healthData) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center h-64">
          <RefreshCw className="h-8 w-8 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* Overall Health Score */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <div>
            <CardTitle className="text-2xl font-bold">System Health</CardTitle>
            <CardDescription>Overall system performance and status</CardDescription>
          </div>
          <Button 
            variant="outline" 
            size="sm" 
            onClick={fetchHealthData}
            disabled={isRefreshing}
          >
            <RefreshCw className={`h-4 w-4 mr-2 ${isRefreshing ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </CardHeader>
        <CardContent>
          <div className="flex items-center space-x-4">
            <div className="flex-1">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium">Health Score</span>
                <span className="text-2xl font-bold">{healthData.score}%</span>
              </div>
              <Progress value={healthData.score} className="h-3" />
            </div>
            <Badge variant={healthData.overall === 'good' ? 'default' : 'secondary'}>
              {healthData.overall.toUpperCase()}
            </Badge>
          </div>
        </CardContent>
      </Card>

      <Tabs defaultValue="components" className="space-y-4">
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="components">Components</TabsTrigger>
          <TabsTrigger value="performance">Performance</TabsTrigger>
          <TabsTrigger value="recommendations">Recommendations</TabsTrigger>
        </TabsList>

        <TabsContent value="components" className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Database Health */}
            <Card>
              <CardHeader className="flex flex-row items-center space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Database</CardTitle>
                {getStatusIcon(healthData.components.database.status)}
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  <div className="flex justify-between">
                    <span className="text-sm text-muted-foreground">Response Time</span>
                    <span className="text-sm font-medium">{healthData.components.database.responseTime}ms</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-muted-foreground">Connections</span>
                    <span className="text-sm font-medium">{healthData.components.database.connections}</span>
                  </div>
                  <Progress value={100 - (healthData.components.database.responseTime / 10)} className="h-2" />
                </div>
              </CardContent>
            </Card>

            {/* API Health */}
            <Card>
              <CardHeader className="flex flex-row items-center space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">API</CardTitle>
                {getStatusIcon(healthData.components.api.status)}
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  <div className="flex justify-between">
                    <span className="text-sm text-muted-foreground">Response Time</span>
                    <span className="text-sm font-medium">{healthData.components.api.responseTime}ms</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-muted-foreground">Error Rate</span>
                    <span className="text-sm font-medium">{healthData.components.api.errorRate}%</span>
                  </div>
                  <Progress value={100 - healthData.components.api.errorRate * 10} className="h-2" />
                </div>
              </CardContent>
            </Card>

            {/* Cache Health */}
            <Card>
              <CardHeader className="flex flex-row items-center space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Cache</CardTitle>
                {getStatusIcon(healthData.components.cache.status)}
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  <div className="flex justify-between">
                    <span className="text-sm text-muted-foreground">Hit Rate</span>
                    <span className="text-sm font-medium">{healthData.components.cache.hitRate.toFixed(1)}%</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-muted-foreground">Memory Usage</span>
                    <span className="text-sm font-medium">{healthData.components.cache.memoryUsage}%</span>
                  </div>
                  <Progress value={healthData.components.cache.hitRate} className="h-2" />
                </div>
              </CardContent>
            </Card>

            {/* Performance Health */}
            <Card>
              <CardHeader className="flex flex-row items-center space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Performance</CardTitle>
                {getStatusIcon(healthData.components.performance.status)}
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  <div className="flex justify-between">
                    <span className="text-sm text-muted-foreground">Render Time</span>
                    <span className="text-sm font-medium">{healthData.components.performance.avgRenderTime.toFixed(1)}ms</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-muted-foreground">Frame Rate</span>
                    <span className="text-sm font-medium">{healthData.components.performance.frameRate.toFixed(0)} fps</span>
                  </div>
                  <Progress value={Math.min(100, healthData.components.performance.frameRate / 60 * 100)} className="h-2" />
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="performance" className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Card>
              <CardHeader className="flex flex-row items-center space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Memory Usage</CardTitle>
                <TrendingUp className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{(metrics.memoryUsage / 1024 / 1024).toFixed(1)} MB</div>
                <p className="text-xs text-muted-foreground">Current session</p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Render Time</CardTitle>
                <TrendingDown className="h-4 w-4 text-green-500" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{metrics.renderTime.toFixed(1)}ms</div>
                <p className="text-xs text-muted-foreground">Average render time</p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Cache Efficiency</CardTitle>
                <TrendingUp className="h-4 w-4 text-green-500" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{metrics.cacheHitRate.toFixed(1)}%</div>
                <p className="text-xs text-muted-foreground">Cache hit rate</p>
                <Button variant="outline" size="sm" onClick={clearCache} className="mt-2">
                  Clear Cache
                </Button>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="recommendations" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Performance Recommendations</CardTitle>
              <CardDescription>Suggested optimizations to improve system performance</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {healthData.recommendations.map((recommendation, index) => (
                  <div key={index} className="flex items-start space-x-3 p-3 rounded-lg bg-muted/50">
                    <CheckCircle className="h-5 w-5 text-green-500 mt-0.5 flex-shrink-0" />
                    <span className="text-sm">{recommendation}</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
