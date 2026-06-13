-- Persist governed bidder-depth evidence when source payloads provide it.
-- NULL means unknown; do not infer bidder depth from bid price or auction stage.
ALTER TABLE public.opportunities
ADD COLUMN IF NOT EXISTS bidder_count INTEGER;

ALTER TABLE public.opportunities
DROP CONSTRAINT IF EXISTS opportunities_bidder_count_nonnegative;

ALTER TABLE public.opportunities
ADD CONSTRAINT opportunities_bidder_count_nonnegative
CHECK (bidder_count IS NULL OR bidder_count >= 0);

WITH bidder_values AS (
  SELECT
    id,
    bidder_value
  FROM public.opportunities
  CROSS JOIN LATERAL (
    VALUES
      (raw_data->>'bidder_count'),
      (raw_data->>'bid_count'),
      (raw_data->>'bidCount'),
      (raw_data->>'bids_count'),
      (raw_data->>'bidsCount'),
      (raw_data->>'number_of_bids'),
      (raw_data->>'numberOfBids'),
      (raw_data->>'num_bids'),
      (raw_data->>'numBids')
  ) AS values(bidder_value)
  WHERE raw_data IS NOT NULL
    AND bidder_value ~ '^[0-9]+(\\.[0-9]+)?$'
),
bidder_evidence AS (
  SELECT
    id,
    MAX(FLOOR(bidder_value::numeric)::integer) AS raw_bidder_count
  FROM bidder_values
  GROUP BY id
)
UPDATE public.opportunities
SET bidder_count = bidder_evidence.raw_bidder_count,
    updated_at = NOW()
FROM bidder_evidence
WHERE opportunities.id = bidder_evidence.id
  AND opportunities.bidder_count IS NULL
  AND bidder_evidence.raw_bidder_count > 0;
