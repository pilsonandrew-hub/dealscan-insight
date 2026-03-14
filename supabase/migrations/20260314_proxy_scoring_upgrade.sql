ALTER TABLE public.opportunities
ADD COLUMN IF NOT EXISTS retail_asking_price_estimate FLOAT,
ADD COLUMN IF NOT EXISTS retail_proxy_multiplier FLOAT,
ADD COLUMN IF NOT EXISTS wholesale_ctm_pct FLOAT,
ADD COLUMN IF NOT EXISTS retail_ctm_pct FLOAT,
ADD COLUMN IF NOT EXISTS estimated_days_to_sale INT,
ADD COLUMN IF NOT EXISTS roi_per_day FLOAT,
ADD COLUMN IF NOT EXISTS mmr_lookup_basis TEXT,
ADD COLUMN IF NOT EXISTS mmr_confidence_proxy FLOAT,
ADD COLUMN IF NOT EXISTS bid_ceiling_pct FLOAT,
ADD COLUMN IF NOT EXISTS max_bid FLOAT,
ADD COLUMN IF NOT EXISTS bid_headroom FLOAT,
ADD COLUMN IF NOT EXISTS ceiling_reason TEXT,
ADD COLUMN IF NOT EXISTS score_version TEXT;
