-- Separate referral queue for post-close auction outcome checks.
-- This is intentionally not the Comp Evidence Ledger. It records "go check
-- this closed auction" requests from lifecycle systems such as the sweeper.

CREATE TABLE IF NOT EXISTS public.post_close_outcome_requests (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  opportunity_id TEXT,
  source_site TEXT NOT NULL,
  source_listing_id TEXT NOT NULL,
  listing_url TEXT NOT NULL,
  auction_end_date TIMESTAMPTZ,
  referral_source TEXT NOT NULL,
  referral_reason TEXT NOT NULL,
  outcome_status TEXT NOT NULL DEFAULT 'pending_outcome_check',
  last_checked_at TIMESTAMPTZ,
  next_check_at TIMESTAMPTZ,
  check_attempts INTEGER NOT NULL DEFAULT 0,
  blocker_reason TEXT,
  year INTEGER,
  make TEXT,
  model TEXT,
  trim TEXT,
  vin TEXT,
  mileage INTEGER,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT chk_post_close_outcome_status
    CHECK (outcome_status IN (
      'pending_outcome_check',
      'checking',
      'sold_candidate_found',
      'not_sold',
      'price_not_visible',
      'source_blocked',
      'needs_review'
    ))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_post_close_outcome_requests_source_listing
  ON public.post_close_outcome_requests(source_site, source_listing_id);

CREATE INDEX IF NOT EXISTS idx_post_close_outcome_requests_status_next_check
  ON public.post_close_outcome_requests(outcome_status, next_check_at);

CREATE INDEX IF NOT EXISTS idx_post_close_outcome_requests_referral_source
  ON public.post_close_outcome_requests(referral_source);

ALTER TABLE public.post_close_outcome_requests ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE public.post_close_outcome_requests IS
  'Referral queue for closed auction outcome checks. Rows are not sold comps and must be proven before C.E.L candidate staging.';
