import { useState, useEffect } from "react";
import { TrendingUp, MapPin, Calendar, DollarSign, Star, ExternalLink, Target, TrendingDown } from "lucide-react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Opportunity } from "@/types/dealerscope";

interface DealOpportunitiesProps {
  opportunities?: Opportunity[];
  isLoading?: boolean;
  isRealtime?: boolean;
  onNewCountCleared?: () => void;
}

// Extended interface for display purposes
interface DealDisplay extends Opportunity {
  title: string;
  marginPercent: number;
}

// Transform Opportunity to DealDisplay
const transformOpportunityToDisplay = (opp: Opportunity): DealDisplay => ({
  ...opp,
  title: `${opp.vehicle.year} ${opp.vehicle.make} ${opp.vehicle.model}`,
  marginPercent: (opp.roi * 100),
});

export const DealOpportunities = ({ 
  opportunities = [], 
  isLoading = false,
  isRealtime = false,
  onNewCountCleared
}: DealOpportunitiesProps) => {
  const [error, setError] = useState<string | null>(null);

  // Transform opportunities to display format
  const deals: DealDisplay[] = opportunities.map(transformOpportunityToDisplay);

  const getStatusColor = (status: string) => {
    switch (status) {
      case "hot": return "bg-success text-success-foreground";
      case "good": return "bg-primary text-primary-foreground";
      case "moderate": return "bg-warning text-warning-foreground";
      default: return "bg-muted text-muted-foreground";
    }
  };

  const getScoreColor = (score: number) => {
    if (score >= 90) return "text-success";
    if (score >= 75) return "text-primary";
    if (score >= 60) return "text-warning";
    return "text-muted-foreground";
  };

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold text-foreground">Deal Opportunities</h2>
            <p className="text-muted-foreground">Loading high-potential arbitrage opportunities...</p>
          </div>
        </div>
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <Card key={i} className="animate-pulse">
              <CardHeader className="pb-3">
                <div className="h-4 bg-muted rounded w-1/3"></div>
                <div className="h-6 bg-muted rounded w-3/4"></div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="h-20 bg-muted rounded"></div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold text-foreground">Deal Opportunities</h2>
            <p className="text-muted-foreground text-destructive">{error}</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-foreground flex items-center gap-2">
            Deal Opportunities
            {isRealtime && <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />}
          </h2>
          <p className="text-muted-foreground">
            {isRealtime ? 'Live updates enabled - ' : ''}High-potential arbitrage opportunities from government auctions
          </p>
        </div>
        <div className="flex items-center space-x-4">
          <div className="text-right">
            <p className="text-sm text-muted-foreground">Total Opportunities</p>
            <p className="text-2xl font-bold text-success">{deals.length}</p>
          </div>
          <div className="text-right">
            <p className="text-sm text-muted-foreground">Avg. ROI</p>
            <p className="text-2xl font-bold text-primary">
              {((deals.reduce((sum, deal) => sum + deal.roi * 100, 0) / deals.length) || 0).toFixed(1)}%
            </p>
          </div>
          <div className="text-right">
            <p className="text-sm text-muted-foreground">Avg. Confidence</p>
            <p className="text-2xl font-bold text-warning">
              {((deals.reduce((sum, deal) => sum + (deal.confidence * 100), 0) / deals.length) || 0).toFixed(0)}%
            </p>
          </div>
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        {deals.map((deal) => (
          <Card key={deal.id} className="group relative overflow-hidden transition-all hover:shadow-lg">
            <div className="absolute inset-0 bg-gradient-to-br from-primary/5 to-transparent opacity-0 transition-opacity group-hover:opacity-100" />
            
            <CardHeader className="pb-3">
              <div className="flex items-start justify-between">
                <Badge className={getStatusColor(deal.status)} variant="secondary">
                  {deal.status.toUpperCase()}
                </Badge>
                <div className="text-right">
                  <div className="flex items-center space-x-1">
                    <Star className="h-4 w-4 fill-current text-warning" />
                    <span className={`font-bold ${getScoreColor(deal.score || Math.floor(deal.confidence * 100))}`}>
                      {deal.score || Math.floor(deal.confidence * 100)}
                    </span>
                  </div>
                </div>
              </div>
              
              <CardTitle className="text-lg leading-tight">
                {deal.title}
              </CardTitle>
            </CardHeader>

            <CardContent className="space-y-4">
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">Mileage</span>
                <span className="font-medium">{deal.vehicle.mileage.toLocaleString()} mi</span>
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Acquisition Cost</span>
                  <span className="font-semibold">${deal.acquisition_cost.toLocaleString()}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Expected Price</span>
                  <span className="font-semibold">${deal.expected_price.toLocaleString()}</span>
                </div>
                <div className="border-t pt-2">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium">Potential Profit</span>
                    <div className="text-right">
                      <div className="font-bold text-success">${deal.profit.toLocaleString()}</div>
                      <div className="text-xs text-success">({(deal.roi * 100).toFixed(1)}% ROI)</div>
                    </div>
                  </div>
                </div>
              </div>

              <div className="flex items-center justify-between text-xs mb-2">
                <div className="flex items-center space-x-1">
                  <Target className="h-3 w-3 text-primary" />
                  <span className="text-muted-foreground">Confidence: {(deal.confidence * 100).toFixed(0)}%</span>
                </div>
                <div className="flex items-center space-x-1">
                  <TrendingUp className="h-3 w-3 text-success" />
                  <span className="text-success font-medium">ROI: {(deal.roi * 100).toFixed(1)}%</span>
                </div>
              </div>

              <Progress value={deal.confidence * 100} className="h-2" />

              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <div className="flex items-center space-x-1">
                  <MapPin className="h-3 w-3" />
                  <span>{deal.location || `${deal.state || 'Unknown'}`}</span>
                </div>
                {deal.auction_end && (
                  <div className="flex items-center space-x-1">
                    <Calendar className="h-3 w-3" />
                    <span>Ends {new Date(deal.auction_end).toLocaleDateString()}</span>
                  </div>
                )}
              </div>

              <Button className="w-full" size="sm">
                <ExternalLink className="mr-2 h-4 w-4" />
                View Auction
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
};