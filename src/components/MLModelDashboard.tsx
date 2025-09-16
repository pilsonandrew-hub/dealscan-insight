import { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Brain, Activity, Target, AlertTriangle, RefreshCw, TrendingUp } from "lucide-react";
import { useToast } from "@/hooks/use-toast";

interface MLModel {
  id: string;
  name: string;
  type: 'price_prediction' | 'anomaly_detection' | 'risk_assessment';
  status: 'training' | 'deployed' | 'updating' | 'error';
  accuracy: number;
  lastTrained: Date;
  trainingDataSize: number;
  version: string;
}

interface ModelMetrics {
  predictions: number;
  accuracy: number;
  latency: number;
  errors: number;
}

export const MLModelDashboard = () => {
  const [models, setModels] = useState<MLModel[]>([
    {
      id: '1',
      name: 'Price Prediction Engine',
      type: 'price_prediction',
      status: 'deployed',
      accuracy: 87.3,
      lastTrained: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000),
      trainingDataSize: 45230,
      version: 'v2.1.0'
    },
    {
      id: '2', 
      name: 'Fraud Detection Model',
      type: 'anomaly_detection',
      status: 'deployed',
      accuracy: 94.1,
      lastTrained: new Date(Date.now() - 1 * 24 * 60 * 60 * 1000),
      trainingDataSize: 12840,
      version: 'v1.8.2'
    },
    {
      id: '3',
      name: 'Risk Assessment AI',
      type: 'risk_assessment', 
      status: 'training',
      accuracy: 91.6,
      lastTrained: new Date(Date.now() - 4 * 60 * 60 * 1000),
      trainingDataSize: 38920,
      version: 'v3.0.0-beta'
    }
  ]);

  const [metrics] = useState<Record<string, ModelMetrics>>({
    '1': { predictions: 2847, accuracy: 87.3, latency: 142, errors: 3 },
    '2': { predictions: 1923, accuracy: 94.1, latency: 89, errors: 1 },
    '3': { predictions: 1456, accuracy: 91.6, latency: 201, errors: 2 }
  });

  const [trainingProgress, setTrainingProgress] = useState(67);
  const { toast } = useToast();

  useEffect(() => {
    const interval = setInterval(() => {
      setTrainingProgress(prev => (prev >= 100 ? 0 : prev + 1));
    }, 2000);
    return () => clearInterval(interval);
  }, []);

  const getStatusColor = (status: MLModel['status']) => {
    switch (status) {
      case 'deployed': return 'bg-green-500';
      case 'training': return 'bg-yellow-500';
      case 'updating': return 'bg-blue-500';
      case 'error': return 'bg-red-500';
      default: return 'bg-gray-500';
    }
  };

  const getTypeIcon = (type: MLModel['type']) => {
    switch (type) {
      case 'price_prediction': return <Target className="h-4 w-4" />;
      case 'anomaly_detection': return <AlertTriangle className="h-4 w-4" />;
      case 'risk_assessment': return <Activity className="h-4 w-4" />;
      default: return <Brain className="h-4 w-4" />;
    }
  };

  const retrain = (modelId: string) => {
    setModels(prev => prev.map(model => 
      model.id === modelId 
        ? { ...model, status: 'training' as const }
        : model
    ));
    
    toast({
      title: "Retraining Started",
      description: "Model retraining initiated with latest data",
    });

    // Simulate training completion
    setTimeout(() => {
      setModels(prev => prev.map(model => 
        model.id === modelId 
          ? { 
              ...model, 
              status: 'deployed' as const,
              lastTrained: new Date(),
              accuracy: Math.min(100, model.accuracy + Math.random() * 2)
            }
          : model
      ));
      
      toast({
        title: "Retraining Complete",
        description: "Model has been successfully retrained and deployed",
      });
    }, 5000);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">ML Model Dashboard</h2>
          <p className="text-muted-foreground">
            Monitor and manage machine learning models for intelligent deal analysis
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="text-green-600 border-green-200">
            <Activity className="h-3 w-3 mr-1" />
            {models.filter(m => m.status === 'deployed').length} Active
          </Badge>
          <Badge variant="outline" className="text-yellow-600 border-yellow-200">
            <RefreshCw className="h-3 w-3 mr-1" />
            {models.filter(m => m.status === 'training').length} Training
          </Badge>
        </div>
      </div>

      <Tabs defaultValue="overview" className="space-y-4">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="models">Models</TabsTrigger>
          <TabsTrigger value="performance">Performance</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-4">
          <div className="grid gap-4 md:grid-cols-3">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Total Predictions</CardTitle>
                <Brain className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {Object.values(metrics).reduce((sum, m) => sum + m.predictions, 0).toLocaleString()}
                </div>
                <p className="text-xs text-muted-foreground">
                  +12.3% from last week
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Average Accuracy</CardTitle>
                <Target className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {(models.reduce((sum, m) => sum + m.accuracy, 0) / models.length).toFixed(1)}%
                </div>
                <p className="text-xs text-muted-foreground">
                  +2.1% improvement
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Model Errors</CardTitle>
                <AlertTriangle className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {Object.values(metrics).reduce((sum, m) => sum + m.errors, 0)}
                </div>
                <p className="text-xs text-muted-foreground">
                  -15% from yesterday
                </p>
              </CardContent>
            </Card>
          </div>

          {/* Training Progress */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Active Training</CardTitle>
              <CardDescription>Risk Assessment AI v3.0.0-beta</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <div className="flex items-center justify-between text-sm">
                  <span>Training Progress</span>
                  <span>{trainingProgress}%</span>
                </div>
                <Progress value={trainingProgress} className="h-2" />
              </div>
              <div className="text-sm text-muted-foreground">
                Estimated time remaining: {Math.max(0, Math.ceil((100 - trainingProgress) * 0.5))} minutes
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="models" className="space-y-4">
          <div className="grid gap-4">
            {models.map((model) => (
              <Card key={model.id}>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      {getTypeIcon(model.type)}
                      <div>
                        <CardTitle className="text-lg">{model.name}</CardTitle>
                        <CardDescription>{model.version}</CardDescription>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant="outline" className={`${getStatusColor(model.status)} text-white border-0`}>
                        {model.status}
                      </Badge>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => retrain(model.id)}
                        disabled={model.status === 'training'}
                      >
                        <RefreshCw className="h-3 w-3 mr-1" />
                        Retrain
                      </Button>
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                    <div>
                      <p className="text-muted-foreground">Accuracy</p>
                      <p className="font-semibold">{model.accuracy}%</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Training Data</p>
                      <p className="font-semibold">{model.trainingDataSize.toLocaleString()}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Last Trained</p>
                      <p className="font-semibold">{model.lastTrained.toLocaleDateString()}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Predictions Today</p>
                      <p className="font-semibold">{metrics[model.id]?.predictions || 0}</p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="performance" className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Model Performance</CardTitle>
                <CardDescription>Accuracy trends over time</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  {models.map((model) => (
                    <div key={model.id} className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        {getTypeIcon(model.type)}
                        <span className="text-sm font-medium">{model.name}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <Progress value={model.accuracy} className="w-20 h-2" />
                        <span className="text-sm font-semibold">{model.accuracy}%</span>
                        <TrendingUp className="h-3 w-3 text-green-500" />
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Response Times</CardTitle>
                <CardDescription>Average latency per model</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  {models.map((model) => (
                    <div key={model.id} className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        {getTypeIcon(model.type)}
                        <span className="text-sm font-medium">{model.name}</span>
                      </div>
                      <div className="text-sm font-semibold">
                        {metrics[model.id]?.latency || 0}ms
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
};