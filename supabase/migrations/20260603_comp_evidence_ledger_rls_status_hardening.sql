-- Harden Comp Evidence Ledger schema constraints and explicit service-role RLS.

ALTER TABLE public.market_scout_runs
  DROP CONSTRAINT IF EXISTS chk_market_scout_run_status;

ALTER TABLE public.market_scout_runs
  ADD CONSTRAINT chk_market_scout_run_status
    CHECK (status IN ('started', 'collecting', 'completed', 'failed'));

ALTER TABLE public.market_scout_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sold_comp_candidates ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sold_comp_reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.verified_sold_comps ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.market_scout_artifacts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS service_role_all_market_scout_runs ON public.market_scout_runs;
CREATE POLICY service_role_all_market_scout_runs
  ON public.market_scout_runs
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

DROP POLICY IF EXISTS service_role_all_sold_comp_candidates ON public.sold_comp_candidates;
CREATE POLICY service_role_all_sold_comp_candidates
  ON public.sold_comp_candidates
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

DROP POLICY IF EXISTS service_role_all_sold_comp_reviews ON public.sold_comp_reviews;
CREATE POLICY service_role_all_sold_comp_reviews
  ON public.sold_comp_reviews
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

DROP POLICY IF EXISTS service_role_all_verified_sold_comps ON public.verified_sold_comps;
CREATE POLICY service_role_all_verified_sold_comps
  ON public.verified_sold_comps
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

DROP POLICY IF EXISTS service_role_all_market_scout_artifacts ON public.market_scout_artifacts;
CREATE POLICY service_role_all_market_scout_artifacts
  ON public.market_scout_artifacts
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);
