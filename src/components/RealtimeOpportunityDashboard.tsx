/**
 * Real-time optimized opportunity dashboard with advanced monitoring
 */

import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Progress } from '@/components/ui/progress';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { OptimizedOpportunityList } from './OptimizedOpportunityList';
import { CrosshairDashboard } from './CrosshairDashboard';
import { SystemHealthDashboard } from './SystemHealthDashboard';
import { useRealtimeOpportunities } from '@/hooks/useRealtimeOpportunities';
import { useAdvancedOptimizer } from '@/hooks/useAdvancedOptimizer';
import { usePerformanceMonitor } from '@/hooks/usePerformanceMonitor';
import { useOptimizedOpportunities } from '@/hooks/useOptimizedOpportunities';
import { useToast } from '@/hooks/use-toast';
import { supabase } from '@/integrations/supabase/client';
import { Opportunity } from '@/types/dealerscope';
import { 
  Activity, 
  Zap, 
  TrendingUp, 
  AlertTriangle, 
  RefreshCw, 
  Target, 
  DollarSign,
  BarChart3,
  Settings,
  Pause,
  Play,
  Bell
} from 'lucide-react';
import { logger } from '@/core/UnifiedLogger';

interface RealtimeStats {
  totalOpportunities: number;
  newInLast24h: number;
  totalValue: number;
  averageROI: number;
  hotDeals: number;
  systemLoad: number;
}

export function RealtimeOpportunityDashboard() {
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [realtimeStats, setRealtimeStats] = useState<RealtimeStats>({
    totalOpportunities: 0,
    newInLast24h: 0,
    totalValue: 0,
    averageROI: 0,
    hotDeals: 0,
    systemLoad: 0
  });
  const [selectedOpportunity, setSelectedOpportunity] = useState<Opportunity | null>(null);
  const [isRealtimeEnabled, setIsRealtimeEnabled] = useState(true);
  const [showPerformanceMetrics, setShowPerformanceMetrics] = useState(false);
  const [alertsEnabled, setAlertsEnabled] = useState(true);

  const { measureAsync } = usePerformanceMonitor('RealtimeOpportunityDashboard');
  const { toast } = useToast();

  const {
    virtualizeData,
    batchProcess,
    measurePerformance,
    prefetch,
    clearCache,
    metrics: optimizerMetrics
  } = useAdvancedOptimizer({
    enableVirtualization: true,
    enableBatching: true,
    enableMemoization: true,
    enablePrefetching: true,
    batchSize: 100
  });

  const {
    opportunities: realtimeOpportunities,
    pipelineStatus,
    newOpportunitiesCount,
    connectionStatus,
    isConnected,
    clearNewCount,
    pausePipeline,
    resumePipeline
  } = useRealtimeOpportunities(opportunities);

  const {
    filteredOpportunities,
    topOpportunities,
    stats: opportunityStats
  } = useOptimizedOpportunities(realtimeOpportunities);

  // Real-time data loading with optimization
  const loadOpportunities = useCallback(
    measurePerformance(async () => {
      try {
        const { data, error } = await supabase
          .from('opportunities')
          .select('*')
          .eq('is_active', true)
          .order('potential_profit', { ascending: false })
          .limit(1000);

        if (error) throw error;

        // Process opportunities in batches for better performance
        const processedOpportunities = await batchProcess(
          data || [],
          async (opportunity) => ({
            ...opportunity,
            profit: opportunity.potential_profit,
            roi: opportunity.roi_percentage,
            confidence: opportunity.confidence_score,
            score: opportunity.score || 0,
            expected_price: opportunity.estimated_sale_price || 0,
            acquisition_cost: opportunity.current_bid || 0,
            vehicle: {
              make: opportunity.make,
              model: opportunity.model,
              year: opportunity.year,
              mileage: opportunity.mileage || 0,
              vin: opportunity.vin || ''
            },
            status: (opportunity.status as "hot" | "good" | "moderate") || 'moderate'
          }),
          (progress) => {
            if (progress % 25 === 0) {
              logger.info('Processing opportunities batch', { progress: `${progress}%` });
            }
          }
        );

        setOpportunities(processedOpportunities);

        // Calculate real-time stats
        const now = new Date();
        const yesterday = new Date(now.getTime() - 24 * 60 * 60 * 1000);
        
        const newInLast24h = processedOpportunities.filter(
          op => new Date(op.created_at) > yesterday
        ).length;

        const totalValue = processedOpportunities.reduce(
          (sum, op) => sum + op.profit, 0
        );

        const averageROI = processedOpportunities.length > 0
          ? processedOpportunities.reduce((sum, op) => sum + op.roi, 0) / processedOpportunities.length
          : 0;

        const hotDeals = processedOpportunities.filter(
          op => op.status === 'hot'
        ).length;

        setRealtimeStats({
          totalOpportunities: processedOpportunities.length,
          newInLast24h,
          totalValue,
          averageROI,
          hotDeals,
          systemLoad: optimizerMetrics.memoryUsage / 1024 / 1024 // MB
        });

        // Prefetch market data for top opportunities
        if (processedOpportunities.length > 0) {
          processedOpportunities.slice(0, 5).forEach(opportunity => {
            prefetch(
              () => loadMarketData(opportunity),
              `market-data-${opportunity.id}`
            );
          });
        }

      } catch (error) {
        logger.error('Error loading opportunities', { error });
        toast({
          title: "Error Loading Data",
          description: "Failed to load opportunities",
          variant: "destructive"
        });
      }
    }),
    [batchProcess, optimizerMetrics.memoryUsage, prefetch, toast]
  );

  // Real-time subscriptions
  useEffect(() => {
    if (!isRealtimeEnabled) return;

    const channel = supabase
      .channel('realtime-opportunities')
      .on(
        'postgres_changes',
        { event: 'INSERT', schema: 'public', table: 'opportunities' },
        (payload) => {
          console.log('New opportunity:', payload);
          if (alertsEnabled) {
            toast({
              title: "🚨 New Opportunity Detected",
              description: `${payload.new.make} ${payload.new.model} - Potential profit: $${payload.new.potential_profit?.toLocaleString()}`,
            });
          }
          loadOpportunities();
        }
      )
      .on(
        'postgres_changes',
        { event: 'UPDATE', schema: 'public', table: 'opportunities' },
        (payload) => {
          console.log('Opportunity updated:', payload);
          loadOpportunities();
        }
      )
      .subscribe();

    // Initial load
    loadOpportunities();

    // Periodic refresh every 30 seconds
    const interval = setInterval(loadOpportunities, 30000);

    return () => {
      supabase.removeChannel(channel);
      clearInterval(interval);
    };
  }, [isRealtimeEnabled, alertsEnabled, loadOpportunities]);

  const loadMarketData = async (opportunity: Opportunity) => {
    // Mock market data loading for prefetching
    return { marketData: true };
  };

  const handleOptimizePerformance = useCallback(() => {
    clearCache();
    toast({
      title: "Performance Optimized",
      description: "Cache cleared and memory optimized",
    });
  }, [clearCache, toast]);

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount);
  };

  const getPerformanceColor = (value: number, thresholds: [number, number]) => {
    if (value <= thresholds[0]) return 'text-green-600';
    if (value <= thresholds[1]) return 'text-yellow-600';
    return 'text-red-600';
  };

  return (
    <div className="space-y-6">
      {/* Real-time Control Header */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center space-x-2">
                <Activity className={`h-5 w-5 ${isConnected ? 'text-green-500 animate-pulse' : 'text-red-500'}`} />
                <span>Real-time Opportunity Center</span>
                {newOpportunitiesCount > 0 && (
                  <Badge variant="destructive" className="animate-bounce">
                    {newOpportunitiesCount} New
                  </Badge>
                )}
              </CardTitle>
              <CardDescription>
                Live monitoring with advanced performance optimization
              </CardDescription>
            </div>
            <div className="flex items-center space-x-4">
              <div className="flex items-center space-x-2">
                <Label htmlFor="realtime-toggle">Real-time</Label>
                <Switch 
                  id="realtime-toggle"
                  checked={isRealtimeEnabled} 
                  onCheckedChange={setIsRealtimeEnabled} 
                />
              </div>
              <div className="flex items-center space-x-2">
                <Label htmlFor="alerts-toggle">Alerts</Label>
                <Switch 
                  id="alerts-toggle"
                  checked={alertsEnabled} 
                  onCheckedChange={setAlertsEnabled} 
                />
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={pipelineStatus.status === 'running' ? pausePipeline : resumePipeline}
              >
                {pipelineStatus.status === 'running' ? (
                  <>
                    <Pause className="h-4 w-4 mr-1" />
                    Pause
                  </>
                ) : (
                  <>
                    <Play className="h-4 w-4 mr-1" />
                    Resume
                  </>
                )}
              </Button>
            </div>
          </div>
        </CardHeader>
      </Card>

      {/* Performance Alert */}
      {optimizerMetrics.renderTime > 100 && (
        <Alert>
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription className="flex items-center justify-between">
            <span>
              Performance degradation detected. Render time: {optimizerMetrics.renderTime.toFixed(0)}ms
            </span>
            <Button size="sm" variant="outline" onClick={handleOptimizePerformance}>
              <RefreshCw className="h-4 w-4 mr-1" />
              Optimize
            </Button>
          </AlertDescription>
        </Alert>
      )}

      {/* Real-time Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-6 gap-4">
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center space-x-2">
              <Target className="h-4 w-4 text-blue-500" />
              <div>
                <div className="text-2xl font-bold">{realtimeStats.totalOpportunities}</div>
                <p className="text-xs text-muted-foreground">Total Active</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center space-x-2">
              <Zap className="h-4 w-4 text-green-500" />
              <div>
                <div className="text-2xl font-bold">{realtimeStats.newInLast24h}</div>
                <p className="text-xs text-muted-foreground">New (24h)</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center space-x-2">
              <DollarSign className="h-4 w-4 text-purple-500" />
              <div>
                <div className="text-2xl font-bold">{formatCurrency(realtimeStats.totalValue)}</div>
                <p className="text-xs text-muted-foreground">Total Value</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center space-x-2">
              <TrendingUp className="h-4 w-4 text-yellow-500" />
              <div>
                <div className={`text-2xl font-bold ${getPerformanceColor(realtimeStats.averageROI, [15, 25])}`}>
                  {realtimeStats.averageROI.toFixed(1)}%
                </div>
                <p className="text-xs text-muted-foreground">Avg ROI</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center space-x-2">
              <Activity className="h-4 w-4 text-red-500" />
              <div>
                <div className="text-2xl font-bold">{realtimeStats.hotDeals}</div>
                <p className="text-xs text-muted-foreground">Hot Deals</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center space-x-2">
              <BarChart3 className="h-4 w-4 text-orange-500" />
              <div>
                <div className={`text-2xl font-bold ${getPerformanceColor(realtimeStats.systemLoad, [50, 100])}`}>
                  {realtimeStats.systemLoad.toFixed(0)}MB
                </div>
                <p className="text-xs text-muted-foreground">Memory</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Main Dashboard Tabs */}
      <Tabs defaultValue="opportunities" className="space-y-4">
        <TabsList className="grid w-full grid-cols-5">
          <TabsTrigger value="opportunities">
            Opportunities
            {topOpportunities.length > 0 && (
              <Badge variant="secondary" className="ml-2">
                {topOpportunities.length}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="crosshair">Crosshair</TabsTrigger>
          <TabsTrigger value="analytics">Analytics</TabsTrigger>
          <TabsTrigger value="health">System Health</TabsTrigger>
          <TabsTrigger value="performance">
            Performance
            {showPerformanceMetrics && (
              <Badge variant="outline" className="ml-1">
                {optimizerMetrics.renderTime.toFixed(0)}ms
              </Badge>
            )}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="opportunities" className="space-y-4">
          <OptimizedOpportunityList 
            opportunities={filteredOpportunities}
            onSelectOpportunity={setSelectedOpportunity}
          />
        </TabsContent>

        <TabsContent value="crosshair" className="space-y-4">
          <CrosshairDashboard />
        </TabsContent>

        <TabsContent value="analytics" className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card>
              <CardHeader>
                <CardTitle>Market Trends</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <div>
                    <div className="flex justify-between mb-2">
                      <span className="text-sm font-medium">Deal Flow</span>
                      <span className="text-sm text-muted-foreground">
                        {opportunityStats.totalOpportunities} active
                      </span>
                    </div>
                    <Progress value={75} className="h-2" />
                  </div>
                  <div>
                    <div className="flex justify-between mb-2">
                      <span className="text-sm font-medium">Quality Score</span>
                      <span className="text-sm text-muted-foreground">
                        {opportunityStats.averageConfidence.toFixed(0)}%
                      </span>
                    </div>
                    <Progress value={opportunityStats.averageConfidence} className="h-2" />
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Pipeline Health</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  <div className="flex justify-between">
                    <span className="text-sm">Status:</span>
                    <Badge variant={pipelineStatus.status === 'running' ? 'default' : 'secondary'}>
                      {pipelineStatus.status.toUpperCase()}
                    </Badge>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm">Processed:</span>
                    <span className="text-sm font-medium">{pipelineStatus.processedCount}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm">Last Update:</span>
                    <span className="text-sm font-medium">
                      {pipelineStatus.lastUpdate.toLocaleTimeString()}
                    </span>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="health" className="space-y-4">
          <SystemHealthDashboard />
        </TabsContent>

        <TabsContent value="performance" className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle>Performance Metrics</CardTitle>
                  <div className="flex items-center space-x-2">
                    <Label htmlFor="show-metrics">Show Live</Label>
                    <Switch 
                      id="show-metrics"
                      checked={showPerformanceMetrics} 
                      onCheckedChange={setShowPerformanceMetrics} 
                    />
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <div>
                    <div className="flex justify-between mb-2">
                      <span className="text-sm font-medium">Render Time</span>
                      <span className={`text-sm font-medium ${getPerformanceColor(optimizerMetrics.renderTime, [50, 100])}`}>
                        {optimizerMetrics.renderTime.toFixed(1)}ms
                      </span>
                    </div>
                    <Progress 
                      value={Math.min(optimizerMetrics.renderTime, 200) / 2} 
                      className="h-2" 
                    />
                  </div>
                  
                  <div>
                    <div className="flex justify-between mb-2">
                      <span className="text-sm font-medium">Memory Usage</span>
                      <span className={`text-sm font-medium ${getPerformanceColor(optimizerMetrics.memoryUsage / 1024 / 1024, [50, 100])}`}>
                        {(optimizerMetrics.memoryUsage / 1024 / 1024).toFixed(1)}MB
                      </span>
                    </div>
                    <Progress 
                      value={Math.min(optimizerMetrics.memoryUsage / 1024 / 1024, 200) / 2} 
                      className="h-2" 
                    />
                  </div>

                  <div>
                    <div className="flex justify-between mb-2">
                      <span className="text-sm font-medium">Cache Hit Rate</span>
                      <span className="text-sm font-medium text-green-600">
                        {optimizerMetrics.cacheHitRate.toFixed(1)}%
                      </span>
                    </div>
                    <Progress value={optimizerMetrics.cacheHitRate} className="h-2" />
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Optimization Controls</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <Button onClick={handleOptimizePerformance} className="w-full">
                    <RefreshCw className="h-4 w-4 mr-2" />
                    Optimize Performance
                  </Button>
                  
                  <Button 
                    variant="outline" 
                    onClick={() => window.location.reload()} 
                    className="w-full"
                  >
                    <Settings className="h-4 w-4 mr-2" />
                    Hard Reset
                  </Button>

                  <div className="text-xs text-muted-foreground space-y-1">
                    <p>• Virtualization: Enabled</p>
                    <p>• Batch Processing: Enabled</p>
                    <p>• Memory Management: Auto</p>
                    <p>• Prefetching: Enabled</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}