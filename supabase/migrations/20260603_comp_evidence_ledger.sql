-- DealerScope Comp Evidence Ledger v1.
-- Purpose: quarantine completed-sale evidence before any comp can influence
-- DealerScope pricing, alerts, or outcome tracking.

CREATE TABLE IF NOT EXISTS public.market_scout_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id TEXT NOT NULL UNIQUE,
  source_name TEXT NOT NULL,
  actor_id TEXT,
  scraper_run_id TEXT,
  schedule_name TEXT,
  policy_version TEXT NOT NULL,
  extractor_version TEXT,
  schema_version TEXT NOT NULL DEFAULT 'comp-evidence-ledger-v1',
  status TEXT NOT NULL DEFAULT 'started',
  vehicle_scope JSONB NOT NULL DEFAULT '[]'::jsonb,
  source_policy JSONB NOT NULL DEFAULT '{}'::jsonb,
  records_scanned INTEGER NOT NULL DEFAULT 0,
  records_found INTEGER NOT NULL DEFAULT 0,
  records_candidate INTEGER NOT NULL DEFAULT 0,
  records_verified INTEGER NOT NULL DEFAULT 0,
  records_rejected INTEGER NOT NULL DEFAULT 0,
  records_needs_review INTEGER NOT NULL DEFAULT 0,
  records_promoted INTEGER NOT NULL DEFAULT 0,
  error_count INTEGER NOT NULL DEFAULT 0,
  source_blocker TEXT,
  started_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
  completed_at TIMESTAMPTZ,
  notes TEXT,
  raw_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now())
);

CREATE TABLE IF NOT EXISTS public.sold_comp_candidates (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id TEXT NOT NULL REFERENCES public.market_scout_runs(run_id) ON DELETE RESTRICT,
  source_name TEXT NOT NULL,
  source_listing_id TEXT NOT NULL,
  listing_url TEXT NOT NULL,
  evidence_ref TEXT,
  evidence_url TEXT,
  raw_artifact_path TEXT,
  screenshot_path TEXT,
  extracted_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
  captured_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
  sale_status_raw TEXT,
  sale_status_normalized TEXT,
  sale_date DATE,
  sold_price_raw NUMERIC,
  sold_price_normalized NUMERIC,
  sold_price_hammer NUMERIC,
  buyer_premium NUMERIC,
  fees NUMERIC,
  price_includes_fees BOOLEAN,
  sold_price_all_in NUMERIC,
  price_basis TEXT NOT NULL DEFAULT 'source_reported',
  currency TEXT NOT NULL DEFAULT 'USD',
  year INTEGER,
  make TEXT,
  model TEXT,
  trim TEXT,
  vin TEXT,
  mileage INTEGER,
  condition_text TEXT,
  defect_signals TEXT[],
  title_brand_status TEXT,
  location_city TEXT,
  location_state TEXT,
  region TEXT,
  seller_name TEXT,
  channel TEXT NOT NULL,
  vehicle_class TEXT,
  target_match BOOLEAN,
  target_reason TEXT,
  raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  scraper_run_id TEXT,
  extractor_version TEXT NOT NULL,
  schema_version TEXT NOT NULL DEFAULT 'comp-evidence-ledger-v1',
  source_policy_version TEXT NOT NULL,
  extraction_confidence NUMERIC,
  field_completeness_pct NUMERIC,
  candidate_status TEXT NOT NULL DEFAULT 'candidate',
  rejection_reason TEXT,
  duplicate_of UUID REFERENCES public.sold_comp_candidates(id) ON DELETE SET NULL,
  dedup_key TEXT NOT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT chk_sold_comp_candidate_status
    CHECK (candidate_status IN ('candidate', 'verified', 'rejected', 'needs_review')),
  CONSTRAINT chk_sold_comp_channel
    CHECK (channel IN ('gov', 'surplus', 'dealer', 'retail', 'salvage', 'unknown')),
  CONSTRAINT chk_sold_comp_currency
    CHECK (currency = 'USD'),
  CONSTRAINT chk_sold_comp_price_basis
    CHECK (price_basis IN ('hammer', 'all_in', 'source_reported', 'unknown'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_sold_comp_candidates_source_listing
  ON public.sold_comp_candidates(source_name, source_listing_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_sold_comp_candidates_dedup_key
  ON public.sold_comp_candidates(dedup_key);

CREATE INDEX IF NOT EXISTS idx_sold_comp_candidates_run_id
  ON public.sold_comp_candidates(run_id);

CREATE INDEX IF NOT EXISTS idx_sold_comp_candidates_status
  ON public.sold_comp_candidates(candidate_status);

CREATE INDEX IF NOT EXISTS idx_sold_comp_candidates_vehicle
  ON public.sold_comp_candidates(make, model, year, trim);

CREATE INDEX IF NOT EXISTS idx_sold_comp_candidates_channel_date
  ON public.sold_comp_candidates(channel, sale_date DESC);

CREATE TABLE IF NOT EXISTS public.sold_comp_reviews (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  candidate_id UUID NOT NULL REFERENCES public.sold_comp_candidates(id) ON DELETE CASCADE,
  run_id TEXT NOT NULL REFERENCES public.market_scout_runs(run_id) ON DELETE RESTRICT,
  reviewer TEXT NOT NULL,
  reviewer_version TEXT NOT NULL,
  review_status TEXT NOT NULL,
  rejection_reason TEXT,
  review_notes TEXT,
  completion_confidence NUMERIC,
  price_confidence NUMERIC,
  identity_confidence NUMERIC,
  condition_confidence NUMERIC,
  mileage_confidence NUMERIC,
  overall_verification_confidence NUMERIC,
  deterministic_checks JSONB NOT NULL DEFAULT '{}'::jsonb,
  llm_enrichment JSONB NOT NULL DEFAULT '{}'::jsonb,
  human_required BOOLEAN NOT NULL DEFAULT false,
  reviewed_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
  created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT chk_sold_comp_review_status
    CHECK (review_status IN ('accepted', 'rejected', 'needs_review'))
);

CREATE INDEX IF NOT EXISTS idx_sold_comp_reviews_candidate_id
  ON public.sold_comp_reviews(candidate_id);

CREATE INDEX IF NOT EXISTS idx_sold_comp_reviews_run_id
  ON public.sold_comp_reviews(run_id);

CREATE TABLE IF NOT EXISTS public.verified_sold_comps (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  candidate_id UUID NOT NULL UNIQUE REFERENCES public.sold_comp_candidates(id) ON DELETE RESTRICT,
  source_name TEXT NOT NULL,
  source_listing_id TEXT NOT NULL,
  listing_url TEXT NOT NULL,
  evidence_ref TEXT NOT NULL,
  sale_date DATE NOT NULL,
  sold_price_hammer NUMERIC,
  buyer_premium NUMERIC,
  fees NUMERIC,
  sold_price_all_in NUMERIC NOT NULL,
  price_basis TEXT NOT NULL,
  currency TEXT NOT NULL DEFAULT 'USD',
  year INTEGER NOT NULL,
  make TEXT NOT NULL,
  model TEXT NOT NULL,
  trim TEXT,
  vin TEXT,
  mileage INTEGER,
  title_brand_status TEXT,
  condition_text TEXT,
  defect_signals TEXT[],
  location_city TEXT,
  location_state TEXT,
  region TEXT,
  channel TEXT NOT NULL,
  normalized_make TEXT,
  normalized_model TEXT,
  normalized_trim TEXT,
  dedup_key TEXT NOT NULL UNIQUE,
  extractor_version TEXT NOT NULL,
  verifier_version TEXT NOT NULL,
  source_policy_version TEXT NOT NULL,
  verification_status TEXT NOT NULL DEFAULT 'verified',
  verified_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
  verification_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT chk_verified_sold_comp_status
    CHECK (verification_status = 'verified'),
  CONSTRAINT chk_verified_sold_comp_channel
    CHECK (channel IN ('gov', 'surplus', 'dealer', 'retail', 'salvage', 'unknown')),
  CONSTRAINT chk_verified_sold_comp_currency
    CHECK (currency = 'USD'),
  CONSTRAINT chk_verified_sold_comp_price_basis
    CHECK (price_basis IN ('hammer', 'all_in', 'source_reported', 'unknown'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_verified_sold_comps_source_listing
  ON public.verified_sold_comps(source_name, source_listing_id);

CREATE INDEX IF NOT EXISTS idx_verified_sold_comps_vehicle_date
  ON public.verified_sold_comps(make, model, year, sale_date DESC);

CREATE INDEX IF NOT EXISTS idx_verified_sold_comps_channel_date
  ON public.verified_sold_comps(channel, sale_date DESC);

CREATE INDEX IF NOT EXISTS idx_verified_sold_comps_vin
  ON public.verified_sold_comps(vin)
  WHERE vin IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.market_scout_artifacts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id TEXT NOT NULL REFERENCES public.market_scout_runs(run_id) ON DELETE RESTRICT,
  candidate_id UUID REFERENCES public.sold_comp_candidates(id) ON DELETE CASCADE,
  source_name TEXT NOT NULL,
  artifact_type TEXT NOT NULL,
  storage_path TEXT NOT NULL,
  content_hash TEXT,
  dom_hash TEXT,
  captured_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT chk_market_scout_artifact_type
    CHECK (artifact_type IN ('raw_html', 'raw_json', 'screenshot', 'metadata'))
);

CREATE INDEX IF NOT EXISTS idx_market_scout_artifacts_run_id
  ON public.market_scout_artifacts(run_id);

CREATE INDEX IF NOT EXISTS idx_market_scout_artifacts_candidate_id
  ON public.market_scout_artifacts(candidate_id);

CREATE INDEX IF NOT EXISTS idx_market_scout_artifacts_content_hash
  ON public.market_scout_artifacts(content_hash)
  WHERE content_hash IS NOT NULL;

ALTER TABLE public.market_scout_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sold_comp_candidates ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sold_comp_reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.verified_sold_comps ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.market_scout_artifacts ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE public.market_scout_runs IS 'Per-run audit ledger for deterministic sold-comp collection and verification.';
COMMENT ON TABLE public.sold_comp_candidates IS 'Quarantine table for untrusted completed-sale candidate comps. DealerScope scoring must not read this table.';
COMMENT ON TABLE public.sold_comp_reviews IS 'Deterministic and human review decisions for sold-comp candidates.';
COMMENT ON TABLE public.verified_sold_comps IS 'Trusted sold comps after evidence and verifier promotion. This is still gated before pricing influence.';
COMMENT ON TABLE public.market_scout_artifacts IS 'Pointers to raw evidence artifacts stored outside Postgres.';
COMMENT ON COLUMN public.sold_comp_candidates.channel IS 'Auction/channel bias control: gov, surplus, dealer, retail, salvage, or unknown.';
COMMENT ON COLUMN public.sold_comp_candidates.sold_price_all_in IS 'Comparable price after visible buyer premium/fees when available; not a magic value when fees are hidden.';
COMMENT ON COLUMN public.sold_comp_candidates.raw_payload IS 'Full source payload retained for replay and audit.';
COMMENT ON COLUMN public.verified_sold_comps.evidence_ref IS 'Operator-clickable pointer to evidence proving the completed sale.';
