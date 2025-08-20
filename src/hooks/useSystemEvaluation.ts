/**
 * Hook for running system evaluations
 * Integrates the system tester with React components
 */

import { useState, useCallback } from 'react';
import { systemTester, type EvaluationReport, type TestResult } from '@/utils/system-tester';
import { useToast } from '@/hooks/use-toast';

export function useSystemEvaluation() {
  const [isRunning, setIsRunning] = useState(false);
  const [lastReport, setLastReport] = useState<EvaluationReport | null>(null);
  const [progress, setProgress] = useState<{ current: number; total: number; currentTest: string }>({
    current: 0,
    total: 0,
    currentTest: ''
  });
  const { toast } = useToast();

  const runEvaluation = useCallback(async () => {
    if (isRunning) return;

    setIsRunning(true);
    setProgress({ current: 0, total: 10, currentTest: 'Starting evaluation...' });

    try {
      toast({
        title: "System Evaluation Started",
        description: "Running comprehensive system tests...",
      });

      // Simulate progress updates
      const progressSteps = [
        'Testing frontend basics...',
        'Checking API endpoints...',
        'Measuring performance...',
        'Testing error handling...',
        'Verifying caching system...',
        'Checking security features...',
        'Generating metrics...',
        'Compiling results...',
        'Creating report...',
        'Finalizing evaluation...'
      ];

      for (let i = 0; i < progressSteps.length; i++) {
        setProgress({ current: i + 1, total: progressSteps.length, currentTest: progressSteps[i] });
        await new Promise(resolve => setTimeout(resolve, 200)); // Small delay for UX
      }

      const report = await systemTester.runFullEvaluation();
      setLastReport(report);

      // Show results toast
      const grade = report.summary.grade;
      const score = report.summary.score_pct;
      
      toast({
        title: `Evaluation Complete - Grade ${grade}`,
        description: `System scored ${score}% (${report.summary.passed}/${report.summary.total} tests passed)`,
        variant: grade === 'A' ? 'default' : grade === 'F' ? 'destructive' : 'default',
      });

    } catch (error) {
      console.error('Evaluation failed:', error);
      toast({
        title: "Evaluation Failed",
        description: "An error occurred during system evaluation",
        variant: "destructive",
      });
    } finally {
      setIsRunning(false);
      setProgress({ current: 0, total: 0, currentTest: '' });
    }
  }, [isRunning, toast]);

  const downloadReport = useCallback(() => {
    if (!lastReport) return;

    try {
      // Generate HTML report
      const htmlContent = systemTester.generateHTMLReport(lastReport);
      
      // Create blob and download
      const blob = new Blob([htmlContent], { type: 'text/html' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `dealerscope-evaluation-${new Date().toISOString().split('T')[0]}.html`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);

      toast({
        title: "Report Downloaded",
        description: "HTML evaluation report has been downloaded",
      });
    } catch (error) {
      toast({
        title: "Download Failed",
        description: "Could not download evaluation report",
        variant: "destructive",
      });
    }
  }, [lastReport, toast]);

  const downloadJSON = useCallback(() => {
    if (!lastReport) return;

    try {
      const jsonContent = JSON.stringify(lastReport, null, 2);
      const blob = new Blob([jsonContent], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `dealerscope-evaluation-${new Date().toISOString().split('T')[0]}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);

      toast({
        title: "JSON Report Downloaded",
        description: "JSON evaluation data has been downloaded",
      });
    } catch (error) {
      toast({
        title: "Download Failed",
        description: "Could not download JSON report",
        variant: "destructive",
      });
    }
  }, [lastReport, toast]);

  return {
    isRunning,
    progress,
    lastReport,
    runEvaluation,
    downloadReport,
    downloadJSON,
    hasReport: !!lastReport
  };
}