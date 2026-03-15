ALTER TABLE public.opportunities
ADD COLUMN IF NOT EXISTS expected_close_bid FLOAT,
ADD COLUMN IF NOT EXISTS current_bid_trust_score FLOAT,
ADD COLUMN IF NOT EXISTS expected_close_source TEXT,
ADD COLUMN IF NOT EXISTS auction_stage_hours_remaining FLOAT;

COMMENT ON COLUMN public.opportunities.expected_close_bid IS
  'Nullable groundwork for expected-close modeling. Remains NULL until a forecast is computed.';

COMMENT ON COLUMN public.opportunities.current_bid_trust_score IS
  'Conservative 0-1 trust score for the current bid based on auction stage and pricing provenance.';

COMMENT ON COLUMN public.opportunities.expected_close_source IS
  'Nullable provenance label for expected_close_bid when a future sprint starts computing it.';

COMMENT ON COLUMN public.opportunities.auction_stage_hours_remaining IS
  'Hours remaining until auction close at score time, clamped at zero when the end time is in the past.';
