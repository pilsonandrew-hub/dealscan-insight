-- Safety migration: ensure dealer_sales upsert conflict key is the composite
-- (opportunity_id, user_id) and not just (opportunity_id).
--
-- Drop any stale single-column unique on opportunity_id if it exists,
-- then ensure the correct composite constraint is present.

DO $$
BEGIN
  -- Drop single-column unique on opportunity_id if someone added one
  IF EXISTS (
    SELECT 1
    FROM pg_constraint c
    JOIN pg_class t ON c.conrelid = t.oid
    WHERE t.relname = 'dealer_sales'
      AND c.contype = 'u'
      AND array_length(c.conkey, 1) = 1
      AND c.conkey[1] = (
        SELECT a.attnum FROM pg_attribute a
        WHERE a.attrelid = t.oid AND a.attname = 'opportunity_id'
      )
  ) THEN
    EXECUTE format(
      'ALTER TABLE dealer_sales DROP CONSTRAINT %I',
      (
        SELECT c.conname
        FROM pg_constraint c
        JOIN pg_class t ON c.conrelid = t.oid
        WHERE t.relname = 'dealer_sales'
          AND c.contype = 'u'
          AND array_length(c.conkey, 1) = 1
          AND c.conkey[1] = (
            SELECT a.attnum FROM pg_attribute a
            WHERE a.attrelid = t.oid AND a.attname = 'opportunity_id'
          )
      )
    );
    RAISE NOTICE 'Dropped stale single-column unique constraint on opportunity_id';
  END IF;

  -- Ensure composite unique exists
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint c
    JOIN pg_class t ON c.conrelid = t.oid
    WHERE t.relname = 'dealer_sales'
      AND c.conname = 'dealer_sales_opportunity_user_unique'
  ) THEN
    ALTER TABLE dealer_sales
      ADD CONSTRAINT dealer_sales_opportunity_user_unique
      UNIQUE (opportunity_id, user_id);
    RAISE NOTICE 'Added composite unique constraint (opportunity_id, user_id)';
  ELSE
    RAISE NOTICE 'Composite unique constraint already present — no action needed';
  END IF;
END $$;
