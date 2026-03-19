-- SniperScope bid assistant — sniper_targets table
-- Migration: 20260318_sniper_targets.sql

CREATE TABLE public.sniper_targets (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id             UUID NOT NULL,
  opportunity_id      UUID NOT NULL REFERENCES public.opportunities(id) ON DELETE CASCADE,
  max_bid             NUMERIC NOT NULL,
  status              TEXT DEFAULT 'active',  -- active, cancelled, expired, ceiling_exceeded
  alert_60min_sent    BOOLEAN DEFAULT FALSE,
  alert_15min_sent    BOOLEAN DEFAULT FALSE,
  alert_5min_sent     BOOLEAN DEFAULT FALSE,
  telegram_chat_id    TEXT,                   -- user's telegram chat ID for per-user alerts
  created_at          TIMESTAMPTZ DEFAULT NOW(),
  updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_sniper_targets_user ON public.sniper_targets(user_id);
CREATE INDEX idx_sniper_targets_status ON public.sniper_targets(status) WHERE status = 'active';
-- Prevent duplicate active targets for the same user+opportunity pair
CREATE UNIQUE INDEX idx_sniper_targets_user_opp_active
  ON public.sniper_targets(user_id, opportunity_id)
  WHERE status = 'active';

ALTER TABLE public.sniper_targets ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage own sniper targets"
  ON public.sniper_targets
  FOR ALL
  USING (auth.uid() = user_id);

-- Updated_at trigger (reuse pattern from existing migrations)
CREATE OR REPLACE FUNCTION public.set_sniper_targets_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_sniper_targets_updated_at
  BEFORE UPDATE ON public.sniper_targets
  FOR EACH ROW
  EXECUTE FUNCTION public.set_sniper_targets_updated_at();
