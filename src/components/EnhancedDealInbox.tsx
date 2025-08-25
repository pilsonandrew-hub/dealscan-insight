/**
 * Enhanced Deal Inbox with Gmail-style management and ML insights
 */

import { useState, useEffect, useCallback } from "react";
import { 
  Bell, Filter, MoreVertical, CheckCircle, Circle, Star, 
  DollarSign, TrendingUp, MapPin, Calendar, ExternalLink,
  Brain, Target, AlertTriangle, Clock, Eye
} from "lucide-react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { supabase } from "@/integrations/supabase/client";
import { toast } from "sonner";
import { Opportunity } from "@/types/dealerscope";
import { useEnhancedDealScoring } from "@/hooks/useEnhancedDealScoring";

interface DealFilters {
  status: string;
  minROI: string;
  maxRisk: string;
  state: string;
  make: string;
  minProfit: string;
  daysToSell: string;
  marketPosition: string;
}

export const EnhancedDealInbox = () => {
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedDeals, setSelectedDeals] = useState<Set<string>>(new Set());
  const [filters, setFilters] = useState<DealFilters>({
    status: 'all',
    minROI: '',
    maxRisk: '',
    state: '',
    make: '',
    minProfit: '',
    daysToSell: '',
    marketPosition: ''
  });
  const [sortBy, setSortBy] = useState('profit');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
  const [viewMode, setViewMode] = useState<'list' | 'cards'>('cards');

  const { 
    isScoring, 
    progress, 
    batchScoreOpportunities, 
    recordUserFeedback 
  } = useEnhancedDealScoring();

  const fetchOpportunities = useCallback(async () => {
    try {
      setLoading(true);
      
      let query = supabase
        .from('opportunities')
        .select('*')
        .eq('is_active', true);

      // Apply filters
      if (filters.status !== 'all') {
        query = query.eq('status', filters.status);
      }
      if (filters.minROI) {
        query = query.gte('roi_percentage', parseFloat(filters.minROI));
      }
      if (filters.maxRisk) {
        query = query.lte('risk_score', parseInt(filters.maxRisk));
      }
      if (filters.minProfit) {
        query = query.gte('potential_profit', parseFloat(filters.minProfit));
      }
      if (filters.state) {
        query = query.eq('state', filters.state);
      }
      if (filters.make) {
        query = query.ilike('make', `%${filters.make}%`);
      }

      const { data, error } = await query
        .order(sortBy === 'profit' ? 'potential_profit' : sortBy, { ascending: sortOrder === 'asc' })
        .limit(100);

      if (error) throw error;

      // Transform and enhance data
      const enhancedOpportunities: Opportunity[] = (data || []).map(opp => ({
        id: opp.id,
        vehicle: {
          make: opp.make,
          model: opp.model,
          year: opp.year,
          mileage: opp.mileage || 0,
          vin: opp.vin || ''
        },
        expected_price: opp.estimated_sale_price,
        acquisition_cost: opp.current_bid,
        profit: opp.potential_profit,
        roi: opp.roi_percentage,
        confidence: opp.confidence_score,
        location: opp.location,
        state: opp.state,
        auction_end: opp.auction_end,
        status: (opp.status as any) || 'new',
        score: opp.score,
        total_cost: opp.total_cost,
        risk_score: opp.risk_score,
        transportation_cost: opp.transportation_cost || 0,
        fees_cost: opp.fees_cost || 0,
        estimated_sale_price: opp.estimated_sale_price,
        profit_margin: opp.profit_margin || 0,
        source_site: opp.source_site,
        current_bid: opp.current_bid,
        vin: opp.vin,
        make: opp.make,
        model: opp.model,
        year: opp.year,
        mileage: opp.mileage
      }));

      setOpportunities(enhancedOpportunities);
    } catch (error) {
      console.error('Error fetching opportunities:', error);
      toast.error('Failed to load opportunities');
    } finally {
      setLoading(false);
    }
  }, [filters, sortBy, sortOrder]);

  useEffect(() => {
    fetchOpportunities();
  }, [fetchOpportunities]);

  // Real-time subscription with enhanced notifications
  useEffect(() => {
    const channel = supabase
      .channel('enhanced-deals-changes')
      .on(
        'postgres_changes',
        {
          event: 'INSERT',
          schema: 'public',
          table: 'opportunities'
        },
        (payload) => {
          console.log('New deal received:', payload);
          fetchOpportunities();
          
          const newDeal = payload.new as Opportunity;
          if (newDeal.roi > 25) {
            toast.success('🔥 Hot deal alert!', {
              description: `${newDeal.make} ${newDeal.model} - ${newDeal.roi.toFixed(1)}% ROI`,
              action: {
                label: 'View Deal',
                onClick: () => scrollToOpportunity(newDeal.id!)
              }
            });
          }
        }
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [fetchOpportunities]);

  const scrollToOpportunity = (id: string) => {
    const element = document.getElementById(`deal-${id}`);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth', block: 'center' });
      element.classList.add('ring-2', 'ring-primary', 'ring-opacity-50');
      setTimeout(() => {
        element.classList.remove('ring-2', 'ring-primary', 'ring-opacity-50');
      }, 3000);
    }
  };

  const handleBulkAction = async (action: 'read' | 'flag' | 'dismiss' | 'ml-score') => {
    const selectedArray = Array.from(selectedDeals);
    if (selectedArray.length === 0) {
      toast.error('Please select deals first');
      return;
    }

    try {
      if (action === 'ml-score') {
        const selectedOpportunities = opportunities.filter(opp => selectedArray.includes(opp.id!));
        const scoredOpportunities = await batchScoreOpportunities(selectedOpportunities);
        
        // Update the opportunities list
        setOpportunities(prev => prev.map(opp => {
          const scored = scoredOpportunities.find(s => s.id === opp.id);
          return scored || opp;
        }));
        
        toast.success(`Enhanced ML scoring complete for ${selectedArray.length} deals`);
      } else {
        const { error } = await supabase
          .from('opportunities')
          .update({ status: action === 'read' ? 'read' : action === 'flag' ? 'flagged' : 'dismissed' })
          .in('id', selectedArray);

        if (error) throw error;

        setOpportunities(prev => prev.map(opp => 
          selectedArray.includes(opp.id!) 
            ? { ...opp, status: action === 'read' ? 'read' : action === 'flag' ? 'flagged' : 'dismissed' as any }
            : opp
        ));

        toast.success(`${selectedArray.length} deal(s) ${action}ed`);
      }

      setSelectedDeals(new Set());
    } catch (error) {
      console.error('Error performing bulk action:', error);
      toast.error('Failed to update deals');
    }
  };

  const handleUserAction = async (opportunityId: string, action: "saved" | "ignored" | "viewed") => {
    await recordUserFeedback(opportunityId, action);
    
    if (action === "saved") {
      toast.success('Deal saved to watchlist');
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'new': return 'bg-green-500 text-white animate-pulse';
      case 'read': return 'bg-muted text-muted-foreground';
      case 'flagged': return 'bg-orange-500 text-white';
      case 'dismissed': return 'bg-red-500 text-white';
      default: return 'bg-muted text-muted-foreground';
    }
  };

  const getRiskBadge = (risk: number) => {
    if (risk <= 30) return { color: 'bg-green-100 text-green-800', label: 'Low Risk' };
    if (risk <= 60) return { color: 'bg-yellow-100 text-yellow-800', label: 'Medium Risk' };
    return { color: 'bg-red-100 text-red-800', label: 'High Risk' };
  };

  const newDealsCount = opportunities.filter(opp => opp.status === 'new').length;
  const totalValue = opportunities.reduce((sum, opp) => sum + opp.profit, 0);

  return (
    <div className="space-y-6">
      {/* Enhanced Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <Target className="w-8 h-8" />
            Enhanced Deal Inbox
          </h1>
          {newDealsCount > 0 && (
            <Badge className="bg-red-500 text-white animate-bounce">
              {newDealsCount} new deals
            </Badge>
          )}
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
            Live tracking
          </div>
        </div>

        <div className="flex items-center gap-2">
          <div className="text-right mr-4">
            <div className="text-sm text-muted-foreground">Total Value</div>
            <div className="text-lg font-bold text-green-600">
              ${totalValue.toLocaleString()}
            </div>
          </div>
          <Button 
            variant="outline" 
            size="sm"
            onClick={() => setViewMode(viewMode === 'cards' ? 'list' : 'cards')}
          >
            {viewMode === 'cards' ? 'List View' : 'Card View'}
          </Button>
        </div>
      </div>

      {/* ML Scoring Progress */}
      {isScoring && progress && (
        <Card>
          <CardContent className="p-6">
            <div className="space-y-4">
              <div className="flex items-center gap-2">
                <Brain className="w-5 h-5 animate-pulse" />
                <span className="font-medium">Enhanced ML Analysis in Progress</span>
              </div>
              <Progress value={(progress.processed / progress.total) * 100} />
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>Status: {progress.currentStage}</div>
                <div>Progress: {progress.processed}/{progress.total}</div>
                <div>ETA: {Math.ceil(progress.estimatedTimeRemaining / 60)} minutes</div>
                <div>Processing rate: ~2 deals/minute</div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Enhanced Action Bar */}
      <Card>
        <CardContent className="p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium">
                {selectedDeals.size} selected
              </span>
              <Button 
                variant="outline" 
                size="sm"
                onClick={() => handleBulkAction('read')}
                disabled={selectedDeals.size === 0}
              >
                <CheckCircle className="w-4 h-4 mr-1" />
                Mark Read
              </Button>
              <Button 
                variant="outline" 
                size="sm"
                onClick={() => handleBulkAction('flag')}
                disabled={selectedDeals.size === 0}
              >
                <Star className="w-4 h-4 mr-1" />
                Flag
              </Button>
              <Button 
                variant="outline" 
                size="sm"
                onClick={() => handleBulkAction('ml-score')}
                disabled={selectedDeals.size === 0 || isScoring}
              >
                <Brain className="w-4 h-4 mr-1" />
                Enhanced ML Score
              </Button>
            </div>

            <div className="flex items-center gap-2">
              <Select value={sortBy} onValueChange={setSortBy}>
                <SelectTrigger className="w-32">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="profit">Profit</SelectItem>
                  <SelectItem value="roi_percentage">ROI</SelectItem>
                  <SelectItem value="confidence_score">Confidence</SelectItem>
                  <SelectItem value="created_at">Date</SelectItem>
                </SelectContent>
              </Select>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')}
              >
                {sortOrder === 'asc' ? '↑' : '↓'}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Enhanced Filters */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Filter className="w-5 h-5" />
            Smart Filters
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
            <Select value={filters.status} onValueChange={(value) => setFilters({...filters, status: value})}>
              <SelectTrigger>
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Status</SelectItem>
                <SelectItem value="new">New</SelectItem>
                <SelectItem value="read">Read</SelectItem>
                <SelectItem value="flagged">Flagged</SelectItem>
                <SelectItem value="dismissed">Dismissed</SelectItem>
              </SelectContent>
            </Select>

            <Input
              placeholder="Min ROI %"
              value={filters.minROI}
              onChange={(e) => setFilters({...filters, minROI: e.target.value})}
              type="number"
            />

            <Input
              placeholder="Min Profit $"
              value={filters.minProfit}
              onChange={(e) => setFilters({...filters, minProfit: e.target.value})}
              type="number"
            />

            <Input
              placeholder="Max Risk"
              value={filters.maxRisk}
              onChange={(e) => setFilters({...filters, maxRisk: e.target.value})}
              type="number"
            />

            <Input
              placeholder="State"
              value={filters.state}
              onChange={(e) => setFilters({...filters, state: e.target.value})}
            />

            <Input
              placeholder="Make"
              value={filters.make}
              onChange={(e) => setFilters({...filters, make: e.target.value})}
            />
          </div>
        </CardContent>
      </Card>

      {/* Enhanced Opportunities List */}
      <div className="space-y-4">
        {loading ? (
          <div className="grid gap-4">
            {[1, 2, 3].map((i) => (
              <Card key={i} className="animate-pulse">
                <CardContent className="p-6">
                  <div className="h-6 bg-muted rounded w-1/3 mb-4"></div>
                  <div className="grid grid-cols-4 gap-4">
                    <div className="h-4 bg-muted rounded"></div>
                    <div className="h-4 bg-muted rounded"></div>
                    <div className="h-4 bg-muted rounded"></div>
                    <div className="h-4 bg-muted rounded"></div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        ) : opportunities.length === 0 ? (
          <Card>
            <CardContent className="p-12 text-center">
              <Bell className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
              <h3 className="text-lg font-semibold mb-2">No deals found</h3>
              <p className="text-muted-foreground">
                Adjust your filters or wait for new opportunities to be discovered.
              </p>
            </CardContent>
          </Card>
        ) : (
          opportunities.map((opportunity) => (
            <Card 
              key={opportunity.id} 
              id={`deal-${opportunity.id}`}
              className={`group transition-all hover:shadow-lg ${
                opportunity.status === 'new' ? 'ring-2 ring-green-500/20 bg-green-50/50' : ''
              }`}
            >
              <CardContent className="p-6">
                <div className="flex items-start gap-4">
                  <Checkbox
                    checked={selectedDeals.has(opportunity.id!)}
                    onCheckedChange={(checked) => {
                      const newSelected = new Set(selectedDeals);
                      if (checked) {
                        newSelected.add(opportunity.id!);
                      } else {
                        newSelected.delete(opportunity.id!);
                      }
                      setSelectedDeals(newSelected);
                    }}
                  />

                  <div className="flex-1 space-y-4">
                    {/* Enhanced Header */}
                    <div className="flex items-start justify-between">
                      <div className="space-y-2">
                        <div className="flex items-center gap-2">
                          <Badge className={getStatusColor(opportunity.status!)}>
                            {opportunity.status?.toUpperCase()}
                          </Badge>
                          <Badge variant="outline">{opportunity.source_site}</Badge>
                          {(() => {
                            const riskBadge = getRiskBadge(opportunity.risk_score);
                            return (
                              <Badge className={riskBadge.color}>
                                {riskBadge.label}
                              </Badge>
                            );
                          })()}
                          {opportunity.predicted_prices && (
                            <Badge className="bg-blue-100 text-blue-800">
                              <Brain className="w-3 h-3 mr-1" />
                              ML Enhanced
                            </Badge>
                          )}
                        </div>
                        <h3 className="text-xl font-semibold">
                          {opportunity.year} {opportunity.make} {opportunity.model}
                        </h3>
                        <p className="text-muted-foreground">
                          {opportunity.mileage?.toLocaleString()} miles • {opportunity.location}, {opportunity.state}
                        </p>
                      </div>

                      <div className="text-right space-y-1">
                        <div className="text-3xl font-bold text-green-600">
                          ${opportunity.profit.toLocaleString()}
                        </div>
                        <div className="text-lg text-green-500">
                          {opportunity.roi.toFixed(1)}% ROI
                        </div>
                        {opportunity.bid_cap && (
                          <div className="text-sm text-muted-foreground">
                            Bid Cap: ${opportunity.bid_cap.toLocaleString()}
                          </div>
                        )}
                      </div>
                    </div>

                    {/* ML Insights */}
                    {opportunity.predicted_prices && (
                      <div className="bg-blue-50 p-4 rounded-lg space-y-2">
                        <h4 className="font-medium flex items-center gap-2">
                          <Brain className="w-4 h-4" />
                          ML Insights
                        </h4>
                        <div className="grid grid-cols-3 gap-4 text-sm">
                          <div>
                            <span className="text-muted-foreground">Price Range:</span>
                            <div className="font-medium">
                              ${opportunity.predicted_prices.p10.toLocaleString()} - ${opportunity.predicted_prices.p90.toLocaleString()}
                            </div>
                          </div>
                          <div>
                            <span className="text-muted-foreground">Days to Sell:</span>
                            <div className="font-medium">{opportunity.days_to_sell} days</div>
                          </div>
                          <div>
                            <span className="text-muted-foreground">Position:</span>
                            <div className="font-medium capitalize">{opportunity.market_position}</div>
                          </div>
                        </div>
                        {opportunity.deal_rationale && (
                          <p className="text-sm text-blue-700 bg-blue-100 p-2 rounded">
                            {opportunity.deal_rationale}
                          </p>
                        )}
                      </div>
                    )}

                    {/* Enhanced Metrics */}
                    <div className="grid grid-cols-2 md:grid-cols-5 gap-4 text-sm">
                      <div>
                        <div className="text-muted-foreground">Current Bid</div>
                        <div className="font-semibold">${opportunity.current_bid.toLocaleString()}</div>
                      </div>
                      <div>
                        <div className="text-muted-foreground">Est. Sale</div>
                        <div className="font-semibold">${opportunity.estimated_sale_price.toLocaleString()}</div>
                      </div>
                      <div>
                        <div className="text-muted-foreground">Total Cost</div>
                        <div className="font-semibold">${opportunity.total_cost.toLocaleString()}</div>
                      </div>
                      <div>
                        <div className="text-muted-foreground">Confidence</div>
                        <div className="flex items-center gap-2">
                          <Progress value={opportunity.confidence} className="flex-1" />
                          <span className="font-semibold">{opportunity.confidence}%</span>
                        </div>
                      </div>
                      <div>
                        <div className="text-muted-foreground">Score</div>
                        <div className="font-semibold">{opportunity.score || 'N/A'}</div>
                      </div>
                    </div>

                    {/* Enhanced Actions */}
                    <div className="flex items-center justify-between pt-4 border-t">
                      <div className="flex items-center gap-4 text-xs text-muted-foreground">
                        <div className="flex items-center gap-1">
                          <Calendar className="w-3 h-3" />
                          Listed {opportunity.last_updated ? new Date(opportunity.last_updated).toLocaleDateString() : 'Recently'}
                        </div>
                        {opportunity.auction_end && (
                          <div className="flex items-center gap-1">
                            <Clock className="w-3 h-3" />
                            Ends {new Date(opportunity.auction_end).toLocaleDateString()}
                          </div>
                        )}
                      </div>

                      <div className="flex items-center gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => handleUserAction(opportunity.id!, "saved")}
                        >
                          <Star className="w-4 h-4 mr-1" />
                          Save
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => handleUserAction(opportunity.id!, "viewed")}
                        >
                          <Eye className="w-4 h-4 mr-1" />
                          View Details
                        </Button>
                        <Button
                          size="sm"
                          onClick={() => {
                            window.open(`https://${opportunity.source_site}`, '_blank');
                            handleUserAction(opportunity.id!, "viewed");
                          }}
                        >
                          <ExternalLink className="w-4 h-4 mr-1" />
                          View Auction
                        </Button>
                      </div>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </div>
    </div>
  );
};