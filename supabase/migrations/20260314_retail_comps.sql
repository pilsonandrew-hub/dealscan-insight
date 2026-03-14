ALTER TABLE public.opportunities
ADD COLUMN IF NOT EXISTS pricing_source TEXT,
ADD COLUMN IF NOT EXISTS retail_comp_price_estimate FLOAT,
ADD COLUMN IF NOT EXISTS retail_comp_low FLOAT,
ADD COLUMN IF NOT EXISTS retail_comp_high FLOAT,
ADD COLUMN IF NOT EXISTS retail_comp_count INT,
ADD COLUMN IF NOT EXISTS retail_comp_confidence FLOAT,
ADD COLUMN IF NOT EXISTS pricing_updated_at TIMESTAMPTZ;
