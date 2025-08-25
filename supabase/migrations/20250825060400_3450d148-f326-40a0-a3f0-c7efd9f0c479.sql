-- Create error_reports table for centralized error logging
CREATE TABLE IF NOT EXISTS public.error_reports (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  error_id text NOT NULL UNIQUE,
  timestamp timestamp with time zone NOT NULL DEFAULT now(),
  severity text NOT NULL CHECK (severity IN ('debug', 'info', 'warn', 'error', 'fatal')),
  category text NOT NULL,
  message text NOT NULL,
  user_message text NOT NULL,
  stack_trace text,
  context jsonb DEFAULT '{}'::jsonb,
  resolved boolean DEFAULT false,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now()
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_error_reports_timestamp ON public.error_reports(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_error_reports_severity ON public.error_reports(severity);
CREATE INDEX IF NOT EXISTS idx_error_reports_category ON public.error_reports(category);
CREATE INDEX IF NOT EXISTS idx_error_reports_resolved ON public.error_reports(resolved);

-- Add content_hash column to public_listings for deduplication
ALTER TABLE public.public_listings ADD COLUMN IF NOT EXISTS content_hash text;

-- Create unique index for content hash deduplication
CREATE UNIQUE INDEX IF NOT EXISTS idx_public_listings_content_hash 
ON public.public_listings(content_hash) 
WHERE content_hash IS NOT NULL;

-- Add ingested_at column for partitioning
ALTER TABLE public.public_listings ADD COLUMN IF NOT EXISTS ingested_at timestamp with time zone DEFAULT now();

-- Create materialized view for live opportunities
CREATE MATERIALIZED VIEW IF NOT EXISTS public.opportunities_live AS
SELECT 
  id, make, model, year, current_bid, estimated_sale_price,
  potential_profit, roi_percentage, confidence_score, 
  auction_end, location, state, source_site, vin,
  created_at, updated_at
FROM public.opportunities 
WHERE is_active = true 
  AND confidence_score >= 85 
  AND roi_percentage >= 15
  AND auction_end > now();

-- Create index on materialized view
CREATE INDEX IF NOT EXISTS idx_opportunities_live_score 
ON public.opportunities_live (confidence_score DESC, roi_percentage DESC);

CREATE INDEX IF NOT EXISTS idx_opportunities_live_auction_end 
ON public.opportunities_live (auction_end);

-- Create labels table for active learning
CREATE TABLE IF NOT EXISTS public.labels (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL,
  field text NOT NULL,
  old_value text,
  new_value text NOT NULL,
  css_path text,
  cluster_id text,
  url text NOT NULL,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now()
);

-- Enable RLS on labels table
ALTER TABLE public.labels ENABLE ROW LEVEL SECURITY;

-- Create RLS policies for labels
CREATE POLICY "Users can view their own labels" 
ON public.labels FOR SELECT 
USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own labels" 
ON public.labels FOR INSERT 
WITH CHECK (auth.uid() = user_id);

-- Create budget tracking table
CREATE TABLE IF NOT EXISTS public.budget_tracking (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  site_id text NOT NULL,
  band text NOT NULL CHECK (band IN ('http', 'headless', 'llm', 'captcha')),
  daily_limit integer NOT NULL DEFAULT 1000,
  used_today integer NOT NULL DEFAULT 0,
  reset_date date NOT NULL DEFAULT CURRENT_DATE,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now()
);

-- Create unique constraint for site_id + band + reset_date
CREATE UNIQUE INDEX IF NOT EXISTS idx_budget_tracking_unique 
ON public.budget_tracking(site_id, band, reset_date);

-- Create index for budget queries
CREATE INDEX IF NOT EXISTS idx_budget_tracking_site_band 
ON public.budget_tracking(site_id, band);

-- Add RLS to error_reports table
ALTER TABLE public.error_reports ENABLE ROW LEVEL SECURITY;

-- Create policy for error_reports (service role can manage all, users can't see any)
CREATE POLICY "Service role can manage error reports" 
ON public.error_reports FOR ALL 
USING (auth.role() = 'service_role');

-- Create trigger for updated_at columns
CREATE OR REPLACE FUNCTION public.handle_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public';

-- Add triggers for updated_at
CREATE TRIGGER update_error_reports_updated_at
  BEFORE UPDATE ON public.error_reports
  FOR EACH ROW
  EXECUTE FUNCTION public.handle_updated_at();

CREATE TRIGGER update_labels_updated_at
  BEFORE UPDATE ON public.labels
  FOR EACH ROW
  EXECUTE FUNCTION public.handle_updated_at();

CREATE TRIGGER update_budget_tracking_updated_at
  BEFORE UPDATE ON public.budget_tracking
  FOR EACH ROW
  EXECUTE FUNCTION public.handle_updated_at();