/**
 * Crosshair directed retrieval system types
 * Matches the specification for premium targeted inventory search
 */

export interface CanonicalQuery {
  make?: string;
  model?: string;
  year_min?: number;
  year_max?: number;
  mileage_max?: number;
  price_max?: number;
  locations?: string[];
  title_status?: ('clean' | 'rebuilt' | 'salvage' | 'flood' | 'lemon')[];
  condition?: ('running' | 'non_running' | 'parts' | 'excellent' | 'good' | 'fair' | 'poor')[];
  fuel?: ('gasoline' | 'diesel' | 'electric' | 'hybrid')[];
  body_type?: ('sedan' | 'suv' | 'truck' | 'pickup' | 'coupe' | 'wagon' | 'van')[];
}

export interface SearchOptions {
  expand_aliases?: boolean;
  nearest_viable_year?: boolean;
  notify_on_first_match?: boolean;
  rescan_interval?: '1h' | '6h' | '12h' | 'daily' | 'weekly';
  sites?: string[];
  max_pages_per_site?: number;
  user_priority?: 'low' | 'medium' | 'high';
}

export interface CanonicalListing {
  id: string;
  source: string;
  external_id: string;
  url: string;
  snapshot_sha?: string;
  make: string;
  model: string;
  year: number;
  trim?: string;
  vin?: string;
  odo_miles?: number;
  title_status?: string;
  condition?: string;
  location: {
    state?: string;
    city?: string;
    lat?: number;
    lng?: number;
  };
  bid_current?: number;
  buy_now?: number;
  auction_ends_at?: string;
  photos: string[];
  seller?: string;
  collected_at: string;
  provenance: {
    via: 'api' | 'scrape';
    source_confidence?: number;
    api_endpoint?: string;
    scrape_method?: string;
  };
  arbitrage_score: number;
  comp_band: {
    p25?: number;
    p50?: number;
    p75?: number;
  };
  flags: string[];
  fuel?: string;
  body_type?: string;
}

export interface CrosshairIntent {
  id: string;
  user_id: string;
  canonical_query: CanonicalQuery;
  search_options: SearchOptions;
  title: string;
  rescan_interval: string;
  notify_on_first_match: boolean;
  is_active: boolean;
  last_scan_at?: string;
  last_results_count: number;
  created_at: string;
  updated_at: string;
}

export interface CrosshairJob {
  id: string;
  intent_id?: string;
  user_id: string;
  canonical_query: CanonicalQuery;
  search_options: SearchOptions;
  status: 'queued' | 'running' | 'completed' | 'failed';
  progress: number;
  sites_targeted: string[];
  results_count: number;
  error_message?: string;
  metadata: Record<string, any>;
  started_at?: string;
  completed_at?: string;
  created_at: string;
  updated_at: string;
}

export interface SearchResponse {
  success: boolean;
  results: CanonicalListing[];
  total_count: number;
  job_id: string;
  pivots?: {
    original_query: CanonicalQuery;
    adjusted_query: CanonicalQuery;
    reason: string;
    explanation: string;
  };
  sources_used: {
    source: string;
    method: 'api' | 'scrape';
    status: 'success' | 'failed' | 'partial';
    results_count: number;
    error?: string;
  }[];
  execution_time_ms: number;
}

export interface SourceConnector {
  id: string;
  name: string;
  capabilities: {
    api: boolean;
    scraping: boolean;
    partial_api?: string[];
  };
  limits: {
    rate_per_sec: number;
    burst: number;
    auth?: 'apiKey' | 'oauth' | 'none';
  };
}

// Vehicle model year ranges for smart pivoting
export const VEHICLE_MODEL_YEARS: Record<string, { first_year: number; last_year?: number }> = {
  'Tesla Cybertruck': { first_year: 2023 },
  'Tesla Model S': { first_year: 2012 },
  'Tesla Model 3': { first_year: 2017 },
  'Tesla Model X': { first_year: 2015 },
  'Tesla Model Y': { first_year: 2020 },
  'Ford Lightning': { first_year: 2022 },
  'Rivian R1T': { first_year: 2022 },
  'GMC Hummer EV': { first_year: 2022 },
  // Add more as needed
};

// Site aliases for fuzzy matching
export const SITE_ALIASES: Record<string, string[]> = {
  'govdeals': ['gov deals', 'government deals'],
  'publicsurplus': ['public surplus', 'govt surplus'],
  'gsaauctions': ['gsa auction', 'gsa auctions', 'government auction'],
  'manheim': ['manheim auction', 'manheim auctions'],
};

// Model aliases for fuzzy matching  
export const MODEL_ALIASES: Record<string, string[]> = {
  'Cybertruck': ['Cyber Truck', 'Tesla Pickup', 'Tesla Truck'],
  'Lightning': ['F-150 Lightning', 'F150 Lightning'],
  'Mustang': ['Mustang GT', 'Mustang Mach'],
  'Camaro': ['Camaro SS', 'Camaro Z28'],
};