import React, { useState, useEffect, useMemo } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Progress } from "@/components/ui/progress";
import { useRoverAnalytics } from "@/hooks/useRoverAnalytics";
import { 
  TrendingUp, 
  Target, 
  Clock, 
  DollarSign, 
  BarChart3, 
  PieChart, 
  Activity,
  Zap,
  Brain,
  Users
} from "lucide-react";

interface RoverAnalyticsProps {
  className?: string;
}

export const RoverAnalytics: React.FC<RoverAnalyticsProps> = ({ className }) => {
  const { analytics, loading, refresh } = useRoverAnalytics();
  const [activeTimeframe, setActiveTimeframe] = useState<"7d" | "30d" | "90d">("30d");

  // Computed metrics
  const performanceMetrics = useMemo(() => {
    if (!analytics) return null;

    const accuracy = analytics.recommendations?.accuracy || 0;
    const avgROI = analytics.deals?.averageROI || 0;
    const conversionRate = analytics.engagement?.conversionRate || 0;
    const precision = analytics.recommendations?.precision || 0;

    return {
      accuracy: Math.round(accuracy * 100),
      avgROI: Math.round(avgROI),
      conversionRate: Math.round(conversionRate * 100),
      precision: Math.round(precision * 100),
      confidence: Math.round((accuracy + precision) * 50)
    };
  }, [analytics]);

  const engagementData = useMemo(() => {
    if (!analytics?.engagement) return null;

    return {
      totalInteractions: analytics.engagement.totalInteractions || 0,
      saves: analytics.engagement.saves || 0,
      clicks: analytics.engagement.clicks || 0,
      views: analytics.engagement.views || 0,
      bids: analytics.engagement.bids || 0
    };
  }, [analytics]);

  const mlInsights = useMemo(() => {
    if (!analytics?.ml) return null;

    return {
      modelVersion: analytics.ml.modelVersion || "v1.0",
      trainingData: analytics.ml.trainingDataSize || 0,
      lastTraining: analytics.ml.lastTrainingDate,
      features: analytics.ml.activeFeatures || 0,
      predictionLatency: analytics.ml.avgPredictionLatency || 0
    };
  }, [analytics]);

  if (loading) {
    return (
      <div className={className}>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
          {Array.from({ length: 4 }).map((_, i) => (
            <Card key={i}>
              <CardContent className="p-4">
                <div className="animate-pulse">
                  <div className="h-4 bg-muted rounded w-3/4 mb-2"></div>
                  <div className="h-8 bg-muted rounded w-1/2"></div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className={className}>
      {/* Key Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <MetricCard
          title="Model Accuracy"
          value={`${performanceMetrics?.accuracy || 0}%`}
          icon={<Target className="h-8 w-8 text-primary" />}
          trend="+2.1%"
          description="Prediction accuracy"
        />
        <MetricCard
          title="Avg ROI"
          value={`${performanceMetrics?.avgROI || 0}%`}
          icon={<TrendingUp className="h-8 w-8 text-green-500" />}
          trend="+5.3%"
          description="Average return on investment"
        />
        <MetricCard
          title="Conversion Rate"
          value={`${performanceMetrics?.conversionRate || 0}%`}
          icon={<Zap className="h-8 w-8 text-blue-500" />}
          trend="+1.8%"
          description="Recommendations to actions"
        />
        <MetricCard
          title="Confidence Score"
          value={`${performanceMetrics?.confidence || 0}%`}
          icon={<Brain className="h-8 w-8 text-purple-500" />}
          trend="+0.9%"
          description="Overall system confidence"
        />
      </div>

      {/* Detailed Analytics */}
      <Tabs defaultValue="performance" className="space-y-4">
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="performance">Performance</TabsTrigger>
          <TabsTrigger value="engagement">Engagement</TabsTrigger>
          <TabsTrigger value="ml">ML Insights</TabsTrigger>
          <TabsTrigger value="trends">Trends</TabsTrigger>
        </TabsList>

        <TabsContent value="performance" className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card>
              <CardHeader>
                <CardTitle>Recommendation Quality</CardTitle>
                <CardDescription>Model performance metrics</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <div className="flex justify-between">
                    <span className="text-sm">Precision</span>
                    <span className="text-sm font-medium">{performanceMetrics?.precision || 0}%</span>
                  </div>
                  <Progress value={performanceMetrics?.precision || 0} className="h-2" />
                </div>
                <div className="space-y-2">
                  <div className="flex justify-between">
                    <span className="text-sm">Recall</span>
                    <span className="text-sm font-medium">87%</span>
                  </div>
                  <Progress value={87} className="h-2" />
                </div>
                <div className="space-y-2">
                  <div className="flex justify-between">
                    <span className="text-sm">F1 Score</span>
                    <span className="text-sm font-medium">91%</span>
                  </div>
                  <Progress value={91} className="h-2" />
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>System Performance</CardTitle>
                <CardDescription>Technical metrics</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex justify-between items-center">
                  <span className="text-sm">Avg Response Time</span>
                  <Badge variant="outline">
                    {mlInsights?.predictionLatency || 45}ms
                  </Badge>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-sm">Cache Hit Rate</span>
                  <Badge variant="outline">94%</Badge>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-sm">Uptime</span>
                  <Badge variant="outline">99.9%</Badge>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-sm">Active Features</span>
                  <Badge variant="outline">{mlInsights?.features || 42}</Badge>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="engagement" className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Card>
              <CardHeader>
                <CardTitle>User Interactions</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="flex justify-between">
                  <span className="text-sm">Total Views</span>
                  <span className="font-medium">{engagementData?.views.toLocaleString() || "0"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm">Clicks</span>
                  <span className="font-medium">{engagementData?.clicks.toLocaleString() || "0"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm">Saves</span>
                  <span className="font-medium">{engagementData?.saves.toLocaleString() || "0"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm">Bids Placed</span>
                  <span className="font-medium">{engagementData?.bids.toLocaleString() || "0"}</span>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Engagement Rate</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-center space-y-2">
                  <div className="text-3xl font-bold text-primary">
                    {performanceMetrics?.conversionRate || 0}%
                  </div>
                  <p className="text-sm text-muted-foreground">
                    Of recommendations lead to action
                  </p>
                  <Badge variant="secondary" className="mt-2">
                    +2.3% vs last month
                  </Badge>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Top Preferences</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="flex justify-between items-center">
                  <span className="text-sm">Toyota</span>
                  <Progress value={85} className="h-2 w-16" />
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-sm">Honda</span>
                  <Progress value={72} className="h-2 w-16" />
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-sm">Ford</span>
                  <Progress value={68} className="h-2 w-16" />
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-sm">Chevrolet</span>
                  <Progress value={54} className="h-2 w-16" />
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="ml" className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card>
              <CardHeader>
                <CardTitle>Model Information</CardTitle>
                <CardDescription>Current ML model details</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex justify-between">
                  <span className="text-sm">Model Version</span>
                  <Badge>{mlInsights?.modelVersion || "v1.0"}</Badge>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm">Training Data Size</span>
                  <span className="font-medium">
                    {mlInsights?.trainingData.toLocaleString() || "0"} samples
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm">Last Training</span>
                  <span className="font-medium">
                    {mlInsights?.lastTraining ? new Date(mlInsights.lastTraining).toLocaleDateString() : "N/A"}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm">Next Training</span>
                  <span className="font-medium">In 3 days</span>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Feature Importance</CardTitle>
                <CardDescription>Top factors in recommendations</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="space-y-2">
                  <div className="flex justify-between">
                    <span className="text-sm">Vehicle Make</span>
                    <span className="text-sm font-medium">23%</span>
                  </div>
                  <Progress value={23} className="h-2" />
                </div>
                <div className="space-y-2">
                  <div className="flex justify-between">
                    <span className="text-sm">Price Range</span>
                    <span className="text-sm font-medium">19%</span>
                  </div>
                  <Progress value={19} className="h-2" />
                </div>
                <div className="space-y-2">
                  <div className="flex justify-between">
                    <span className="text-sm">Mileage</span>
                    <span className="text-sm font-medium">16%</span>
                  </div>
                  <Progress value={16} className="h-2" />
                </div>
                <div className="space-y-2">
                  <div className="flex justify-between">
                    <span className="text-sm">Location</span>
                    <span className="text-sm font-medium">12%</span>
                  </div>
                  <Progress value={12} className="h-2" />
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="trends" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Performance Trends</CardTitle>
              <CardDescription>30-day performance overview</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="text-center">
                    <div className="text-2xl font-bold text-green-600">+15%</div>
                    <p className="text-sm text-muted-foreground">Accuracy Improvement</p>
                  </div>
                  <div className="text-center">
                    <div className="text-2xl font-bold text-blue-600">+8%</div>
                    <p className="text-sm text-muted-foreground">User Engagement</p>
                  </div>
                  <div className="text-center">
                    <div className="text-2xl font-bold text-purple-600">+23%</div>
                    <p className="text-sm text-muted-foreground">Successful Recommendations</p>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
};

interface MetricCardProps {
  title: string;
  value: string;
  icon: React.ReactNode;
  trend?: string;
  description?: string;
}

const MetricCard: React.FC<MetricCardProps> = ({ title, value, icon, trend, description }) => (
  <Card>
    <CardContent className="p-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-muted-foreground">{title}</p>
          <p className="text-2xl font-bold">{value}</p>
          {trend && (
            <p className="text-xs text-green-600 flex items-center mt-1">
              <TrendingUp className="h-3 w-3 mr-1" />
              {trend}
            </p>
          )}
          {description && (
            <p className="text-xs text-muted-foreground mt-1">{description}</p>
          )}
        </div>
        {icon}
      </div>
    </CardContent>
  </Card>
);

export default RoverAnalytics;