-- Migration: Add index on opportunities.vin for fast VIN deduplication lookups
-- Created: 2026-03-18

-- Create a non-unique index on vin (VINs can appear across multiple auction sources,
-- but we deduplicate by checking for live records with the same VIN before insert)
CREATE INDEX IF NOT EXISTS idx_opportunities_vin
    ON opportunities (vin)
    WHERE vin IS NOT NULL;
