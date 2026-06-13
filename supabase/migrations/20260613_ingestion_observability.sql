CREATE TABLE IF NOT EXISTS public.scrape_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id TEXT NOT NULL UNIQUE,
  source_name TEXT NOT NULL,
  actor_id TEXT,
  dataset_id TEXT,
  status TEXT NOT NULL DEFAULT 'started',
  item_count INTEGER NOT NULL DEFAULT 0,
  evaluated_count INTEGER NOT NULL DEFAULT 0,
  saved_count INTEGER NOT NULL DEFAULT 0,
  existing_count INTEGER NOT NULL DEFAULT 0,
  skipped_count INTEGER NOT NULL DEFAULT 0,
  failed_count INTEGER NOT NULL DEFAULT 0,
  duplicate_count INTEGER NOT NULL DEFAULT 0,
  hot_deal_count INTEGER NOT NULL DEFAULT 0,
  alert_blocked_count INTEGER NOT NULL DEFAULT 0,
  parse_event_count INTEGER NOT NULL DEFAULT 0,
  skip_reasons JSONB NOT NULL DEFAULT '{}'::jsonb,
  save_outcomes JSONB NOT NULL DEFAULT '{}'::jsonb,
  error_message TEXT,
  started_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT chk_scrape_runs_status
    CHECK (status IN ('started', 'processed', 'error', 'ignored_replay', 'ignored_stale'))
);

CREATE TABLE IF NOT EXISTS public.parse_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id TEXT NOT NULL REFERENCES public.scrape_runs(run_id) ON DELETE CASCADE,
  source_name TEXT NOT NULL,
  event_type TEXT NOT NULL,
  item_index INTEGER,
  listing_id TEXT,
  status TEXT NOT NULL,
  reason TEXT,
  error_message TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_scrape_runs_source_started
  ON public.scrape_runs (source_name, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_scrape_runs_status_started
  ON public.scrape_runs (status, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_parse_events_run_id
  ON public.parse_events (run_id);

CREATE INDEX IF NOT EXISTS idx_parse_events_source_created
  ON public.parse_events (source_name, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_parse_events_status_created
  ON public.parse_events (status, created_at DESC);

DROP VIEW IF EXISTS public.source_health_daily;
CREATE VIEW public.source_health_daily AS
SELECT
  source_name,
  started_at::date AS observed_date,
  COUNT(*)::integer AS total_runs,
  COUNT(*) FILTER (WHERE status = 'processed')::integer AS processed_runs,
  COUNT(*) FILTER (WHERE status = 'error')::integer AS failed_runs,
  SUM(item_count)::integer AS item_count,
  SUM(evaluated_count)::integer AS evaluated_count,
  SUM(saved_count)::integer AS saved_count,
  SUM(existing_count)::integer AS existing_count,
  SUM(skipped_count)::integer AS skipped_count,
  SUM(failed_count)::integer AS failed_count,
  SUM(parse_event_count)::integer AS parse_event_count,
  MAX(started_at) AS latest_started_at,
  MAX(completed_at) AS latest_completed_at
FROM public.scrape_runs
GROUP BY source_name, started_at::date;

ALTER TABLE public.scrape_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.parse_events ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS service_role_all_scrape_runs ON public.scrape_runs;
CREATE POLICY service_role_all_scrape_runs
  ON public.scrape_runs
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

DROP POLICY IF EXISTS service_role_all_parse_events ON public.parse_events;
CREATE POLICY service_role_all_parse_events
  ON public.parse_events
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

COMMENT ON TABLE public.scrape_runs IS
  'One durable source-run ledger row per Apify/webhook run.';
COMMENT ON TABLE public.parse_events IS
  'Sanitized per-item parse/save/skip events for source observability.';
COMMENT ON VIEW public.source_health_daily IS
  'Daily source health aggregate over scrape_runs.';

NOTIFY pgrst, 'reload schema';
