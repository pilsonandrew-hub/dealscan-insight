import { useState, useCallback } from 'react'
import { supabase } from '@/integrations/supabase/client'
import { toast } from 'sonner'
import type { PublicListing, ScrapingResult, SiteName } from '@/types/scraper'

interface UseVehicleScraperReturn {
  listings: PublicListing[]
  isLoading: boolean
  isScraping: boolean
  startScraping: (sites: SiteName[]) => Promise<void>
  fetchListings: (limit?: number) => Promise<void>
  refreshListings: () => Promise<void>
  clearListings: () => void
}

export const useVehicleScraper = (): UseVehicleScraperReturn => {
  const [listings, setListings] = useState<PublicListing[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [isScraping, setIsScraping] = useState(false)

  const fetchListings = useCallback(async (limit = 50) => {
    setIsLoading(true)
    try {
      // Use GET request with query parameters instead of body
      const { data, error } = await supabase.functions.invoke(`vehicle-scraper?limit=${limit}`, {
        method: 'GET'
      })

      if (error) {
        toast.error('Failed to fetch listings: ' + error.message)
        return
      }

      if (data?.listings) {
        setListings(data.listings)
        toast.success(`Loaded ${data.listings.length} vehicle listings`)
      }
    } catch (error) {
      console.error('Error fetching listings:', error)
      toast.error('Failed to fetch vehicle listings')
    } finally {
      setIsLoading(false)
    }
  }, [])

  const startScraping = useCallback(async (sites: SiteName[]) => {
    setIsScraping(true)
    try {
      toast.info(`Starting scraping for ${sites.length} sites...`, {
        description: sites.join(', ')
      })

      const { data, error } = await supabase.functions.invoke('vehicle-scraper', {
        body: {
          action: 'start_scraping',
          sites
        }
      })

      if (error) {
        toast.error('Scraping failed: ' + error.message)
        return
      }

      const result: ScrapingResult = data.result
      toast.success(`Scraping completed!`, {
        description: `Found ${result.total_scraped} vehicles from ${result.sites_processed.join(', ')}`
      })

      // Refresh listings to show new data
      await fetchListings()
    } catch (error) {
      console.error('Error starting scraping:', error)
      toast.error('Failed to start scraping process')
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
    startScraping,
    fetchListings,
    refreshListings,
    clearListings
  }
}