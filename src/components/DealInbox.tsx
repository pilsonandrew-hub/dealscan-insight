import { useState, useEffect } from "react";
import { Bell, Filter, MoreVertical, CheckCircle, Circle, Star, DollarSign, TrendingUp, MapPin, Calendar, ExternalLink } from "lucide-react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { supabase } from "@/integrations/supabase/client";
import { toast } from "sonner";
import { createLogger } from "@/utils/productionLogger";

interface Deal {
  id: string;
  listing_id: string;
  estimated_sale_price: number;
  total_cost: number;
  potential_profit: number;
  roi_percentage: number;
  risk_score: number;
  confidence_score: number;
  status: 'new' | 'read' | 'flagged' | 'dismissed';
  created_at: string;
  listing?: {
    source_site: string;
    listing_url: string;
    year?: number;
    make?: string;
    model?: string;
    mileage?: number;
    current_bid?: number;
    location?: string;
    state?: string;
    auction_end?: string;
    photo_url?: string;
  };
}

interface DealInboxProps {
  className?: string;
}

export const DealInbox = ({ className = "" }: DealInboxProps) => {
  const logger = createLogger('DealInbox');
  const [deals, setDeals] = useState<Deal[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedDeals, setSelectedDeals] = useState<Set<string>>(new Set());
  const [filters, setFilters] = useState({
    status: 'all',
    minROI: '',
    maxRisk: '',
    state: '',
    make: ''
  });
  const [sortBy, setSortBy] = useState('created_at');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');

  // Real-time subscription to new deals
  useEffect(() => {
    const channel = supabase
      .channel('deals-changes')
      .on(
        'postgres_changes',
        {
          event: 'INSERT',
          schema: 'public',
          table: 'opportunities'
        },
        (payload) => {
          logger.info('New deal received', { payload });
          fetchDeals(); // Refresh deals list
          toast.success('New profitable deal found!', {
            description: `ROI: ${(payload.new.roi_percentage || 0).toFixed(1)}% - Check your inbox`,
            action: {
              label: 'View',
              onClick: () => window.scrollTo({ top: 0, behavior: 'smooth' })
            }
          });
        }
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, []);

  const fetchDeals = async () => {
    try {
      setLoading(true);
      
      let query = supabase
        .from('opportunities')
        .select(`
          id,
          listing_id,
          estimated_sale_price,
          total_cost,
          potential_profit,
          roi_percentage,
          risk_score,
          confidence_score,
          status,
          created_at,
          public_listings!inner(
            source_site,
            listing_url,
            year,
            make,
            model,
            mileage,
            current_bid,
            location,
            state,
            auction_end,
            photo_url
          )
        `)
        .order(sortBy, { ascending: sortOrder === 'asc' });

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

      const { data, error } = await query.limit(100);

      if (error) {
        console.error('Error fetching deals:', error);
        toast.error('Failed to load deals');
        return;
      }

      // Transform data structure for easier access
      const transformedDeals = data?.map(deal => ({
        ...deal,
        status: (deal.status as 'new' | 'read' | 'flagged' | 'dismissed') || 'new',
        listing: deal.public_listings
      })) || [];

      setDeals(transformedDeals);
    } catch (error) {
      console.error('Error:', error);
      toast.error('Failed to load deals');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDeals();
  }, [filters, sortBy, sortOrder]);

  const markAsRead = async (dealIds: string[]) => {
    try {
      const { error } = await supabase
        .from('opportunities')
        .update({ status: 'read' })
        .in('id', dealIds);

      if (error) throw error;

      setDeals(deals.map(deal => 
        dealIds.includes(deal.id) 
          ? { ...deal, status: 'read' as const }
          : deal
      ));
      
      toast.success(`Marked ${dealIds.length} deal(s) as read`);
    } catch (error) {
      console.error('Error marking deals as read:', error);
      toast.error('Failed to update deals');
    }
  };

  const markAsFlagged = async (dealIds: string[]) => {
    try {
      const { error } = await supabase
        .from('opportunities')
        .update({ status: 'flagged' })
        .in('id', dealIds);

      if (error) throw error;

      setDeals(deals.map(deal => 
        dealIds.includes(deal.id) 
          ? { ...deal, status: 'flagged' as const }
          : deal
      ));
      
      toast.success(`Flagged ${dealIds.length} deal(s) for follow-up`);
    } catch (error) {
      console.error('Error flagging deals:', error);
      toast.error('Failed to flag deals');
    }
  };

  const handleBulkAction = (action: 'read' | 'flag') => {
    const selectedArray = Array.from(selectedDeals);
    if (selectedArray.length === 0) {
      toast.error('Please select deals first');
      return;
    }

    if (action === 'read') {
      markAsRead(selectedArray);
    } else if (action === 'flag') {
      markAsFlagged(selectedArray);
    }
    
    setSelectedDeals(new Set());
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'new': return 'bg-success text-success-foreground';
      case 'read': return 'bg-muted text-muted-foreground';
      case 'flagged': return 'bg-warning text-warning-foreground';
      case 'dismissed': return 'bg-destructive text-destructive-foreground';
      default: return 'bg-muted text-muted-foreground';
    }
  };

  const getRiskColor = (risk: number) => {
    if (risk <= 30) return 'text-success';
    if (risk <= 60) return 'text-warning';
    return 'text-destructive';
  };

  const newDealsCount = deals.filter(deal => deal.status === 'new').length;

  return (
    <div className={`space-y-6 ${className}`}>
      {/* Header with unread count */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className="text-2xl font-bold text-foreground">Deal Inbox</h2>
          {newDealsCount > 0 && (
            <Badge className="bg-red-500 text-white animate-bounce">
              {newDealsCount} new
            </Badge>
          )}
          <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse" title="Live updates active" />
        </div>
        
        <div className="flex items-center gap-2">
          <Button 
            variant="outline" 
            size="sm"
            onClick={() => handleBulkAction('read')}
            disabled={selectedDeals.size === 0}
          >
            <CheckCircle className="w-4 h-4 mr-2" />
            Mark Read
          </Button>
          <Button 
            variant="outline" 
            size="sm"
            onClick={() => handleBulkAction('flag')}
            disabled={selectedDeals.size === 0}
          >
            <Star className="w-4 h-4 mr-2" />
            Flag
          </Button>
        </div>
      </div>

      {/* Filters */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Filter className="w-4 h-4" />
            Filters & Sorting
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <Select value={filters.status} onValueChange={(value) => setFilters({...filters, status: value})}>
              <SelectTrigger>
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Deals</SelectItem>
                <SelectItem value="new">New</SelectItem>
                <SelectItem value="read">Read</SelectItem>
                <SelectItem value="flagged">Flagged</SelectItem>
              </SelectContent>
            </Select>

            <Input
              placeholder="Min ROI %"
              value={filters.minROI}
              onChange={(e) => setFilters({...filters, minROI: e.target.value})}
              type="number"
            />

            <Input
              placeholder="Max Risk Score"
              value={filters.maxRisk}
              onChange={(e) => setFilters({...filters, maxRisk: e.target.value})}
              type="number"
            />

            <Select value={sortBy} onValueChange={setSortBy}>
              <SelectTrigger>
                <SelectValue placeholder="Sort by" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="created_at">Date</SelectItem>
                <SelectItem value="roi_percentage">ROI</SelectItem>
                <SelectItem value="potential_profit">Profit</SelectItem>
                <SelectItem value="risk_score">Risk</SelectItem>
              </SelectContent>
            </Select>

            <Button
              variant="outline"
              onClick={() => setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')}
            >
              {sortOrder === 'asc' ? '↑' : '↓'}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Deals List */}
      <div className="space-y-4">
        {loading ? (
          <div className="grid gap-4">
            {[1, 2, 3].map((i) => (
              <Card key={i} className="animate-pulse">
                <CardContent className="p-6">
                  <div className="h-4 bg-muted rounded w-1/4 mb-2"></div>
                  <div className="h-6 bg-muted rounded w-1/2 mb-4"></div>
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
        ) : deals.length === 0 ? (
          <Card>
            <CardContent className="p-12 text-center">
              <Bell className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
              <h3 className="text-lg font-semibold mb-2">No deals found</h3>
              <p className="text-muted-foreground">
                No profitable opportunities match your current filters. Try adjusting your criteria.
              </p>
            </CardContent>
          </Card>
        ) : (
          deals.map((deal) => (
            <Card 
              key={deal.id} 
              className={`group transition-all hover:shadow-lg ${
                deal.status === 'new' ? 'ring-2 ring-success/50' : ''
              }`}
            >
              <CardContent className="p-6">
                <div className="flex items-start gap-4">
                  <Checkbox
                    checked={selectedDeals.has(deal.id)}
                    onCheckedChange={(checked) => {
                      const newSelected = new Set(selectedDeals);
                      if (checked) {
                        newSelected.add(deal.id);
                      } else {
                        newSelected.delete(deal.id);
                      }
                      setSelectedDeals(newSelected);
                    }}
                  />

                  <div className="flex-1 space-y-4">
                    {/* Header */}
                    <div className="flex items-start justify-between">
                      <div>
                        <div className="flex items-center gap-2 mb-2">
                          <Badge className={getStatusColor(deal.status)}>
                            {deal.status.toUpperCase()}
                          </Badge>
                          <Badge variant="outline">
                            {deal.listing?.source_site}
                          </Badge>
                          {deal.status === 'new' && (
                            <Circle className="w-2 h-2 fill-current text-success animate-pulse" />
                          )}
                        </div>
                        <h3 className="text-lg font-semibold">
                          {deal.listing?.year} {deal.listing?.make} {deal.listing?.model}
                        </h3>
                        <p className="text-sm text-muted-foreground">
                          {deal.listing?.mileage?.toLocaleString()} miles • {deal.listing?.location}
                        </p>
                      </div>

                      <div className="text-right">
                        <div className="text-2xl font-bold text-success">
                          ${deal.potential_profit.toLocaleString()}
                        </div>
                        <div className="text-sm text-muted-foreground">
                          {deal.roi_percentage.toFixed(1)}% ROI
                        </div>
                      </div>
                    </div>

                    {/* Metrics Grid */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                      <div>
                        <div className="text-muted-foreground">Current Bid</div>
                        <div className="font-semibold">
                          ${deal.listing?.current_bid?.toLocaleString() || 'N/A'}
                        </div>
                      </div>
                      <div>
                        <div className="text-muted-foreground">Est. Sale Price</div>
                        <div className="font-semibold">
                          ${deal.estimated_sale_price.toLocaleString()}
                        </div>
                      </div>
                      <div>
                        <div className="text-muted-foreground">Total Cost</div>
                        <div className="font-semibold">
                          ${deal.total_cost.toLocaleString()}
                        </div>
                      </div>
                      <div>
                        <div className="text-muted-foreground">Risk Score</div>
                        <div className={`font-semibold ${getRiskColor(deal.risk_score)}`}>
                          {deal.risk_score}/100
                        </div>
                      </div>
                    </div>

                    {/* Actions */}
                    <div className="flex items-center justify-between pt-4 border-t">
                      <div className="flex items-center gap-4 text-xs text-muted-foreground">
                        <div className="flex items-center gap-1">
                          <Calendar className="w-3 h-3" />
                          {new Date(deal.created_at).toLocaleDateString()}
                        </div>
                        <div className="flex items-center gap-1">
                          <Star className="w-3 h-3" />
                          {deal.confidence_score}% confidence
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        {deal.status === 'new' && (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => markAsRead([deal.id])}
                          >
                            Mark Read
                          </Button>
                        )}
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => window.open(deal.listing?.listing_url, '_blank')}
                        >
                          <ExternalLink className="w-4 h-4 mr-2" />
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