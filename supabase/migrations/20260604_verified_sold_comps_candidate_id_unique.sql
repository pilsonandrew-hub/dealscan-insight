-- Ensure verifier write-mode upserts have a live conflict target even when
-- verified_sold_comps was created before candidate_id uniqueness was added.
CREATE UNIQUE INDEX IF NOT EXISTS idx_verified_sold_comps_candidate_id
  ON public.verified_sold_comps(candidate_id);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid = 'public.verified_sold_comps'::regclass
      AND conname = 'verified_sold_comps_candidate_id_key'
  ) THEN
    ALTER TABLE public.verified_sold_comps
      ADD CONSTRAINT verified_sold_comps_candidate_id_key UNIQUE (candidate_id);
  END IF;
END
$$;

NOTIFY pgrst, 'reload schema';
