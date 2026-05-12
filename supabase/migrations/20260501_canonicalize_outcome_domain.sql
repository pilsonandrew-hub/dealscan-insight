-- DEA-50: Canonicalize dealer_sales outcome domain to won/lost/passed/pending.
-- Supersedes the sold/passed/pending enum from 20260318_dealer_sales.sql.
-- Strategy: convert column from enum to text with CHECK constraint.
-- This is safe because prod already stores text values in most paths.

-- Step 1: Drop the enum type from the column (cast to text)
-- The column was typed as public.outcome_status; alter to plain text.
ALTER TABLE public.dealer_sales
  ALTER COLUMN outcome TYPE TEXT USING outcome::TEXT;

-- Step 2: Set default to 'pending'
ALTER TABLE public.dealer_sales
  ALTER COLUMN outcome SET DEFAULT 'pending';

-- Step 3: Add CHECK constraint as NOT VALID so live writes are guarded
ALTER TABLE public.dealer_sales
  ADD CONSTRAINT chk_dealer_sales_outcome
  CHECK (outcome IN ('won', 'lost', 'passed', 'pending')) NOT VALID;

-- Step 4: Backfill sold -> won before validating the constraint
UPDATE public.dealer_sales
  SET outcome = 'won'
  WHERE outcome = 'sold';

-- Step 5: Reject unknown values before validating the constraint
DO $$
DECLARE
  bad_count INTEGER;
BEGIN
  SELECT COUNT(*) INTO bad_count
    FROM public.dealer_sales
    WHERE outcome NOT IN ('won', 'lost', 'passed', 'pending');
  IF bad_count > 0 THEN
    RAISE EXCEPTION 'Found % rows with non-canonical outcome values after backfill', bad_count;
  END IF;
END $$;

-- Step 6: Validate the constraint after the table is clean
ALTER TABLE public.dealer_sales
  VALIDATE CONSTRAINT chk_dealer_sales_outcome;

-- Step 7: Drop the old enum type (no longer referenced)
DROP TYPE IF EXISTS public.outcome_status;

COMMENT ON COLUMN public.dealer_sales.outcome IS 'Outcome status: won | lost | passed | pending (canonical domain, DEA-50)';
