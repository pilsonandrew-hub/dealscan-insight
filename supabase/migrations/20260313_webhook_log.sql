CREATE TABLE IF NOT EXISTS webhook_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  received_at TIMESTAMPTZ DEFAULT now(),
  source TEXT,
  actor_id TEXT,
  run_id TEXT,
  item_count INTEGER,
  raw_payload JSONB,
  processing_status TEXT DEFAULT 'pending',
  error_message TEXT
);
