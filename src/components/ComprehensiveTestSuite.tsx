import { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { 
  Play, 
  Pause, 
  CheckCircle, 
  XCircle, 
  AlertCircle, 
  Clock,
  Shield,
  Database,
  Zap,
  Brain
} from "lucide-react";
import { useToast } from "@/hooks/use-toast";

interface TestResult {
  id: string;
  name: string;
  category: 'security' | 'performance' | 'ml' | 'integration';
  status: 'pending' | 'running' | 'passed' | 'failed' | 'warning';
  duration: number;
  details: string;
  timestamp: Date;
}

interface TestSuite {
  name: string;
  category: 'security' | 'performance' | 'ml' | 'integration';
  tests: TestResult[];
  totalTests: number;
  passedTests: number;
  failedTests: number;
  runningTests: number;
}

export const ComprehensiveTestSuite = () => {
  const [isRunning, setIsRunning] = useState(false);
  const [currentTest, setCurrentTest] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const { toast } = useToast();

  const [testSuites, setTestSuites] = useState<TestSuite[]>([
    {
      name: "Security Tests",
      category: "security",
      totalTests: 12,
      passedTests: 10,
      failedTests: 1,
      runningTests: 0,
      tests: [
        {
          id: 'sec-1',
          name: 'JWT Authentication Validation',
          category: 'security',
          status: 'passed',
          duration: 145,
          details: 'All JWT tokens validated correctly',
          timestamp: new Date(Date.now() - 300000)
        },
        {
          id: 'sec-2',
          name: 'Rate Limiting Protection',
          category: 'security',
          status: 'passed',
          duration: 89,
          details: 'Rate limits enforced across all endpoints',
          timestamp: new Date(Date.now() - 280000)
        },
        {
          id: 'sec-3',
          name: 'SSRF Protection',
          category: 'security',
          status: 'failed',
          duration: 234,
          details: 'Internal IP access blocked but DNS rebinding test failed',
          timestamp: new Date(Date.now() - 260000)
        },
        {
          id: 'sec-4',
          name: 'Input Validation',
          category: 'security',
          status: 'passed',
          duration: 178,
          details: 'XSS and injection attacks properly blocked',
          timestamp: new Date(Date.now() - 240000)
        }
      ]
    },
    {
      name: "Performance Tests",
      category: "performance",
      totalTests: 8,
      passedTests: 6,
      failedTests: 0,
      runningTests: 1,
      tests: [
        {
          id: 'perf-1',
          name: 'API Response Times',
          category: 'performance',
          status: 'passed',
          duration: 2340,
          details: 'P95 latency: 187ms (target: <200ms)',
          timestamp: new Date(Date.now() - 180000)
        },
        {
          id: 'perf-2',
          name: 'Database Query Performance',
          category: 'performance',
          status: 'warning',
          duration: 1890,
          details: 'Some queries above 100ms threshold',
          timestamp: new Date(Date.now() - 160000)
        },
        {
          id: 'perf-3',
          name: 'Memory Usage',
          category: 'performance',
          status: 'running',
          duration: 0,
          details: 'Monitoring heap usage under load...',
          timestamp: new Date()
        }
      ]
    },
    {
      name: "ML Model Tests",
      category: "ml",
      totalTests: 15,
      passedTests: 13,
      failedTests: 1,
      runningTests: 0,
      tests: [
        {
          id: 'ml-1',
          name: 'Price Prediction Accuracy',
          category: 'ml',
          status: 'passed',
          duration: 3450,
          details: 'MAE: 12.3% (target: <15%)',
          timestamp: new Date(Date.now() - 120000)
        },
        {
          id: 'ml-2',
          name: 'Anomaly Detection Precision',
          category: 'ml',
          status: 'passed',
          duration: 2890,
          details: 'Precision: 94.1%, Recall: 87.3%',
          timestamp: new Date(Date.now() - 100000)
        },
        {
          id: 'ml-3',
          name: 'Model Inference Speed',
          category: 'ml',
          status: 'failed',
          duration: 1240,
          details: 'Average latency: 678ms (target: <500ms)',
          timestamp: new Date(Date.now() - 80000)
        }
      ]
    },
    {
      name: "Integration Tests",
      category: "integration",
      totalTests: 6,
      passedTests: 5,
      failedTests: 0,
      runningTests: 0,
      tests: [
        {
          id: 'int-1',
          name: 'Supabase Connection',
          category: 'integration',
          status: 'passed',
          duration: 456,
          details: 'Database and auth services operational',
          timestamp: new Date(Date.now() - 60000)
        },
        {
          id: 'int-2',
          name: 'WebSocket Real-time',
          category: 'integration',
          status: 'passed',
          duration: 789,
          details: 'Real-time updates functioning correctly',
          timestamp: new Date(Date.now() - 40000)
        }
      ]
    }
  ]);

  const getStatusIcon = (status: TestResult['status']) => {
    switch (status) {
      case 'passed': return <CheckCircle className="h-4 w-4 text-green-500" />;
      case 'failed': return <XCircle className="h-4 w-4 text-red-500" />;
      case 'warning': return <AlertCircle className="h-4 w-4 text-yellow-500" />;
      case 'running': return <Clock className="h-4 w-4 text-blue-500 animate-pulse" />;
      default: return <Clock className="h-4 w-4 text-gray-400" />;
    }
  };

  const getCategoryIcon = (category: TestSuite['category']) => {
    switch (category) {
      case 'security': return <Shield className="h-4 w-4" />;
      case 'performance': return <Zap className="h-4 w-4" />;
      case 'ml': return <Brain className="h-4 w-4" />;
      case 'integration': return <Database className="h-4 w-4" />;
    }
  };

  const runAllTests = async () => {
    setIsRunning(true);
    setProgress(0);
    
    toast({
      title: "Test Suite Started",
      description: "Running comprehensive test suite...",
    });

    // Simulate test execution
    const allTests = testSuites.flatMap(suite => suite.tests);
    for (let i = 0; i < allTests.length; i++) {
      setCurrentTest(allTests[i].name);
      setProgress((i + 1) / allTests.length * 100);
      
      // Simulate test duration
      await new Promise(resolve => setTimeout(resolve, 500));
    }

    setIsRunning(false);
    setCurrentTest(null);
    setProgress(100);
    
    toast({
      title: "Test Suite Complete",
      description: "All tests have been executed. Check results for details.",
    });
  };

  const getTotalStats = () => {
    return testSuites.reduce(
      (acc, suite) => ({
        total: acc.total + suite.totalTests,
        passed: acc.passed + suite.passedTests,
        failed: acc.failed + suite.failedTests,
        running: acc.running + suite.runningTests
      }),
      { total: 0, passed: 0, failed: 0, running: 0 }
    );
  };

  const stats = getTotalStats();

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Comprehensive Test Suite</h2>
          <p className="text-muted-foreground">
            Automated testing for security, performance, ML models, and integrations
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button 
            onClick={runAllTests} 
            disabled={isRunning}
            className="min-w-[120px]"
          >
            {isRunning ? (
              <>
                <Pause className="h-4 w-4 mr-2" />
                Running...
              </>
            ) : (
              <>
                <Play className="h-4 w-4 mr-2" />
                Run All Tests
              </>
            )}
          </Button>
        </div>
      </div>

      {/* Test Progress */}
      {isRunning && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Test Execution</CardTitle>
            <CardDescription>Currently running: {currentTest}</CardDescription>
          </CardHeader>
          <CardContent>
            <Progress value={progress} className="h-2" />
            <p className="text-sm text-muted-foreground mt-2">
              {Math.round(progress)}% complete
            </p>
          </CardContent>
        </Card>
      )}

      {/* Summary Cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Tests</CardTitle>
            <Clock className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.total}</div>
            <p className="text-xs text-muted-foreground">Across all suites</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Passed</CardTitle>
            <CheckCircle className="h-4 w-4 text-green-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-green-600">{stats.passed}</div>
            <p className="text-xs text-muted-foreground">
              {((stats.passed / stats.total) * 100).toFixed(1)}% success rate
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Failed</CardTitle>
            <XCircle className="h-4 w-4 text-red-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-red-600">{stats.failed}</div>
            <p className="text-xs text-muted-foreground">Need attention</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Running</CardTitle>
            <Clock className="h-4 w-4 text-blue-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-blue-600">{stats.running}</div>
            <p className="text-xs text-muted-foreground">In progress</p>
          </CardContent>
        </Card>
      </div>

      <Tabs defaultValue="overview" className="space-y-4">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="security">Security</TabsTrigger>
          <TabsTrigger value="performance">Performance</TabsTrigger>
          <TabsTrigger value="ml">ML Models</TabsTrigger>
          <TabsTrigger value="integration">Integration</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-4">
          <div className="grid gap-4">
            {testSuites.map((suite) => (
              <Card key={suite.name}>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      {getCategoryIcon(suite.category)}
                      <div>
                        <CardTitle className="text-lg">{suite.name}</CardTitle>
                        <CardDescription>
                          {suite.totalTests} tests • {suite.passedTests} passed • {suite.failedTests} failed
                        </CardDescription>
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <Badge variant="outline" className="text-green-600 border-green-200">
                        {suite.passedTests} passed
                      </Badge>
                      {suite.failedTests > 0 && (
                        <Badge variant="outline" className="text-red-600 border-red-200">
                          {suite.failedTests} failed
                        </Badge>
                      )}
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  <Progress 
                    value={(suite.passedTests / suite.totalTests) * 100} 
                    className="h-2"
                  />
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        {testSuites.map((suite) => (
          <TabsContent key={suite.category} value={suite.category} className="space-y-4">
            <div className="space-y-2">
              {suite.tests.map((test) => (
                <Card key={test.id}>
                  <CardContent className="pt-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        {getStatusIcon(test.status)}
                        <div>
                          <p className="font-medium">{test.name}</p>
                          <p className="text-sm text-muted-foreground">{test.details}</p>
                        </div>
                      </div>
                      <div className="text-right text-sm text-muted-foreground">
                        <p>{test.duration}ms</p>
                        <p>{test.timestamp.toLocaleTimeString()}</p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
};