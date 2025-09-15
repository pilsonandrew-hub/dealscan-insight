import { useState, useEffect } from "react";
import { Brain, TrendingUp, AlertTriangle, CheckCircle, Clock, Target } from "lucide-react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { useToast } from "@/hooks/use-toast";

interface AIDecision {
  id: string;
  vehicleId: string;
  make: string;
  model: string;
  year: number;
  recommendation: 'buy' | 'watch' | 'pass';
  confidence: number;
  reasoning: string[];
  estimatedProfit: number;
  riskScore: number;
  timestamp: Date;
  status: 'pending' | 'executed' | 'declined';
}

interface MLInsight {
  type: 'market_trend' | 'price_prediction' | 'demand_forecast' | 'risk_alert';
  title: string;
  description: string;
  confidence: number;
  impact: 'high' | 'medium' | 'low';
  timeframe: string;
}

export const AIDecisionEngine = () => {
  const [decisions, setDecisions] = useState<AIDecision[]>([]);
  const [insights, setInsights] = useState<MLInsight[]>([]);
  const [automationEnabled, setAutomationEnabled] = useState(false);
  const [processing, setProcessing] = useState(false);
  const { toast } = useToast();

  useEffect(() => {
    // Simulate AI decision making
    const mockDecisions: AIDecision[] = [
      {
        id: '1',
        vehicleId: 'v123',
        make: 'Ford',
        model: 'F-150',
        year: 2021,
        recommendation: 'buy',
        confidence: 0.87,
        reasoning: [
          'Price 18% below market average',
          'High demand region (Texas)',
          'Clean title with low mileage',
          'Seasonal demand peak approaching'
        ],
        estimatedProfit: 4200,
        riskScore: 0.12,
        timestamp: new Date(),
        status: 'pending'
      },
      {
        id: '2',
        vehicleId: 'v124',
        make: 'Toyota',
        model: 'Camry',
        year: 2020,
        recommendation: 'watch',
        confidence: 0.64,
        reasoning: [
          'Price near market value',
          'Moderate demand region',
          'Minor accident history detected',
          'Competition from similar listings'
        ],
        estimatedProfit: 1800,
        riskScore: 0.35,
        timestamp: new Date(),
        status: 'pending'
      },
      {
        id: '3',
        vehicleId: 'v125',
        make: 'BMW',
        model: 'X5',
        year: 2019,
        recommendation: 'pass',
        confidence: 0.91,
        reasoning: [
          'Overpriced by 22%',
          'High maintenance costs predicted',
          'Declining luxury SUV demand',
          'Multiple red flags in history'
        ],
        estimatedProfit: -1200,
        riskScore: 0.78,
        timestamp: new Date(),
        status: 'pending'
      }
    ];

    const mockInsights: MLInsight[] = [
      {
        type: 'market_trend',
        title: 'Electric Vehicle Surge',
        description: 'EV prices dropping 12% as supply increases, creating arbitrage opportunities',
        confidence: 0.85,
        impact: 'high',
        timeframe: 'Next 30 days'
      },
      {
        type: 'price_prediction',
        title: 'Truck Market Stabilization',
        description: 'Full-size truck prices expected to plateau after 6-month decline',
        confidence: 0.72,
        impact: 'medium',
        timeframe: 'Next 60 days'
      },
      {
        type: 'demand_forecast',
        title: 'Southeast Region Hot Streak',
        description: 'Florida and Georgia showing 28% higher buyer activity',
        confidence: 0.79,
        impact: 'high',
        timeframe: 'Current'
      }
    ];

    setDecisions(mockDecisions);
    setInsights(mockInsights);
  }, []);

  const executeDecision = (decisionId: string, action: 'accept' | 'decline') => {
    setProcessing(true);
    setTimeout(() => {
      setDecisions(prev => prev.map(d => 
        d.id === decisionId 
          ? { ...d, status: action === 'accept' ? 'executed' : 'declined' }
          : d
      ));
      setProcessing(false);
      toast({
        title: action === 'accept' ? "Decision Executed" : "Decision Declined",
        description: `AI recommendation has been ${action === 'accept' ? 'accepted' : 'declined'}.`,
      });
    }, 1500);
  };

  const getRecommendationColor = (rec: string) => {
    switch (rec) {
      case 'buy': return 'text-success';
      case 'watch': return 'text-warning';
      case 'pass': return 'text-destructive';
      default: return 'text-muted-foreground';
    }
  };

  const getRecommendationBadge = (rec: string) => {
    switch (rec) {
      case 'buy': return 'default';
      case 'watch': return 'secondary';
      case 'pass': return 'destructive';
      default: return 'outline';
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-foreground flex items-center gap-2">
            <Brain className="h-6 w-6 text-primary" />
            AI Decision Engine
          </h2>
          <p className="text-muted-foreground">AI-powered deal analysis and automated decision making</p>
        </div>
        <div className="flex items-center gap-4">
          <Badge variant={automationEnabled ? "default" : "secondary"}>
            {automationEnabled ? "Auto-Execution ON" : "Manual Mode"}
          </Badge>
          <Button
            variant={automationEnabled ? "destructive" : "default"}
            onClick={() => setAutomationEnabled(!automationEnabled)}
          >
            {automationEnabled ? "Disable Auto-Execution" : "Enable Auto-Execution"}
          </Button>
        </div>
      </div>

      {/* ML Insights */}
      <div className="grid gap-4 md:grid-cols-3">
        {insights.map((insight, index) => (
          <Card key={index} className="border-l-4 border-l-primary">
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center gap-2">
                {insight.type === 'market_trend' && <TrendingUp className="h-4 w-4" />}
                {insight.type === 'price_prediction' && <Target className="h-4 w-4" />}
                {insight.type === 'demand_forecast' && <Clock className="h-4 w-4" />}
                {insight.type === 'risk_alert' && <AlertTriangle className="h-4 w-4" />}
                {insight.title}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <p className="text-sm text-muted-foreground">{insight.description}</p>
              <div className="flex items-center justify-between">
                <Badge variant={insight.impact === 'high' ? 'default' : insight.impact === 'medium' ? 'secondary' : 'outline'}>
                  {insight.impact.toUpperCase()} IMPACT
                </Badge>
                <span className="text-xs text-muted-foreground">{Math.round(insight.confidence * 100)}% confidence</span>
              </div>
              <p className="text-xs text-muted-foreground">{insight.timeframe}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* AI Decisions */}
      <Card>
        <CardHeader>
          <CardTitle>AI Recommendations</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {decisions.map((decision) => (
              <div key={decision.id} className="border rounded-lg p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <Badge variant={getRecommendationBadge(decision.recommendation)} className="capitalize">
                      {decision.recommendation}
                    </Badge>
                    <span className="font-medium">
                      {decision.year} {decision.make} {decision.model}
                    </span>
                    <Badge variant="outline">{Math.round(decision.confidence * 100)}% confidence</Badge>
                  </div>
                  <div className="text-right">
                    <div className={`font-medium ${decision.estimatedProfit > 0 ? 'text-success' : 'text-destructive'}`}>
                      ${decision.estimatedProfit > 0 ? '+' : ''}{decision.estimatedProfit.toLocaleString()}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      Risk: {Math.round(decision.riskScore * 100)}%
                    </div>
                  </div>
                </div>

                <div className="space-y-1">
                  <div className="text-sm font-medium">AI Reasoning:</div>
                  <ul className="text-sm text-muted-foreground space-y-1">
                    {decision.reasoning.map((reason, idx) => (
                      <li key={idx} className="flex items-center gap-2">
                        <div className="w-1 h-1 bg-primary rounded-full" />
                        {reason}
                      </li>
                    ))}
                  </ul>
                </div>

                {decision.status === 'pending' && (
                  <div className="flex gap-2 pt-2">
                    <Button
                      size="sm"
                      onClick={() => executeDecision(decision.id, 'accept')}
                      disabled={processing}
                      className="flex items-center gap-1"
                    >
                      <CheckCircle className="h-3 w-3" />
                      Accept
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => executeDecision(decision.id, 'decline')}
                      disabled={processing}
                    >
                      Decline
                    </Button>
                  </div>
                )}

                {decision.status !== 'pending' && (
                  <Badge variant={decision.status === 'executed' ? 'default' : 'secondary'}>
                    {decision.status === 'executed' ? 'Executed' : 'Declined'}
                  </Badge>
                )}
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
};