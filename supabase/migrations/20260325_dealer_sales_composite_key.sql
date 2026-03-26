-- Deduplicate dealer_sales by keeping the newest row for each opportunity/user pair.
WITH numbered_duplicates AS (
    SELECT
        id,
        opportunity_id,
        user_id,
        ROW_NUMBER() OVER (
            PARTITION BY opportunity_id, user_id
            ORDER BY created_at DESC, id DESC
        ) AS rn
    FROM dealer_sales
)
DELETE FROM dealer_sales
WHERE id IN (
    SELECT id
    FROM numbered_duplicates
    WHERE rn > 1
);

ALTER TABLE dealer_sales
ADD CONSTRAINT dealer_sales_opportunity_user_unique UNIQUE (opportunity_id, user_id);
