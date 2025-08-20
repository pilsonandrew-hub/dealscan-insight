-- Create public_listings table for scraped vehicle data
CREATE TABLE IF NOT EXISTS public.public_listings (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  source_site TEXT NOT NULL,
  listing_url TEXT NOT NULL UNIQUE,
  auction_end TIMESTAMP WITH TIME ZONE,
  year INTEGER,
  make TEXT,
  model TEXT,
  trim TEXT,
  mileage INTEGER,
  current_bid DECIMAL(10,2),
  location TEXT,
  state TEXT,
  vin TEXT,
  photo_url TEXT,
  title_status TEXT CHECK (title_status IN ('clean', 'salvage', 'rebuilt', 'flood', 'lemon', 'unknown')),
  description TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  is_active BOOLEAN DEFAULT true,
  scrape_metadata JSONB DEFAULT '{}'::jsonb
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_public_listings_source_site ON public.public_listings(source_site);
CREATE INDEX IF NOT EXISTS idx_public_listings_auction_end ON public.public_listings(auction_end);
CREATE INDEX IF NOT EXISTS idx_public_listings_make_model ON public.public_listings(make, model);
CREATE INDEX IF NOT EXISTS idx_public_listings_state ON public.public_listings(state);
CREATE INDEX IF NOT EXISTS idx_public_listings_active ON public.public_listings(is_active) WHERE is_active = true;

-- Create scraper_configs table for managing scraper settings
CREATE TABLE IF NOT EXISTS public.scraper_configs (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  site_name TEXT NOT NULL UNIQUE,
  site_url TEXT NOT NULL,
  category TEXT NOT NULL CHECK (category IN ('federal_nationwide', 'state_municipal')),
  is_enabled BOOLEAN DEFAULT true,
  rate_limit_seconds INTEGER DEFAULT 3,
  max_pages INTEGER DEFAULT 50,
  selectors JSONB DEFAULT '{}'::jsonb,
  headers JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Insert initial scraper configurations
INSERT INTO public.scraper_configs (site_name, site_url, category, selectors, headers) VALUES
('GovDeals', 'https://www.govdeals.com', 'federal_nationwide', '{"vehicle_category": "/vehicles", "listing_selector": ".item-row", "pagination": ".pagination a"}', '{"User-Agent": "Mozilla/5.0 DealerScope Bot"}'),
('PublicSurplus', 'https://www.publicsurplus.com', 'federal_nationwide', '{"vehicle_category": "/vehicles", "listing_selector": ".auction-item", "pagination": ".page-nav a"}', '{"User-Agent": "Mozilla/5.0 DealerScope Bot"}'),
('GSA Auctions', 'https://gsaauctions.gov', 'federal_nationwide', '{"vehicle_category": "/vehicles", "listing_selector": ".listing", "pagination": ".pagination-link"}', '{"User-Agent": "Mozilla/5.0 DealerScope Bot"}');

-- Enable RLS
ALTER TABLE public.public_listings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.scraper_configs ENABLE ROW LEVEL SECURITY;

-- Create RLS policies (public read for listings, admin only for configs)
CREATE POLICY "Public listings are viewable by everyone" 
ON public.public_listings FOR SELECT 
USING (true);

CREATE POLICY "Scraper configs are viewable by everyone" 
ON public.scraper_configs FOR SELECT 
USING (true);

-- Create updated_at trigger function
CREATE OR REPLACE FUNCTION public.handle_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create triggers for updated_at
CREATE TRIGGER handle_public_listings_updated_at
  BEFORE UPDATE ON public.public_listings
  FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

CREATE TRIGGER handle_scraper_configs_updated_at
  BEFORE UPDATE ON public.scraper_configs
  FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();