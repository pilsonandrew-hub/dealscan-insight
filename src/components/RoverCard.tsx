import React from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { DealItem } from '@/services/roverAPI';
import { DollarSign, MapPin, Clock, TrendingUp, Star } from 'lucide-react';

interface RoverCardProps {
  item: DealItem;
  onInteraction: (item: DealItem, eventType: 'view' | 'click' | 'save' | 'bid') => void;
  showExplanation?: boolean;
}

export const RoverCard: React.FC<RoverCardProps> = ({ 
  item, 
  onInteraction, 
  showExplanation = false 
}) => {
  const handleClick = () => {
    onInteraction(item, 'click');
  };

  const handleSave = (e: React.MouseEvent) => {
    e.stopPropagation();
    onInteraction(item, 'save');
  };

  const handleBid = (e: React.MouseEvent) => {
    e.stopPropagation();
    onInteraction(item, 'bid');
  };

  const getScoreColor = (score: number) => {
    if (score >= 0.8) return 'bg-green-100 text-green-800 border-green-200';
    if (score >= 0.6) return 'bg-yellow-100 text-yellow-800 border-yellow-200';
    return 'bg-gray-100 text-gray-800 border-gray-200';
  };

  const getROIColor = (roi: number) => {
    if (roi >= 30) return 'bg-emerald-100 text-emerald-800 border-emerald-200';
    if (roi >= 15) return 'bg-green-100 text-green-800 border-green-200';
    return 'bg-blue-100 text-blue-800 border-blue-200';
  };

  return (
    <Card 
      className="hover:shadow-lg transition-all duration-200 cursor-pointer border-l-4 border-l-primary/20 hover:border-l-primary"
      onClick={handleClick}
    >
      <CardContent className="p-6">
        <div className="flex items-start justify-between mb-4">
          <div className="flex-1">
            <div className="flex items-center space-x-3 mb-2">
              <h3 className="text-xl font-bold text-card-foreground">
                {item.year} {item.make} {item.model}
              </h3>
              
              {item._score && (
                <Badge className={getScoreColor(item._score)}>
                  <Star className="h-3 w-3 mr-1" />
                  {Math.round(item._score * 100)}
                </Badge>
              )}
              
              {item.roi_percentage && (
                <Badge className={getROIColor(item.roi_percentage)}>
                  <TrendingUp className="h-3 w-3 mr-1" />
                  ROI: {Math.round(item.roi_percentage)}%
                </Badge>
              )}
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
              <div className="flex items-center space-x-2 text-muted-foreground">
                <DollarSign className="h-4 w-4" />
                <span className="font-medium">${item.price?.toLocaleString()}</span>
              </div>
              
              {item.mileage && (
                <div className="flex items-center space-x-2 text-muted-foreground">
                  <Clock className="h-4 w-4" />
                  <span>{item.mileage.toLocaleString()} mi</span>
                </div>
              )}
              
              {item.state && (
                <div className="flex items-center space-x-2 text-muted-foreground">
                  <MapPin className="h-4 w-4" />
                  <span>{item.state}</span>
                </div>
              )}
              
              {item.source && (
                <Badge variant="outline" className="w-fit">
                  {item.source}
                </Badge>
              )}
            </div>

            {item.potential_profit && (
              <div className="bg-gradient-to-r from-green-50 to-emerald-50 p-3 rounded-lg mb-4">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-green-800">
                    Potential Profit
                  </span>
                  <span className="text-lg font-bold text-green-600">
                    ${item.potential_profit.toLocaleString()}
                  </span>
                </div>
              </div>
            )}

            {showExplanation && item._score && (
              <div className="bg-muted/50 p-3 rounded-lg mb-4">
                <h4 className="text-sm font-medium mb-2">Why Rover recommends this:</h4>
                <ul className="text-xs text-muted-foreground space-y-1">
                  {item.roi_percentage && item.roi_percentage > 15 && (
                    <li>• High ROI potential ({Math.round(item.roi_percentage)}%)</li>
                  )}
                  {item._score > 0.7 && (
                    <li>• Strong match for your preferences</li>
                  )}
                  {item.arbitrage_score && item.arbitrage_score > 70 && (
                    <li>• Excellent arbitrage opportunity</li>
                  )}
                  <li>• Recently discovered opportunity</li>
                </ul>
              </div>
            )}
          </div>
        </div>

        <div className="flex space-x-3">
          <Button 
            variant="outline" 
            size="sm"
            onClick={handleSave}
          >
            Save
          </Button>
          <Button 
            size="sm"
            onClick={handleBid}
          >
            Place Bid
          </Button>
          <Button 
            variant="ghost" 
            size="sm"
          >
            View Details
          </Button>
        </div>
      </CardContent>
    </Card>
  );
};

export default RoverCard;