ALTER TABLE public.opportunities
  ADD COLUMN IF NOT EXISTS first_seen_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS relist_count INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS bid_change_count INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS source_fingerprint TEXT;

UPDATE public.opportunities
SET
  first_seen_at = COALESCE(first_seen_at, created_at, updated_at, NOW()),
  last_seen_at = COALESCE(last_seen_at, updated_at, created_at, NOW()),
  relist_count = COALESCE(relist_count, 0),
  bid_change_count = COALESCE(bid_change_count, 0),
  source_fingerprint = COALESCE(
    source_fingerprint,
    md5(
      lower(trim(coalesce(source_site, source, ''))) || '|' ||
      coalesce(
        nullif(trim(canonical_id), ''),
        nullif(upper(trim(vin)), ''),
        nullif(trim(listing_url), ''),
        concat_ws(
          '|',
          nullif(trim(year::TEXT), ''),
          nullif(lower(trim(make)), ''),
          nullif(lower(trim(model)), ''),
          nullif(upper(trim(state)), '')
        )
      )
    )
  )
WHERE
  first_seen_at IS NULL
  OR last_seen_at IS NULL
  OR relist_count IS NULL
  OR bid_change_count IS NULL
  OR source_fingerprint IS NULL;

CREATE INDEX IF NOT EXISTS idx_opportunities_lifecycle_last_seen
  ON public.opportunities (last_seen_at DESC);

CREATE INDEX IF NOT EXISTS idx_opportunities_source_fingerprint
  ON public.opportunities (source_fingerprint);

COMMENT ON COLUMN public.opportunities.first_seen_at IS
  'First time DealerScope observed this source-side opportunity identity.';
COMMENT ON COLUMN public.opportunities.last_seen_at IS
  'Most recent ingest observation for this opportunity identity.';
COMMENT ON COLUMN public.opportunities.relist_count IS
  'Number of observed auction identity changes for the same canonical vehicle/opportunity.';
COMMENT ON COLUMN public.opportunities.bid_change_count IS
  'Number of observed current_bid changes across duplicate/refresh ingests.';
COMMENT ON COLUMN public.opportunities.source_fingerprint IS
  'Stable source + canonical/listing fingerprint used for lifecycle continuity.';

NOTIFY pgrst, 'reload schema';
