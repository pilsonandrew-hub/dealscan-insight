ALTER TABLE public.alert_log
  ADD COLUMN IF NOT EXISTS alert_type TEXT;

CREATE INDEX IF NOT EXISTS idx_alert_log_alert_type
  ON public.alert_log(alert_type);
