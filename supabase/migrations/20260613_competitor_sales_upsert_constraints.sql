-- Make competitor_sales PostgREST upserts match the scraper conflict targets.
--
-- The original table migration created partial unique indexes. PostgreSQL can
-- enforce those, but PostgREST cannot use a partial index for the scraper's
-- on_conflict targets. These non-partial indexes preserve idempotent scraper
-- writes while still allowing multiple NULL source_listing_id rows because
-- PostgreSQL treats NULLs as distinct.

WITH ranked_url_duplicates AS (
  SELECT
    id,
    first_value(id) OVER (
      PARTITION BY source, listing_url
      ORDER BY
        (source_listing_id IS NOT NULL) DESC,
        scraped_at DESC NULLS LAST,
        created_at DESC NULLS LAST,
        id
    ) AS keep_id,
    source_listing_id
  FROM public.competitor_sales
),
merged_url_duplicates AS (
  SELECT
    keep_id,
    max(source_listing_id) FILTER (WHERE source_listing_id IS NOT NULL) AS source_listing_id
  FROM ranked_url_duplicates
  GROUP BY keep_id
)
UPDATE public.competitor_sales AS keep
SET source_listing_id = COALESCE(keep.source_listing_id, merged.source_listing_id)
FROM merged_url_duplicates AS merged
WHERE keep.id = merged.keep_id
  AND merged.source_listing_id IS NOT NULL;

WITH ranked_url_duplicates AS (
  SELECT
    id,
    first_value(id) OVER (
      PARTITION BY source, listing_url
      ORDER BY
        (source_listing_id IS NOT NULL) DESC,
        scraped_at DESC NULLS LAST,
        created_at DESC NULLS LAST,
        id
    ) AS keep_id
  FROM public.competitor_sales
)
DELETE FROM public.competitor_sales AS duplicate
USING ranked_url_duplicates AS ranked
WHERE duplicate.id = ranked.id
  AND ranked.id <> ranked.keep_id;

WITH ranked_listing_duplicates AS (
  SELECT
    id,
    first_value(id) OVER (
      PARTITION BY source, source_listing_id
      ORDER BY
        scraped_at DESC NULLS LAST,
        created_at DESC NULLS LAST,
        id
    ) AS keep_id
  FROM public.competitor_sales
  WHERE source_listing_id IS NOT NULL
)
DELETE FROM public.competitor_sales AS duplicate
USING ranked_listing_duplicates AS ranked
WHERE duplicate.id = ranked.id
  AND ranked.id <> ranked.keep_id;

CREATE UNIQUE INDEX IF NOT EXISTS idx_competitor_sales_source_listing_upsert
  ON public.competitor_sales(source, source_listing_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_competitor_sales_source_url_upsert
  ON public.competitor_sales(source, listing_url);

DROP INDEX IF EXISTS public.idx_competitor_sales_source_listing;
DROP INDEX IF EXISTS public.idx_competitor_sales_source_url;

NOTIFY pgrst, 'reload schema';
