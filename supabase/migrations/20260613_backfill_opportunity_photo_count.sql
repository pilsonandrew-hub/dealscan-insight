-- Backfill governed photo_count from existing sanitized raw_data image evidence.
-- This only raises zero-count rows when raw_data already carries a photo array
-- or a single image URL; it never lowers an existing governed count.

WITH photo_evidence AS (
  SELECT
    id,
    CASE
      WHEN jsonb_typeof(raw_data->'photos') = 'array'
        THEN jsonb_array_length(raw_data->'photos')
      WHEN jsonb_typeof(raw_data->'photo_urls') = 'array'
        THEN jsonb_array_length(raw_data->'photo_urls')
      WHEN NULLIF(raw_data->>'photo_url', '') IS NOT NULL
        THEN 1
      WHEN NULLIF(raw_data->>'image_url', '') IS NOT NULL
        THEN 1
      WHEN NULLIF(raw_data->>'imageUrl', '') IS NOT NULL
        THEN 1
      ELSE 0
    END AS raw_photo_count
  FROM public.opportunities
  WHERE photo_count = 0
)
UPDATE public.opportunities AS opportunities
SET
  photo_count = photo_evidence.raw_photo_count,
  updated_at = NOW()
FROM photo_evidence
WHERE opportunities.id = photo_evidence.id
  AND photo_evidence.raw_photo_count > opportunities.photo_count;
