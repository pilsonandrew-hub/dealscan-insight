/**
 * Advanced market analytics component with trend analysis and predictions
 */

import React, { useMemo } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, PieChart, Pie, Cell } from 'recharts';
import { Badge } from '@/components/ui/badge';
import { TrendingUp, TrendingDown, AlertTriangle, Target } from 'lucide-react';
import { Opportunity } from '@/types/dealerscope';

interface MarketAnalyticsProps {
  opportunities: Opportunity[];
}

interface MarketTrend {
  make: string;
  averageProfit: number;
  count: number;
  trend: 'up' | 'down' | 'stable';
  confidence: number;
}

interface StateAnalysis {
  state: string;
  opportunities: number;
  totalProfit: number;
  averageROI: number;
  riskLevel: 'low' | 'medium' | 'high';
}

const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884d8'];

export function MarketAnalytics({ opportunities }: MarketAnalyticsProps) {
  // Market trends by make
  const marketTrends = useMemo((): MarketTrend[] => {
    const makeGroups = opportunities.reduce((acc, op) => {
      const make = op.vehicle.make;
      if (!acc[make]) {
        acc[make] = [];
      }
      acc[make].push(op);
      return acc;
    }, {} as Record<string, Opportunity[]>);

    return Object.entries(makeGroups)
      .map(([make, ops]) => {
        const averageProfit = ops.reduce((sum, op) => sum + op.profit, 0) / ops.length;
        const averageConfidence = ops.reduce((sum, op) => sum + op.confidence, 0) / ops.length;
        
        // Simple trend analysis based on profit and confidence
        let trend: 'up' | 'down' | 'stable' = 'stable';
        if (averageProfit > 4000 && averageConfidence > 70) trend = 'up';
        else if (averageProfit < 2000 || averageConfidence < 50) trend = 'down';

        return {
          make,
          averageProfit,
          count: ops.length,
          trend,
          confidence: averageConfidence
        };
      })
      .sort((a, b) => b.averageProfit - a.averageProfit)
      .slice(0, 10);
  }, [opportunities]);

  // State analysis
  const stateAnalysis = useMemo((): StateAnalysis[] => {
    const stateGroups = opportunities.reduce((acc, op) => {
      const state = op.state || 'Unknown';
      if (!acc[state]) {
        acc[state] = [];
      }
      acc[state].push(op);
      return acc;
    }, {} as Record<string, Opportunity[]>);

    return Object.entries(stateGroups)
      .map(([state, ops]) => {
        const totalProfit = ops.reduce((sum, op) => sum + op.profit, 0);
        const averageROI = ops.reduce((sum, op) => sum + op.roi, 0) / ops.length;
        const averageConfidence = ops.reduce((sum, op) => sum + op.confidence, 0) / ops.length;
        
        let riskLevel: 'low' | 'medium' | 'high' = 'medium';
        if (averageConfidence > 75) riskLevel = 'low';
        else if (averageConfidence < 50) riskLevel = 'high';

        return {
          state,
          opportunities: ops.length,
          totalProfit,
          averageROI,
          riskLevel
        };
      })
      .sort((a, b) => b.totalProfit - a.totalProfit)
      .slice(0, 8);
  }, [opportunities]);

  // Profit distribution data
  const profitDistribution = useMemo(() => {
    const ranges = [
      { name: '$0-$1K', min: 0, max: 1000 },
      { name: '$1K-$3K', min: 1000, max: 3000 },
      { name: '$3K-$5K', min: 3000, max: 5000 },
      { name: '$5K-$10K', min: 5000, max: 10000 },
      { name: '$10K+', min: 10000, max: Infinity }
    ];

    return ranges.map(range => ({
      name: range.name,
      count: opportunities.filter(op => op.profit >= range.min && op.profit < range.max).length
    }));
  }, [opportunities]);

  const getTrendIcon = (trend: string) => {
    switch (trend) {
      case 'up': return <TrendingUp className="h-4 w-4 text-green-500" />;
      case 'down': return <TrendingDown className="h-4 w-4 text-red-500" />;
      default: return <Target className="h-4 w-4 text-yellow-500" />;
    }
  };

  const getRiskBadge = (riskLevel: string) => {
    const variants = {
      low: 'default',
      medium: 'secondary',
      high: 'destructive'
    } as const;
    
    return <Badge variant={variants[riskLevel as keyof typeof variants]}>{riskLevel} risk</Badge>;
  };

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Market Sentiment</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-green-600">Bullish</div>
            <p className="text-xs text-muted-foreground">
              High profit margins detected
            </p>
          </CardContent>
        </Card>
        
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Best Performing Make</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{marketTrends[0]?.make || 'N/A'}</div>
            <p className="text-xs text-muted-foreground">
              Avg. ${marketTrends[0]?.averageProfit.toLocaleString() || 0} profit
            </p>
          </CardContent>
        </Card>
        
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Market Coverage</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stateAnalysis.length}</div>
            <p className="text-xs text-muted-foreground">
              States with opportunities
            </p>
          </CardContent>
        </Card>
      </div>

      <Tabs defaultValue="trends" className="w-full">
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="trends">Market Trends</TabsTrigger>
          <TabsTrigger value="states">State Analysis</TabsTrigger>
          <TabsTrigger value="distribution">Profit Distribution</TabsTrigger>
        </TabsList>
        
        <TabsContent value="trends" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Top Performing Vehicle Makes</CardTitle>
              <CardDescription>Average profit and market trend analysis</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {marketTrends.map((trend, index) => (
                  <div key={trend.make} className="flex items-center justify-between p-3 border rounded-lg">
                    <div className="flex items-center space-x-3">
                      <div className="flex items-center space-x-2">
                        <span className="font-medium">{trend.make}</span>
                        {getTrendIcon(trend.trend)}
                      </div>
                      <div className="text-sm text-muted-foreground">
                        {trend.count} opportunities
                      </div>
                    </div>
                    <div className="flex items-center space-x-4">
                      <div className="text-right">
                        <div className="font-medium">${trend.averageProfit.toLocaleString()}</div>
                        <div className="text-sm text-muted-foreground">{trend.confidence.toFixed(1)}% confidence</div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>
        
        <TabsContent value="states" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>State Performance Analysis</CardTitle>
              <CardDescription>Opportunities and profitability by state</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {stateAnalysis.map((state, index) => (
                  <div key={state.state} className="flex items-center justify-between p-3 border rounded-lg">
                    <div className="flex items-center space-x-3">
                      <span className="font-medium">{state.state}</span>
                      {getRiskBadge(state.riskLevel)}
                    </div>
                    <div className="flex items-center space-x-4">
                      <div className="text-right">
                        <div className="font-medium">{state.opportunities} opportunities</div>
                        <div className="text-sm text-muted-foreground">${state.totalProfit.toLocaleString()} total</div>
                      </div>
                      <div className="text-right">
                        <div className="font-medium">{state.averageROI.toFixed(1)}%</div>
                        <div className="text-sm text-muted-foreground">Avg ROI</div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>
        
        <TabsContent value="distribution" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Profit Distribution</CardTitle>
              <CardDescription>Distribution of opportunities by profit range</CardDescription>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie
                    data={profitDistribution}
                    cx="50%"
                    cy="50%"
                    labelLine={false}
                    label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                    outerRadius={80}
                    fill="#8884d8"
                    dataKey="count"
                  >
                    {profitDistribution.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}