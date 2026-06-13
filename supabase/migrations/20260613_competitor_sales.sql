-- DealerScope Competitive Pricing Intelligence — competitor_sales.
-- Purpose: store comparable *completed/sold* auction listings scraped from
-- competitor government/surplus auction sites (GovDeals, PublicSurplus, GovPlanet)
-- so the DOS scoring engine can price ceilings against ACTUAL market sales
-- instead of model-proxy MMR when enough real comps exist for a vehicle class.
--
-- This table is the canonical, query-ready comparable-sales store consumed by
-- backend/ingest/competitor_pricing.py. Rows are sold listings only (a real
-- sale_price is required).

CREATE TABLE IF NOT EXISTS public.competitor_sales (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- Provenance
  source             TEXT NOT NULL,            -- 'govdeals' | 'publicsurplus' | 'govplanet'
  source_listing_id  TEXT,                     -- stable per-source lot/asset id when available
  listing_url        TEXT NOT NULL,

  -- Vehicle identity
  vin                TEXT,
  year               INTEGER,
  make               TEXT,
  model              TEXT,
  trim               TEXT,
  mileage            INTEGER,
  vehicle_class      TEXT,                     -- normalized class: 'f-150' | 'f-250' | 'silverado-1500' | ...

  -- Sale facts (sold listings only)
  sale_price         NUMERIC NOT NULL,         -- actual winning/sold price
  currency           TEXT NOT NULL DEFAULT 'USD',
  auction_end_date   TIMESTAMPTZ,              -- when the auction closed / sale completed

  -- Context
  condition_notes    TEXT,
  location           TEXT,                     -- raw "City, ST" location string
  state              TEXT,                     -- normalized 2-letter state when parseable

  -- Bookkeeping
  raw_payload        JSONB NOT NULL DEFAULT '{}'::jsonb,
  scraped_at         TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
  created_at         TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),

  CONSTRAINT chk_competitor_sales_currency CHECK (currency = 'USD'),
  CONSTRAINT chk_competitor_sales_price_positive CHECK (sale_price > 0)
);

-- Dedup: one row per (source, source_listing_id). Falls back to (source, listing_url)
-- for sources that do not expose a stable listing id.
CREATE UNIQUE INDEX IF NOT EXISTS idx_competitor_sales_source_listing
  ON public.competitor_sales(source, source_listing_id)
  WHERE source_listing_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_competitor_sales_source_url
  ON public.competitor_sales(source, listing_url)
  WHERE source_listing_id IS NULL;

-- Primary comp query path: make/model + year window, recency-ordered.
CREATE INDEX IF NOT EXISTS idx_competitor_sales_make_model_year
  ON public.competitor_sales(make, model, year, auction_end_date DESC);

-- Class-based aggregation path (F-150 / F-250 / Silverado 1500 rollups).
CREATE INDEX IF NOT EXISTS idx_competitor_sales_class_date
  ON public.competitor_sales(vehicle_class, auction_end_date DESC)
  WHERE vehicle_class IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_competitor_sales_vin
  ON public.competitor_sales(vin)
  WHERE vin IS NOT NULL;

-- -----------------------------------------------------------------------
-- Row Level Security
--   * Comps are non-sensitive aggregate market data: allow read to all roles.
--   * Writes are restricted to the service role (scraper ingestion).
-- -----------------------------------------------------------------------
ALTER TABLE public.competitor_sales ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Anyone can read competitor_sales" ON public.competitor_sales;
CREATE POLICY "Anyone can read competitor_sales"
  ON public.competitor_sales FOR SELECT
  USING (true);

DROP POLICY IF EXISTS "Service role can insert competitor_sales" ON public.competitor_sales;
CREATE POLICY "Service role can insert competitor_sales"
  ON public.competitor_sales FOR INSERT
  WITH CHECK (auth.role() = 'service_role');

DROP POLICY IF EXISTS "Service role can update competitor_sales" ON public.competitor_sales;
CREATE POLICY "Service role can update competitor_sales"
  ON public.competitor_sales FOR UPDATE
  USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');

COMMENT ON TABLE public.competitor_sales IS
  'Comparable completed/sold auction listings scraped from competitor sites (GovDeals, PublicSurplus, GovPlanet). Source of real market comps for DOS ceiling pricing.';
COMMENT ON COLUMN public.competitor_sales.sale_price IS 'Actual winning/sold price for the lot (sold listings only).';
COMMENT ON COLUMN public.competitor_sales.vehicle_class IS 'Normalized DealerScope vehicle class used for comp rollups (e.g. f-150, f-250, silverado-1500).';
COMMENT ON COLUMN public.competitor_sales.auction_end_date IS 'Timestamp the auction closed / sale completed; used for comp recency windows and date-range reporting.';
COMMENT ON COLUMN public.competitor_sales.raw_payload IS 'Full normalized source payload retained for replay and audit.';
