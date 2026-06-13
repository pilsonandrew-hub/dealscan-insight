-- Correct legacy governed photo_count when raw_data has empty photo arrays
-- plus a single image URL. The previous backfill could stop at an empty
-- raw_data.photos array and miss image_url/photo_url evidence.
--
-- This migration is monotonic: it only raises photo_count when existing
-- sanitized raw_data evidence proves a higher count.

WITH photo_evidence AS (
  SELECT
    id,
    GREATEST(
      CASE
        WHEN jsonb_typeof(raw_data->'photos') = 'array'
          THEN (
            SELECT COUNT(*)::INTEGER
            FROM jsonb_array_elements_text(raw_data->'photos') AS photo(value)
            WHERE NULLIF(BTRIM(photo.value), '') IS NOT NULL
          )
        ELSE 0
      END,
      CASE
        WHEN jsonb_typeof(raw_data->'photo_urls') = 'array'
          THEN (
            SELECT COUNT(*)::INTEGER
            FROM jsonb_array_elements_text(raw_data->'photo_urls') AS photo(value)
            WHERE NULLIF(BTRIM(photo.value), '') IS NOT NULL
          )
        ELSE 0
      END,
      CASE WHEN NULLIF(BTRIM(raw_data->>'photo_url'), '') IS NOT NULL THEN 1 ELSE 0 END,
      CASE WHEN NULLIF(BTRIM(raw_data->>'image_url'), '') IS NOT NULL THEN 1 ELSE 0 END,
      CASE WHEN NULLIF(BTRIM(raw_data->>'imageUrl'), '') IS NOT NULL THEN 1 ELSE 0 END
    ) AS raw_photo_count
  FROM public.opportunities
)
UPDATE public.opportunities AS opportunities
SET
  photo_count = photo_evidence.raw_photo_count,
  updated_at = NOW()
FROM photo_evidence
WHERE opportunities.id = photo_evidence.id
  AND photo_evidence.raw_photo_count > opportunities.photo_count;
