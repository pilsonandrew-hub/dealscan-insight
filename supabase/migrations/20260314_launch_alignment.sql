ALTER TABLE public.opportunities
ADD COLUMN IF NOT EXISTS buyer_premium FLOAT,
ADD COLUMN IF NOT EXISTS city TEXT,
ADD COLUMN IF NOT EXISTS condition_grade TEXT,
ADD COLUMN IF NOT EXISTS legacy_dos_score FLOAT,
ADD COLUMN IF NOT EXISTS pricing_maturity TEXT,
ADD COLUMN IF NOT EXISTS outcome_sale_price FLOAT,
ADD COLUMN IF NOT EXISTS outcome_sale_date DATE,
ADD COLUMN IF NOT EXISTS outcome_days_to_sale INT,
ADD COLUMN IF NOT EXISTS outcome_notes TEXT,
ADD COLUMN IF NOT EXISTS outcome_recorded_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_opportunities_pricing_maturity
  ON public.opportunities(pricing_maturity);

CREATE INDEX IF NOT EXISTS idx_opportunities_outcome_sale_date
  ON public.opportunities(outcome_sale_date DESC)
  WHERE outcome_sale_date IS NOT NULL;

COMMENT ON COLUMN public.opportunities.pricing_maturity IS
  'Canonical pricing confidence stage: live_market, market_comp, proxy, or unknown.';

COMMENT ON COLUMN public.opportunities.outcome_sale_price IS
  'Canonical recorded sale outcome stored on the opportunity row for launch-safe outcome tracking.';
