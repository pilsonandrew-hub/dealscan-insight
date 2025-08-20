import { useState } from "react";
import { TrendingUp, MapPin, Calendar, DollarSign, Star, ExternalLink } from "lucide-react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";

interface Deal {
  id: string;
  title: string;
  year: number;
  make: string;
  model: string;
  mileage: number;
  currentBid: number;
  estimatedValue: number;
  margin: number;
  marginPercent: number;
  score: number;
  location: string;
  state: string;
  auctionEnd: string;
  status: "hot" | "good" | "moderate";
  imageUrl?: string;
}

const mockDeals: Deal[] = [
  {
    id: "1",
    title: "2021 Ford F-150 XLT SuperCrew",
    year: 2021,
    make: "Ford",
    model: "F-150",
    mileage: 45230,
    currentBid: 28500,
    estimatedValue: 36800,
    margin: 8300,
    marginPercent: 29.1,
    score: 94,
    location: "Phoenix, AZ",
    state: "AZ",
    auctionEnd: "2024-01-15T18:00:00Z",
    status: "hot"
  },
  {
    id: "2",
    title: "2020 Chevrolet Silverado 1500 LT",
    year: 2020,
    make: "Chevrolet",
    model: "Silverado 1500",
    mileage: 52100,
    currentBid: 24750,
    estimatedValue: 31200,
    margin: 6450,
    marginPercent: 26.1,
    score: 87,
    location: "Denver, CO",
    state: "CO",
    auctionEnd: "2024-01-16T16:30:00Z",
    status: "good"
  },
  {
    id: "3",
    title: "2019 RAM 1500 Big Horn Crew Cab",
    year: 2019,
    make: "RAM",
    model: "1500",
    mileage: 68400,
    currentBid: 22100,
    estimatedValue: 27800,
    margin: 5700,
    marginPercent: 25.8,
    score: 81,
    location: "Dallas, TX",
    state: "TX",
    auctionEnd: "2024-01-17T19:00:00Z",
    status: "good"
  }
];

export const DealOpportunities = () => {
  const [deals] = useState<Deal[]>(mockDeals);

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

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-foreground">Deal Opportunities</h2>
          <p className="text-muted-foreground">High-potential arbitrage opportunities from government auctions</p>
        </div>
        <div className="flex items-center space-x-4">
          <div className="text-right">
            <p className="text-sm text-muted-foreground">Total Opportunities</p>
            <p className="text-2xl font-bold text-success">{deals.length}</p>
          </div>
          <div className="text-right">
            <p className="text-sm text-muted-foreground">Avg. Margin</p>
            <p className="text-2xl font-bold text-primary">
              {((deals.reduce((sum, deal) => sum + deal.marginPercent, 0) / deals.length) || 0).toFixed(1)}%
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
                    <span className={`font-bold ${getScoreColor(deal.score)}`}>{deal.score}</span>
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
                <span className="font-medium">{deal.mileage.toLocaleString()} mi</span>
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Current Bid</span>
                  <span className="font-semibold">${deal.currentBid.toLocaleString()}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Est. CA Value</span>
                  <span className="font-semibold">${deal.estimatedValue.toLocaleString()}</span>
                </div>
                <div className="border-t pt-2">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium">Potential Margin</span>
                    <div className="text-right">
                      <div className="font-bold text-success">${deal.margin.toLocaleString()}</div>
                      <div className="text-xs text-success">({deal.marginPercent}%)</div>
                    </div>
                  </div>
                </div>
              </div>

              <Progress value={deal.marginPercent} className="h-2" />

              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <div className="flex items-center space-x-1">
                  <MapPin className="h-3 w-3" />
                  <span>{deal.location}</span>
                </div>
                <div className="flex items-center space-x-1">
                  <Calendar className="h-3 w-3" />
                  <span>Ends {new Date(deal.auctionEnd).toLocaleDateString()}</span>
                </div>
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