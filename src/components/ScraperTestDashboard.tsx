import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { toast } from 'sonner'
import { ScraperTester } from '@/utils/scraperTester'
import { CheckCircle, XCircle, Clock, Target } from 'lucide-react'

interface ScrapingTestResult {
  siteId: string
  siteName: string
  success: boolean
  error?: string
  vehiclesFound?: number
  responseTime?: number
}

export const ScraperTestDashboard = () => {
  const [testResults, setTestResults] = useState<ScrapingTestResult[]>([])
  const [isRunning, setIsRunning] = useState(false)
  const [currentSite, setCurrentSite] = useState<string>('')
  const [progress, setProgress] = useState(0)

  const runIndividualTest = async (siteId: string) => {
    setIsRunning(true)
    setCurrentSite(siteId)
    
    try {
      const result = await ScraperTester.testIndividualSite(siteId)
      
      // Update results
      setTestResults(prev => {
        const filtered = prev.filter(r => r.siteId !== siteId)
        return [...filtered, result].sort((a, b) => a.siteName.localeCompare(b.siteName))
      })

      if (result.success) {
        toast.success(`✅ ${result.siteName} test passed`, {
          description: `Found ${result.vehiclesFound} vehicles in ${result.responseTime}ms`
        })
      } else {
        toast.error(`❌ ${result.siteName} test failed`, {
          description: result.error
        })
      }
    } catch (error) {
      toast.error('Test failed', {
        description: error instanceof Error ? error.message : 'Unknown error'
      })
    } finally {
      setIsRunning(false)
      setCurrentSite('')
    }
  }

  const runAllTests = async () => {
    setIsRunning(true)
    setTestResults([])
    setProgress(0)
    
    try {
      toast.info('Starting comprehensive scraper test...', {
        description: 'Testing all configured auction sites'
      })

      const results = await ScraperTester.testAllSites()
      setTestResults(results)
      setProgress(100)

      const summary = ScraperTester.getTestSummary(results)
      
      toast.success(`Tests completed: ${summary.successRate}% success rate`, {
        description: `${summary.successful}/${summary.total} sites working, found ${summary.totalVehicles} total vehicles`
      })
    } catch (error) {
      toast.error('Test suite failed', {
        description: error instanceof Error ? error.message : 'Unknown error'
      })
    } finally {
      setIsRunning(false)
      setProgress(0)
    }
  }

  const summary = testResults.length > 0 ? ScraperTester.getTestSummary(testResults) : null

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Scraper Test Dashboard</h2>
          <p className="text-muted-foreground">Verify auction site scraping functionality</p>
        </div>
        <div className="flex gap-2">
          <Button 
            onClick={runAllTests} 
            disabled={isRunning}
            variant="default"
          >
            {isRunning ? 'Testing...' : 'Test All Sites'}
          </Button>
        </div>
      </div>

      {isRunning && progress > 0 && (
        <Card>
          <CardContent className="pt-4">
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span>Testing Progress</span>
                <span>{progress}%</span>
              </div>
              <Progress value={progress} />
              {currentSite && (
                <p className="text-sm text-muted-foreground">
                  Currently testing: {currentSite}
                </p>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {summary && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Card>
            <CardContent className="flex items-center space-x-2 p-4">
              <Target className="h-4 w-4 text-blue-500" />
              <div>
                <p className="text-sm text-muted-foreground">Total Sites</p>
                <p className="text-2xl font-bold">{summary.total}</p>
              </div>
            </CardContent>
          </Card>
          
          <Card>
            <CardContent className="flex items-center space-x-2 p-4">
              <CheckCircle className="h-4 w-4 text-green-500" />
              <div>
                <p className="text-sm text-muted-foreground">Success Rate</p>
                <p className="text-2xl font-bold">{summary.successRate}%</p>
              </div>
            </CardContent>
          </Card>
          
          <Card>
            <CardContent className="flex items-center space-x-2 p-4">
              <Target className="h-4 w-4 text-purple-500" />
              <div>
                <p className="text-sm text-muted-foreground">Vehicles Found</p>
                <p className="text-2xl font-bold">{summary.totalVehicles}</p>
              </div>
            </CardContent>
          </Card>
          
          <Card>
            <CardContent className="flex items-center space-x-2 p-4">
              <Clock className="h-4 w-4 text-orange-500" />
              <div>
                <p className="text-sm text-muted-foreground">Avg Response</p>
                <p className="text-2xl font-bold">{summary.avgResponseTime}ms</p>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {testResults.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Test Results</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {testResults.map((result) => (
                <div
                  key={result.siteId}
                  className="flex items-center justify-between p-3 border rounded-lg"
                >
                  <div className="flex items-center space-x-3">
                    {result.success ? (
                      <CheckCircle className="h-5 w-5 text-green-500" />
                    ) : (
                      <XCircle className="h-5 w-5 text-red-500" />
                    )}
                    <div>
                      <p className="font-medium">{result.siteName}</p>
                      <p className="text-sm text-muted-foreground">
                        {result.success 
                          ? `Found ${result.vehiclesFound} vehicles in ${result.responseTime}ms`
                          : result.error
                        }
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center space-x-2">
                    <Badge variant={result.success ? 'default' : 'destructive'}>
                      {result.success ? 'Pass' : 'Fail'}
                    </Badge>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => runIndividualTest(result.siteId)}
                      disabled={isRunning}
                    >
                      Retest
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}