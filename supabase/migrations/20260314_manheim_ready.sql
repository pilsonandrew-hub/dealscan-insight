ALTER TABLE public.opportunities
ADD COLUMN IF NOT EXISTS manheim_mmr_mid FLOAT,
ADD COLUMN IF NOT EXISTS manheim_mmr_low FLOAT,
ADD COLUMN IF NOT EXISTS manheim_mmr_high FLOAT,
ADD COLUMN IF NOT EXISTS manheim_range_width_pct FLOAT,
ADD COLUMN IF NOT EXISTS manheim_confidence FLOAT,
ADD COLUMN IF NOT EXISTS manheim_source_status TEXT,
ADD COLUMN IF NOT EXISTS manheim_updated_at TIMESTAMPTZ;
