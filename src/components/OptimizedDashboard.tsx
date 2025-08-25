
import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { DealOpportunities } from '@/components/DealOpportunities';
import { SystemHealthDashboard } from '@/components/SystemHealthDashboard';
import { ProfitDistributionChart } from '@/components/ProfitDistributionChart';
import { useAdvancedOptimizer } from '@/hooks/useAdvancedOptimizer';
import { useOptimizedOpportunities } from '@/hooks/useOptimizedOpportunities';
import { supabase } from '@/integrations/supabase/client';
import { Opportunity } from '@/types/dealerscope';
import { RefreshCw, TrendingUp, DollarSign, Target, AlertCircle } from 'lucide-react';
import { createLogger } from '@/utils/productionLogger';

export function OptimizedDashboard() {
  const logger = createLogger('OptimizedDashboard');
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  const { 
    virtualizeData, 
    batchProcess, 
    measurePerformance, 
    metrics 
  } = useAdvancedOptimizer({
    enableVirtualization: true,
    enableMemoization: true,
    enableBatching: true,
    batchSize: 50
  });

  const {
    filteredOpportunities,
    topOpportunities,
    stats
  } = useOptimizedOpportunities(opportunities);

  const loadOpportunities = measurePerformance(async () => {
    try {
      setIsLoading(true);
      setError(null);

      const { data, error: supabaseError } = await supabase
        .from('opportunities')
        .select('*')
        .eq('is_active', true)
        .order('potential_profit', { ascending: false })
        .limit(1000);

      if (supabaseError) throw supabaseError;

      // Process in batches for better performance
      const processedData = await batchProcess(
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
          status: (opportunity.status as "hot" | "good" | "moderate") || 'good'
        }),
        (progress) => logger.info('Processing dashboard data', { progress: `${progress}%` })
      );

      setOpportunities(processedData);
    } catch (err) {
      console.error('Error loading opportunities:', err);
      setError(err instanceof Error ? err.message : 'Failed to load opportunities');
    } finally {
      setIsLoading(false);
    }
  });

  useEffect(() => {
    loadOpportunities();
  }, []);

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount);
  };

  const formatPercentage = (value: number) => {
    return `${value.toFixed(1)}%`;
  };

  if (error) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center h-64">
          <div className="text-center">
            <AlertCircle className="h-12 w-12 text-red-500 mx-auto mb-4" />
            <p className="text-lg font-semibold">Error Loading Dashboard</p>
            <p className="text-muted-foreground mb-4">{error}</p>
            <Button onClick={loadOpportunities}>
              <RefreshCw className="h-4 w-4 mr-2" />
              Retry
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* Performance Metrics Header */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Opportunities</CardTitle>
            <Target className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.totalOpportunities}</div>
            <p className="text-xs text-muted-foreground">
              Active listings
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Profit Potential</CardTitle>
            <DollarSign className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{formatCurrency(stats.totalProfit)}</div>
            <p className="text-xs text-muted-foreground">
              Estimated total profit
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Average ROI</CardTitle>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{formatPercentage(stats.averageROI)}</div>
            <p className="text-xs text-muted-foreground">
              Return on investment
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Performance</CardTitle>
            <RefreshCw className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{metrics.renderTime.toFixed(0)}ms</div>
            <p className="text-xs text-muted-foreground">
              Render time
            </p>
            <Badge variant={metrics.renderTime < 50 ? 'default' : 'secondary'} className="mt-1">
              {metrics.renderTime < 50 ? 'Optimal' : 'Good'}
            </Badge>
          </CardContent>
        </Card>
      </div>

      {/* Main Dashboard Tabs */}
      <Tabs defaultValue="opportunities" className="space-y-4">
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="opportunities">Opportunities</TabsTrigger>
          <TabsTrigger value="analytics">Analytics</TabsTrigger>
          <TabsTrigger value="health">System Health</TabsTrigger>
          <TabsTrigger value="performance">Performance</TabsTrigger>
        </TabsList>

        <TabsContent value="opportunities" className="space-y-4">
          <DealOpportunities 
            opportunities={topOpportunities} 
            isLoading={isLoading}
          />
        </TabsContent>

        <TabsContent value="analytics" className="space-y-4">
          <ProfitDistributionChart opportunities={filteredOpportunities} />
        </TabsContent>

        <TabsContent value="health" className="space-y-4">
          <SystemHealthDashboard />
        </TabsContent>

        <TabsContent value="performance" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Performance Metrics</CardTitle>
              <CardDescription>Real-time application performance monitoring</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <h4 className="text-sm font-medium mb-2">Render Performance</h4>
                  <div className="space-y-2">
                    <div className="flex justify-between">
                      <span className="text-sm text-muted-foreground">Current Render Time</span>
                      <span className="text-sm font-medium">{metrics.renderTime.toFixed(1)}ms</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-sm text-muted-foreground">Frame Rate</span>
                      <span className="text-sm font-medium">{metrics.frameRate.toFixed(0)} fps</span>
                    </div>
                  </div>
                </div>
                
                <div>
                  <h4 className="text-sm font-medium mb-2">Memory Usage</h4>
                  <div className="space-y-2">
                    <div className="flex justify-between">
                      <span className="text-sm text-muted-foreground">Current Usage</span>
                      <span className="text-sm font-medium">{(metrics.memoryUsage / 1024 / 1024).toFixed(1)} MB</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-sm text-muted-foreground">Cache Hit Rate</span>
                      <span className="text-sm font-medium">{metrics.cacheHitRate.toFixed(1)}%</span>
                    </div>
                  </div>
                </div>
              </div>
              
              <Button onClick={loadOpportunities} className="w-full">
                <RefreshCw className="h-4 w-4 mr-2" />
                Refresh Data
              </Button>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
