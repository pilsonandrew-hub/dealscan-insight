CREATE TABLE IF NOT EXISTS public.user_passes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL,
  opportunity_id UUID NOT NULL REFERENCES public.opportunities(id) ON DELETE CASCADE,
  passed_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(user_id, opportunity_id)
);
ALTER TABLE public.user_passes ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users manage own passes" ON public.user_passes FOR ALL USING (auth.uid() = user_id);
CREATE INDEX IF NOT EXISTS idx_user_passes_user ON public.user_passes(user_id);
