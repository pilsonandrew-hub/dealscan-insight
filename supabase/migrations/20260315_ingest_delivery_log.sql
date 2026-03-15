CREATE TABLE IF NOT EXISTS ingest_delivery_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id VARCHAR(64) NOT NULL,
  listing_id TEXT NOT NULL,
  listing_url TEXT,
  opportunity_id UUID REFERENCES opportunities(id) ON DELETE SET NULL,
  channel VARCHAR(32) NOT NULL,
  status VARCHAR(32) NOT NULL,
  external_id TEXT,
  error_message TEXT,
  attempt_count INTEGER NOT NULL DEFAULT 1,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_ingest_delivery_log_unique
  ON ingest_delivery_log(run_id, listing_id, channel);

CREATE INDEX IF NOT EXISTS idx_ingest_delivery_log_run_id
  ON ingest_delivery_log(run_id);

CREATE INDEX IF NOT EXISTS idx_ingest_delivery_log_opportunity_id
  ON ingest_delivery_log(opportunity_id);
