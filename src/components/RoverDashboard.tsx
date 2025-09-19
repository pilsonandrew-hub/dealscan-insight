import React, { useState, useEffect, useCallback, useMemo } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import { roverAPI, DealItem, RoverRecommendations } from "@/services/roverAPI";
import { CrosshairSearch } from "./CrosshairSearch";
import { RoverAnalytics } from "./RoverAnalytics";
import { formatCurrency, formatMileage, formatScore, getScoreColor, timeAgo, formatDate, isHighValue } from "@/utils/roverUtils";
import { Rocket, Target, TrendingUp, AlertTriangle, Star, Clock, DollarSign, MapPin, Search, BarChart3, Crosshair } from "lucide-react";

interface RoverDashboardProps {
  isPremium: boolean;
  userId?: string;
}

interface SavedIntent {
  id: string;
  title: string;
  is_active: boolean;
  created_at?: string;
  last_scan_at?: string;
}

const REFRESH_MS = 5 * 60 * 1000; // 5 minutes

export const RoverDashboard: React.FC<RoverDashboardProps> = ({ isPremium, userId }) => {
  const [recommendations, setRecommendations] = useState<RoverRecommendations | null>(null);
  const [savedIntents, setSavedIntents] = useState<SavedIntent[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"feed" | "crosshair" | "intents" | "analytics">("feed");
  const { toast } = useToast();

  const currentUserId = useMemo(() => {
    if (userId) return userId;
    if (typeof window !== "undefined") {
      return (window as any).__USER_ID__ || "current_user";
    }
    return "current_user";
  }, [userId]);

  const loadRecommendations = useCallback(async () => {
    if (!isPremium) return;
    setLoading(true);
    setError(null);
    try {
      const recs = await roverAPI.getRecommendations(25);
      setRecommendations(recs);
    } catch {
      setError("Failed to load recommendations");
      toast({
        title: "Failed to load recommendations",
        description: "Please try again later.",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  }, [isPremium, toast]);

  const loadSavedIntents = useCallback(async () => {
    if (!isPremium) return;
    try {
      const intents = await roverAPI.getUserIntents();
      setSavedIntents((intents || []) as SavedIntent[]);
    } catch (e) {
      console.error("Failed to load saved intents:", e);
    }
  }, [isPremium]);

  useEffect(() => {
    if (!isPremium) return;
    let mounted = true;
    (async () => {
      await Promise.allSettled([loadRecommendations(), loadSavedIntents()]);
    })();
    const interval = setInterval(() => {
      if (mounted) loadRecommendations();
    }, REFRESH_MS);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, [isPremium, loadRecommendations, loadSavedIntents]);

  const handleItemInteraction = useCallback(
    async (item: DealItem, eventType: "view" | "click" | "save" | "bid") => {
      try {
        await roverAPI.trackEvent({ userId: currentUserId, event: eventType, item });
        if (eventType === "save") {
          toast({
            title: "Deal saved",
            description: `${[item.year, item.make, item.model].filter(Boolean).join(" ")} added to your watchlist.`,
          });
        } else if (eventType === "bid") {
          toast({
            title: "Bid tracked",
            description: "Your bidding activity has been recorded for better recommendations.",
          });
        }
      } catch (e) {
        console.warn("trackEvent failed", e);
      }
    },
    [currentUserId, toast]
  );

  const confidencePercent = useMemo(
    () => (recommendations ? Math.round((Number(recommendations.confidence) || 0) * 100) : 0),
    [recommendations]
  );

  const averageROI = useMemo(() => {
    const items = recommendations?.items || [];
    if (!items.length) return 0;
    const sum = items.reduce((acc, it: any) => acc + (Number(it.roi_percentage) || 0), 0);
    return Math.round(sum / items.length);
  }, [recommendations]);

  const highValueDeals = useMemo(() => {
    return recommendations?.items.filter(isHighValue).length || 0;
  }, [recommendations]);

  if (!isPremium) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-background to-muted/20">
        <div className="container mx-auto px-4 py-8">
          <div className="text-center py-12">
            <Rocket className="h-16 w-16 mx-auto mb-6 text-primary" aria-hidden />
            <h1 className="text-4xl font-bold mb-4 bg-gradient-to-r from-primary via-purple-500 to-accent bg-clip-text text-transparent">
              Rover Premium
            </h1>
            <p className="text-xl text-muted-foreground mb-8 max-w-2xl mx-auto">
              Your always-on intelligence engine that scouts the market for premium arbitrage opportunities.
            </p>
            <Card className="max-w-2xl mx-auto border-dashed border-2 border-primary/20">
              <CardHeader>
                <CardTitle className="text-2xl text-center">🎯 Premium Features</CardTitle>
                <CardDescription className="text-center">
                  Enterprise-grade ML recommendations with real-time market intelligence.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <FeatureLine icon={<TrendingUp className="h-5 w-5 text-primary" />} label="AI-Powered Recommendations" />
                  <FeatureLine icon={<Crosshair className="h-5 w-5 text-primary" />} label="Precision Crosshair Search" />
                  <FeatureLine icon={<AlertTriangle className="h-5 w-5 text-primary" />} label="Real-time Market Alerts" />
                  <FeatureLine icon={<Star className="h-5 w-5 text-primary" />} label="ML Arbitrage Scoring" />
                  <FeatureLine icon={<BarChart3 className="h-5 w-5 text-primary" />} label="Advanced Analytics" />
                  <FeatureLine icon={<Target className="h-5 w-5 text-primary" />} label="Intent Monitoring" />
                </div>
                <Button size="lg" className="w-full mt-6" onClick={() => window.dispatchEvent(new CustomEvent("open-upgrade-modal"))}>
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
              <p className="text-lg text-muted-foreground">Always-on market scouting • Premium arbitrage detection</p>
            </div>
            <Badge variant="secondary" className="bg-primary/10 text-primary border-primary/20" aria-label="Premium Active">
              <Rocket className="h-4 w-4 mr-1" aria-hidden /> Premium Active
            </Badge>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
          <StatCard title="Active Picks" value={recommendations?.items.length || 0} icon={<TrendingUp className="h-8 w-8 text-primary" />} />
          <StatCard title="Confidence" value={`${confidencePercent}%`} icon={<Target className="h-8 w-8 text-primary" />} />
          <StatCard title="High Value" value={highValueDeals} icon={<Star className="h-8 w-8 text-green-500" />} />
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">Last Update</p>
                  <p className="text-sm font-medium">
                    {recommendations?.precomputedAt ? timeAgo(recommendations.precomputedAt) : "Never"}
                  </p>
                </div>
                <Clock className="h-8 w-8 text-primary" aria-hidden />
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Tabs */}
        <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as typeof activeTab)}>
          <TabsList className="grid w-full grid-cols-4">
            <TabsTrigger value="feed">Rover Feed</TabsTrigger>
            <TabsTrigger value="crosshair">Crosshair Search</TabsTrigger>
            <TabsTrigger value="intents">Saved Intents</TabsTrigger>
            <TabsTrigger value="analytics">Analytics</TabsTrigger>
          </TabsList>

          <TabsContent value="feed" className="space-y-4">
            {/* Refresh control */}
            <div className="flex justify-end">
              <Button size="sm" variant="outline" onClick={loadRecommendations} disabled={loading}>
                Refresh
              </Button>
            </div>

            {error && (
              <Alert variant="destructive">
                <AlertTriangle className="h-4 w-4" aria-hidden />
                <AlertDescription>{error}. Please try refreshing.</AlertDescription>
              </Alert>
            )}

            {loading && !recommendations && <FeedSkeleton />}

            {!loading && recommendations?.items?.length === 0 && (
              <Alert>
                <AlertTriangle className="h-4 w-4" aria-hidden />
                <AlertDescription>
                  No recommendations yet. Rover is learning your preferences—interact with deals to improve suggestions.
                </AlertDescription>
              </Alert>
            )}

            {!loading && !!recommendations?.items?.length && (
              <div className="space-y-4">
                {recommendations.items.map((item) => (
                  <Card
                    key={item.id}
                    className="hover:shadow-lg transition-shadow cursor-pointer"
                    onClick={() => handleItemInteraction(item, "click")}
                    aria-label={`View ${[item.year, item.make, item.model].filter(Boolean).join(" ")}`}
                  >
                    <CardContent className="p-6">
                      <div className="flex items-center justify-between">
                        <div className="flex-1">
                          <div className="flex items-center space-x-3 mb-2">
                            <h3 className="text-lg font-semibold">{[item.year, item.make, item.model].filter(Boolean).join(" ")}</h3>
                            <Badge variant="outline" className={getScoreColor(item._score)}>
                              Score: {formatScore(item._score)}
                            </Badge>
                            {item.roi_percentage && (
                              <Badge variant="outline" className="bg-green-100 text-green-800">
                                ROI: {Math.round(item.roi_percentage)}%
                              </Badge>
                            )}
                            {isHighValue(item) && (
                              <Badge variant="default" className="bg-primary">
                                High Value
                              </Badge>
                            )}
                          </div>

                          <div className="flex items-center flex-wrap gap-4 text-sm text-muted-foreground">
                            <div className="flex items-center space-x-1">
                              <DollarSign className="h-4 w-4" aria-hidden />
                              <span>{formatCurrency(item.price)}</span>
                            </div>
                            {item.mileage && <span>{formatMileage(item.mileage)} miles</span>}
                            {item.state && (
                              <div className="flex items-center space-x-1">
                                <MapPin className="h-4 w-4" aria-hidden />
                                <span>{item.state}</span>
                              </div>
                            )}
                            {item.source && <Badge variant="secondary">{item.source}</Badge>}
                          </div>

                          {item.potential_profit && (
                            <div className="mt-2">
                              <span className="text-sm font-medium text-green-600">
                                Potential Profit: {formatCurrency(item.potential_profit)}
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
                              handleItemInteraction(item, "save");
                            }}
                            aria-label="Save deal"
                          >
                            Save
                          </Button>
                          <Button 
                            size="sm" 
                            onClick={(e) => {
                              e.stopPropagation();
                              handleItemInteraction(item, "bid");
                            }}
                          >
                            Track Bid
                          </Button>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </TabsContent>

          <TabsContent value="crosshair" className="space-y-4">
            <CrosshairSearch onResultsFound={(results) => {
              toast({
                title: "Search Results",
                description: `Found ${results.length} matching opportunities.`
              });
            }} />
          </TabsContent>

          <TabsContent value="intents" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>Saved Search Intents</CardTitle>
                <CardDescription>Rover monitors these and alerts you to new matches.</CardDescription>
              </CardHeader>
              <CardContent>
                {savedIntents.length > 0 ? (
                  <div className="space-y-3">
                    {savedIntents.map((intent) => (
                      <div key={intent.id} className="flex items-center justify-between p-3 border rounded-lg">
                        <div>
                          <h4 className="font-medium">{intent.title}</h4>
                          <p className="text-sm text-muted-foreground">
                            Last scan: {formatDate(intent.last_scan_at || intent.created_at)}
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
            <RoverAnalytics />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
};

/* ------------------------------ helpers ------------------------------ */

function FeatureLine({ icon, label }: { icon: React.ReactNode; label: string }) {
  return (
    <div className="flex items-center space-x-3">
      {icon}
      <span>{label}</span>
    </div>
  );
}

function StatCard({ title, value, icon }: { title: string; value: React.ReactNode; icon: React.ReactNode }) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-muted-foreground">{title}</p>
            <p className="text-2xl font-bold">{value}</p>
          </div>
          {icon}
        </div>
      </CardContent>
    </Card>
  );
}

function FeedSkeleton() {
  return (
    <div className="grid gap-4">
      {Array.from({ length: 5 }).map((_, i) => (
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
  );
}

export default RoverDashboard;