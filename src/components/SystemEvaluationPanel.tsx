/**
 * System Evaluation Panel Component
 * Provides UI for running and viewing system evaluations
 */

import React from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { 
  Play, 
  Download, 
  FileText, 
  BarChart3,
  CheckCircle,
  AlertCircle,
  XCircle,
  Clock,
  Zap,
  Shield
} from 'lucide-react';
import { useSystemEvaluation } from '@/hooks/useSystemEvaluation';
import { cn } from '@/lib/utils';

export function SystemEvaluationPanel() {
  const {
    isRunning,
    progress,
    lastReport,
    runEvaluation,
    downloadReport,
    downloadJSON,
    hasReport
  } = useSystemEvaluation();

  const getGradeColor = (grade: string) => {
    switch (grade) {
      case 'A': return 'bg-success text-success-foreground';
      case 'B': return 'bg-info text-info-foreground';
      case 'C': return 'bg-warning text-warning-foreground';
      case 'D': return 'bg-warning text-warning-foreground';
      case 'F': return 'bg-destructive text-destructive-foreground';
      default: return 'bg-muted text-muted-foreground';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'pass': return <CheckCircle className="w-4 h-4 text-success" />;
      case 'warn': return <AlertCircle className="w-4 h-4 text-warning" />;
      case 'fail': return <XCircle className="w-4 h-4 text-destructive" />;
      default: return <Clock className="w-4 h-4 text-muted-foreground" />;
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">System Evaluation</h2>
          <p className="text-muted-foreground">Comprehensive testing and performance analysis</p>
        </div>
        <div className="flex gap-2">
          <Button
            onClick={runEvaluation}
            disabled={isRunning}
            className="gap-2"
          >
            <Play className={cn("w-4 h-4", isRunning && "animate-pulse")} />
            {isRunning ? 'Running...' : 'Run Evaluation'}
          </Button>
          {hasReport && (
            <>
              <Button variant="outline" onClick={downloadReport} className="gap-2">
                <FileText className="w-4 h-4" />
                HTML Report
              </Button>
              <Button variant="outline" onClick={downloadJSON} className="gap-2">
                <Download className="w-4 h-4" />
                JSON Data
              </Button>
            </>
          )}
        </div>
      </div>

      {/* Progress */}
      {isRunning && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Zap className="w-5 h-5 animate-pulse" />
              Evaluation in Progress
            </CardTitle>
            <CardDescription>{progress.currentTest}</CardDescription>
          </CardHeader>
          <CardContent>
            <Progress 
              value={(progress.current / progress.total) * 100} 
              className="w-full"
            />
            <p className="text-sm text-muted-foreground mt-2">
              Step {progress.current} of {progress.total}
            </p>
          </CardContent>
        </Card>
      )}

      {/* Results Summary */}
      {lastReport && (
        <div className="grid gap-6 md:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <BarChart3 className="w-5 h-5" />
                Overall Score
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-4">
                <div className={cn(
                  "px-4 py-2 rounded-lg text-2xl font-bold",
                  getGradeColor(lastReport.summary.grade)
                )}>
                  {lastReport.summary.grade}
                </div>
                <div>
                  <div className="text-3xl font-bold">{lastReport.summary.score_pct}%</div>
                  <p className="text-sm text-muted-foreground">
                    {lastReport.summary.passed} of {lastReport.summary.total} tests passed
                  </p>
                </div>
              </div>
              
              <Separator className="my-4" />
              
              <div className="grid grid-cols-2 gap-4 text-center">
                <div>
                  <div className="text-2xl font-bold text-success">{lastReport.summary.passed}</div>
                  <p className="text-xs text-muted-foreground">Passed</p>
                </div>
                <div>
                  <div className="text-2xl font-bold text-destructive">{lastReport.summary.failed}</div>
                  <p className="text-xs text-muted-foreground">Failed</p>
                </div>
                <div>
                  <div className="text-2xl font-bold text-warning">{lastReport.summary.warned}</div>
                  <p className="text-xs text-muted-foreground">Warnings</p>
                </div>
                <div>
                  <div className="text-2xl font-bold text-muted-foreground">{lastReport.summary.skipped}</div>
                  <p className="text-xs text-muted-foreground">Skipped</p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Shield className="w-5 h-5" />
                Key Metrics
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex justify-between items-center">
                <span className="text-sm font-medium">Avg Response Time</span>
                <Badge variant={lastReport.metrics.dashboard_avg_ms < 1000 ? 'default' : 'secondary'}>
                  {lastReport.metrics.dashboard_avg_ms}ms
                </Badge>
              </div>
              
              <div className="flex justify-between items-center">
                <span className="text-sm font-medium">Cache Hit Rate</span>
                <Badge variant="default">
                  {lastReport.metrics.cache_hit_rate || 0}%
                </Badge>
              </div>
              
              {lastReport.metrics.memory_usage && (
                <div className="flex justify-between items-center">
                  <span className="text-sm font-medium">Memory Usage</span>
                  <Badge variant={lastReport.metrics.memory_usage < 50 ? 'default' : 'secondary'}>
                    {lastReport.metrics.memory_usage}MB
                  </Badge>
                </div>
              )}

              <div className="flex justify-between items-center">
                <span className="text-sm font-medium">API Success Rate</span>
                <Badge variant="default">
                  {lastReport.metrics.api_success_rate || 'N/A'}%
                </Badge>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Detailed Results */}
      {lastReport && (
        <Card>
          <CardHeader>
            <CardTitle>Test Results</CardTitle>
            <CardDescription>
              Detailed results from {lastReport.tests.length} system tests
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {lastReport.tests.map((test, index) => (
                <div
                  key={index}
                  className="flex items-center justify-between p-3 border rounded-lg"
                >
                  <div className="flex items-center gap-3">
                    {getStatusIcon(test.status)}
                    <div>
                      <p className="font-medium">{test.name.replace(/-/g, ' ')}</p>
                      <p className="text-sm text-muted-foreground">{test.detail}</p>
                    </div>
                  </div>
                  <div className="text-right text-sm text-muted-foreground">
                    {test.duration && (
                      <p>{Math.round(test.duration)}ms</p>
                    )}
                    <p>{new Date(test.timestamp).toLocaleTimeString()}</p>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* No Results State */}
      {!hasReport && !isRunning && (
        <Card>
          <CardContent className="text-center py-12">
            <BarChart3 className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
            <h3 className="text-lg font-semibold mb-2">No Evaluation Results</h3>
            <p className="text-muted-foreground mb-4">
              Run a system evaluation to see comprehensive performance and security metrics.
            </p>
            <Button onClick={runEvaluation} className="gap-2">
              <Play className="w-4 h-4" />
              Run First Evaluation
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}