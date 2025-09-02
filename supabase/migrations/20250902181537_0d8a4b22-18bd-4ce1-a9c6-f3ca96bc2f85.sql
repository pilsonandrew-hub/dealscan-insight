-- 1.4 SCRAPER CONFIGS - Restrict to admin-only access
-- Remove overly permissive policies
DROP POLICY IF EXISTS "Only authenticated users can view scraper configs" ON public.scraper_configs;
DROP POLICY IF EXISTS "Only service role can modify scraper configs" ON public.scraper_configs;

-- Ensure RLS is enabled
ALTER TABLE public.scraper_configs ENABLE ROW LEVEL SECURITY;

-- Admin-only access to sensitive scraper configurations
CREATE POLICY "scraper_configs_admin_only"
ON public.scraper_configs FOR ALL TO authenticated
USING (COALESCE((auth.jwt()->>'is_admin')::boolean, false))
WITH CHECK (COALESCE((auth.jwt()->>'is_admin')::boolean, false));

-- Service role for system operations
CREATE POLICY "scraper_configs_service_manage"
ON public.scraper_configs FOR ALL TO service_role
USING (true)
WITH CHECK (true);