ALTER TABLE opportunities
  ADD COLUMN IF NOT EXISTS canonical_id VARCHAR(64),
  ADD COLUMN IF NOT EXISTS is_duplicate BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS canonical_record_id UUID REFERENCES opportunities(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS all_sources TEXT[] DEFAULT ARRAY[]::TEXT[],
  ADD COLUMN IF NOT EXISTS duplicate_count INTEGER DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_opportunities_canonical_id ON opportunities(canonical_id);

-- Partial unique index: only one canonical record per canonical_id
CREATE UNIQUE INDEX IF NOT EXISTS idx_opportunities_canonical_unique
  ON opportunities(canonical_id) WHERE is_duplicate = FALSE;

COMMENT ON COLUMN opportunities.canonical_id IS 'SHA256 of VIN (if present) or year+make+model+state+mileage_bucket';
COMMENT ON COLUMN opportunities.is_duplicate IS 'TRUE if another record with same canonical_id exists';
COMMENT ON COLUMN opportunities.all_sources IS 'All auction sites where this vehicle has been seen';
