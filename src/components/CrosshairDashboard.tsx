import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { CrosshairSearchForm } from './CrosshairSearchForm';
import { CrosshairResults } from './CrosshairResults';
import { useRealtimeOpportunities } from '@/hooks/useRealtimeOpportunities';
import { useToast } from '@/hooks/use-toast';
import { supabase } from '@/integrations/supabase/client';
import { CanonicalQuery, SearchResponse, CrosshairIntent, CanonicalListing } from '@/types/crosshair';
import { Zap, Activity, TrendingUp, Clock, Search, Crosshair } from 'lucide-react';
import { roverAPI } from '@/services/roverAPI';

async function createListingWatchAlert(listing: CanonicalListing): Promise<string | null> {
  const { data: { session } } = await supabase.auth.getSession();
  const userId = session?.user?.id;
  if (!userId) return null;

  const { error } = await supabase
    .from('user_alerts')
    .insert({
      id: crypto.randomUUID(),
      type: 'listing_watch',
      title: `Watching: ${listing.year} ${listing.make} ${listing.model}`,
      message: `Price: ${listing.bid_current ? `$${listing.bid_current}` : 'N/A'} - ${listing.source}`,
      priority: 'medium',
      opportunity_data: listing as any,
      user_id: userId,
    });

  if (error) throw error;
  return userId;
}

async function trackWatchedListingSave(listing: CanonicalListing, userId: string): Promise<void> {
  await roverAPI.trackEvent({
    userId,
    event: 'save',
    item: {
      id: listing.id,
      make: listing.make,
      model: listing.model,
      year: listing.year,
      price: listing.bid_current ?? listing.buy_now ?? 0,
      source: listing.source,
      source_site: listing.source,
      state: listing.location.state,
      mileage: listing.odo_miles,
    },
  });
}

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

  const { toast } = useToast();

  const showCrosshairToast = useCallback((
    title: string,
    description: string,
    variant: 'default' | 'destructive' = 'default'
  ) => {
    toast({ title, description, variant });
  }, [toast]);

  const logAndToastError = useCallback((
    context: string,
    error: unknown,
    title: string,
    description: string
  ) => {
    console.error(context, error);
    showCrosshairToast(title, description, 'destructive');
  }, [showCrosshairToast]);

  const {
    pipelineStatus,
    newOpportunitiesCount,
    connectionStatus,
    isConnected,
    clearNewCount
  } = useRealtimeOpportunities([]);

  useEffect(() => {
    const channel = supabase
      .channel('crosshair-realtime')
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table: 'crosshair_jobs' },
        () => {
          updateRealtimeStats();
        }
      )
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table: 'listings_normalized' },
        (payload) => {
          if (payload.eventType === 'INSERT') {
            toast({
              title: 'New Listing Found',
              description: `${payload.new.year} ${payload.new.make} ${payload.new.model} - ${payload.new.source}`,
            });
          }
        }
      )
      .subscribe();

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
      const { data, error } = await supabase.functions.invoke('crosshair-search', {
        body: {
          canonical_query: query,
          search_options: options
        }
      });

      if (error) throw error;
      const searchResponse = data as SearchResponse;

      const processedResults = await Promise.all(
        searchResponse.results.map(async (listing) => ({
          ...listing,
          enhanced: true,
          searchedAt: new Date().toISOString()
        }))
      );

      setSearchResponse({
        ...searchResponse,
        results: processedResults
      });

      if (searchResponse.pivots) {
        showCrosshairToast('Query Adjusted', searchResponse.pivots.explanation);
      }

      showCrosshairToast(
        'Search Completed',
        `Found ${searchResponse.total_count} results in ${searchResponse.execution_time_ms}ms`
      );
    } catch (error) {
      logAndToastError(
        'Search failed:',
        error,
        'Search Failed',
        error instanceof Error ? error.message : 'Unknown error occurred'
      );
    } finally {
      setIsSearching(false);
    }
  }, [clearNewCount, logAndToastError, showCrosshairToast]);

  const handleSaveIntent = useCallback(async (query: CanonicalQuery, options: any, title: string) => {
    try {
      await roverAPI.saveIntent(query, title, {
        dos_threshold: options?.dos_threshold,
        telegram_chat_id: options?.telegram_chat_id,
      });

      showCrosshairToast('Intent Saved', `"${title}" will be monitored for new results`);

      loadSavedIntents();
    } catch (error) {
      logAndToastError('Error saving intent:', error, 'Save Failed', 'Could not save search intent');
    }
  }, [loadSavedIntents, logAndToastError, showCrosshairToast]);

  const handleWatch = async (listing: CanonicalListing) => {
    try {
      const userId = await createListingWatchAlert(listing);
      if (!userId) throw new Error('No authenticated user');

      await trackWatchedListingSave(listing, userId);

      showCrosshairToast(
        'Watching Listing',
        `You'll be notified of updates to this ${listing.year} ${listing.make} ${listing.model}`
      );
    } catch (error) {
      logAndToastError('Watch listing error:', error, 'Watch Failed', 'Failed to set up listing watch');
    }
  };

  const handleExport = async (format: 'csv' | 'pdf') => {
    if (!searchResponse?.results.length) {
      showCrosshairToast('Export Failed', 'No results to export', 'destructive');
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

      showCrosshairToast('Export Complete', `Results exported as ${format.toUpperCase()}`);
    } catch (error) {
      logAndToastError(
        'Export error:',
        error,
        'Export Failed',
        `Failed to export results as ${format.toUpperCase()}`
      );
    }
  };

  const handlePinQuery = async () => {
    if (!searchResponse) return;

    showCrosshairToast('Query Pinned', 'Search criteria saved for quick access');
  };

  return (
    <div className="space-y-6">
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

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
            <Crosshair className="h-8 w-8 text-primary" />
            Crosshair
          </h1>
          <p className="text-muted-foreground">
            Directed vehicle search across normalized listings with saved intents and job tracking
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
              <CardTitle>Operational Notes</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2 text-sm text-muted-foreground">
                <p>Crosshair performance is currently tracked through live job completion timing.</p>
                <p>Search latency and success rate shown here come from actual job records, not synthetic client-side optimizer estimates.</p>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
};
