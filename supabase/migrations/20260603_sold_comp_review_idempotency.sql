-- Make Market Scout verifier runs replay-safe.
-- A given verifier version should write at most one review per candidate.

CREATE UNIQUE INDEX IF NOT EXISTS idx_sold_comp_reviews_candidate_reviewer_version
  ON public.sold_comp_reviews(candidate_id, reviewer, reviewer_version);
