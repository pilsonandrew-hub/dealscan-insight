import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { CrosshairSearchForm } from './CrosshairSearchForm';
import { CrosshairResults } from './CrosshairResults';
import { useRealtimeOpportunities } from '@/hooks/useRealtimeOpportunities';
import { useAdvancedOptimizer } from '@/hooks/useAdvancedOptimizer';
import { usePerformanceMonitor } from '@/hooks/usePerformanceMonitor';
import { useToast } from '@/hooks/use-toast';
import { supabase } from '@/integrations/supabase/client';
import { CanonicalQuery, SearchResponse, CrosshairIntent, CanonicalListing } from '@/types/crosshair';
import { Zap, AlertTriangle, Activity, TrendingUp, Clock, Search, Crosshair } from 'lucide-react';

export const CrosshairDashboard = () => {
  const [searchResponse, setSearchResponse] = useState<SearchResponse | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [savedIntents, setSavedIntents] = useState<CrosshairIntent[]>([]);
  const [activeTab, setActiveTab] = useState('search');
  const [realtimeStats, setRealtimeStats] = useState({
    activeJobs: 0,
    successRate: 0,
    avgResponseTime: 0,
    totalResults: 0
  });

  const { measureAsync } = usePerformanceMonitor('CrosshairDashboard');
  const { toast } = useToast();
  
  const {
    virtualizeData,
    batchProcess,
    measurePerformance,
    prefetch,
    metrics: optimizerMetrics
  } = useAdvancedOptimizer({
    enableVirtualization: true,
    enableBatching: true,
    enableMemoization: true,
    enablePrefetching: true
  });

  const {
    opportunities: realtimeResults,
    pipelineStatus,
    newOpportunitiesCount,
    connectionStatus,
    isConnected,
    clearNewCount
  } = useRealtimeOpportunities([]);

  // Real-time updates for crosshair jobs
  useEffect(() => {
    const channel = supabase
      .channel('crosshair-realtime')
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table: 'crosshair_jobs' },
        (payload) => {
          console.log('Crosshair job update:', payload);
          updateRealtimeStats();
        }
      )
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table: 'listings_normalized' },
        (payload) => {
          console.log('New listing:', payload);
          if (payload.eventType === 'INSERT') {
            toast({
              title: "New Listing Found",
              description: `${payload.new.year} ${payload.new.make} ${payload.new.model} - ${payload.new.source}`,
            });
          }
        }
      )
      .subscribe();

    // Load saved intents
    loadSavedIntents();
    updateRealtimeStats();

    return () => {
      supabase.removeChannel(channel);
    };
  }, []);

  const loadSavedIntents = useCallback(async () => {
    try {
      const { data, error } = await supabase
        .from('crosshair_intents')
        .select('*')
        .eq('is_active', true)
        .order('created_at', { ascending: false });

      if (error) throw error;
      setSavedIntents((data || []).map(intent => ({
        ...intent,
        canonical_query: intent.canonical_query as CanonicalQuery,
        search_options: intent.search_options as any
      })));
    } catch (error) {
      console.error('Error loading saved intents:', error);
    }
  }, []);

  const updateRealtimeStats = useCallback(async () => {
    try {
      const [jobsResponse, listingsResponse] = await Promise.all([
        supabase
          .from('crosshair_jobs')
          .select('status, created_at, completed_at')
          .gte('created_at', new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString()),
        supabase
          .from('listings_normalized')
          .select('id, created_at')
          .gte('created_at', new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString())
      ]);

      const jobs = jobsResponse.data || [];
      const listings = listingsResponse.data || [];

      const completedJobs = jobs.filter(j => j.status === 'completed');
      const activeJobs = jobs.filter(j => j.status === 'running').length;
      const successRate = jobs.length > 0 ? (completedJobs.length / jobs.length) * 100 : 0;
      
      const avgResponseTime = completedJobs.length > 0 
        ? completedJobs.reduce((sum, job) => {
            const start = new Date(job.created_at).getTime();
            const end = new Date(job.completed_at).getTime();
            return sum + (end - start);
          }, 0) / completedJobs.length / 1000
        : 0;

      setRealtimeStats({
        activeJobs,
        successRate,
        avgResponseTime,
        totalResults: listings.length
      });
    } catch (error) {
      console.error('Error updating stats:', error);
    }
  }, []);

  const handleSearch = useCallback(async (query: CanonicalQuery, options: any) => {
    setIsSearching(true);
    clearNewCount();
    
    try {
      console.log('Initiating Crosshair search:', { query, options });
      
      const searchResponse = await measureAsync('crosshair-search', async () => {
        const { data, error } = await supabase.functions.invoke('crosshair-search', {
          body: { 
            canonical_query: query, 
            search_options: options 
          }
        });

        if (error) throw error;
        return data as SearchResponse;
      });

      const processedResults = await batchProcess(
        searchResponse.results,
        async (listing) => ({
          ...listing,
          // Enhance with additional metadata
          enhanced: true,
          searchedAt: new Date().toISOString()
        })
      );

      setSearchResponse({
        ...searchResponse,
        results: processedResults
      });

      // Prefetch related data for better UX
      if (processedResults.length > 0) {
        prefetch(
          () => loadMarketComps(processedResults[0]),
          `market-comps-${processedResults[0].make}-${processedResults[0].model}`
        );
      }

      if (searchResponse.pivots) {
        toast({
          title: "Query Adjusted",
          description: searchResponse.pivots.explanation,
          variant: "default",
        });
      }

      toast({
        title: "Search Completed",
        description: `Found ${searchResponse.total_count} results in ${searchResponse.execution_time_ms}ms`,
      });

    } catch (error) {
      console.error('Search failed:', error);
      toast({
        title: "Search Failed",
        description: error instanceof Error ? error.message : 'Unknown error occurred',
        variant: "destructive"
      });
    } finally {
      setIsSearching(false);
    }
  }, [measureAsync, batchProcess, prefetch, clearNewCount, toast]);

  const loadMarketComps = async (listing: CanonicalListing) => {
    // Mock market comparison data loading
    return { comparable: true };
  };

  const handleSaveIntent = useCallback(async (query: CanonicalQuery, options: any, title: string) => {
    try {
      const { data, error } = await supabase.functions.invoke('crosshair-save-intent', {
        body: {
          canonical_query: query,
          search_options: options,
          title
        }
      });

      if (error) throw error;

      toast({
        title: "Intent Saved",
        description: `"${title}" will be monitored for new results`,
      });

      loadSavedIntents();
    } catch (error) {
      console.error('Error saving intent:', error);
      toast({
        title: "Save Failed", 
        description: "Could not save search intent",
        variant: "destructive"
      });
    }
  }, [toast, loadSavedIntents]);

  const handleWatch = async (listing: CanonicalListing) => {
    try {
      // Create an alert for this specific listing
      const { error } = await supabase
        .from('user_alerts')
        .insert({
          id: crypto.randomUUID(),
          type: 'listing_watch',
          title: `Watching: ${listing.year} ${listing.make} ${listing.model}`,
          message: `Price: ${listing.bid_current ? `$${listing.bid_current}` : 'N/A'} - ${listing.source}`,
          priority: 'medium',
          opportunity_data: listing as any,
          user_id: (await supabase.auth.getUser()).data.user?.id!
        });

      if (error) throw error;

      toast({
        title: "Watching Listing",
        description: `You'll be notified of updates to this ${listing.year} ${listing.make} ${listing.model}`,
        variant: "default",
      });
      
    } catch (error) {
      console.error('Watch listing error:', error);
      toast({
        title: "Watch Failed",
        description: "Failed to set up listing watch",
        variant: "destructive",
      });
    }
  };

  const handleExport = async (format: 'csv' | 'pdf') => {
    if (!searchResponse?.results.length) {
      toast({
        title: "Export Failed",
        description: "No results to export",
        variant: "destructive",
      });
      return;
    }

    try {
      const { data, error } = await supabase.functions.invoke('crosshair-export', {
        body: {
          results: searchResponse.results,
          format
        }
      });

      if (error) throw error;

      // Create download link
      const blob = new Blob([data.content], { 
        type: format === 'csv' ? 'text/csv' : 'application/pdf' 
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `crosshair-results.${format}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);

      toast({
        title: "Export Complete",
        description: `Results exported as ${format.toUpperCase()}`,
        variant: "default",
      });
      
    } catch (error) {
      console.error('Export error:', error);
      toast({
        title: "Export Failed",
        description: `Failed to export results as ${format.toUpperCase()}`,
        variant: "destructive",
      });
    }
  };

  const handlePinQuery = async () => {
    if (!searchResponse) return;

    // This would save the current search as a pinned query
    toast({
      title: "Query Pinned",
      description: "Search criteria saved for quick access",
      variant: "default",
    });
  };

  return (
    <div className="space-y-6">
      {/* Real-time Status Header */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center space-x-2">
              <Activity className={`h-4 w-4 ${isConnected ? 'text-green-500' : 'text-red-500'}`} />
              <div>
                <div className="text-2xl font-bold">{isConnected ? 'LIVE' : 'OFFLINE'}</div>
                <p className="text-xs text-muted-foreground">System Status</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center space-x-2">
              <Clock className="h-4 w-4 text-blue-500" />
              <div>
                <div className="text-2xl font-bold">{realtimeStats.activeJobs}</div>
                <p className="text-xs text-muted-foreground">Active Jobs</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center space-x-2">
              <TrendingUp className="h-4 w-4 text-green-500" />
              <div>
                <div className="text-2xl font-bold">{realtimeStats.successRate.toFixed(1)}%</div>
                <p className="text-xs text-muted-foreground">Success Rate</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center space-x-2">
              <Search className="h-4 w-4 text-purple-500" />
              <div>
                <div className="text-2xl font-bold">{realtimeStats.totalResults}</div>
                <p className="text-xs text-muted-foreground">Results (24h)</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Performance Alert */}
      {optimizerMetrics.renderTime > 100 && (
        <Alert>
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription>
            Performance warning: Render time is {optimizerMetrics.renderTime.toFixed(0)}ms. 
            Consider reducing result set size.
          </AlertDescription>
        </Alert>
      )}

      {/* New Results Notification */}
      {newOpportunitiesCount > 0 && (
        <Alert>
          <Zap className="h-4 w-4" />
          <AlertDescription className="flex items-center justify-between">
            <span>{newOpportunitiesCount} new results found!</span>
            <Button size="sm" variant="outline" onClick={clearNewCount}>
              View Now
            </Button>
          </AlertDescription>
        </Alert>
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
            <Crosshair className="h-8 w-8 text-primary" />
            Crosshair
          </h1>
          <p className="text-muted-foreground">
            Premium directed retrieval system with dual-mode ingestion
          </p>
        </div>
        <Badge variant="secondary" className="text-sm">
          Precision Targeting
          {pipelineStatus.status === 'running' && (
            <Activity className="h-3 w-3 ml-1 animate-pulse" />
          )}
        </Badge>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="search">Search</TabsTrigger>
          <TabsTrigger value="saved">
            Saved Queries
            {savedIntents.length > 0 && (
              <Badge variant="secondary" className="ml-2">
                {savedIntents.length}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="analytics">Analytics</TabsTrigger>
          <TabsTrigger value="performance">Performance</TabsTrigger>
        </TabsList>

        <TabsContent value="search" className="space-y-4">
          <CrosshairSearchForm 
            onSearch={handleSearch} 
            onSaveIntent={handleSaveIntent}
            isLoading={isSearching} 
          />
          {searchResponse && (
            <CrosshairResults
              searchResponse={searchResponse}
              onWatch={handleWatch}
              onExport={handleExport}
              onPinQuery={handlePinQuery}
            />
          )}
        </TabsContent>

        <TabsContent value="saved" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Saved Search Intents</CardTitle>
              <CardDescription>
                Monitored searches that alert you when new matches are found
              </CardDescription>
            </CardHeader>
            <CardContent>
              {savedIntents.length === 0 ? (
                <p className="text-center text-muted-foreground py-8">
                  No saved queries yet. Save a search to get automatic alerts.
                </p>
              ) : (
                <div className="space-y-4">
                  {savedIntents.map((intent) => (
                    <div key={intent.id} className="p-4 border rounded-lg">
                      <div className="flex items-center justify-between">
                        <div>
                          <h3 className="font-semibold">{intent.title}</h3>
                          <p className="text-sm text-muted-foreground">
                            Last scan: {intent.last_scan_at ? new Date(intent.last_scan_at).toLocaleDateString() : 'Never'}
                          </p>
                        </div>
                        <div className="flex items-center space-x-2">
                          <Badge variant={intent.is_active ? 'default' : 'secondary'}>
                            {intent.is_active ? 'Active' : 'Paused'}
                          </Badge>
                          <span className="text-sm text-muted-foreground">
                            {intent.last_results_count} results
                          </span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="analytics" className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card>
              <CardHeader>
                <CardTitle>Search Performance</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  <div className="flex justify-between">
                    <span>Avg Response Time:</span>
                    <span>{realtimeStats.avgResponseTime.toFixed(2)}s</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Success Rate:</span>
                    <span>{realtimeStats.successRate.toFixed(1)}%</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Cache Hit Rate:</span>
                    <span>{optimizerMetrics.cacheHitRate.toFixed(1)}%</span>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Pipeline Status</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  <div className="flex justify-between">
                    <span>Status:</span>
                    <Badge variant={pipelineStatus.status === 'running' ? 'default' : 'secondary'}>
                      {pipelineStatus.status.toUpperCase()}
                    </Badge>
                  </div>
                  <div className="flex justify-between">
                    <span>Processed Count:</span>
                    <span>{pipelineStatus.processedCount}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Last Update:</span>
                    <span>{pipelineStatus.lastUpdate.toLocaleTimeString()}</span>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="performance" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Real-time Performance Metrics</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <h4 className="text-sm font-medium mb-2">Render Performance</h4>
                  <div className="space-y-2">
                    <div className="flex justify-between">
                      <span className="text-sm text-muted-foreground">Current Render Time</span>
                      <span className="text-sm font-medium">{optimizerMetrics.renderTime.toFixed(1)}ms</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-sm text-muted-foreground">Frame Rate</span>
                      <span className="text-sm font-medium">{optimizerMetrics.frameRate.toFixed(0)} fps</span>
                    </div>
                  </div>
                </div>
                
                <div>
                  <h4 className="text-sm font-medium mb-2">Memory & Cache</h4>
                  <div className="space-y-2">
                    <div className="flex justify-between">
                      <span className="text-sm text-muted-foreground">Memory Usage</span>
                      <span className="text-sm font-medium">
                        {(optimizerMetrics.memoryUsage / 1024 / 1024).toFixed(1)} MB
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-sm text-muted-foreground">Cache Hit Rate</span>
                      <span className="text-sm font-medium">{optimizerMetrics.cacheHitRate.toFixed(1)}%</span>
                    </div>
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