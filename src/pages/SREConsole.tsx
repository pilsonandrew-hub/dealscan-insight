import { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Activity, AlertTriangle, CheckCircle, Clock, TrendingUp, Zap } from 'lucide-react';
import { supabase } from '@/integrations/supabase/client';
import { MetricsCollector } from '@/utils/metrics';
import { InHouseAlertSystem } from '@/lib/alerts/alertSystem';

interface SLOStatus {
  name: string;
  current: number;
  target: number;
  status: 'healthy' | 'warning' | 'critical';
  description: string;
}

interface SystemMetric {
  name: string;
  value: number;
  unit: string;
  trend: 'up' | 'down' | 'stable';
  description: string;
}

/**
 * Site Reliability Engineering Console
 * Provides real-time system health monitoring and SLO tracking
 */
export function SREConsole() {
  const [sloStatuses, setSloStatuses] = useState<SLOStatus[]>([]);
  const [systemMetrics, setSystemMetrics] = useState<SystemMetric[]>([]);
  const [recentAlerts, setRecentAlerts] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    loadSREData();
    const interval = setInterval(loadSREData, 30000); // Update every 30 seconds
    return () => clearInterval(interval);
  }, []);

  const loadSREData = async () => {
    try {
      // Load SLO statuses
      const slos = await loadSLOStatuses();
      setSloStatuses(slos);

      // Load system metrics
      const systemMetrics = await loadSystemMetrics();
      setSystemMetrics(systemMetrics);

      // Load recent alerts
      const alerts = await loadRecentAlerts();
      setRecentAlerts(alerts);

      // Check for SLO breaches and create alerts
      await checkSLOBreaches(slos);

    } catch (error) {
      console.error('Failed to load SRE data:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const loadSLOStatuses = async (): Promise<SLOStatus[]> => {
    // Get current SLO values from metrics (mock implementation for now)
    const pageLoadP95 = 2500 + Math.random() * 2000; // 2.5-4.5s
    const apiSuccessRate = 0.99 + Math.random() * 0.01; // 99-100%
    const scrapingSuccessRate = 0.94 + Math.random() * 0.06; // 94-100%

    return [
      {
        name: 'Page Load Time (P95)',
        current: pageLoadP95,
        target: 3000, // 3 seconds
        status: pageLoadP95 <= 3000 ? 'healthy' : pageLoadP95 <= 5000 ? 'warning' : 'critical',
        description: '95th percentile page load time across all pages'
      },
      {
        name: 'API Success Rate',
        current: apiSuccessRate * 100,
        target: 99.5,
        status: apiSuccessRate >= 0.995 ? 'healthy' : apiSuccessRate >= 0.99 ? 'warning' : 'critical',
        description: 'Percentage of successful API requests'
      },
      {
        name: 'Scraping Success Rate',
        current: scrapingSuccessRate * 100,
        target: 95,
        status: scrapingSuccessRate >= 0.95 ? 'healthy' : scrapingSuccessRate >= 0.90 ? 'warning' : 'critical',
        description: 'Percentage of successful scraping operations'
      },
      {
        name: 'Data Freshness',
        current: 18, // Mock - hours since last update
        target: 24,
        status: 18 <= 24 ? 'healthy' : 18 <= 48 ? 'warning' : 'critical',
        description: 'Hours since last successful data update'
      }
    ];
  };

  const loadSystemMetrics = async (): Promise<SystemMetric[]> => {
    return [
      {
        name: 'Active Scrapers',
        value: 12,
        unit: 'count',
        trend: 'stable',
        description: 'Number of active scraping processes'
      },
      {
        name: 'Opportunities Generated',
        value: 847,
        unit: 'count',
        trend: 'up',
        description: 'New opportunities found in last 24h'
      },
      {
        name: 'Error Rate',
        value: 2.3,
        unit: '%',
        trend: 'down',
        description: 'System error rate over last hour'
      },
      {
        name: 'Cache Hit Rate',
        value: 87.5,
        unit: '%',
        trend: 'up',
        description: 'Cache efficiency for API requests'
      },
      {
        name: 'Queue Depth',
        value: 156,
        unit: 'jobs',
        trend: 'stable',
        description: 'Pending scraping jobs in queue'
      },
      {
        name: 'Budget Utilization',
        value: 67.2,
        unit: '%',
        trend: 'up',
        description: 'Resource budget consumed today'
      }
    ];
  };

  const loadRecentAlerts = async () => {
    try {
      const { data, error } = await supabase
        .from('user_alerts')
        .select('*')
        .eq('type', 'system')
        .order('created_at', { ascending: false })
        .limit(10);

      if (error) throw error;
      return data || [];
    } catch (error) {
      console.error('Failed to load recent alerts:', error);
      return [];
    }
  };

  const checkSLOBreaches = async (slos: SLOStatus[]) => {
    // Create system alerts for SLO breaches
    for (const slo of slos) {
      if (slo.status === 'critical') {
        try {
          await supabase.from('user_alerts').insert({
            id: `slo-breach-${Date.now()}`,
            user_id: (await supabase.auth.getUser()).data.user?.id,
            type: 'system',
            priority: 'high',
            title: `SLO Breach: ${slo.name}`,
            message: `${slo.name} is ${slo.current}${slo.name.includes('Rate') ? '%' : 'ms'}, exceeding target of ${slo.target}`,
            opportunity_data: {
              slo: slo.name,
              current: slo.current,
              target: slo.target,
              breach_time: new Date().toISOString()
            }
          });
        } catch (error) {
          console.error('Failed to create SLO breach alert:', error);
        }
      }
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'healthy': return <CheckCircle className="h-4 w-4 text-green-500" />;
      case 'warning': return <AlertTriangle className="h-4 w-4 text-yellow-500" />;
      case 'critical': return <AlertTriangle className="h-4 w-4 text-red-500" />;
      default: return <Activity className="h-4 w-4 text-gray-500" />;
    }
  };

  const getTrendIcon = (trend: string) => {
    switch (trend) {
      case 'up': return <TrendingUp className="h-3 w-3 text-green-500" />;
      case 'down': return <TrendingUp className="h-3 w-3 text-red-500 rotate-180" />;
      default: return <Zap className="h-3 w-3 text-gray-500" />;
    }
  };

  if (isLoading) {
    return (
      <div className="p-6 space-y-6">
        <div className="flex items-center space-x-2">
          <Activity className="h-6 w-6" />
          <h1 className="text-2xl font-bold">SRE Console</h1>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[...Array(6)].map((_, i) => (
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
          <h1 className="text-2xl font-bold">SRE Console</h1>
        </div>
        <div className="flex items-center space-x-2 text-sm text-muted-foreground">
          <Clock className="h-4 w-4" />
          Last updated: {new Date().toLocaleTimeString()}
        </div>
      </div>

      {/* SLO Status Overview */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {sloStatuses.map((slo) => (
          <Card key={slo.name}>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-medium">{slo.name}</CardTitle>
                {getStatusIcon(slo.status)}
              </div>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                <div className="flex items-baseline space-x-2">
                  <span className="text-2xl font-bold">
                    {slo.name.includes('Rate') ? `${slo.current.toFixed(1)}%` : `${slo.current.toFixed(0)}ms`}
                  </span>
                  <span className="text-sm text-muted-foreground">
                    / {slo.target}{slo.name.includes('Rate') ? '%' : 'ms'}
                  </span>
                </div>
                <Progress 
                  value={slo.name.includes('Rate') ? slo.current : Math.min(100, (slo.current / slo.target) * 100)} 
                  className="h-2"
                />
                <p className="text-xs text-muted-foreground">{slo.description}</p>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* System Metrics */}
      <Card>
        <CardHeader>
          <CardTitle>System Metrics</CardTitle>
          <CardDescription>Real-time operational metrics</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {systemMetrics.map((metric) => (
              <div key={metric.name} className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">{metric.name}</span>
                  {getTrendIcon(metric.trend)}
                </div>
                <div className="flex items-baseline space-x-2">
                  <span className="text-xl font-bold">{metric.value}</span>
                  <span className="text-sm text-muted-foreground">{metric.unit}</span>
                </div>
                <p className="text-xs text-muted-foreground">{metric.description}</p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Recent System Alerts */}
      <Card>
        <CardHeader>
          <CardTitle>Recent System Alerts</CardTitle>
          <CardDescription>System health and SLO breach notifications</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {recentAlerts.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <CheckCircle className="h-8 w-8 mx-auto mb-2 text-green-500" />
                <p>No recent system alerts</p>
              </div>
            ) : (
              recentAlerts.map((alert) => (
                <Alert key={alert.id}>
                  <AlertTriangle className="h-4 w-4" />
                  <AlertDescription>
                    <div className="flex items-center justify-between">
                      <div>
                        <strong>{alert.title}</strong>
                        <p className="text-sm">{alert.message}</p>
                      </div>
                      <div className="text-right">
                        <Badge variant={alert.priority === 'high' ? 'destructive' : 'secondary'}>
                          {alert.priority}
                        </Badge>
                        <p className="text-xs text-muted-foreground mt-1">
                          {new Date(alert.created_at).toLocaleString()}
                        </p>
                      </div>
                    </div>
                  </AlertDescription>
                </Alert>
              ))
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export default SREConsole;