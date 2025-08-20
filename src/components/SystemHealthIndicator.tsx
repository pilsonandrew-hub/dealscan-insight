/**
 * System Health Indicator with comprehensive monitoring
 * Implements observability patterns from v4.7 plan
 */

import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { 
  Activity, 
  AlertCircle, 
  CheckCircle, 
  Clock, 
  Database, 
  Globe, 
  HardDrive, 
  RefreshCw, 
  TrendingUp,
  Wifi,
  ChevronDown
} from 'lucide-react';
import { useHealthStatus, healthChecker } from '@/utils/health-checker';
import { performanceMonitor } from '@/utils/performance-monitor';
import { apiCache } from '@/utils/api-cache';
import { usePWAStatus } from '@/utils/pwa-manager';
import { cn } from '@/lib/utils';

interface HealthMetric {
  name: string;
  value: string | number;
  status: 'good' | 'warning' | 'critical';
  icon: React.ReactNode;
  description?: string;
}

export function SystemHealthIndicator() {
  const { status: healthStatus, loading, checkHealth } = useHealthStatus();
  const pwaStatus = usePWAStatus();
  const [showDetails, setShowDetails] = useState(false);
  const [metrics, setMetrics] = useState<HealthMetric[]>([]);

  // Update metrics periodically
  useEffect(() => {
    const updateMetrics = () => {
      const perfStats = performanceMonitor.getStats();
      const cacheStats = apiCache.getStats();
      
      const newMetrics: HealthMetric[] = [
        {
          name: 'API Response Time',
          value: `${Math.round(perfStats.averageResponseTime || 0)}ms`,
          status: (perfStats.averageResponseTime || 0) < 1000 ? 'good' : 
                  (perfStats.averageResponseTime || 0) < 3000 ? 'warning' : 'critical',
          icon: <Activity className="w-4 h-4" />,
          description: 'Average API response time'
        },
        {
          name: 'Cache Usage',
          value: `${Math.round((cacheStats.size / cacheStats.maxSize) * 100)}%`,
          status: (cacheStats.size / cacheStats.maxSize) < 0.8 ? 'good' : 
                  (cacheStats.size / cacheStats.maxSize) < 0.95 ? 'warning' : 'critical',
          icon: <HardDrive className="w-4 h-4" />,
          description: 'Cache utilization percentage'
        },
        {
          name: 'Connection',
          value: pwaStatus.isOnline ? 'Online' : 'Offline',
          status: pwaStatus.isOnline ? 'good' : 'critical',
          icon: <Wifi className="w-4 h-4" />,
          description: 'Network connectivity status'
        },
        {
          name: 'Success Rate',
          value: `${Math.round((perfStats.overallSuccessRate || 0) * 100)}%`,
          status: (perfStats.overallSuccessRate || 0) > 0.95 ? 'good' : 
                  (perfStats.overallSuccessRate || 0) > 0.90 ? 'warning' : 'critical',
          icon: <CheckCircle className="w-4 h-4" />,
          description: 'Percentage of successful operations'
        },
        {
          name: 'Uptime',
          value: formatUptime(healthStatus?.overall.uptime || 0),
          status: 'good',
          icon: <Clock className="w-4 h-4" />,
          description: 'Application uptime'
        }
      ];

      setMetrics(newMetrics);
    };

    updateMetrics();
    const interval = setInterval(updateMetrics, 30000); // Update every 30 seconds

    return () => clearInterval(interval);
  }, [healthStatus, pwaStatus]);

  // Auto-refresh health status
  useEffect(() => {
    checkHealth();
    const interval = setInterval(checkHealth, 60000); // Check every minute
    return () => clearInterval(interval);
  }, [checkHealth]);

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'healthy':
      case 'pass':
      case 'good':
        return 'bg-success text-success-foreground';
      case 'degraded':
      case 'warn':
      case 'warning':
        return 'bg-warning text-warning-foreground';
      case 'unhealthy':
      case 'fail':
      case 'critical':
        return 'bg-destructive text-destructive-foreground';
      default:
        return 'bg-muted text-muted-foreground';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'healthy':
      case 'pass':
      case 'good':
        return <CheckCircle className="w-4 h-4" />;
      case 'degraded':
      case 'warn':
      case 'warning':
        return <AlertCircle className="w-4 h-4" />;
      case 'unhealthy':
      case 'fail':
      case 'critical':
        return <AlertCircle className="w-4 h-4" />;
      default:
        return <Activity className="w-4 h-4" />;
    }
  };

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className={cn(
              "w-8 h-8 rounded-full flex items-center justify-center",
              getStatusColor(healthStatus?.status || 'unknown')
            )}>
              {getStatusIcon(healthStatus?.status || 'unknown')}
            </div>
            <div>
              <CardTitle className="text-lg">System Health</CardTitle>
              <CardDescription>
                {healthStatus?.overall.message || 'Checking system status...'}
              </CardDescription>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="outline">
              Score: {healthStatus?.overall.score || 0}/100
            </Badge>
            <Button
              variant="ghost"
              size="sm"
              onClick={checkHealth}
              disabled={loading}
            >
              <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} />
            </Button>
          </div>
        </div>
        
        {healthStatus && (
          <Progress 
            value={healthStatus.overall.score} 
            className="mt-3"
          />
        )}
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Quick Metrics Grid */}
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {metrics.map((metric) => (
            <div
              key={metric.name}
              className="flex items-center gap-2 p-2 rounded-lg bg-muted/50"
            >
              <div className={cn(
                "p-1 rounded",
                getStatusColor(metric.status)
              )}>
                {metric.icon}
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium truncate">{metric.name}</p>
                <p className="text-xs text-muted-foreground">{metric.value}</p>
              </div>
            </div>
          ))}
        </div>

        {/* PWA Status */}
        {(pwaStatus.isInstallable || pwaStatus.hasUpdate) && (
          <div className="flex items-center gap-2 p-3 bg-primary/10 rounded-lg">
            <TrendingUp className="w-4 h-4 text-primary" />
            <div className="flex-1">
              {pwaStatus.isInstallable && (
                <p className="text-sm font-medium">App can be installed</p>
              )}
              {pwaStatus.hasUpdate && (
                <p className="text-sm font-medium">Update available</p>
              )}
            </div>
            <div className="flex gap-2">
              {pwaStatus.isInstallable && (
                <Button size="sm" onClick={pwaStatus.installApp}>
                  Install
                </Button>
              )}
              {pwaStatus.hasUpdate && (
                <Button size="sm" variant="outline" onClick={pwaStatus.applyUpdate}>
                  Update
                </Button>
              )}
            </div>
          </div>
        )}

        {/* Detailed Health Checks */}
        <Collapsible open={showDetails} onOpenChange={setShowDetails}>
          <CollapsibleTrigger asChild>
            <Button variant="ghost" className="w-full justify-between">
              <span>Detailed Health Checks</span>
              <ChevronDown className={cn(
                "w-4 h-4 transition-transform",
                showDetails && "transform rotate-180"
              )} />
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent className="space-y-2 pt-2">
            {healthStatus?.checks && Object.entries(healthStatus.checks).map(([name, check]) => (
              <div
                key={name}
                className="flex items-center justify-between p-2 rounded border"
              >
                <div className="flex items-center gap-2">
                  <div className={cn(
                    "w-6 h-6 rounded-full flex items-center justify-center",
                    getStatusColor(check.status)
                  )}>
                    {getStatusIcon(check.status)}
                  </div>
                  <div>
                    <p className="text-sm font-medium capitalize">
                      {name.replace(/_/g, ' ')}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {check.message}
                    </p>
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-xs text-muted-foreground">
                    {check.duration}ms
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {new Date(check.timestamp).toLocaleTimeString()}
                  </p>
                </div>
              </div>
            ))}
          </CollapsibleContent>
        </Collapsible>
      </CardContent>
    </Card>
  );
}

function formatUptime(ms: number): string {
  const seconds = Math.floor(ms / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);

  if (days > 0) return `${days}d ${hours % 24}h`;
  if (hours > 0) return `${hours}h ${minutes % 60}m`;
  if (minutes > 0) return `${minutes}m ${seconds % 60}s`;
  return `${seconds}s`;
}