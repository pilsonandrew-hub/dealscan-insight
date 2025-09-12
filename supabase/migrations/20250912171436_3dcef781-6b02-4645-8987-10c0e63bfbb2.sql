-- Create Crosshair core tables for directed retrieval system
-- Raw pages cache for compliance and auditability
CREATE TABLE IF NOT EXISTS raw_pages (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  url TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  html_content TEXT,
  api_response JSONB,
  collected_at TIMESTAMPTZ DEFAULT now(),
  source_site TEXT NOT NULL,
  compliance_result JSONB DEFAULT '{}',
  provenance TEXT NOT NULL DEFAULT 'scrape' CHECK (provenance IN ('scrape', 'api')),
  snapshot_sha TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Normalized listings for unified search
CREATE TABLE IF NOT EXISTS listings_normalized (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  source TEXT NOT NULL,
  external_id TEXT NOT NULL,
  url TEXT NOT NULL,
  snapshot_sha TEXT,
  make TEXT NOT NULL,
  model TEXT NOT NULL,
  year INTEGER NOT NULL,
  trim TEXT,
  vin TEXT,
  odo_miles INTEGER,
  title_status TEXT CHECK (title_status IN ('clean', 'salvage', 'rebuilt', 'flood', 'lemon', 'unknown')),
  condition TEXT CHECK (condition IN ('running', 'non_running', 'parts', 'excellent', 'good', 'fair', 'poor')),
  location JSONB DEFAULT '{}', -- {state, city, lat, lng}
  bid_current NUMERIC,
  buy_now NUMERIC,
  auction_ends_at TIMESTAMPTZ,
  photos TEXT[],
  seller TEXT,
  collected_at TIMESTAMPTZ DEFAULT now(),
  provenance JSONB DEFAULT '{"via":"scrape"}',
  arbitrage_score NUMERIC DEFAULT 0,
  comp_band JSONB DEFAULT '{}', -- {p25, p50, p75}
  flags TEXT[] DEFAULT '{}',
  is_active BOOLEAN DEFAULT true,
  fuel TEXT,
  body_type TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(source, external_id)
);

-- Crosshair search intents for saved queries and alerts
CREATE TABLE IF NOT EXISTS crosshair_intents (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID NOT NULL,
  canonical_query JSONB NOT NULL,
  search_options JSONB DEFAULT '{}',
  title TEXT NOT NULL,
  rescan_interval TEXT DEFAULT '6h',
  notify_on_first_match BOOLEAN DEFAULT true,
  is_active BOOLEAN DEFAULT true,
  last_scan_at TIMESTAMPTZ,
  last_results_count INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Crosshair jobs for async processing
CREATE TABLE IF NOT EXISTS crosshair_jobs (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  intent_id UUID REFERENCES crosshair_intents(id),
  user_id UUID NOT NULL,
  canonical_query JSONB NOT NULL,
  search_options JSONB DEFAULT '{}',
  status TEXT DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'completed', 'failed')),
  progress INTEGER DEFAULT 0,
  sites_targeted TEXT[] DEFAULT '{}',
  results_count INTEGER DEFAULT 0,
  error_message TEXT,
  metadata JSONB DEFAULT '{}',
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Enable RLS
ALTER TABLE raw_pages ENABLE ROW LEVEL SECURITY;
ALTER TABLE listings_normalized ENABLE ROW LEVEL SECURITY;
ALTER TABLE crosshair_intents ENABLE ROW LEVEL SECURITY;
ALTER TABLE crosshair_jobs ENABLE ROW LEVEL SECURITY;

-- RLS Policies
CREATE POLICY "Service role manages raw pages" ON raw_pages FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Authenticated users read raw pages" ON raw_pages FOR SELECT USING (auth.role() = 'authenticated');

CREATE POLICY "Service role manages listings" ON listings_normalized FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Authenticated users read listings" ON listings_normalized FOR SELECT USING (auth.role() = 'authenticated');

CREATE POLICY "Users manage own intents" ON crosshair_intents FOR ALL USING (user_id = auth.uid());
CREATE POLICY "Users view own jobs" ON crosshair_jobs FOR SELECT USING (user_id = auth.uid());
CREATE POLICY "Service role manages jobs" ON crosshair_jobs FOR ALL USING (auth.role() = 'service_role');

-- Indexes for performance
CREATE INDEX idx_listings_make_model_year ON listings_normalized(make, model, year);
CREATE INDEX idx_listings_collected_at ON listings_normalized(collected_at DESC);
CREATE INDEX idx_listings_provenance ON listings_normalized USING GIN(provenance);
CREATE INDEX idx_crosshair_jobs_status ON crosshair_jobs(status, created_at);
CREATE INDEX idx_raw_pages_url_hash ON raw_pages(url, content_hash);

-- Triggers for updated_at
CREATE TRIGGER update_listings_normalized_updated_at
  BEFORE UPDATE ON listings_normalized
  FOR EACH ROW EXECUTE FUNCTION handle_updated_at();

CREATE TRIGGER update_crosshair_intents_updated_at
  BEFORE UPDATE ON crosshair_intents  
  FOR EACH ROW EXECUTE FUNCTION handle_updated_at();

CREATE TRIGGER update_crosshair_jobs_updated_at
  BEFORE UPDATE ON crosshair_jobs
  FOR EACH ROW EXECUTE FUNCTION handle_updated_at();