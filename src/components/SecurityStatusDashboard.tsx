/**
 * Security Status Dashboard - Phase 4 Production Monitoring
 * Real-time security system monitoring and metrics
 */

import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Progress } from '@/components/ui/progress';
import { useSecurityStatus, securityOrchestrator } from '@/middleware/SecurityMiddlewareIntegration';
import { getSecurityMetrics } from '@/utils/intrusionDetection';
import { Shield, AlertTriangle, CheckCircle, XCircle, Activity, Clock } from 'lucide-react';

interface SecurityMetrics {
  totalThreats: number;
  threatsByType: Record<string, number>;
  threatsBySeverity: Record<string, number>;
  topAttackers: Array<{ ip: string; count: number }>;
}

export const SecurityStatusDashboard: React.FC = () => {
  const securityStatus = useSecurityStatus();
  const [metrics, setMetrics] = useState<SecurityMetrics | null>(null);
  const [healthCheck, setHealthCheck] = useState<{
    healthy: boolean;
    issues: string[];
    recommendations: string[];
  } | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date());

  useEffect(() => {
    const updateMetrics = async () => {
      try {
        // Get security metrics from last 24 hours
        const securityMetrics = getSecurityMetrics(24 * 60 * 60 * 1000);
        setMetrics(securityMetrics);

        // Perform health check
        const health = await securityOrchestrator.performSecurityHealthCheck();
        setHealthCheck(health);

        setLastUpdate(new Date());
      } catch (error) {
        console.error('Failed to update security metrics:', error);
      }
    };

    updateMetrics();
    const interval = setInterval(updateMetrics, 30000); // Update every 30 seconds

    return () => clearInterval(interval);
  }, []);

  const getSecurityScoreColor = (score: number) => {
    if (score >= 90) return 'text-green-600';
    if (score >= 75) return 'text-yellow-600';
    return 'text-red-600';
  };

  const getSecurityScoreVariant = (score: number): "default" | "secondary" | "destructive" | "outline" => {
    if (score >= 90) return 'default';
    if (score >= 75) return 'secondary';
    return 'destructive';
  };

  if (!securityStatus) {
    return (
      <div className="p-6 space-y-4">
        <div className="animate-pulse">
          <div className="h-8 bg-gray-200 rounded w-1/3 mb-4"></div>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="h-24 bg-gray-200 rounded"></div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">Security Dashboard</h2>
          <p className="text-muted-foreground">
            Real-time security monitoring and threat detection
          </p>
        </div>
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Clock className="h-4 w-4" />
          Last updated: {lastUpdate.toLocaleTimeString()}
        </div>
      </div>

      {/* Overall Security Score */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            Overall Security Score
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between">
            <div>
              <div className={`text-4xl font-bold ${getSecurityScoreColor(securityStatus.overallSecurityScore)}`}>
                {securityStatus.overallSecurityScore}%
              </div>
              <Badge variant={getSecurityScoreVariant(securityStatus.overallSecurityScore)}>
                {securityStatus.overallSecurityScore >= 90 ? 'Excellent' : 
                 securityStatus.overallSecurityScore >= 75 ? 'Good' : 'Needs Attention'}
              </Badge>
            </div>
            <Progress 
              value={securityStatus.overallSecurityScore} 
              className="w-32"
            />
          </div>
        </CardContent>
      </Card>

      {/* Security Components Status */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Security Headers</CardTitle>
            {securityStatus.headersActive ? 
              <CheckCircle className="h-4 w-4 text-green-600" /> : 
              <XCircle className="h-4 w-4 text-red-600" />
            }
          </CardHeader>
          <CardContent>
            <Badge variant={securityStatus.headersActive ? 'default' : 'destructive'}>
              {securityStatus.headersActive ? 'Active' : 'Inactive'}
            </Badge>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Intrusion Detection</CardTitle>
            {securityStatus.intrusionDetectionActive ? 
              <CheckCircle className="h-4 w-4 text-green-600" /> : 
              <XCircle className="h-4 w-4 text-red-600" />
            }
          </CardHeader>
          <CardContent>
            <Badge variant={securityStatus.intrusionDetectionActive ? 'default' : 'destructive'}>
              {securityStatus.intrusionDetectionActive ? 'Monitoring' : 'Offline'}
            </Badge>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Upload Security</CardTitle>
            {securityStatus.uploadHardeningActive ? 
              <CheckCircle className="h-4 w-4 text-green-600" /> : 
              <XCircle className="h-4 w-4 text-red-600" />
            }
          </CardHeader>
          <CardContent>
            <Badge variant={securityStatus.uploadHardeningActive ? 'default' : 'destructive'}>
              {securityStatus.uploadHardeningActive ? 'Protected' : 'Vulnerable'}
            </Badge>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Rate Limiting</CardTitle>
            {securityStatus.rateLimitingActive ? 
              <CheckCircle className="h-4 w-4 text-green-600" /> : 
              <XCircle className="h-4 w-4 text-red-600" />
            }
          </CardHeader>
          <CardContent>
            <Badge variant={securityStatus.rateLimitingActive ? 'default' : 'destructive'}>
              {securityStatus.rateLimitingActive ? 'Active' : 'Disabled'}
            </Badge>
          </CardContent>
        </Card>
      </div>

      {/* Health Check Results */}
      {healthCheck && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Activity className="h-5 w-5" />
              Security Health Check
            </CardTitle>
          </CardHeader>
          <CardContent>
            {healthCheck.healthy ? (
              <Alert>
                <CheckCircle className="h-4 w-4" />
                <AlertTitle>All Systems Operational</AlertTitle>
                <AlertDescription>
                  Security systems are functioning normally with no detected issues.
                </AlertDescription>
              </Alert>
            ) : (
              <div className="space-y-4">
                <Alert variant="destructive">
                  <AlertTriangle className="h-4 w-4" />
                  <AlertTitle>Security Issues Detected</AlertTitle>
                  <AlertDescription>
                    {healthCheck.issues.length} issue(s) require attention.
                  </AlertDescription>
                </Alert>
                
                <div className="space-y-2">
                  <h4 className="font-semibold">Issues:</h4>
                  {healthCheck.issues.map((issue, index) => (
                    <div key={index} className="text-sm text-red-600">• {issue}</div>
                  ))}
                </div>
                
                <div className="space-y-2">
                  <h4 className="font-semibold">Recommendations:</h4>
                  {healthCheck.recommendations.map((rec, index) => (
                    <div key={index} className="text-sm text-muted-foreground">• {rec}</div>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Threat Metrics */}
      {metrics && (
        <div className="grid gap-4 md:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Threat Statistics (24h)</CardTitle>
              <CardDescription>Security threats detected in the last 24 hours</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <div>
                  <div className="text-2xl font-bold">{metrics.totalThreats}</div>
                  <div className="text-sm text-muted-foreground">Total Threats Detected</div>
                </div>
                
                {Object.entries(metrics.threatsBySeverity).length > 0 && (
                  <div>
                    <h4 className="font-semibold mb-2">By Severity</h4>
                    {Object.entries(metrics.threatsBySeverity).map(([severity, count]) => (
                      <div key={severity} className="flex justify-between text-sm">
                        <span className="capitalize">{severity}</span>
                        <span>{count}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Top Threat Types</CardTitle>
              <CardDescription>Most common security threats</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {Object.entries(metrics.threatsByType)
                  .sort(([,a], [,b]) => b - a)
                  .slice(0, 5)
                  .map(([type, count]) => (
                    <div key={type} className="flex justify-between text-sm">
                      <span className="capitalize">{type.replace(/_/g, ' ')}</span>
                      <Badge variant="outline">{count}</Badge>
                    </div>
                  ))}
                {Object.keys(metrics.threatsByType).length === 0 && (
                  <div className="text-sm text-muted-foreground">No threats detected</div>
                )}
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
};