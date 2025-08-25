-- Create user_alerts table for in-app notifications
CREATE TABLE IF NOT EXISTS public.user_alerts (
  id text PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES auth.users(id),
  opportunity_id text,
  type text NOT NULL CHECK (type IN ('hot_deal','price_drop','ending_soon','new_opportunity')),
  title text NOT NULL,
  message text NOT NULL,
  priority text NOT NULL CHECK (priority IN ('critical','high','medium','low')),
  dismissed boolean NOT NULL DEFAULT false,
  viewed boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  opportunity_data jsonb
);

-- Enable RLS
ALTER TABLE public.user_alerts ENABLE ROW LEVEL SECURITY;

-- RLS policies for user_alerts
CREATE POLICY "Users can read own alerts" ON public.user_alerts
  FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can update own alerts" ON public.user_alerts
  FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "System can insert alerts" ON public.user_alerts
  FOR INSERT WITH CHECK (true);

-- Update user_settings table for sound settings
ALTER TABLE public.user_settings 
ADD COLUMN IF NOT EXISTS sound_enabled boolean DEFAULT true,
ADD COLUMN IF NOT EXISTS notification_duration integer DEFAULT 10000;

-- Create scraper_sites table for comprehensive scraping
CREATE TABLE IF NOT EXISTS public.scraper_sites (
  id text PRIMARY KEY,
  name text NOT NULL,
  base_url text NOT NULL,
  enabled boolean NOT NULL DEFAULT true,
  status text NOT NULL DEFAULT 'active',
  category text NOT NULL,
  priority int NOT NULL DEFAULT 5,
  last_scrape timestamptz,
  vehicles_found int DEFAULT 0,
  updated_at timestamptz DEFAULT now()
);

-- Create scraping_jobs table for job tracking
CREATE TABLE IF NOT EXISTS public.scraping_jobs (
  id text PRIMARY KEY,
  status text NOT NULL,
  sites_targeted text[],
  config jsonb,
  started_at timestamptz DEFAULT now(),
  completed_at timestamptz,
  error_message text,
  results jsonb
);

-- Insert comprehensive scraper sites
INSERT INTO public.scraper_sites (id, name, base_url, category, priority) VALUES
('gsa_auctions', 'GSA Auctions', 'https://gsaauctions.gov', 'federal', 1),
('treasury_auctions', 'Treasury Auctions', 'https://treasuryauctions.gov', 'federal', 1),
('us_marshals', 'US Marshals Sales', 'https://usmarshals.gov', 'federal', 1),
('govdeals', 'GovDeals', 'https://govdeals.com', 'public_surplus', 2),
('publicsurplus', 'PublicSurplus', 'https://publicsurplus.com', 'public_surplus', 2),
('municibid', 'Municibid', 'https://municibid.com', 'municipal', 3),
('allsurplus', 'AllSurplus', 'https://allsurplus.com', 'surplus', 3),
('hibid', 'HiBid', 'https://hibid.com', 'auction_house', 4),
('proxibid', 'Proxibid', 'https://proxibid.com', 'auction_house', 4),
('equipmentfacts', 'EquipmentFacts', 'https://equipmentfacts.com', 'equipment', 4),
('govplanet', 'GovPlanet', 'https://govplanet.com', 'military', 2),
('govliquidation', 'GovLiquidation', 'https://govliquidation.com', 'federal', 2),
('usgovbid', 'USGovBid', 'https://usgovbid.com', 'federal', 3),
('iaai', 'IAAI', 'https://iaai.com', 'insurance', 5),
('copart', 'Copart', 'https://copart.com', 'insurance', 5),
('ca_dgs', 'California DGS', 'https://caleprocure.ca.gov', 'state', 3),
('la_county', 'LA County Surplus', 'https://lacounty.gov', 'county', 4),
('wa_des', 'Washington DES', 'https://des.wa.gov', 'state', 3),
('ny_ogs', 'New York OGS', 'https://ogs.ny.gov', 'state', 3),
('fl_dms', 'Florida DMS', 'https://dms.myflorida.com', 'state', 3);

-- Enable realtime for user_alerts
ALTER TABLE public.user_alerts REPLICA IDENTITY FULL;
ALTER PUBLICATION supabase_realtime ADD TABLE public.user_alerts;