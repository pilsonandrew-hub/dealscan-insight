import { useState, useEffect } from "react";
import { Shield, AlertTriangle, TrendingDown, Eye, Filter, Clock } from "lucide-react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

interface Anomaly {
  id: string;
  type: 'price' | 'demand' | 'supply' | 'fraud' | 'market';
  severity: 'critical' | 'high' | 'medium' | 'low';
  title: string;
  description: string;
  affectedVehicles: number;
  detectedAt: Date;
  confidence: number;
  status: 'active' | 'investigating' | 'resolved' | 'dismissed';
  financialImpact?: number;
  location?: string;
  makeModel?: string;
}

interface AnomalyStats {
  totalDetected: number;
  criticalActive: number;
  falsePositiveRate: number;
  avgDetectionTime: number;
  potentialSavings: number;
}

export const AnomalyDetectionPanel = () => {
  const [anomalies, setAnomalies] = useState<Anomaly[]>([]);
  const [stats, setStats] = useState<AnomalyStats>({
    totalDetected: 0,
    criticalActive: 0,
    falsePositiveRate: 0,
    avgDetectionTime: 0,
    potentialSavings: 0
  });
  const [activeFilter, setActiveFilter] = useState<string>('all');

  useEffect(() => {
    // Simulate anomaly detection data
    const mockAnomalies: Anomaly[] = [
      {
        id: '1',
        type: 'price',
        severity: 'critical',
        title: 'Unusual Price Drop - Ford F-150',
        description: 'Ford F-150 prices in Dallas region dropped 15% overnight, significantly above market volatility threshold',
        affectedVehicles: 147,
        detectedAt: new Date(Date.now() - 2 * 60 * 60 * 1000),
        confidence: 0.94,
        status: 'active',
        financialImpact: 28400,
        location: 'Dallas, TX',
        makeModel: 'Ford F-150'
      },
      {
        id: '2',
        type: 'fraud',
        severity: 'high',
        title: 'Suspicious Listing Pattern',
        description: 'Multiple high-value vehicles listed with identical descriptions and suspicious pricing patterns',
        affectedVehicles: 23,
        detectedAt: new Date(Date.now() - 4 * 60 * 60 * 1000),
        confidence: 0.87,
        status: 'investigating',
        financialImpact: 156000,
        location: 'Multiple States'
      },
      {
        id: '3',
        type: 'demand',
        severity: 'medium',
        title: 'Demand Spike - Electric Vehicles',
        description: 'Tesla Model 3 demand increased 340% in California, suggesting market manipulation or major event',
        affectedVehicles: 89,
        detectedAt: new Date(Date.now() - 6 * 60 * 60 * 1000),
        confidence: 0.76,
        status: 'active',
        location: 'California',
        makeModel: 'Tesla Model 3'
      },
      {
        id: '4',
        type: 'supply',
        severity: 'high',
        title: 'Supply Chain Disruption',
        description: 'Sudden availability increase of luxury vehicles suggests fleet liquidation or supply chain event',
        affectedVehicles: 312,
        detectedAt: new Date(Date.now() - 8 * 60 * 60 * 1000),
        confidence: 0.82,
        status: 'investigating',
        financialImpact: 89300
      },
      {
        id: '5',
        type: 'market',
        severity: 'low',
        title: 'Regional Price Variance',
        description: 'Honda Civic prices showing unusual variance between neighboring states',
        affectedVehicles: 67,
        detectedAt: new Date(Date.now() - 12 * 60 * 60 * 1000),
        confidence: 0.68,
        status: 'resolved',
        makeModel: 'Honda Civic'
      }
    ];

    const mockStats: AnomalyStats = {
      totalDetected: 156,
      criticalActive: 3,
      falsePositiveRate: 0.08,
      avgDetectionTime: 4.2,
      potentialSavings: 847300
    };

    setAnomalies(mockAnomalies);
    setStats(mockStats);
  }, []);

  const updateAnomalyStatus = (id: string, newStatus: Anomaly['status']) => {
    setAnomalies(prev => prev.map(a => a.id === id ? { ...a, status: newStatus } : a));
  };

  const filteredAnomalies = anomalies.filter(anomaly => {
    if (activeFilter === 'all') return true;
    if (activeFilter === 'active') return anomaly.status === 'active';
    if (activeFilter === 'critical') return anomaly.severity === 'critical';
    return anomaly.type === activeFilter;
  });

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'critical': return 'text-destructive';
      case 'high': return 'text-warning';
      case 'medium': return 'text-primary';
      case 'low': return 'text-muted-foreground';
      default: return 'text-muted-foreground';
    }
  };

  const getSeverityBadge = (severity: string) => {
    switch (severity) {
      case 'critical': return 'destructive';
      case 'high': return 'secondary';
      case 'medium': return 'default';
      case 'low': return 'outline';
      default: return 'outline';
    }
  };

  const getTypeIcon = (type: string) => {
    switch (type) {
      case 'price': return <TrendingDown className="h-4 w-4" />;
      case 'fraud': return <Shield className="h-4 w-4" />;
      case 'demand': return <TrendingDown className="h-4 w-4" />;
      case 'supply': return <Filter className="h-4 w-4" />;
      case 'market': return <Eye className="h-4 w-4" />;
      default: return <AlertTriangle className="h-4 w-4" />;
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-foreground flex items-center gap-2">
          <Shield className="h-6 w-6 text-primary" />
          Anomaly Detection System
        </h2>
        <p className="text-muted-foreground">AI-powered detection of market anomalies and fraudulent patterns</p>
      </div>

      {/* Stats Overview */}
      <div className="grid gap-4 md:grid-cols-5">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Total Detected</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.totalDetected}</div>
            <p className="text-xs text-muted-foreground">Last 30 days</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Critical Active</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-destructive">{stats.criticalActive}</div>
            <p className="text-xs text-muted-foreground">Requires immediate attention</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">False Positive Rate</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-success">{(stats.falsePositiveRate * 100).toFixed(1)}%</div>
            <p className="text-xs text-muted-foreground">Model accuracy improving</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Avg Detection Time</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.avgDetectionTime}m</div>
            <p className="text-xs text-muted-foreground">Mean time to detection</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Potential Savings</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-success">${stats.potentialSavings.toLocaleString()}</div>
            <p className="text-xs text-muted-foreground">Losses prevented</p>
          </CardContent>
        </Card>
      </div>

      {/* Filters */}
      <Tabs value={activeFilter} onValueChange={setActiveFilter}>
        <TabsList>
          <TabsTrigger value="all">All Anomalies</TabsTrigger>
          <TabsTrigger value="active">Active</TabsTrigger>
          <TabsTrigger value="critical">Critical</TabsTrigger>
          <TabsTrigger value="price">Price</TabsTrigger>
          <TabsTrigger value="fraud">Fraud</TabsTrigger>
          <TabsTrigger value="demand">Demand</TabsTrigger>
        </TabsList>

        <TabsContent value={activeFilter} className="space-y-4">
          {filteredAnomalies.map((anomaly) => (
            <Card key={anomaly.id} className={`border-l-4 ${anomaly.severity === 'critical' ? 'border-l-destructive' : anomaly.severity === 'high' ? 'border-l-warning' : 'border-l-primary'}`}>
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    {getTypeIcon(anomaly.type)}
                    <CardTitle className="text-base">{anomaly.title}</CardTitle>
                    <Badge variant={getSeverityBadge(anomaly.severity)} className="capitalize">
                      {anomaly.severity}
                    </Badge>
                    <Badge variant="outline">
                      {Math.round(anomaly.confidence * 100)}% confidence
                    </Badge>
                  </div>
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <Clock className="h-3 w-3" />
                    {Math.round((Date.now() - anomaly.detectedAt.getTime()) / (1000 * 60 * 60))}h ago
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="text-sm text-muted-foreground">{anomaly.description}</p>
                
                <div className="grid gap-2 md:grid-cols-3 text-sm">
                  <div>
                    <span className="font-medium">Affected Vehicles: </span>
                    <span className="text-muted-foreground">{anomaly.affectedVehicles}</span>
                  </div>
                  {anomaly.location && (
                    <div>
                      <span className="font-medium">Location: </span>
                      <span className="text-muted-foreground">{anomaly.location}</span>
                    </div>
                  )}
                  {anomaly.financialImpact && (
                    <div>
                      <span className="font-medium">Financial Impact: </span>
                      <span className="text-destructive">${anomaly.financialImpact.toLocaleString()}</span>
                    </div>
                  )}
                </div>

                <div className="flex items-center justify-between pt-2">
                  <Badge variant={anomaly.status === 'active' ? 'destructive' : anomaly.status === 'investigating' ? 'secondary' : 'default'}>
                    {anomaly.status.toUpperCase()}
                  </Badge>
                  
                  {anomaly.status === 'active' && (
                    <div className="flex gap-2">
                      <Button size="sm" onClick={() => updateAnomalyStatus(anomaly.id, 'investigating')}>
                        Investigate
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => updateAnomalyStatus(anomaly.id, 'dismissed')}>
                        Dismiss
                      </Button>
                    </div>
                  )}
                  
                  {anomaly.status === 'investigating' && (
                    <div className="flex gap-2">
                      <Button size="sm" onClick={() => updateAnomalyStatus(anomaly.id, 'resolved')}>
                        Mark Resolved
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => updateAnomalyStatus(anomaly.id, 'dismissed')}>
                        Dismiss
                      </Button>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </TabsContent>
      </Tabs>
    </div>
  );
};