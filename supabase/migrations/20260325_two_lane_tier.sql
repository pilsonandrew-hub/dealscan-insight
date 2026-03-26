ALTER TABLE opportunities
  ADD COLUMN IF NOT EXISTS designated_lane TEXT DEFAULT 'unassigned',
  ADD COLUMN IF NOT EXISTS dos_premium NUMERIC,
  ADD COLUMN IF NOT EXISTS dos_standard NUMERIC,
  ADD COLUMN IF NOT EXISTS risk_flags TEXT[] DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS vehicle_tier TEXT DEFAULT 'unassigned',
  ADD COLUMN IF NOT EXISTS ai_confidence_score NUMERIC,
  ADD COLUMN IF NOT EXISTS bid_ceiling_pct NUMERIC,
  ADD COLUMN IF NOT EXISTS min_margin_target NUMERIC;

CREATE INDEX IF NOT EXISTS idx_opportunities_lane ON opportunities (designated_lane);
CREATE INDEX IF NOT EXISTS idx_opportunities_tier_dos ON opportunities (vehicle_tier, dos_premium, dos_standard);

UPDATE opportunities SET
  designated_lane = CASE
    WHEN year IS NOT NULL AND (EXTRACT(YEAR FROM NOW()) - year) <= 4 THEN 'premium'
    WHEN year IS NOT NULL AND (EXTRACT(YEAR FROM NOW()) - year) <= 10 THEN 'standard'
    WHEN year IS NOT NULL AND (EXTRACT(YEAR FROM NOW()) - year) > 10 THEN 'rejected'
    ELSE 'unassigned'
  END,
  vehicle_tier = designated_lane
WHERE designated_lane = 'unassigned';
