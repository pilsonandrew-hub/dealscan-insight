import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Progress } from '@/components/ui/progress';
import { 
  TrendingUp, 
  TrendingDown, 
  DollarSign, 
  MapPin, 
  Clock, 
  AlertTriangle,
  Zap,
  Target,
  BarChart3
} from 'lucide-react';
import { supabase } from '@/integrations/supabase/client';
import { Opportunity } from '@/types/dealerscope';
import { useMarketAnalysis, useMarketMetrics } from '@/hooks/useMarketAnalysis';
import { useAdvancedOptimizer } from '@/hooks/useAdvancedOptimizer';
import { useToast } from '@/hooks/use-toast';

interface DashboardStats {
  totalOpportunities: number;
  totalProfit: number;
  averageROI: number;
  highValueDeals: number;
  hotDeals: number;
}

export function OpportunityDashboard() {
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [stats, setStats] = useState<DashboardStats>({
    totalOpportunities: 0,
    totalProfit: 0,
    averageROI: 0,
    highValueDeals: 0,
    hotDeals: 0
  });
  const [loading, setLoading] = useState(true);
  const [selectedOpportunity, setSelectedOpportunity] = useState<Opportunity | null>(null);
  const [activeTab, setActiveTab] = useState('overview');

  const { analysis, analyzeOpportunity, isLoading: analysisLoading } = useMarketAnalysis();
  const marketMetrics = useMarketMetrics(opportunities);
  const optimizer = useAdvancedOptimizer({
    enableVirtualization: true,
    enableBatching: true,
    enableMemoization: true
  });
  const { toast } = useToast();

  useEffect(() => {
    fetchOpportunities();
    
    // Set up real-time updates
    const channel = supabase
      .channel('opportunities-changes')
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table: 'opportunities' },
        () => fetchOpportunities()
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, []);

  const fetchOpportunities = async () => {
    try {
      const { data, error } = await supabase
        .from('opportunities')
        .select('*')
        .eq('is_active', true)
        .order('score', { ascending: false })
        .limit(100);

      if (error) throw error;

      const processedOpportunities = await optimizer.batchProcess(
        data || [],
        (opportunity) => ({
          ...opportunity,
          expected_price: opportunity.estimated_sale_price || 0,
          acquisition_cost: opportunity.current_bid || 0,
          profit: opportunity.potential_profit,
          roi: opportunity.roi_percentage,
          confidence: opportunity.confidence_score,
          status: (opportunity.status as "hot" | "good" | "moderate") || 'moderate',
          vehicle: {
            make: opportunity.make,
            model: opportunity.model,
            year: opportunity.year,
            mileage: opportunity.mileage || 0,
            vin: opportunity.vin || ''
          }
        }),
        (progress) => console.log(`Processing opportunities: ${progress}%`)
      );

      setOpportunities(processedOpportunities);
      calculateStats(processedOpportunities);
    } catch (error) {
      console.error('Error fetching opportunities:', error);
      toast({
        title: "Error",
        description: "Failed to fetch opportunities",
        variant: "destructive"
      });
    } finally {
      setLoading(false);
    }
  };

  const calculateStats = (opps: Opportunity[]) => {
    const totalProfit = opps.reduce((sum, opp) => sum + opp.profit, 0);
    const averageROI = opps.length > 0 
      ? opps.reduce((sum, opp) => sum + opp.roi, 0) / opps.length 
      : 0;
    const highValueDeals = opps.filter(opp => opp.profit > 5000).length;
    const hotDeals = opps.filter(opp => opp.status === 'hot').length;

    setStats({
      totalOpportunities: opps.length,
      totalProfit,
      averageROI,
      highValueDeals,
      hotDeals
    });
  };

  const handleAnalyzeOpportunity = async (opportunity: Opportunity) => {
    setSelectedOpportunity(opportunity);
    await analyzeOpportunity(opportunity);
    setActiveTab('analysis');
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'hot': return 'bg-red-500';
      case 'good': return 'bg-green-500';
      case 'moderate': return 'bg-yellow-500';
      default: return 'bg-gray-500';
    }
  };

  const getROIColor = (roi: number) => {
    if (roi >= 25) return 'text-green-600';
    if (roi >= 15) return 'text-yellow-600';
    return 'text-red-600';
  };

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0
    }).format(amount);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto mb-4"></div>
          <p className="text-muted-foreground">Loading opportunities...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Stats Overview */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Opportunities</CardTitle>
            <Target className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.totalOpportunities}</div>
            <p className="text-xs text-muted-foreground">
              {marketMetrics.marketMomentum === 'bullish' ? '+' : marketMetrics.marketMomentum === 'bearish' ? '-' : ''}
              Active deals in pipeline
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Profit Potential</CardTitle>
            <DollarSign className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{formatCurrency(stats.totalProfit)}</div>
            <p className="text-xs text-muted-foreground">
              Combined opportunity value
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Average ROI</CardTitle>
            <BarChart3 className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className={`text-2xl font-bold ${getROIColor(stats.averageROI)}`}>
              {stats.averageROI.toFixed(1)}%
            </div>
            <p className="text-xs text-muted-foreground">
              Return on investment
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">High Value Deals</CardTitle>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.highValueDeals}</div>
            <p className="text-xs text-muted-foreground">
              Profit over $5,000
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Hot Deals</CardTitle>
            <Zap className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-red-600">{stats.hotDeals}</div>
            <p className="text-xs text-muted-foreground">
              Immediate action required
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Market Momentum Alert */}
      {marketMetrics.marketMomentum !== 'neutral' && (
        <Alert>
          <TrendingUp className="h-4 w-4" />
          <AlertDescription>
            Market is currently <strong>{marketMetrics.marketMomentum}</strong>. 
            {marketMetrics.marketMomentum === 'bullish' 
              ? ' Great time to acquire inventory!' 
              : ' Exercise caution with high-risk opportunities.'}
          </AlertDescription>
        </Alert>
      )}

      {/* Main Dashboard */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="overview">Opportunity List</TabsTrigger>
          <TabsTrigger value="analysis">Market Analysis</TabsTrigger>
          <TabsTrigger value="performance">Performance</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-4">
          <div className="grid gap-4">
            {opportunities.map((opportunity) => (
              <Card key={opportunity.id} className="hover:shadow-md transition-shadow">
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-3">
                      <Badge className={`${getStatusColor(opportunity.status || 'moderate')} text-white`}>
                        {opportunity.status?.toUpperCase()}
                      </Badge>
                      <CardTitle className="text-lg">
                        {opportunity.vehicle.year} {opportunity.vehicle.make} {opportunity.vehicle.model}
                      </CardTitle>
                    </div>
                    <div className="text-right">
                      <div className="text-2xl font-bold text-green-600">
                        {formatCurrency(opportunity.profit)}
                      </div>
                      <div className={`text-sm ${getROIColor(opportunity.roi)}`}>
                        {opportunity.roi.toFixed(1)}% ROI
                      </div>
                    </div>
                  </div>
                  <CardDescription className="flex items-center space-x-4">
                    <span className="flex items-center">
                      <MapPin className="h-4 w-4 mr-1" />
                      {opportunity.location}, {opportunity.state}
                    </span>
                    <span className="flex items-center">
                      <Clock className="h-4 w-4 mr-1" />
                      {opportunity.source_site}
                    </span>
                    {opportunity.risk_score > 70 && (
                      <span className="flex items-center text-yellow-600">
                        <AlertTriangle className="h-4 w-4 mr-1" />
                        High Risk
                      </span>
                    )}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                    <div>
                      <div className="text-sm text-muted-foreground">Current Bid</div>
                      <div className="font-medium">{formatCurrency(opportunity.current_bid)}</div>
                    </div>
                    <div>
                      <div className="text-sm text-muted-foreground">Est. Sale Price</div>
                      <div className="font-medium">{formatCurrency(opportunity.estimated_sale_price)}</div>
                    </div>
                    <div>
                      <div className="text-sm text-muted-foreground">Total Cost</div>
                      <div className="font-medium">{formatCurrency(opportunity.total_cost)}</div>
                    </div>
                    <div>
                      <div className="text-sm text-muted-foreground">Confidence</div>
                      <div className="flex items-center space-x-2">
                        <Progress value={opportunity.confidence} className="flex-1" />
                        <span className="text-sm">{opportunity.confidence}%</span>
                      </div>
                    </div>
                  </div>
                  <div className="flex justify-between items-center">
                    <div className="text-sm text-muted-foreground">
                      VIN: {opportunity.vehicle.vin || 'N/A'} - 
                      Mileage: {opportunity.vehicle.mileage?.toLocaleString() || 'N/A'}
                    </div>
                    <Button 
                      onClick={() => handleAnalyzeOpportunity(opportunity)}
                      variant="outline"
                      size="sm"
                    >
                      Analyze
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="analysis" className="space-y-4">
          {analysisLoading ? (
            <Card>
              <CardContent className="flex items-center justify-center h-64">
                <div className="text-center">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto mb-2"></div>
                  <p className="text-muted-foreground">Analyzing market data...</p>
                </div>
              </CardContent>
            </Card>
          ) : analysis && selectedOpportunity ? (
            <div className="grid gap-4">
              <Card>
                <CardHeader>
                  <CardTitle>Market Analysis for {selectedOpportunity.vehicle.year} {selectedOpportunity.vehicle.make} {selectedOpportunity.vehicle.model}</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div>
                      <h4 className="font-semibold mb-2">Market Trend</h4>
                      <div className="space-y-1">
                        <div className="flex justify-between">
                          <span className="text-sm">Average Price:</span>
                          <span className="font-medium">{formatCurrency(analysis.trend.averagePrice)}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-sm">Price Change:</span>
                          <span className={`font-medium ${analysis.trend.priceChange >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                            {analysis.trend.priceChange >= 0 ? '+' : ''}{analysis.trend.priceChange.toFixed(1)}%
                          </span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-sm">Demand Index:</span>
                          <span className="font-medium">{(analysis.trend.demandIndex * 100).toFixed(0)}%</span>
                        </div>
                      </div>
                    </div>
                    
                    <div>
                      <h4 className="font-semibold mb-2">Competitive Position</h4>
                      <div className="space-y-1">
                        <div className="flex justify-between">
                          <span className="text-sm">Market Position:</span>
                          <Badge variant={analysis.competitive.pricePosition === 'below' ? 'default' : 'secondary'}>
                            {analysis.competitive.pricePosition}
                          </Badge>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-sm">Competitors:</span>
                          <span className="font-medium">{analysis.competitive.competitorCount}</span>
                        </div>
                      </div>
                    </div>
                    
                    <div>
                      <h4 className="font-semibold mb-2">Profit Forecast</h4>
                      <div className="space-y-1">
                        <div className="flex justify-between">
                          <span className="text-sm">30-Day:</span>
                          <span className="font-medium">{formatCurrency(analysis.forecast.projectedProfit30Days)}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-sm">60-Day:</span>
                          <span className="font-medium">{formatCurrency(analysis.forecast.projectedProfit60Days)}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-sm">Opportunity Score:</span>
                          <span className="font-medium">{analysis.forecast.opportunityScore}/100</span>
                        </div>
                      </div>
                    </div>
                  </div>
                  
                  {analysis.forecast.riskFactors.length > 0 && (
                    <div>
                      <h4 className="font-semibold mb-2">Risk Factors</h4>
                      <ul className="list-disc list-inside space-y-1">
                        {analysis.forecast.riskFactors.map((risk, index) => (
                          <li key={index} className="text-sm text-muted-foreground">{risk}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  
                  <div>
                    <h4 className="font-semibold mb-2">Recommendation</h4>
                    <Alert>
                      <AlertDescription>
                        {analysis.competitive.recommendedAction}
                      </AlertDescription>
                    </Alert>
                  </div>
                </CardContent>
              </Card>
            </div>
          ) : (
            <Card>
              <CardContent className="flex items-center justify-center h-64">
                <p className="text-muted-foreground">Select an opportunity to view market analysis</p>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="performance" className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card>
              <CardHeader>
                <CardTitle>Risk Distribution</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  <div className="flex justify-between items-center">
                    <span className="text-sm">Low Risk</span>
                    <div className="flex items-center space-x-2">
                      <Progress value={(marketMetrics.riskDistribution.low / opportunities.length) * 100} className="w-24" />
                      <span className="text-sm font-medium">{marketMetrics.riskDistribution.low}</span>
                    </div>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-sm">Medium Risk</span>
                    <div className="flex items-center space-x-2">
                      <Progress value={(marketMetrics.riskDistribution.medium / opportunities.length) * 100} className="w-24" />
                      <span className="text-sm font-medium">{marketMetrics.riskDistribution.medium}</span>
                    </div>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-sm">High Risk</span>
                    <div className="flex items-center space-x-2">
                      <Progress value={(marketMetrics.riskDistribution.high / opportunities.length) * 100} className="w-24" />
                      <span className="text-sm font-medium">{marketMetrics.riskDistribution.high}</span>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Top Performers</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {marketMetrics.topPerformers.slice(0, 5).map((opp, index) => (
                    <div key={opp.id} className="flex justify-between items-center">
                      <div className="flex items-center space-x-2">
                        <Badge variant="outline">{index + 1}</Badge>
                        <span className="text-sm">{opp.vehicle.year} {opp.vehicle.make}</span>
                      </div>
                      <span className="text-sm font-medium text-green-600">
                        {formatCurrency(opp.profit)}
                      </span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}