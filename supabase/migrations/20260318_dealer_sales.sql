-- dealer_sales schema enhancement: add outcome tracking and arbitrage columns
-- Adds columns required by SniperScope/outcomes endpoint that were missing
-- from the original dealer_sales table (20250820165123).

-- Outcome status enum
DO $$ BEGIN
  CREATE TYPE public.outcome_status AS ENUM ('sold', 'passed', 'pending');
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

-- Add missing columns to dealer_sales
ALTER TABLE public.dealer_sales
  ADD COLUMN IF NOT EXISTS opportunity_id  UUID         REFERENCES public.opportunities(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS vehicle_id      TEXT,                          -- VIN or internal vehicle ref
  ADD COLUMN IF NOT EXISTS sold_price      NUMERIC,                       -- final sale price (alias-friendly; sale_price kept for compat)
  ADD COLUMN IF NOT EXISTS asking_price    NUMERIC,                       -- original asking / bid price from opportunity
  ADD COLUMN IF NOT EXISTS dealer_id       TEXT,                          -- dealer identifier (user_id or external)
  ADD COLUMN IF NOT EXISTS dealer_name     TEXT,                          -- human-readable dealer name
  ADD COLUMN IF NOT EXISTS outcome         public.outcome_status DEFAULT 'pending',
  ADD COLUMN IF NOT EXISTS gross_margin    NUMERIC,                       -- sold_price - total_cost
  ADD COLUMN IF NOT EXISTS roi_pct         NUMERIC,                       -- (gross_margin / total_cost) * 100
  ADD COLUMN IF NOT EXISTS days_to_sale    INTEGER,                       -- calendar days from buy to sale
  ADD COLUMN IF NOT EXISTS source         TEXT DEFAULT 'outcome_tracking'; -- ingestion source tag

-- Back-fill vehicle_id from vin for any existing rows
UPDATE public.dealer_sales SET vehicle_id = vin WHERE vehicle_id IS NULL AND vin IS NOT NULL;

-- Indexes for new columns
CREATE INDEX IF NOT EXISTS idx_dealer_sales_opportunity_id  ON public.dealer_sales(opportunity_id);
CREATE INDEX IF NOT EXISTS idx_dealer_sales_outcome         ON public.dealer_sales(outcome);
CREATE INDEX IF NOT EXISTS idx_dealer_sales_dealer_id       ON public.dealer_sales(dealer_id);
CREATE INDEX IF NOT EXISTS idx_dealer_sales_sold_price      ON public.dealer_sales(sold_price DESC);

-- -----------------------------------------------------------------------
-- RLS policies (dealer_sales already has RLS enabled)
-- Add user-scoped policies for the new outcome rows inserted by the API.
-- -----------------------------------------------------------------------

-- Authenticated users can view their own outcome rows
DROP POLICY IF EXISTS "Users can view own dealer_sales" ON public.dealer_sales;
CREATE POLICY "Users can view own dealer_sales"
  ON public.dealer_sales FOR SELECT
  USING (
    auth.uid() IS NOT NULL
    AND (user_id = auth.uid() OR user_id IS NULL)   -- null = legacy CSV rows, public
  );

-- Authenticated users can insert their own outcome rows
DROP POLICY IF EXISTS "Users can insert own dealer_sales" ON public.dealer_sales;
CREATE POLICY "Users can insert own dealer_sales"
  ON public.dealer_sales FOR INSERT
  WITH CHECK (
    auth.uid() IS NOT NULL
    AND user_id = auth.uid()
  );

-- Service-role / anonymous import can still insert (source_type = 'csv' etc.)
-- The original "Anyone can insert dealer sales" policy already covers this,
-- so no additional policy needed.

COMMENT ON COLUMN public.dealer_sales.opportunity_id  IS 'FK to opportunities table — links outcome to the arbitrage opportunity';
COMMENT ON COLUMN public.dealer_sales.vehicle_id      IS 'VIN or internal vehicle reference';
COMMENT ON COLUMN public.dealer_sales.sold_price      IS 'Actual final sale price recorded at outcome';
COMMENT ON COLUMN public.dealer_sales.asking_price    IS 'Original asking / auction bid price from the opportunity';
COMMENT ON COLUMN public.dealer_sales.dealer_id       IS 'Dealer identifier — maps to auth.users.id for platform users';
COMMENT ON COLUMN public.dealer_sales.dealer_name     IS 'Human-readable dealer name for reporting';
COMMENT ON COLUMN public.dealer_sales.outcome         IS 'Outcome status: sold | passed | pending';
COMMENT ON COLUMN public.dealer_sales.gross_margin    IS 'Gross margin: sold_price minus total acquisition cost';
COMMENT ON COLUMN public.dealer_sales.roi_pct         IS 'Return on investment percentage: (gross_margin / asking_price) * 100';
COMMENT ON COLUMN public.dealer_sales.days_to_sale    IS 'Calendar days from vehicle acquisition to sale';
COMMENT ON COLUMN public.dealer_sales.source          IS 'Ingestion source tag (outcome_tracking, csv, manheim_api, etc.)';
