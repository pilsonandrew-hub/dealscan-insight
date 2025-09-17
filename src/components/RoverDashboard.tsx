import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Skeleton } from '@/components/ui/skeleton';
import { useToast } from '@/hooks/use-toast';
import { roverAPI, DealItem, RoverRecommendations } from '@/services/roverAPI';
import { Rocket, Target, TrendingUp, AlertTriangle, Star, Clock, DollarSign, MapPin } from 'lucide-react';

interface RoverDashboardProps {
  isPremium: boolean;
}

export const RoverDashboard: React.FC<RoverDashboardProps> = ({ isPremium }) => {
  const [recommendations, setRecommendations] = useState<RoverRecommendations | null>(null);
  const [savedIntents, setSavedIntents] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('feed');
  const { toast } = useToast();

  const loadRecommendations = useCallback(async () => {
    if (!isPremium) return;
    
    try {
      setLoading(true);
      const recs = await roverAPI.getRecommendations(25);
      setRecommendations(recs);
    } catch (error) {
      toast({
        title: "Failed to load recommendations",
        description: "Please try again later",
        variant: "destructive"
      });
    } finally {
      setLoading(false);
    }
  }, [isPremium, toast]);

  const loadSavedIntents = useCallback(async () => {
    if (!isPremium) return;
    
    try {
      const intents = await roverAPI.getUserIntents();
      setSavedIntents(intents);
    } catch (error) {
      console.error('Failed to load saved intents:', error);
    }
  }, [isPremium]);

  useEffect(() => {
    if (isPremium) {
      loadRecommendations();
      loadSavedIntents();

      // Auto-refresh every 5 minutes
      const interval = setInterval(loadRecommendations, 5 * 60 * 1000);
      return () => clearInterval(interval);
    }
  }, [isPremium, loadRecommendations, loadSavedIntents]);

  const handleItemInteraction = async (item: DealItem, eventType: 'view' | 'click' | 'save') => {
    await roverAPI.trackEvent({
      userId: 'current_user',
      event: eventType,
      item
    });

    if (eventType === 'save') {
      toast({
        title: "Deal saved!",
        description: `${item.year} ${item.make} ${item.model} added to your watchlist`,
      });
    }
  };

  if (!isPremium) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-background to-muted/20">
        <div className="container mx-auto px-4 py-8">
          <div className="text-center py-12">
            <Rocket className="h-16 w-16 mx-auto mb-6 text-primary" />
            <h1 className="text-4xl font-bold mb-4 bg-gradient-to-r from-primary via-purple-500 to-accent bg-clip-text text-transparent">
              Rover Premium
            </h1>
            <p className="text-xl text-muted-foreground mb-8 max-w-2xl mx-auto">
              Your always-on intelligence engine that scouts the market for premium arbitrage opportunities
            </p>
            
            <Card className="max-w-2xl mx-auto border-dashed border-2 border-primary/20">
              <CardHeader>
                <CardTitle className="text-2xl text-center">🎯 Premium Features</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="flex items-center space-x-3">
                    <TrendingUp className="h-5 w-5 text-primary" />
                    <span>AI-Powered Recommendations</span>
                  </div>
                  <div className="flex items-center space-x-3">
                    <Target className="h-5 w-5 text-primary" />
                    <span>Precision Crosshair Search</span>
                  </div>
                  <div className="flex items-center space-x-3">
                    <AlertTriangle className="h-5 w-5 text-primary" />
                    <span>Real-time Alerts</span>
                  </div>
                  <div className="flex items-center space-x-3">
                    <Star className="h-5 w-5 text-primary" />
                    <span>Advanced ML Scoring</span>
                  </div>
                </div>
                <Button size="lg" className="w-full mt-6">
                  Upgrade to Premium
                </Button>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-background to-muted/20">
      <div className="container mx-auto px-4 py-8">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-4xl font-bold mb-2 bg-gradient-to-r from-primary via-purple-500 to-accent bg-clip-text text-transparent">
                Rover Intelligence
              </h1>
              <p className="text-lg text-muted-foreground">
                Always-on market scouting • Premium arbitrage detection
              </p>
            </div>
            <Badge variant="secondary" className="bg-primary/10 text-primary border-primary/20">
              <Rocket className="h-4 w-4 mr-1" />
              Premium Active
            </Badge>
          </div>
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">Active Picks</p>
                  <p className="text-2xl font-bold">{recommendations?.items.length || 0}</p>
                </div>
                <TrendingUp className="h-8 w-8 text-primary" />
              </div>
            </CardContent>
          </Card>
          
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">Confidence</p>
                  <p className="text-2xl font-bold">
                    {recommendations ? Math.round(recommendations.confidence * 100) : 0}%
                  </p>
                </div>
                <Target className="h-8 w-8 text-primary" />
              </div>
            </CardContent>
          </Card>
          
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">Saved Intents</p>
                  <p className="text-2xl font-bold">{savedIntents.length}</p>
                </div>
                <Star className="h-8 w-8 text-primary" />
              </div>
            </CardContent>
          </Card>
          
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">Last Update</p>
                  <p className="text-sm font-medium">
                    {recommendations?.precomputedAt ? 
                      new Date(recommendations.precomputedAt).toLocaleTimeString() : 'Never'
                    }
                  </p>
                </div>
                <Clock className="h-8 w-8 text-primary" />
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Main Content Tabs */}
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="feed">Rover Feed</TabsTrigger>
            <TabsTrigger value="intents">Saved Intents</TabsTrigger>
            <TabsTrigger value="analytics">Analytics</TabsTrigger>
          </TabsList>

          <TabsContent value="feed" className="space-y-4">
            {loading ? (
              <div className="grid gap-4">
                {[...Array(5)].map((_, i) => (
                  <Card key={i}>
                    <CardContent className="p-6">
                      <div className="flex items-center space-x-4">
                        <Skeleton className="h-12 w-12 rounded-full" />
                        <div className="space-y-2 flex-1">
                          <Skeleton className="h-4 w-[250px]" />
                          <Skeleton className="h-4 w-[200px]" />
                        </div>
                        <Skeleton className="h-10 w-20" />
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            ) : recommendations?.items.length ? (
              <div className="space-y-4">
                {recommendations.items.map((item) => (
                  <Card key={item.id} className="hover:shadow-lg transition-shadow cursor-pointer"
                    onClick={() => handleItemInteraction(item, 'click')}>
                    <CardContent className="p-6">
                      <div className="flex items-center justify-between">
                        <div className="flex-1">
                          <div className="flex items-center space-x-3 mb-2">
                            <h3 className="text-lg font-semibold">
                              {item.year} {item.make} {item.model}
                            </h3>
                            <Badge variant="outline" className="bg-primary/10 text-primary">
                              Score: {Math.round((item._score || 0) * 100)}
                            </Badge>
                            {item.roi_percentage && (
                              <Badge variant="outline" className="bg-green-100 text-green-800">
                                ROI: {Math.round(item.roi_percentage)}%
                              </Badge>
                            )}
                          </div>
                          
                          <div className="flex items-center space-x-6 text-sm text-muted-foreground">
                            <div className="flex items-center space-x-1">
                              <DollarSign className="h-4 w-4" />
                              <span>${item.price?.toLocaleString()}</span>
                            </div>
                            {item.mileage && (
                              <span>{item.mileage.toLocaleString()} miles</span>
                            )}
                            {item.state && (
                              <div className="flex items-center space-x-1">
                                <MapPin className="h-4 w-4" />
                                <span>{item.state}</span>
                              </div>
                            )}
                            {item.source && (
                              <Badge variant="secondary">{item.source}</Badge>
                            )}
                          </div>
                          
                          {item.potential_profit && (
                            <div className="mt-2">
                              <span className="text-sm font-medium text-green-600">
                                Potential Profit: ${item.potential_profit.toLocaleString()}
                              </span>
                            </div>
                          )}
                        </div>
                        
                        <div className="flex space-x-2">
                          <Button 
                            variant="outline" 
                            size="sm"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleItemInteraction(item, 'save');
                            }}
                          >
                            Save
                          </Button>
                          <Button size="sm">
                            View Details
                          </Button>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            ) : (
              <Alert>
                <AlertTriangle className="h-4 w-4" />
                <AlertDescription>
                  No recommendations available yet. Rover is learning your preferences - interact with deals to improve suggestions.
                </AlertDescription>
              </Alert>
            )}
          </TabsContent>

          <TabsContent value="intents" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>Saved Search Intents</CardTitle>
                <CardDescription>
                  Rover automatically monitors these searches and alerts you to new matches
                </CardDescription>
              </CardHeader>
              <CardContent>
                {savedIntents.length > 0 ? (
                  <div className="space-y-3">
                    {savedIntents.map((intent) => (
                      <div key={intent.id} className="flex items-center justify-between p-3 border rounded-lg">
                        <div>
                          <h4 className="font-medium">{intent.title}</h4>
                          <p className="text-sm text-muted-foreground">
                            Last scan: {new Date(intent.last_scan_at || intent.created_at).toLocaleDateString()}
                          </p>
                        </div>
                        <Badge variant={intent.is_active ? "default" : "secondary"}>
                          {intent.is_active ? "Active" : "Paused"}
                        </Badge>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-muted-foreground text-center py-4">
                    No saved intents yet. Use Crosshair search to create targeted alerts.
                  </p>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="analytics" className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Card>
                <CardHeader>
                  <CardTitle>Performance Metrics</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    <div className="flex justify-between">
                      <span>Recommendation Accuracy</span>
                      <span className="font-medium">
                        {recommendations ? Math.round(recommendations.confidence * 100) : 0}%
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span>Average ROI</span>
                      <span className="font-medium">
                        {recommendations?.items.length ? 
                          Math.round(recommendations.items.reduce((acc, item) => 
                            acc + (item.roi_percentage || 0), 0) / recommendations.items.length) : 0}%
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span>Active Opportunities</span>
                      <span className="font-medium">{recommendations?.items.length || 0}</span>
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Learning Status</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    <div className="flex justify-between">
                      <span>Data Collection</span>
                      <Badge variant="default">Active</Badge>
                    </div>
                    <div className="flex justify-between">
                      <span>Model Training</span>
                      <Badge variant="default">Continuous</Badge>
                    </div>
                    <div className="flex justify-between">
                      <span>Preference Learning</span>
                      <Badge variant="default">Improving</Badge>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
};

export default RoverDashboard;