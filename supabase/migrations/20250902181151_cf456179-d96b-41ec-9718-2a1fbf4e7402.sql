-- 0.1 Enable RLS on all public tables (safe even if already enabled)
DO $$
DECLARE r RECORD;
BEGIN
  FOR r IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', r.tablename);
  END LOOP;
END$$;

-- 0.2 Emergency lockdown - temporarily block access to biggest risks
DROP POLICY IF EXISTS "emergency_profiles" ON public.profiles;
CREATE POLICY "emergency_profiles" ON public.profiles FOR ALL TO authenticated USING (false) WITH CHECK (false);

DROP POLICY IF EXISTS "emergency_scraping" ON public.scraping_jobs;
CREATE POLICY "emergency_scraping" ON public.scraping_jobs FOR ALL TO authenticated USING (false) WITH CHECK (false);

DROP POLICY IF EXISTS "emergency_public_listings" ON public.public_listings;
CREATE POLICY "emergency_public_listings" ON public.public_listings FOR ALL TO authenticated USING (false) WITH CHECK (false);