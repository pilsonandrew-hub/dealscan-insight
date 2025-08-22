import { useState, useCallback } from 'react'
import { supabase } from '@/integrations/supabase/client'
import { toast } from 'sonner'
import type { PublicListing, ScrapingResult, SiteName } from '@/types/scraper'

interface UseVehicleScraperReturn {
  listings: PublicListing[]
  isLoading: boolean
  isScraping: boolean
  error: string | null
  startScraping: (sites: SiteName[]) => Promise<void>
  fetchListings: (limit?: number) => Promise<void>
  refreshListings: () => Promise<void>
  clearListings: () => void
}

export const useVehicleScraper = (): UseVehicleScraperReturn => {
  const [listings, setListings] = useState<PublicListing[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [isScraping, setIsScraping] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchListings = useCallback(async (limit = 50) => {
    setIsLoading(true)
    setError(null)
    
    try {
      // Get auth session for proper authentication
      const { data: { session } } = await supabase.auth.getSession()
      
      if (!session) {
        throw new Error('Authentication required. Please log in.')
      }

      const { data, error } = await supabase.functions.invoke('vehicle-scraper', {
        method: 'POST',
        body: {
          action: 'get_listings',
          limit
        },
        headers: {
          Authorization: `Bearer ${session.access_token}`
        }
      })

      if (error) {
        const errorMessage = error.message || 'Failed to fetch listings'
        setError(errorMessage)
        toast.error(errorMessage)
        return
      }

      if (data?.listings) {
        setListings(data.listings)
        toast.success(`Loaded ${data.listings.length} vehicle listings`)
      } else {
        setListings([])
        toast.info('No listings found')
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to fetch vehicle listings'
      console.error('Error fetching listings:', error)
      setError(errorMessage)
      toast.error(errorMessage)
    } finally {
      setIsLoading(false)
    }
  }, [])

  const startScraping = useCallback(async (sites: SiteName[]) => {
    setIsScraping(true)
    setError(null)
    
    try {
      // Get auth session for proper authentication
      const { data: { session } } = await supabase.auth.getSession()
      
      if (!session) {
        throw new Error('Authentication required. Please log in.')
      }

      toast.info(`Starting scraping for ${sites.length} sites...`, {
        description: sites.join(', ')
      })

      const { data, error } = await supabase.functions.invoke('vehicle-scraper', {
        method: 'POST',
        body: {
          action: 'start_scraping',
          sites
        },
        headers: {
          Authorization: `Bearer ${session.access_token}`
        }
      })

      if (error) {
        const errorMessage = error.message || 'Scraping failed'
        setError(errorMessage)
        toast.error(errorMessage)
        return
      }

      const result: ScrapingResult = data.result
      
      // Show detailed results if available
      if (data.result.results) {
        const successfulSites = data.result.results.filter((r: any) => !r.error)
        const failedSites = data.result.results.filter((r: any) => r.error)
        
        if (successfulSites.length > 0) {
          toast.success(`Scraping completed!`, {
            description: `Found ${result.total_scraped} vehicles from ${successfulSites.length} sites`
          })
        }
        
        if (failedSites.length > 0) {
          toast.warning(`Some sites failed`, {
            description: `${failedSites.length} sites encountered errors`
          })
        }
      } else {
        toast.success(`Scraping completed!`, {
          description: `Found ${result.total_scraped} vehicles from ${result.sites_processed.join(', ')}`
        })
      }

      // Refresh listings to show new data
      setTimeout(() => fetchListings(), 2000) // Brief delay to ensure data is saved
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to start scraping process'
      console.error('Error starting scraping:', error)
      setError(errorMessage)
      toast.error(errorMessage)
    } finally {
      setIsScraping(false)
    }
  }, [fetchListings])

  const refreshListings = useCallback(async () => {
    await fetchListings()
  }, [fetchListings])

  const clearListings = useCallback(() => {
    setListings([])
  }, [])

  return {
    listings,
    isLoading,
    isScraping,
    error,
    startScraping,
    fetchListings,
    refreshListings,
    clearListings
  }
}