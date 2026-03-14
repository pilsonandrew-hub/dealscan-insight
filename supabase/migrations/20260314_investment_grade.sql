ALTER TABLE public.opportunities
ADD COLUMN IF NOT EXISTS ctm_pct FLOAT,
ADD COLUMN IF NOT EXISTS segment_tier INT,
ADD COLUMN IF NOT EXISTS investment_grade TEXT;
