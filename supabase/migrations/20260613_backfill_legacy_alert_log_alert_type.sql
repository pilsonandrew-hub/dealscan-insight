DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'alert_log'
      AND column_name = 'alert_type'
  ) THEN
    UPDATE public.alert_log
    SET alert_type = 'hot'
    WHERE channel = 'telegram'
      AND COALESCE(delivery_state, 'sent') <> 'failed'
      AND (alert_type IS NULL OR LOWER(TRIM(alert_type)) IN ('', 'hot_deal', 'hot'));

    UPDATE public.alert_log
    SET alert_type = 'platinum'
    WHERE channel = 'telegram'
      AND COALESCE(delivery_state, 'sent') <> 'failed'
      AND LOWER(TRIM(alert_type)) = 'platinum';
  END IF;
END $$;
