-- Ensure the retail-comp market price cache exists with the contract used by
-- backend.ingest.retail_comps and the internal pipeline-truth readiness check.

CREATE TABLE IF NOT EXISTS public.market_prices (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  year INTEGER NOT NULL,
  make TEXT NOT NULL,
  model TEXT NOT NULL,
  state TEXT,
  avg_price NUMERIC NOT NULL,
  low_price NUMERIC NOT NULL,
  high_price NUMERIC NOT NULL,
  sample_size INTEGER NOT NULL DEFAULT 0,
  source TEXT,
  source_api TEXT,
  source_run_id TEXT,
  source_url TEXT,
  confidence_notes TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  last_updated TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
  expires_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()) + interval '7 days',
  created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now())
);

ALTER TABLE public.market_prices
  ADD COLUMN IF NOT EXISTS year INTEGER,
  ADD COLUMN IF NOT EXISTS make TEXT,
  ADD COLUMN IF NOT EXISTS model TEXT,
  ADD COLUMN IF NOT EXISTS state TEXT,
  ADD COLUMN IF NOT EXISTS avg_price NUMERIC,
  ADD COLUMN IF NOT EXISTS low_price NUMERIC,
  ADD COLUMN IF NOT EXISTS high_price NUMERIC,
  ADD COLUMN IF NOT EXISTS sample_size INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS source TEXT,
  ADD COLUMN IF NOT EXISTS source_api TEXT,
  ADD COLUMN IF NOT EXISTS source_run_id TEXT,
  ADD COLUMN IF NOT EXISTS source_url TEXT,
  ADD COLUMN IF NOT EXISTS confidence_notes TEXT,
  ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS last_updated TIMESTAMPTZ DEFAULT timezone('utc', now()),
  ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ DEFAULT timezone('utc', now()) + interval '7 days',
  ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT timezone('utc', now()),
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT timezone('utc', now());

UPDATE public.market_prices
SET
  source = COALESCE(source, source_api),
  sample_size = COALESCE(sample_size, 0),
  metadata = COALESCE(metadata, '{}'::jsonb),
  last_updated = COALESCE(last_updated, timezone('utc', now())),
  expires_at = COALESCE(expires_at, timezone('utc', now()) + interval '7 days'),
  created_at = COALESCE(created_at, timezone('utc', now())),
  updated_at = COALESCE(updated_at, timezone('utc', now()))
WHERE
  source IS NULL
  OR sample_size IS NULL
  OR metadata IS NULL
  OR last_updated IS NULL
  OR expires_at IS NULL
  OR created_at IS NULL
  OR updated_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_market_prices_ymm_state_updated
  ON public.market_prices(year, make, model, state, last_updated DESC);

CREATE INDEX IF NOT EXISTS idx_market_prices_ymm_updated
  ON public.market_prices(year, make, model, last_updated DESC);

CREATE INDEX IF NOT EXISTS idx_market_prices_expires_at
  ON public.market_prices(expires_at);

CREATE INDEX IF NOT EXISTS idx_market_prices_provenance_source
  ON public.market_prices(source);

ALTER TABLE public.market_prices ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE public.market_prices IS 'Provenance-backed retail market comp cache for pricing maturity; do not seed from proxy-only MMR estimates.';
COMMENT ON COLUMN public.market_prices.source IS 'Evidence source for market comp readiness; required for rows to count as usable pricing substrate.';
COMMENT ON COLUMN public.market_prices.source_run_id IS 'Optional upstream run/import id for auditability.';
COMMENT ON COLUMN public.market_prices.confidence_notes IS 'Short operator-readable confidence/provenance notes for seeded or imported rows.';
