-- Single-operator opportunities RLS: remove public/anon inventory reads.
-- Backend ingest continues to use service_role for writes.

DROP POLICY IF EXISTS opportunities_read_policy ON public.opportunities;
DROP POLICY IF EXISTS "Opportunities are viewable by everyone" ON public.opportunities;

-- Authenticated operator reads (JWT required).
DROP POLICY IF EXISTS opportunities_authenticated_read ON public.opportunities;
CREATE POLICY opportunities_authenticated_read
  ON public.opportunities
  FOR SELECT
  TO authenticated
  USING (true);

-- Service role retains full access for ingest and cron.
DROP POLICY IF EXISTS opportunities_service_role_all ON public.opportunities;
CREATE POLICY opportunities_service_role_all
  ON public.opportunities
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

REVOKE ALL ON public.opportunities FROM anon;
GRANT SELECT ON public.opportunities TO authenticated;
GRANT ALL ON public.opportunities TO service_role;
