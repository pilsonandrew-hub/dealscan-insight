import { useState, useEffect } from "react";
import { Zap, Play, Pause, Settings, Clock, Target, DollarSign, TrendingUp } from "lucide-react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useToast } from "@/hooks/use-toast";

interface AutomationRule {
  id: string;
  name: string;
  type: 'bidding' | 'monitoring' | 'analysis' | 'alerting';
  description: string;
  isActive: boolean;
  triggers: string[];
  actions: string[];
  performance: {
    successRate: number;
    dealsExecuted: number;
    avgProfit: number;
    totalSaved: number;
  };
  lastRun?: Date;
  nextRun?: Date;
}

interface AutomationMetrics {
  totalRules: number;
  activeRules: number;
  dealsProcessed: number;
  automationSavings: number;
  errorRate: number;
}

export const AdvancedAutomationHub = () => {
  const [rules, setRules] = useState<AutomationRule[]>([]);
  const [metrics, setMetrics] = useState<AutomationMetrics>({
    totalRules: 0,
    activeRules: 0,
    dealsProcessed: 0,
    automationSavings: 0,
    errorRate: 0
  });
  const [masterSwitch, setMasterSwitch] = useState(true);
  const { toast } = useToast();

  useEffect(() => {
    // Simulate automation rules data
    const mockRules: AutomationRule[] = [
      {
        id: '1',
        name: 'High-Confidence Auto Bidder',
        type: 'bidding',
        description: 'Automatically place bids on vehicles with >85% confidence score and >$3000 profit margin',
        isActive: true,
        triggers: ['New high-confidence listing', 'Price drop detected', 'Auction ending soon'],
        actions: ['Calculate max bid', 'Place competitive bid', 'Monitor competition', 'Adjust bid strategy'],
        performance: {
          successRate: 0.73,
          dealsExecuted: 47,
          avgProfit: 4280,
          totalSaved: 201160
        },
        lastRun: new Date(Date.now() - 15 * 60 * 1000),
        nextRun: new Date(Date.now() + 5 * 60 * 1000)
      },
      {
        id: '2',
        name: 'Market Anomaly Detector',
        type: 'monitoring',
        description: 'Continuously monitor for price anomalies, fraud patterns, and market manipulation',
        isActive: true,
        triggers: ['Price deviation >20%', 'Suspicious listing patterns', 'Volume spikes'],
        actions: ['Flag anomalies', 'Alert administrators', 'Pause affected rules', 'Generate reports'],
        performance: {
          successRate: 0.91,
          dealsExecuted: 156,
          avgProfit: 0,
          totalSaved: 89400
        },
        lastRun: new Date(Date.now() - 2 * 60 * 1000),
        nextRun: new Date(Date.now() + 3 * 60 * 1000)
      },
      {
        id: '3',
        name: 'Smart Deal Analyzer',
        type: 'analysis',
        description: 'Analyze all new listings for arbitrage opportunities and generate scored recommendations',
        isActive: true,
        triggers: ['New listing added', 'Price update', 'Market data refresh'],
        actions: ['Calculate arbitrage score', 'Predict profit potential', 'Assess risk factors', 'Generate recommendation'],
        performance: {
          successRate: 0.84,
          dealsExecuted: 892,
          avgProfit: 2150,
          totalSaved: 1918800
        },
        lastRun: new Date(Date.now() - 1 * 60 * 1000),
        nextRun: new Date(Date.now() + 1 * 60 * 1000)
      },
      {
        id: '4',
        name: 'Critical Alert System',
        type: 'alerting',
        description: 'Send instant notifications for high-value opportunities and urgent situations',
        isActive: true,
        triggers: ['Profit margin >$5000', 'Auction ending <30min', 'Critical anomaly detected'],
        actions: ['Send SMS alert', 'Email notification', 'In-app notification', 'Create priority task'],
        performance: {
          successRate: 0.96,
          dealsExecuted: 234,
          avgProfit: 0,
          totalSaved: 45600
        },
        lastRun: new Date(Date.now() - 8 * 60 * 1000),
        nextRun: new Date(Date.now() + 2 * 60 * 1000)
      },
      {
        id: '5',
        name: 'Seasonal Strategy Optimizer',
        type: 'analysis',
        description: 'Adjust bidding strategies based on seasonal trends and market conditions',
        isActive: false,
        triggers: ['Seasonal pattern detected', 'Market condition change', 'Weekly strategy review'],
        actions: ['Update bid multipliers', 'Adjust risk thresholds', 'Modify target categories', 'Rebalance portfolio'],
        performance: {
          successRate: 0.67,
          dealsExecuted: 23,
          avgProfit: 3890,
          totalSaved: 89470
        },
        lastRun: new Date(Date.now() - 24 * 60 * 60 * 1000)
      }
    ];

    const mockMetrics: AutomationMetrics = {
      totalRules: mockRules.length,
      activeRules: mockRules.filter(r => r.isActive).length,
      dealsProcessed: mockRules.reduce((sum, r) => sum + r.performance.dealsExecuted, 0),
      automationSavings: mockRules.reduce((sum, r) => sum + r.performance.totalSaved, 0),
      errorRate: 0.04
    };

    setRules(mockRules);
    setMetrics(mockMetrics);
  }, []);

  const toggleRule = (ruleId: string) => {
    setRules(prev => prev.map(rule => 
      rule.id === ruleId 
        ? { ...rule, isActive: !rule.isActive }
        : rule
    ));
    toast({
      title: "Automation Rule Updated",
      description: "Rule status has been changed successfully.",
    });
  };

  const getTypeIcon = (type: string) => {
    switch (type) {
      case 'bidding': return <Target className="h-4 w-4" />;
      case 'monitoring': return <TrendingUp className="h-4 w-4" />;
      case 'analysis': return <Settings className="h-4 w-4" />;
      case 'alerting': return <Zap className="h-4 w-4" />;
      default: return <Settings className="h-4 w-4" />;
    }
  };

  const getTypeColor = (type: string) => {
    switch (type) {
      case 'bidding': return 'text-primary';
      case 'monitoring': return 'text-success';
      case 'analysis': return 'text-warning';
      case 'alerting': return 'text-destructive';
      default: return 'text-muted-foreground';
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-foreground flex items-center gap-2">
            <Zap className="h-6 w-6 text-primary" />
            Advanced Automation Hub
          </h2>
          <p className="text-muted-foreground">Intelligent automation for deal discovery, bidding, and monitoring</p>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <Switch checked={masterSwitch} onCheckedChange={setMasterSwitch} />
            <span className="text-sm font-medium">Master Control</span>
          </div>
          <Badge variant={masterSwitch ? "default" : "secondary"}>
            {masterSwitch ? "AUTOMATION ACTIVE" : "AUTOMATION PAUSED"}
          </Badge>
        </div>
      </div>

      {/* Metrics Overview */}
      <div className="grid gap-4 md:grid-cols-5">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Total Rules</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{metrics.totalRules}</div>
            <p className="text-xs text-muted-foreground">Configured automation rules</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Active Rules</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-primary">{metrics.activeRules}</div>
            <p className="text-xs text-muted-foreground">Currently running</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Deals Processed</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{metrics.dealsProcessed.toLocaleString()}</div>
            <p className="text-xs text-muted-foreground">Total automated actions</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Automation Savings</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-success">${metrics.automationSavings.toLocaleString()}</div>
            <p className="text-xs text-muted-foreground">Time and cost savings</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Error Rate</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-success">{(metrics.errorRate * 100).toFixed(1)}%</div>
            <p className="text-xs text-muted-foreground">System reliability</p>
          </CardContent>
        </Card>
      </div>

      {/* Automation Rules */}
      <Tabs defaultValue="all">
        <TabsList>
          <TabsTrigger value="all">All Rules</TabsTrigger>
          <TabsTrigger value="bidding">Bidding</TabsTrigger>
          <TabsTrigger value="monitoring">Monitoring</TabsTrigger>
          <TabsTrigger value="analysis">Analysis</TabsTrigger>
          <TabsTrigger value="alerting">Alerting</TabsTrigger>
        </TabsList>

        <TabsContent value="all" className="space-y-4">
          {rules.map((rule) => (
            <Card key={rule.id} className={`${rule.isActive ? 'border-l-4 border-l-primary' : 'opacity-60'}`}>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className={getTypeColor(rule.type)}>
                      {getTypeIcon(rule.type)}
                    </div>
                    <CardTitle className="text-base">{rule.name}</CardTitle>
                    <Badge variant="outline" className="capitalize">
                      {rule.type}
                    </Badge>
                    <Badge variant={rule.isActive ? "default" : "secondary"}>
                      {rule.isActive ? "ACTIVE" : "INACTIVE"}
                    </Badge>
                  </div>
                  <div className="flex items-center gap-2">
                    <Switch checked={rule.isActive} onCheckedChange={() => toggleRule(rule.id)} />
                    <Button size="sm" variant="outline">
                      <Settings className="h-3 w-3" />
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <p className="text-sm text-muted-foreground">{rule.description}</p>

                {/* Performance Metrics */}
                <div className="grid gap-4 md:grid-cols-4">
                  <div className="space-y-1">
                    <div className="text-sm font-medium">Success Rate</div>
                    <div className="text-lg font-bold text-success">
                      {(rule.performance.successRate * 100).toFixed(0)}%
                    </div>
                  </div>
                  <div className="space-y-1">
                    <div className="text-sm font-medium">Deals Executed</div>
                    <div className="text-lg font-bold">
                      {rule.performance.dealsExecuted.toLocaleString()}
                    </div>
                  </div>
                  <div className="space-y-1">
                    <div className="text-sm font-medium">Avg Profit</div>
                    <div className="text-lg font-bold text-primary">
                      {rule.performance.avgProfit > 0 ? `$${rule.performance.avgProfit.toLocaleString()}` : 'N/A'}
                    </div>
                  </div>
                  <div className="space-y-1">
                    <div className="text-sm font-medium">Total Saved</div>
                    <div className="text-lg font-bold text-success">
                      ${rule.performance.totalSaved.toLocaleString()}
                    </div>
                  </div>
                </div>

                {/* Timing Information */}
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <div className="flex items-center gap-4">
                    {rule.lastRun && (
                      <div className="flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        Last run: {Math.round((Date.now() - rule.lastRun.getTime()) / (1000 * 60))}m ago
                      </div>
                    )}
                    {rule.nextRun && (
                      <div className="flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        Next run: {Math.round((rule.nextRun.getTime() - Date.now()) / (1000 * 60))}m
                      </div>
                    )}
                  </div>
                  <div className="flex gap-2">
                    <Button size="sm" variant="outline">
                      View Logs
                    </Button>
                    <Button size="sm" variant="outline">
                      Test Run
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </TabsContent>

        {/* Individual type tabs would filter the rules by type */}
        {['bidding', 'monitoring', 'analysis', 'alerting'].map(type => (
          <TabsContent key={type} value={type} className="space-y-4">
            {rules.filter(rule => rule.type === type).map((rule) => (
              <Card key={rule.id} className={`${rule.isActive ? 'border-l-4 border-l-primary' : 'opacity-60'}`}>
                {/* Same card content as above */}
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className={getTypeColor(rule.type)}>
                        {getTypeIcon(rule.type)}
                      </div>
                      <CardTitle className="text-base">{rule.name}</CardTitle>
                      <Badge variant={rule.isActive ? "default" : "secondary"}>
                        {rule.isActive ? "ACTIVE" : "INACTIVE"}
                      </Badge>
                    </div>
                    <Switch checked={rule.isActive} onCheckedChange={() => toggleRule(rule.id)} />
                  </div>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-muted-foreground">{rule.description}</p>
                </CardContent>
              </Card>
            ))}
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
};