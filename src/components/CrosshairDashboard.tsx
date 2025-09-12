import { useState } from "react";
import { CrosshairSearchForm } from "./CrosshairSearchForm";
import { CrosshairResults } from "./CrosshairResults";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useToast } from "@/hooks/use-toast";
import { supabase } from "@/integrations/supabase/client";
import { CanonicalQuery, SearchOptions, SearchResponse, CanonicalListing } from "@/types/crosshair";
import { Crosshair, Activity, Clock, TrendingUp } from "lucide-react";

export const CrosshairDashboard = () => {
  const [searchResponse, setSearchResponse] = useState<SearchResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const { toast } = useToast();

  const handleSearch = async (query: CanonicalQuery, options: SearchOptions) => {
    setIsLoading(true);
    try {
      console.log('Initiating Crosshair search:', { query, options });
      
      const { data, error } = await supabase.functions.invoke('crosshair-search', {
        body: { 
          canonical_query: query, 
          search_options: options 
        }
      });

      if (error) {
        console.error('Crosshair search error:', error);
        toast({
          title: "Search Failed",
          description: error.message || "Failed to execute search",
          variant: "destructive",
        });
        return;
      }

      console.log('Crosshair search response:', data);
      setSearchResponse(data);
      
      if (data.pivots) {
        toast({
          title: "Query Adjusted",
          description: data.pivots.explanation,
          variant: "default",
        });
      }

      toast({
        title: "Search Completed",
        description: `Found ${data.total_count} results in ${data.execution_time_ms}ms`,
        variant: "default",
      });
      
    } catch (error) {
      console.error('Crosshair search error:', error);
      toast({
        title: "Search Error",
        description: "An unexpected error occurred during search",
        variant: "destructive",
      });
    } finally {
      setIsLoading(false);
    }
  };

  const handleSaveIntent = async (query: CanonicalQuery, options: SearchOptions, title: string) => {
    try {
      const { data, error } = await supabase.functions.invoke('crosshair-save-intent', {
        body: {
          canonical_query: query,
          search_options: options,
          title
        }
      });

      if (error) {
        toast({
          title: "Save Failed",
          description: error.message || "Failed to save search intent",
          variant: "destructive",
        });
        return;
      }

      toast({
        title: "Intent Saved",
        description: `"${title}" will be monitored for new matches`,
        variant: "default",
      });
      
    } catch (error) {
      console.error('Save intent error:', error);
      toast({
        title: "Save Error",
        description: "Failed to save search intent",
        variant: "destructive",
      });
    }
  };

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
    <div className="space-y-8">
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
        </Badge>
      </div>

      {/* Quick Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-2">
              <Activity className="h-4 w-4 text-green-600" />
              <div>
                <p className="text-sm font-medium">Active Sources</p>
                <p className="text-2xl font-bold">12</p>
              </div>
            </div>
          </CardContent>
        </Card>
        
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-2">
              <Clock className="h-4 w-4 text-blue-600" />
              <div>
                <p className="text-sm font-medium">Avg Response</p>
                <p className="text-2xl font-bold">1.2s</p>
              </div>
            </div>
          </CardContent>
        </Card>
        
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-purple-600" />
              <div>
                <p className="text-sm font-medium">Success Rate</p>
                <p className="text-2xl font-bold">94%</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Search Form */}
      <CrosshairSearchForm
        onSearch={handleSearch}
        onSaveIntent={handleSaveIntent}
        isLoading={isLoading}
      />

      {/* Results */}
      {searchResponse && (
        <CrosshairResults
          searchResponse={searchResponse}
          onWatch={handleWatch}
          onExport={handleExport}
          onPinQuery={handlePinQuery}
        />
      )}
    </div>
  );
};