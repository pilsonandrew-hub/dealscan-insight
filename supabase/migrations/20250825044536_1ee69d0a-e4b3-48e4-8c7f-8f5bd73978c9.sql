-- Add content deduplication and compliance tracking
ALTER TABLE public_listings ADD COLUMN IF NOT EXISTS content_hash TEXT;
ALTER TABLE public_listings ADD COLUMN IF NOT EXISTS etag TEXT;
ALTER TABLE public_listings ADD COLUMN IF NOT EXISTS last_modified TEXT;
ALTER TABLE public_listings ADD COLUMN IF NOT EXISTS compliance_result JSONB DEFAULT '{}';

-- Create unique index for content deduplication
CREATE UNIQUE INDEX IF NOT EXISTS uniq_listing_by_hash ON public_listings(content_hash) WHERE content_hash IS NOT NULL;

-- Create labels table for human-in-the-loop corrections
CREATE TABLE IF NOT EXISTS labels (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  url TEXT NOT NULL,
  cluster_id TEXT,
  field TEXT NOT NULL,
  old_value TEXT,
  new_value TEXT NOT NULL,
  css_path TEXT,
  user_id UUID,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Enable RLS on labels table
ALTER TABLE labels ENABLE ROW LEVEL SECURITY;

-- Create policies for labels
CREATE POLICY "Users can insert their own labels" 
ON labels FOR INSERT 
WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can view their own labels" 
ON labels FOR SELECT 
USING (auth.uid() = user_id);

-- Create canary_tests table for CI/CD validation
CREATE TABLE IF NOT EXISTS canary_tests (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  site_name TEXT NOT NULL,
  test_url TEXT NOT NULL,
  expected_fields JSONB NOT NULL,
  last_run TIMESTAMPTZ,
  pass_rate NUMERIC DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Enable RLS on canary_tests
ALTER TABLE canary_tests ENABLE ROW LEVEL SECURITY;

-- Allow authenticated users to read canary tests
CREATE POLICY "Authenticated users can read canary tests" 
ON canary_tests FOR SELECT 
USING (auth.role() = 'authenticated');

-- Create extraction_strategies table for fallback chain tracking
CREATE TABLE IF NOT EXISTS extraction_strategies (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  site_name TEXT NOT NULL,
  cluster_id TEXT,
  field_name TEXT NOT NULL,
  strategy TEXT NOT NULL CHECK (strategy IN ('selector', 'ml', 'llm', 'human')),
  confidence_threshold NUMERIC DEFAULT 0.8,
  fallback_order INTEGER NOT NULL,
  selector_config JSONB,
  ml_config JSONB,
  llm_config JSONB,
  success_rate NUMERIC DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Enable RLS on extraction_strategies
ALTER TABLE extraction_strategies ENABLE ROW LEVEL SECURITY;

-- Allow authenticated users to read extraction strategies
CREATE POLICY "Authenticated users can read extraction strategies" 
ON extraction_strategies FOR SELECT 
USING (auth.role() = 'authenticated');

-- Create index for fast lookups
CREATE INDEX IF NOT EXISTS idx_extraction_strategies_lookup ON extraction_strategies(site_name, cluster_id, field_name);

-- Add triggers for updated_at
CREATE TRIGGER update_labels_updated_at
BEFORE UPDATE ON labels
FOR EACH ROW
EXECUTE FUNCTION handle_updated_at();

CREATE TRIGGER update_canary_tests_updated_at
BEFORE UPDATE ON canary_tests
FOR EACH ROW
EXECUTE FUNCTION handle_updated_at();

CREATE TRIGGER update_extraction_strategies_updated_at
BEFORE UPDATE ON extraction_strategies
FOR EACH ROW
EXECUTE FUNCTION handle_updated_at();