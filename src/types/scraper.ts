export interface PublicListing {
  id: string
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
  title_status?: 'clean' | 'salvage' | 'rebuilt' | 'flood' | 'lemon' | 'unknown'
  description?: string
  created_at: string
  updated_at: string
  is_active: boolean
  scrape_metadata?: Record<string, any>
}

export interface ScrapingResult {
  total_scraped: number
  sites_processed: string[]
  timestamp: string
}

export interface ScrapingRequest {
  action: 'start_scraping' | 'get_status' | 'get_listings'
  sites?: string[]
  limit?: number
}

export interface ScraperConfig {
  id: string
  site_name: string
  site_url: string
  category: 'federal_nationwide' | 'state_municipal'
  is_enabled: boolean
  rate_limit_seconds: number
  max_pages: number
  selectors: Record<string, string>
  headers: Record<string, string>
  created_at: string
  updated_at: string
}

export const FEDERAL_SITES = [
  'GovDeals',
  'PublicSurplus', 
  'GSAauctions',
  'TreasuryAuctions',
  'USMarshals',
  'MuniciBid',
  'AllSurplus',
  'HiBid',
  'Proxibid',
  'EquipmentFacts',
  'GovPlanet',
  'GovLiquidation',
  'USGovBid',
  'IRSAuctions',
  'BidSpotter'
] as const

export const STATE_SITES = [
  'California DGS',
  'LA County',
  'Washington State',
  'New York State',
  'Florida DMS',
  'Oregon DAS',
  'North Carolina DOA'
] as const

export type SiteName = typeof FEDERAL_SITES[number] | typeof STATE_SITES[number]