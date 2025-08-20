import { serve } from "https://deno.land/std@0.168.0/http/server.ts"
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
}

interface ScrapingRequest {
  action: 'start_scraping' | 'get_status' | 'get_listings'
  sites?: string[]
  limit?: number
}

interface VehicleListing {
  source_site: string
  listing_url: string
  auction_end?: string
  year?: number
  make?: string
  model?: string
  trim?: string
  mileage?: number
  current_bid?: number
  location?: string
  state?: string
  vin?: string
  photo_url?: string
  title_status?: string
  description?: string
  scrape_metadata?: Record<string, any>
}

const USER_AGENTS = [
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
  'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
]

class VehicleScraper {
  private supabase: any
  private rateLimitDelay = 3000 // 3 seconds
  
  constructor(supabaseUrl: string, supabaseKey: string) {
    this.supabase = createClient(supabaseUrl, supabaseKey)
  }

  private async delay(ms: number) {
    return new Promise(resolve => setTimeout(resolve, ms))
  }

  private getRandomUserAgent(): string {
    return USER_AGENTS[Math.floor(Math.random() * USER_AGENTS.length)]
  }

  private async fetchWithRetry(url: string, options: RequestInit = {}, maxRetries = 3): Promise<Response | null> {
    for (let i = 0; i < maxRetries; i++) {
      try {
        const response = await fetch(url, {
          ...options,
          headers: {
            'User-Agent': this.getRandomUserAgent(),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            ...options.headers
          }
        })
        
        if (response.ok) {
          return response
        } else if (response.status === 429) {
          console.log(`Rate limited on attempt ${i + 1}, waiting...`)
          await this.delay(this.rateLimitDelay * (i + 1))
          continue
        } else {
          console.log(`HTTP ${response.status} on attempt ${i + 1}`)
        }
      } catch (error) {
        console.error(`Fetch attempt ${i + 1} failed:`, error)
        if (i < maxRetries - 1) {
          await this.delay(1000 * (i + 1))
        }
      }
    }
    return null
  }

  private extractText(html: string, selector: string): string {
    // Basic text extraction - in production, you'd use a proper HTML parser
    const regex = new RegExp(`<[^>]*class[^>]*${selector}[^>]*>([^<]*)<`, 'i')
    const match = html.match(regex)
    return match ? match[1].trim() : ''
  }

  private parseVehicleData(html: string, url: string, siteName: string): VehicleListing | null {
    try {
      // This is a simplified parser - each site would need custom parsing logic
      const listing: VehicleListing = {
        source_site: siteName,
        listing_url: url,
        scrape_metadata: {
          scraped_at: new Date().toISOString(),
          html_length: html.length
        }
      }

      // Generic patterns for common vehicle data
      const patterns = {
        year: /(?:year|model year)[:\s]*(\d{4})/i,
        make: /(?:make|manufacturer)[:\s]*([a-zA-Z]+)/i,
        model: /(?:model)[:\s]*([a-zA-Z0-9\s]+)/i,
        mileage: /(?:mileage|miles)[:\s]*([0-9,]+)/i,
        current_bid: /(?:current bid|price)[:\s]*\$?([0-9,]+\.?\d*)/i,
        location: /(?:location|city)[:\s]*([a-zA-Z\s,]+)/i,
        vin: /(?:vin|vehicle identification)[:\s]*([a-zA-Z0-9]{17})/i
      }

      for (const [key, pattern] of Object.entries(patterns)) {
        const match = html.match(pattern)
        if (match) {
          let value: any = match[1].trim()
          
          if (key === 'year' || key === 'mileage') {
            value = parseInt(value.replace(/,/g, ''))
          } else if (key === 'current_bid') {
            value = parseFloat(value.replace(/,/g, ''))
          }
          
          listing[key as keyof VehicleListing] = value
        }
      }

      return listing
    } catch (error) {
      console.error('Error parsing vehicle data:', error)
      return null
    }
  }

  async scrapeGovDeals(): Promise<VehicleListing[]> {
    console.log('Starting GovDeals scraping...')
    const listings: VehicleListing[] = []
    
    try {
      const vehiclesUrl = 'https://www.govdeals.com/index.cfm?fa=Main.AdvSearchResultsNew&searchPg=Category&additionalParams=true&sortBy=ad&sortDir=ASC&kWord=&kWordSelect=2&catId=97&timing=ByDate&locationType=proximity&proximityType=city&kWordSelectLocation=2&locId=&categoryTypeId=1&timing=BySimple&timingSimple=0'
      
      const response = await this.fetchWithRetry(vehiclesUrl)
      if (!response) {
        console.error('Failed to fetch GovDeals vehicles page')
        return listings
      }

      const html = await response.text()
      console.log(`Fetched ${html.length} characters from GovDeals`)

      // Extract listing URLs (simplified - would need proper HTML parsing)
      const listingUrls = html.match(/href="[^"]*fa=Main\.Item[^"]*"/g) || []
      console.log(`Found ${listingUrls.length} potential listings`)

      for (let i = 0; i < Math.min(listingUrls.length, 10); i++) {
        const urlMatch = listingUrls[i].match(/href="([^"]*)"/)
        if (!urlMatch) continue

        const listingUrl = 'https://www.govdeals.com' + urlMatch[1].replace(/&amp;/g, '&')
        console.log(`Scraping listing ${i + 1}: ${listingUrl}`)

        await this.delay(this.rateLimitDelay)

        const listingResponse = await this.fetchWithRetry(listingUrl)
        if (!listingResponse) continue

        const listingHtml = await listingResponse.text()
        const listing = this.parseVehicleData(listingHtml, listingUrl, 'GovDeals')
        
        if (listing) {
          listings.push(listing)
        }
      }
    } catch (error) {
      console.error('Error scraping GovDeals:', error)
    }

    return listings
  }

  async scrapePublicSurplus(): Promise<VehicleListing[]> {
    console.log('Starting PublicSurplus scraping...')
    const listings: VehicleListing[] = []
    
    try {
      const vehiclesUrl = 'https://www.publicsurplus.com/sms/browse/category/catauctions?catid=13'
      
      const response = await this.fetchWithRetry(vehiclesUrl)
      if (!response) {
        console.error('Failed to fetch PublicSurplus vehicles page')
        return listings
      }

      const html = await response.text()
      console.log(`Fetched ${html.length} characters from PublicSurplus`)

      // Extract listing URLs (simplified)
      const listingUrls = html.match(/href="[^"]*\/auction\/[^"]*"/g) || []
      console.log(`Found ${listingUrls.length} potential listings`)

      for (let i = 0; i < Math.min(listingUrls.length, 10); i++) {
        const urlMatch = listingUrls[i].match(/href="([^"]*)"/)
        if (!urlMatch) continue

        const listingUrl = urlMatch[1].startsWith('http') ? urlMatch[1] : 'https://www.publicsurplus.com' + urlMatch[1]
        console.log(`Scraping listing ${i + 1}: ${listingUrl}`)

        await this.delay(this.rateLimitDelay)

        const listingResponse = await this.fetchWithRetry(listingUrl)
        if (!listingResponse) continue

        const listingHtml = await listingResponse.text()
        const listing = this.parseVehicleData(listingHtml, listingUrl, 'PublicSurplus')
        
        if (listing) {
          listings.push(listing)
        }
      }
    } catch (error) {
      console.error('Error scraping PublicSurplus:', error)
    }

    return listings
  }

  async saveListings(listings: VehicleListing[]): Promise<void> {
    if (listings.length === 0) return

    try {
      const { data, error } = await this.supabase
        .from('public_listings')
        .upsert(listings, { 
          onConflict: 'listing_url',
          ignoreDuplicates: false 
        })

      if (error) {
        console.error('Error saving listings:', error)
      } else {
        console.log(`Saved ${listings.length} listings to database`)
      }
    } catch (error) {
      console.error('Database error:', error)
    }
  }

  async startScraping(sites: string[] = ['GovDeals', 'PublicSurplus']) {
    console.log('Starting vehicle scraping for sites:', sites)
    const allListings: VehicleListing[] = []

    for (const site of sites) {
      try {
        let listings: VehicleListing[] = []
        
        switch (site) {
          case 'GovDeals':
            listings = await this.scrapeGovDeals()
            break
          case 'PublicSurplus':
            listings = await this.scrapePublicSurplus()
            break
          default:
            console.log(`Scraper for ${site} not implemented yet`)
        }

        allListings.push(...listings)
        console.log(`Scraped ${listings.length} listings from ${site}`)
      } catch (error) {
        console.error(`Error scraping ${site}:`, error)
      }
    }

    await this.saveListings(allListings)
    return {
      total_scraped: allListings.length,
      sites_processed: sites,
      timestamp: new Date().toISOString()
    }
  }
}

serve(async (req) => {
  // Handle CORS preflight requests
  if (req.method === 'OPTIONS') {
    return new Response(null, { headers: corsHeaders })
  }

  try {
    const supabaseUrl = Deno.env.get('SUPABASE_URL')!
    const supabaseServiceKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!
    
    const scraper = new VehicleScraper(supabaseUrl, supabaseServiceKey)
    
    if (req.method === 'GET') {
      // Get existing listings
      const url = new URL(req.url)
      const limit = parseInt(url.searchParams.get('limit') || '50')
      
      const supabase = createClient(supabaseUrl, supabaseServiceKey)
      const { data: listings, error } = await supabase
        .from('public_listings')
        .select('*')
        .eq('is_active', true)
        .order('created_at', { ascending: false })
        .limit(limit)

      if (error) {
        return new Response(JSON.stringify({ error: error.message }), {
          status: 500,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        })
      }

      return new Response(JSON.stringify({ listings }), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      })
    }

    if (req.method === 'POST') {
      const body: ScrapingRequest = await req.json()
      
      if (body.action === 'start_scraping') {
        const result = await scraper.startScraping(body.sites)
        
        return new Response(JSON.stringify({
          success: true,
          result
        }), {
          headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        })
      }
    }

    return new Response(JSON.stringify({ error: 'Invalid request' }), {
      status: 400,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    })

  } catch (error) {
    console.error('Function error:', error)
    return new Response(JSON.stringify({ error: error.message }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    })
  }
})