ALTER TABLE opportunities
  ADD COLUMN IF NOT EXISTS run_id VARCHAR(64),
  ADD COLUMN IF NOT EXISTS source_run_id VARCHAR(64),
  ADD COLUMN IF NOT EXISTS pipeline_step VARCHAR(32),
  ADD COLUMN IF NOT EXISTS step_status VARCHAR(16) DEFAULT 'pending',
  ADD COLUMN IF NOT EXISTS processed_at TIMESTAMPTZ DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_opportunities_run_id ON opportunities(run_id);

CREATE TABLE IF NOT EXISTS alert_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  opportunity_id UUID REFERENCES opportunities(id) ON DELETE SET NULL,
  run_id VARCHAR(64),
  alert_id VARCHAR(64),
  message_id VARCHAR(128),
  channel VARCHAR(32) DEFAULT 'telegram',
  sent_at TIMESTAMPTZ DEFAULT NOW(),
  delivery_state VARCHAR(16) DEFAULT 'sent',
  dos_score FLOAT,
  vehicle_title TEXT
);

CREATE INDEX IF NOT EXISTS idx_alert_log_run_id ON alert_log(run_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_alert_log_idempotency ON alert_log(run_id, opportunity_id) WHERE delivery_state != 'failed';
