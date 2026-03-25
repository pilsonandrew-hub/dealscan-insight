ALTER TABLE public.opportunities
ADD COLUMN IF NOT EXISTS bid_amount FLOAT,
ADD COLUMN IF NOT EXISTS won BOOLEAN,
ADD COLUMN IF NOT EXISTS outcome_notes TEXT,
ADD COLUMN IF NOT EXISTS outcome_recorded_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_opportunities_outcome_recorded_at
  ON public.opportunities(outcome_recorded_at DESC)
  WHERE outcome_recorded_at IS NOT NULL;

COMMENT ON COLUMN public.opportunities.bid_amount IS
  'Recorded bid amount for an opportunity outcome.';

COMMENT ON COLUMN public.opportunities.won IS
  'Whether the recorded bid resulted in a win.';
