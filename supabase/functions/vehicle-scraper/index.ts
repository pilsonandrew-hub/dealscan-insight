import { serve } from "https://deno.land/std@0.168.0/http/server.ts"
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'
import * as cheerio from 'https://esm.sh/cheerio@1.0.0-rc.12'

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
}

interface ScrapingRequest {
  action: 'start_scraping' | 'get_status' | 'get_listings'
  sites?: string[]
  limit?: number
}

// Valid sites whitelist for security - matching frontend types
const VALID_SITES = [
  // Federal sites
  'GovDeals', 'PublicSurplus', 'GSAauctions', 'TreasuryAuctions', 'USMarshals',
  'MuniciBid', 'AllSurplus', 'HiBid', 'Proxibid', 'EquipmentFacts',
  'GovPlanet', 'GovLiquidation', 'USGovBid', 'IRSAuctions',
  // State sites
  'California DGS', 'LA County', 'Washington State', 'New York State',
  'Florida DMS', 'Oregon DAS', 'North Carolina DOA'
] as const
const MAX_LIMIT = 1000
const MAX_SITES_PER_REQUEST = 10

// Rate limiting storage (in production, use Redis)
const rateLimitMap = new Map<string, { count: number; resetTime: number }>()

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

// Circuit breaker for API resilience
class CircuitBreaker {
  private failures = 0
  private lastFailureTime = 0
  private state: 'CLOSED' | 'OPEN' | 'HALF_OPEN' = 'CLOSED'
  
  constructor(private threshold = 5, private timeout = 60000) {}
  
  async execute<T>(operation: () => Promise<T>): Promise<T> {
    if (this.state === 'OPEN') {
      if (Date.now() - this.lastFailureTime > this.timeout) {
        this.state = 'HALF_OPEN'
      } else {
        throw new Error('Circuit breaker is OPEN')
      }
    }
    
    try {
      const result = await operation()
      this.onSuccess()
      return result
    } catch (error) {
      this.onFailure()
      throw error
    }
  }
  
  private onSuccess() {
    this.failures = 0
    this.state = 'CLOSED'
  }
  
  private onFailure() {
    this.failures++
    this.lastFailureTime = Date.now()
    if (this.failures >= this.threshold) {
      this.state = 'OPEN'
    }
  }
}

class VehicleScraper {
  private supabase: any
  private rateLimitDelay = 3000
  private circuitBreaker = new CircuitBreaker()
  private cache = new Map<string, { data: any, timestamp: number }>()
  private readonly CACHE_TTL = 300000 // 5 minutes
  
  constructor(supabaseUrl: string, supabaseKey: string) {
    this.supabase = createClient(supabaseUrl, supabaseKey)
  }

  private async delay(ms: number) {
    return new Promise(resolve => setTimeout(resolve, ms))
  }

  private getRandomUserAgent(): string {
    return USER_AGENTS[Math.floor(Math.random() * USER_AGENTS.length)]
  }

  private getCachedData(key: string): any | null {
    const cached = this.cache.get(key)
    if (cached && Date.now() - cached.timestamp < this.CACHE_TTL) {
      return cached.data
    }
    this.cache.delete(key)
    return null
  }
  
  private setCachedData(key: string, data: any): void {
    this.cache.set(key, { data, timestamp: Date.now() })
  }

  private async fetchWithRetry(
    url: string, 
    options: RequestInit = {}, 
    maxRetries = 3,
    baseDelay = 1000
  ): Promise<Response | null> {
    // Check cache first
    const cacheKey = `${url}_${JSON.stringify(options)}`
    const cached = this.getCachedData(cacheKey)
    if (cached) {
      console.log(`Cache hit for ${url}`)
      return new Response(cached, { status: 200 })
    }
    
    // Validate URL to prevent SSRF attacks
    if (!isValidURL(url)) {
      console.error(`Invalid URL rejected: ${url}`)
      return null
    }
    
    return this.circuitBreaker.execute(async () => {
      for (let attempt = 1; attempt <= maxRetries; attempt++) {
        try {
          const controller = new AbortController()
          const timeoutId = setTimeout(() => controller.abort(), 30000) // 30s timeout
          
          const response = await fetch(url, {
            ...options,
            signal: controller.signal,
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
          
          clearTimeout(timeoutId)
          
          if (response.ok) {
            // Cache successful responses
            const text = await response.text()
            this.setCachedData(cacheKey, text)
            return new Response(text, { status: response.status })
          } else if (response.status === 429) {
            // Rate limited - exponential backoff with jitter
            const delay = baseDelay * Math.pow(2, attempt - 1) + Math.random() * 1000
            console.log(`Rate limited on attempt ${attempt}, waiting ${delay}ms`)
            await this.delay(delay)
            continue
          } else if (response.status >= 500) {
            // Server error - retry
            console.log(`Server error ${response.status} on attempt ${attempt}`)
            const delay = baseDelay * Math.pow(2, attempt - 1)
            await this.delay(delay)
            continue
          } else {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`)
          }
        } catch (error) {
          console.error(`Fetch attempt ${attempt} failed:`, error)
          
          if (attempt === maxRetries) {
            throw error
          }
          
          // Exponential backoff with jitter
          const delay = baseDelay * Math.pow(2, attempt - 1) + Math.random() * 1000
          await this.delay(delay)
        }
      }
      
      throw new Error(`Failed to fetch ${url} after ${maxRetries} attempts`)
    })
  }

  private parseVehicleData(html: string, url: string, siteName: string): VehicleListing | null {
    try {
      const $ = cheerio.load(html)
      
      const listing: VehicleListing = {
        source_site: siteName,
        listing_url: url,
        scrape_metadata: {
          scraped_at: new Date().toISOString(),
          html_length: html.length,
          success: true
        }
      }

      // Site-specific parsing logic with CSS selectors
      if (siteName === 'GovDeals') {
        listing.year = this.parseNumber($('.item-year, .year, [class*="year"]').first().text())
        listing.make = this.cleanText($('.item-make, .make, [class*="make"]').first().text())
        listing.model = this.cleanText($('.item-model, .model, [class*="model"]').first().text())
        listing.mileage = this.parseNumber($('.mileage, [class*="mile"]').first().text())
        listing.current_bid = this.parseCurrency($('.current-bid, .bid, [class*="bid"]').first().text())
        listing.location = this.cleanText($('.location, [class*="location"]').first().text())
        listing.vin = this.cleanText($('.vin, [class*="vin"]').first().text())
        listing.description = this.cleanText($('.description, .item-description').first().text())
        
        // Extract auction end date
        const auctionEndText = $('.auction-end, .end-date, [class*="end"]').first().text()
        if (auctionEndText) {
          const endDate = new Date(auctionEndText)
          if (!isNaN(endDate.getTime())) {
            listing.auction_end = endDate.toISOString()
          }
        }
        
      } else if (siteName === 'PublicSurplus') {
        listing.year = this.parseNumber($('.vehicle-year, .year').first().text())
        listing.make = this.cleanText($('.vehicle-make, .make').first().text())
        listing.model = this.cleanText($('.vehicle-model, .model').first().text())
        listing.mileage = this.parseNumber($('.vehicle-mileage, .mileage').first().text())
        listing.current_bid = this.parseCurrency($('.current-bid, .high-bid').first().text())
        listing.location = this.cleanText($('.item-location, .location').first().text())
        listing.description = this.cleanText($('.item-description, .description').first().text())
      }
      
      // Validate that we extracted some meaningful data
      if (!listing.make && !listing.model && !listing.year) {
        console.warn(`No vehicle data extracted from ${url}`)
        return null
      }

      return listing
    } catch (error) {
      console.error('Error parsing vehicle data:', error)
      return null
    }
  }
  
  private parseNumber(text: string): number | undefined {
    if (!text) return undefined
    const cleaned = text.replace(/[^0-9]/g, '')
    const num = parseInt(cleaned)
    return isNaN(num) ? undefined : num
  }
  
  private parseCurrency(text: string): number | undefined {
    if (!text) return undefined
    const cleaned = text.replace(/[^0-9.]/g, '')
    const num = parseFloat(cleaned)
    return isNaN(num) ? undefined : num
  }
  
  private cleanText(text: string): string | undefined {
    if (!text) return undefined
    const cleaned = text.trim().replace(/\s+/g, ' ')
    return cleaned || undefined
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

    // Batch inserts for better performance
    const BATCH_SIZE = 100
    let totalSaved = 0
    
    try {
      for (let i = 0; i < listings.length; i += BATCH_SIZE) {
        const batch = listings.slice(i, i + BATCH_SIZE)
        
        const { data, error } = await this.supabase
          .from('public_listings')
          .upsert(batch, { 
            onConflict: 'listing_url',
            ignoreDuplicates: false 
          })

        if (error) {
          console.error(`Error saving batch ${Math.floor(i/BATCH_SIZE) + 1}:`, error)
          // Continue with next batch instead of failing completely
        } else {
          totalSaved += batch.length
          console.log(`Saved batch ${Math.floor(i/BATCH_SIZE) + 1}: ${batch.length} listings`)
        }
        
        // Small delay between batches to avoid overwhelming the database
        if (i + BATCH_SIZE < listings.length) {
          await this.delay(100)
        }
      }
      
      console.log(`Successfully saved ${totalSaved}/${listings.length} listings to database`)
    } catch (error) {
      console.error('Database error:', error)
      throw error
    }
  }

  private async scrapeSite(site: string): Promise<VehicleListing[]> {
    try {
      switch (site) {
        case 'GovDeals':
          return await this.scrapeGovDeals()
        case 'PublicSurplus':
          return await this.scrapePublicSurplus()
        default:
          console.log(`Scraper for ${site} not implemented yet`)
          return []
      }
    } catch (error) {
      console.error(`Error scraping ${site}:`, error)
      return []
    }
  }

  async startScraping(sites: string[] = ['GovDeals', 'PublicSurplus']) {
    console.log('Starting concurrent vehicle scraping for sites:', sites)
    
    // Process sites concurrently with limited concurrency
    const BATCH_SIZE = 3
    const allListings: VehicleListing[] = []
    const results: { site: string, count: number, error?: string }[] = []
    
    for (let i = 0; i < sites.length; i += BATCH_SIZE) {
      const batch = sites.slice(i, i + BATCH_SIZE)
      const batchPromises = batch.map(async (site) => {
        try {
          const listings = await this.scrapeSite(site)
          return { site, listings, error: null }
        } catch (error) {
          console.error(`Failed to scrape ${site}:`, error)
          return { site, listings: [], error: error.message }
        }
      })
      
      const batchResults = await Promise.allSettled(batchPromises)
      
      batchResults.forEach((result, index) => {
        const site = batch[index]
        if (result.status === 'fulfilled') {
          const { listings, error } = result.value
          allListings.push(...listings)
          results.push({ 
            site, 
            count: listings.length, 
            error: error || undefined 
          })
          console.log(`Scraped ${listings.length} listings from ${site}`)
        } else {
          results.push({ 
            site, 
            count: 0, 
            error: `Promise rejected: ${result.reason}` 
          })
          console.error(`Promise rejected for ${site}:`, result.reason)
        }
      })
      
      // Brief pause between batches to be respectful
      if (i + BATCH_SIZE < sites.length) {
        await this.delay(2000)
      }
    }

    // Save all listings in batches
    await this.saveListings(allListings)
    
    return {
      total_scraped: allListings.length,
      sites_processed: sites,
      results: results,
      timestamp: new Date().toISOString()
    }
  }
}

// Security helper functions
function getClientIP(req: Request): string {
  return req.headers.get('x-forwarded-for')?.split(',')[0] || 
    req.headers.get('x-real-ip') || 
    'unknown'
}

function isRateLimited(clientIP: string): boolean {
  const now = Date.now()
  const clientData = rateLimitMap.get(clientIP)
  
  if (!clientData || now > clientData.resetTime) {
    rateLimitMap.set(clientIP, { count: 1, resetTime: now + 60000 })
    return false
  }
  
  if (clientData.count >= 100) { // 100 requests per minute
    return true
  }
  
  clientData.count++
  return false
}

function validateScrapingRequest(body: any): { valid: boolean; error?: string; data?: ScrapingRequest } {
  if (!body || typeof body !== 'object') {
    return { valid: false, error: 'Invalid request body' }
  }
  
  const { action, sites, limit } = body
  
  if (!action || typeof action !== 'string') {
    return { valid: false, error: 'Missing or invalid action' }
  }
  
  if (!['start_scraping', 'get_status', 'get_listings'].includes(action)) {
    return { valid: false, error: 'Invalid action specified' }
  }
  
  if (sites && (!Array.isArray(sites) || sites.length > MAX_SITES_PER_REQUEST)) {
    return { valid: false, error: `Invalid sites array or too many sites (max ${MAX_SITES_PER_REQUEST})` }
  }
  
  if (sites && sites.some(site => !VALID_SITES.includes(site))) {
    return { valid: false, error: 'Invalid site specified' }
  }
  
  if (limit && (typeof limit !== 'number' || limit > MAX_LIMIT || limit < 1)) {
    return { valid: false, error: `Invalid limit (must be 1-${MAX_LIMIT})` }
  }
  
  return { valid: true, data: { action, sites, limit } }
}

function isValidURL(url: string): boolean {
  try {
    const parsedUrl = new URL(url)
    
    // Only allow HTTPS for external sites
    if (parsedUrl.protocol !== 'https:') {
      return false
    }
    
    // Whitelist allowed domains
    const allowedDomains = [
      'www.govdeals.com',
      'www.publicsurplus.com',
      'gsaauctions.gov'
    ]
    
    return allowedDomains.some(domain => parsedUrl.hostname === domain)
  } catch {
    return false
  }
}

serve(async (req) => {
  // Handle CORS preflight requests
  if (req.method === 'OPTIONS') {
    return new Response(null, { headers: corsHeaders })
  }

  try {
    // Rate limiting
    const clientIP = getClientIP(req)
    if (isRateLimited(clientIP)) {
      return new Response(JSON.stringify({ error: 'Rate limit exceeded' }), {
        status: 429,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      })
    }

    const supabaseUrl = Deno.env.get('SUPABASE_URL')!
    const supabaseAnonKey = Deno.env.get('SUPABASE_ANON_KEY')!
    
    // Proper JWT authentication
    const authHeader = req.headers.get('Authorization')
    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      return new Response(JSON.stringify({ error: 'Authentication required - Bearer token missing' }), {
        status: 401,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      })
    }

    // Verify JWT token
    const token = authHeader.substring(7)
    const supabase = createClient(supabaseUrl, supabaseAnonKey)
    
    const { data: { user }, error: authError } = await supabase.auth.getUser(token)
    if (authError || !user) {
      console.error('Authentication failed:', authError)
      return new Response(JSON.stringify({ error: 'Invalid or expired token' }), {
        status: 401,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      })
    }
    
    console.log(`Authenticated request from user: ${user.id}`)
    
    // Use service role key only for the scraper operations
    const supabaseServiceKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!
    const scraper = new VehicleScraper(supabaseUrl, supabaseServiceKey)
    
    if (req.method === 'GET') {
      // Redirect GET requests to use POST with action for consistency
      return new Response(JSON.stringify({ error: 'Please use POST with action parameter' }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      })
    }

    if (req.method === 'POST') {
      let body: any
      
      try {
        body = await req.json()
      } catch {
        return new Response(JSON.stringify({ error: 'Invalid JSON body' }), {
          status: 400,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        })
      }
      
      const validation = validateScrapingRequest(body)
      if (!validation.valid) {
        return new Response(JSON.stringify({ error: validation.error }), {
          status: 400,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        })
      }
      
      const scrapingRequest = validation.data!
      
      if (scrapingRequest.action === 'start_scraping') {
        const result = await scraper.startScraping(scrapingRequest.sites)
        
        return new Response(JSON.stringify({
          success: true,
          result
        }), {
          headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        })
      }
      
      if (scrapingRequest.action === 'get_listings') {
        const limit = scrapingRequest.limit || 50
        
        const supabaseService = createClient(supabaseUrl, supabaseServiceKey)
        const { data: listings, error } = await supabaseService
          .from('public_listings')
          .select('*')
          .eq('is_active', true)
          .order('created_at', { ascending: false })
          .limit(limit)

        if (error) {
          console.error('Database error:', error)
          return new Response(JSON.stringify({ error: 'Database query failed' }), {
            status: 500,
            headers: { ...corsHeaders, 'Content-Type': 'application/json' }
          })
        }

        return new Response(JSON.stringify({ listings }), {
          headers: { ...corsHeaders, 'Content-Type': 'application/json' }
        })
      }
    }

    return new Response(JSON.stringify({ error: 'Method not allowed' }), {
      status: 405,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    })

  } catch (error) {
    console.error('Function error:', error)
    return new Response(JSON.stringify({ error: 'Internal server error' }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    })
  }
})