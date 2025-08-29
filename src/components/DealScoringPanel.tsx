import { useState } from "react";
import { Play, Pause, BarChart3, Target, TrendingUp, AlertCircle } from "lucide-react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { useDealScoring } from "@/hooks/useDealScoring";
import { toast } from "sonner";
import { logger } from "@/core/UnifiedLogger";

export const DealScoringPanel = () => {
  const { isScoring, progress, scoreAllListings, cancelScoring } = useDealScoring();

  const handleStartScoring = async () => {
    try {
      await scoreAllListings();
    } catch (error) {
      logger.error('Error starting scoring', { error });
      toast.error('Failed to start scoring');
    }
  };

  const handleCancelScoring = () => {
    cancelScoring();
    toast.info('Scoring cancelled');
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-foreground">Deal Scoring Engine</h2>
          <p className="text-muted-foreground">
            Analyze listings and identify profitable opportunities automatically
          </p>
        </div>
        
        <div className="flex items-center gap-2">
          {isScoring ? (
            <Button onClick={handleCancelScoring} variant="destructive" size="sm">
              <Pause className="w-4 h-4 mr-2" />
              Cancel Scoring
            </Button>
          ) : (
            <Button onClick={handleStartScoring} size="sm">
              <Play className="w-4 h-4 mr-2" />
              Start Scoring
            </Button>
          )}
        </div>
      </div>

      {/* Scoring Progress */}
      {progress && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <BarChart3 className="w-5 h-5" />
              Scoring Progress
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-3 gap-4 text-center">
              <div>
                <div className="text-2xl font-bold text-primary">{progress.processed}</div>
                <div className="text-sm text-muted-foreground">Processed</div>
              </div>
              <div>
                <div className="text-2xl font-bold text-warning">{progress.total}</div>
                <div className="text-sm text-muted-foreground">Total</div>
              </div>
              <div>
                <div className="text-2xl font-bold text-success">{progress.opportunities}</div>
                <div className="text-sm text-muted-foreground">Opportunities</div>
              </div>
            </div>
            
            <Progress 
              value={(progress.processed / progress.total) * 100} 
              className="h-3"
            />
            
            <div className="text-center text-sm text-muted-foreground">
              {Math.round((progress.processed / progress.total) * 100)}% complete
            </div>
          </CardContent>
        </Card>
      )}

      {/* Scoring Metrics Info */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <Target className="w-5 h-5 text-primary" />
              Profitability Thresholds
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex justify-between items-center">
              <span className="text-sm text-muted-foreground">Min ROI</span>
              <Badge variant="outline">15%</Badge>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-muted-foreground">Min Profit</span>
              <Badge variant="outline">$3,000</Badge>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-muted-foreground">Max Risk</span>
              <Badge variant="outline">70/100</Badge>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-muted-foreground">Min Confidence</span>
              <Badge variant="outline">40%</Badge>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <TrendingUp className="w-5 h-5 text-success" />
              Risk Factors
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="text-sm">
              <div className="font-medium mb-2">Age Risk</div>
              <div className="text-muted-foreground text-xs space-y-1">
                <div>• &lt;5 years: Low (5pts)</div>
                <div>• 5-10 years: Medium (10pts)</div>
                <div>• &gt;10 years: High (15pts)</div>
              </div>
            </div>
            <div className="text-sm">
              <div className="font-medium mb-2">Title Status</div>
              <div className="text-muted-foreground text-xs space-y-1">
                <div>• Clean: 0pts</div>
                <div>• Salvage: +30pts</div>
                <div>• Flood: +35pts</div>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <AlertCircle className="w-5 h-5 text-warning" />
              State Filters
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="text-sm">
              <div className="font-medium mb-2 text-success">Preferred States</div>
              <div className="text-muted-foreground text-xs">
                CA, NV, AZ, OR, WA, TX
              </div>
            </div>
            <div className="text-sm">
              <div className="font-medium mb-2 text-warning">Rust Belt (+20 risk)</div>
              <div className="text-muted-foreground text-xs">
                MI, OH, IL, IN, WI, MN
              </div>
            </div>
            <div className="text-xs text-muted-foreground mt-3">
              Transport costs calculated based on distance from CA hub
            </div>
          </CardContent>
        </Card>
      </div>

      {/* How It Works */}
      <Card>
        <CardHeader>
          <CardTitle>How Deal Scoring Works</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 text-sm">
            <div>
              <h4 className="font-semibold mb-2">1. Market Value Estimation</h4>
              <p className="text-muted-foreground mb-4">
                Uses historical dealer sales data and ML regression to estimate true market value, 
                adjusted for mileage, age, and title status.
              </p>
              
              <h4 className="font-semibold mb-2">3. Risk Assessment</h4>
              <p className="text-muted-foreground">
                Calculates risk score based on vehicle age, mileage, title status, 
                market volatility, and state corrosion risk.
              </p>
            </div>
            <div>
              <h4 className="font-semibold mb-2">2. Cost Calculation</h4>
              <p className="text-muted-foreground mb-4">
                Factors in buyer's premium, doc fees, transportation costs (state-based), 
                and other acquisition expenses.
              </p>
              
              <h4 className="font-semibold mb-2">4. Opportunity Creation</h4>
              <p className="text-muted-foreground">
                Only creates opportunities that meet all profitability thresholds: 
                15% ROI, $3k profit, &lt;70 risk, 40% confidence.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};