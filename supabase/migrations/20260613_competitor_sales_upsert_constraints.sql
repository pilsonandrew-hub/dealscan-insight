-- Make competitor_sales PostgREST upserts match the scraper conflict targets.
--
-- The original table migration created partial unique indexes. PostgreSQL can
-- enforce those, but PostgREST cannot use a partial index for the scraper's
-- on_conflict targets. These non-partial indexes preserve idempotent scraper
-- writes while still allowing multiple NULL source_listing_id rows because
-- PostgreSQL treats NULLs as distinct.

BEGIN;

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
      ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS keep_id,
    first_value(source_listing_id) OVER (
      PARTITION BY source, listing_url
      ORDER BY
        (source_listing_id IS NOT NULL) DESC,
        scraped_at DESC NULLS LAST,
        created_at DESC NULLS LAST,
        id
      ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS keep_source_listing_id
  FROM public.competitor_sales
),
merged_url_duplicates AS (
  SELECT
    keep_id,
    keep_source_listing_id AS source_listing_id
  FROM ranked_url_duplicates
  GROUP BY keep_id, keep_source_listing_id
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
      ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
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
      ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
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

CREATE OR REPLACE FUNCTION public.reconcile_competitor_sale_url_only_duplicate(row_payload jsonb)
RETURNS SETOF public.competitor_sales
LANGUAGE plpgsql
SET search_path = public
AS $$
DECLARE
  payload_source TEXT := NULLIF(row_payload->>'source', '');
  payload_source_listing_id TEXT := NULLIF(row_payload->>'source_listing_id', '');
  payload_listing_url TEXT := NULLIF(row_payload->>'listing_url', '');
  existing_url_source_listing_id TEXT;
BEGIN
  IF payload_source IS NULL OR payload_source_listing_id IS NULL OR payload_listing_url IS NULL THEN
    RAISE EXCEPTION 'competitor sale reconciliation requires source, source_listing_id, and listing_url'
      USING ERRCODE = '23502';
  END IF;

  SELECT source_listing_id
  INTO existing_url_source_listing_id
  FROM public.competitor_sales
  WHERE source = payload_source
    AND listing_url = payload_listing_url
  FOR UPDATE;

  IF existing_url_source_listing_id IS NOT NULL
     AND existing_url_source_listing_id <> payload_source_listing_id THEN
    RAISE EXCEPTION 'listing_url is already tied to a different source_listing_id'
      USING ERRCODE = '23505',
            CONSTRAINT = 'idx_competitor_sales_source_url_upsert';
  END IF;

  DELETE FROM public.competitor_sales
  WHERE source = payload_source
    AND listing_url = payload_listing_url
    AND source_listing_id IS NULL;

  RETURN QUERY
  INSERT INTO public.competitor_sales (
    source,
    source_listing_id,
    listing_url,
    vin,
    year,
    make,
    model,
    trim,
    mileage,
    vehicle_class,
    sale_price,
    currency,
    auction_end_date,
    condition_notes,
    location,
    state,
    raw_payload,
    scraped_at
  )
  VALUES (
    payload_source,
    payload_source_listing_id,
    payload_listing_url,
    NULLIF(row_payload->>'vin', ''),
    NULLIF(row_payload->>'year', '')::integer,
    NULLIF(row_payload->>'make', ''),
    NULLIF(row_payload->>'model', ''),
    NULLIF(row_payload->>'trim', ''),
    NULLIF(row_payload->>'mileage', '')::integer,
    NULLIF(row_payload->>'vehicle_class', ''),
    NULLIF(row_payload->>'sale_price', '')::numeric,
    COALESCE(NULLIF(row_payload->>'currency', ''), 'USD'),
    NULLIF(row_payload->>'auction_end_date', '')::timestamptz,
    NULLIF(row_payload->>'condition_notes', ''),
    NULLIF(row_payload->>'location', ''),
    NULLIF(row_payload->>'state', ''),
    COALESCE(row_payload->'raw_payload', '{}'::jsonb),
    COALESCE(NULLIF(row_payload->>'scraped_at', '')::timestamptz, timezone('utc', now()))
  )
  ON CONFLICT (source, source_listing_id) DO UPDATE SET
    listing_url = EXCLUDED.listing_url,
    vin = EXCLUDED.vin,
    year = EXCLUDED.year,
    make = EXCLUDED.make,
    model = EXCLUDED.model,
    trim = EXCLUDED.trim,
    mileage = EXCLUDED.mileage,
    vehicle_class = EXCLUDED.vehicle_class,
    sale_price = EXCLUDED.sale_price,
    currency = EXCLUDED.currency,
    auction_end_date = EXCLUDED.auction_end_date,
    condition_notes = EXCLUDED.condition_notes,
    location = EXCLUDED.location,
    state = EXCLUDED.state,
    raw_payload = EXCLUDED.raw_payload,
    scraped_at = EXCLUDED.scraped_at,
    updated_at = timezone('utc', now())
  RETURNING *;
END;
$$;

GRANT EXECUTE ON FUNCTION public.reconcile_competitor_sale_url_only_duplicate(jsonb) TO service_role;

NOTIFY pgrst, 'reload schema';

COMMIT;
