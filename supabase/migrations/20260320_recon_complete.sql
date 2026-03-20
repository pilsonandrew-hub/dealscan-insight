-- ============================================================
-- DEALERSCOPE RECON — Complete Migration
-- Run in: supabase.com/dashboard/project/lbnxzvqppccajllsqaaw/sql/new
-- ============================================================

-- ── 1. Fix dealer_sales table (missing columns) ──────────────

ALTER TABLE public.dealer_sales
ADD COLUMN IF NOT EXISTS year INTEGER,
ADD COLUMN IF NOT EXISTS make TEXT,
ADD COLUMN IF NOT EXISTS model TEXT,
ADD COLUMN IF NOT EXISTS trim TEXT,
ADD COLUMN IF NOT EXISTS color TEXT,
ADD COLUMN IF NOT EXISTS doors TEXT,
ADD COLUMN IF NOT EXISTS cylinders TEXT,
ADD COLUMN IF NOT EXISTS fuel_type TEXT,
ADD COLUMN IF NOT EXISTS transmission TEXT,
ADD COLUMN IF NOT EXISTS drive_type TEXT,
ADD COLUMN IF NOT EXISTS odometer INTEGER,
ADD COLUMN IF NOT EXISTS sale_price NUMERIC,
ADD COLUMN IF NOT EXISTS auction_location TEXT,
ADD COLUMN IF NOT EXISTS sale_date_label TEXT,
ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'manheim_postsale';

CREATE INDEX IF NOT EXISTS idx_dealer_sales_make_model_year ON public.dealer_sales(make, model, year);
CREATE INDEX IF NOT EXISTS idx_dealer_sales_odometer ON public.dealer_sales(odometer);
CREATE INDEX IF NOT EXISTS idx_dealer_sales_sale_price ON public.dealer_sales(sale_price);
CREATE INDEX IF NOT EXISTS idx_dealer_sales_location ON public.dealer_sales(auction_location);

-- ── 2. Market calibration table ──────────────────────────────

CREATE TABLE IF NOT EXISTS public.market_calibration (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  make TEXT NOT NULL,
  model TEXT NOT NULL,
  year INTEGER NOT NULL,
  mileage_band TEXT NOT NULL,
  region TEXT DEFAULT 'national',
  avg_retail_price NUMERIC,
  avg_days_listed INTEGER,
  comp_count INTEGER DEFAULT 0,
  mmr_price NUMERIC,
  mmr_trend TEXT CHECK (mmr_trend IN ('up','down','flat')),
  data_source TEXT,
  last_updated TIMESTAMPTZ DEFAULT NOW(),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_market_cal_make_model_year ON public.market_calibration(make, model, year);
CREATE INDEX IF NOT EXISTS idx_market_cal_updated ON public.market_calibration(last_updated DESC);

-- ── 3. Recon evaluations table ───────────────────────────────

CREATE TABLE IF NOT EXISTS public.recon_evaluations (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID,
  make TEXT NOT NULL,
  model TEXT NOT NULL,
  year INTEGER NOT NULL CHECK (year >= 1990 AND year <= 2030),
  mileage INTEGER NOT NULL CHECK (mileage >= 1 AND mileage <= 300000),
  asking_price NUMERIC NOT NULL CHECK (asking_price > 0),
  source TEXT DEFAULT 'Other',
  state TEXT,
  vin TEXT,
  trim TEXT,
  condition_grade TEXT CHECK (condition_grade IN ('Excellent','Good','Fair','Poor')),
  title_status TEXT DEFAULT 'clean',
  is_fleet BOOLEAN DEFAULT false,
  fleet_has_records BOOLEAN DEFAULT false,
  condition_notes TEXT,
  pessimistic_sale NUMERIC,
  optimistic_sale NUMERIC,
  avg_sale NUMERIC,
  pricing_source TEXT,
  comp_count INTEGER DEFAULT 0,
  reliability_grade TEXT CHECK (reliability_grade IN ('A+','A','B','C')),
  reliability_reason TEXT,
  comps_stale BOOLEAN DEFAULT false,
  dos_score NUMERIC,
  confidence_multiplier NUMERIC,
  adjusted_dos NUMERIC,
  margin_score NUMERIC,
  velocity_score NUMERIC,
  segment_score NUMERIC,
  model_score NUMERIC,
  verdict TEXT CHECK (verdict IN ('HOT BUY','BUY','WATCH','PASS')),
  verdict_reason TEXT,
  max_bid NUMERIC,
  ctm_ceiling NUMERIC,
  condition_penalty NUMERIC DEFAULT 0,
  fleet_stigma_penalty NUMERIC DEFAULT 0,
  transport_cost NUMERIC DEFAULT 0,
  buyer_premium NUMERIC DEFAULT 0,
  doc_fee NUMERIC DEFAULT 0,
  manheim_sell_fee NUMERIC DEFAULT 250,
  total_all_in_cost NUMERIC,
  profit_expected NUMERIC,
  profit_pessimistic NUMERIC,
  profit_optimistic NUMERIC,
  roi_pct NUMERIC,
  promoted_to_pipeline BOOLEAN DEFAULT false,
  opportunity_id UUID,
  sniper_armed BOOLEAN DEFAULT false,
  full_report JSONB DEFAULT '{}'::jsonb,
  evaluated_at TIMESTAMPTZ DEFAULT NOW(),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_recon_user ON public.recon_evaluations(user_id);
CREATE INDEX IF NOT EXISTS idx_recon_verdict ON public.recon_evaluations(verdict);
CREATE INDEX IF NOT EXISTS idx_recon_dos ON public.recon_evaluations(adjusted_dos DESC);
CREATE INDEX IF NOT EXISTS idx_recon_created ON public.recon_evaluations(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_recon_make_model ON public.recon_evaluations(make, model);
CREATE INDEX IF NOT EXISTS idx_recon_not_promoted ON public.recon_evaluations(promoted_to_pipeline) WHERE promoted_to_pipeline = false;

ALTER TABLE public.recon_evaluations ENABLE ROW LEVEL SECURITY;
CREATE POLICY "recon_select_own" ON public.recon_evaluations FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "recon_insert_own" ON public.recon_evaluations FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "recon_update_own" ON public.recon_evaluations FOR UPDATE USING (auth.uid() = user_id);

ALTER TABLE public.market_calibration ENABLE ROW LEVEL SECURITY;
CREATE POLICY "market_cal_read_all" ON public.market_calibration FOR SELECT USING (true);

-- ── 4. Extend opportunities for Recon promotion ───────────────

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='opportunities' AND column_name='source_type') THEN
    ALTER TABLE public.opportunities ADD COLUMN source_type TEXT DEFAULT 'scraped';
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='opportunities' AND column_name='recon_id') THEN
    ALTER TABLE public.opportunities ADD COLUMN recon_id UUID;
  END IF;
END $$;
