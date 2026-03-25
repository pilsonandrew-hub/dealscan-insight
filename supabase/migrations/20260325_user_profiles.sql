-- DealerScope missing profile + alert log tables
-- Migration: 20260325_user_profiles.sql

CREATE TABLE IF NOT EXISTS public.user_profiles (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  display_name TEXT,
  telegram_chat_id TEXT,
  preferences JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_profiles_telegram_chat_id
  ON public.user_profiles(telegram_chat_id);

ALTER TABLE public.user_profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users manage own profile"
  ON public.user_profiles
  FOR ALL
  USING (auth.uid() = id)
  WITH CHECK (auth.uid() = id);

CREATE OR REPLACE FUNCTION public.set_user_profiles_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_user_profiles_updated_at ON public.user_profiles;
CREATE TRIGGER trg_user_profiles_updated_at
  BEFORE UPDATE ON public.user_profiles
  FOR EACH ROW
  EXECUTE FUNCTION public.set_user_profiles_updated_at();

CREATE TABLE IF NOT EXISTS public.sniper_alert_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  sniper_target_id UUID REFERENCES public.sniper_targets(id) ON DELETE CASCADE,
  alert_type TEXT,
  sent_at TIMESTAMPTZ DEFAULT NOW(),
  telegram_message_id TEXT,
  success BOOLEAN DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_sniper_alert_log_sniper_target_id
  ON public.sniper_alert_log(sniper_target_id);

CREATE INDEX IF NOT EXISTS idx_sniper_alert_log_sent_at
  ON public.sniper_alert_log(sent_at DESC);

CREATE INDEX IF NOT EXISTS idx_sniper_alert_log_alert_type
  ON public.sniper_alert_log(alert_type);

ALTER TABLE public.sniper_alert_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users manage own sniper alert log"
  ON public.sniper_alert_log
  FOR ALL
  USING (
    EXISTS (
      SELECT 1
      FROM public.sniper_targets st
      WHERE st.id = sniper_target_id
        AND st.user_id = auth.uid()
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1
      FROM public.sniper_targets st
      WHERE st.id = sniper_target_id
        AND st.user_id = auth.uid()
    )
  );
