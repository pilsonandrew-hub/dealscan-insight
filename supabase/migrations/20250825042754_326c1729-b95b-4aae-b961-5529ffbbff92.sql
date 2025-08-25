-- Create pipeline metrics table for observability
CREATE TABLE IF NOT EXISTS public.pipeline_metrics (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  metric_name TEXT NOT NULL,
  metric_value NUMERIC NOT NULL,
  metric_unit TEXT NOT NULL DEFAULT 'count',
  tags JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Index for efficient queries
CREATE INDEX IF NOT EXISTS idx_pipeline_metrics_name_time ON public.pipeline_metrics(metric_name, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_pipeline_metrics_tags ON public.pipeline_metrics USING GIN(tags);

-- RLS policies
ALTER TABLE public.pipeline_metrics ENABLE ROW LEVEL SECURITY;

CREATE POLICY "System can insert metrics" ON public.pipeline_metrics
  FOR INSERT WITH CHECK (true);

CREATE POLICY "Authenticated users can read metrics" ON public.pipeline_metrics
  FOR SELECT USING (auth.role() = 'authenticated');