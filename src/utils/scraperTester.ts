import { supabase } from '@/integrations/supabase/client'

interface ScrapingTestResult {
  siteId: string
  siteName: string
  success: boolean
  error?: string
  vehiclesFound?: number
  responseTime?: number
}

export class ScraperTester {
  /**
   * Test scraping functionality for individual sites
   */
  static async testIndividualSite(siteId: string): Promise<ScrapingTestResult> {
    const startTime = Date.now()
    
    try {
      // Get auth session
      const { data: { session } } = await supabase.auth.getSession()
      
      if (!session) {
        throw new Error('Authentication required')
      }

      // Get site details
      const { data: site, error: siteError } = await supabase
        .from('scraper_sites')
        .select('*')
        .eq('id', siteId)
        .single()

      if (siteError || !site) {
        throw new Error(`Site not found: ${siteId}`)
      }

      console.log(`Testing scraper for site: ${site.name} (${site.base_url})`)

      // Test using the scrape-coordinator function
      const { data, error } = await supabase.functions.invoke('scrape-coordinator', {
        body: {
          jobId: `test-${siteId}-${Date.now()}`,
          sites: [{
            id: site.id,
            name: site.name,
            baseUrl: site.base_url,
            category: site.category
          }],
          mode: 'demo' // Use demo mode for testing
        },
        headers: {
          Authorization: `Bearer ${session.access_token}`
        }
      })

      const responseTime = Date.now() - startTime

      if (error) {
        return {
          siteId,
          siteName: site.name,
          success: false,
          error: error.message,
          responseTime
        }
      }

      return {
        siteId,
        siteName: site.name,
        success: data.success || false,
        vehiclesFound: data.totalVehicles || 0,
        responseTime
      }

    } catch (error) {
      return {
        siteId,
        siteName: 'Unknown',
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error',
        responseTime: Date.now() - startTime
      }
    }
  }

  /**
   * Test all configured scraper sites
   */
  static async testAllSites(): Promise<ScrapingTestResult[]> {
    try {
      // Get all enabled sites
      const { data: sites, error } = await supabase
        .from('scraper_sites')
        .select('id, name')
        .eq('enabled', true)
        .order('name')

      if (error || !sites) {
        throw new Error('Failed to fetch scraper sites')
      }

      console.log(`Testing ${sites.length} scraper sites...`)

      // Test each site individually with some delay between tests
      const results: ScrapingTestResult[] = []
      
      for (const site of sites) {
        const result = await this.testIndividualSite(site.id)
        results.push(result)
        
        // Brief delay between tests to avoid overwhelming servers
        await new Promise(resolve => setTimeout(resolve, 1000))
      }

      return results
    } catch (error) {
      console.error('Error testing all sites:', error)
      return []
    }
  }

  /**
   * Get summary statistics from test results
   */
  static getTestSummary(results: ScrapingTestResult[]) {
    const total = results.length
    const successful = results.filter(r => r.success).length
    const failed = results.filter(r => !r.success).length
    const totalVehicles = results.reduce((sum, r) => sum + (r.vehiclesFound || 0), 0)
    const avgResponseTime = results.reduce((sum, r) => sum + (r.responseTime || 0), 0) / total

    return {
      total,
      successful,
      failed,
      successRate: ((successful / total) * 100).toFixed(1),
      totalVehicles,
      avgResponseTime: Math.round(avgResponseTime)
    }
  }
}