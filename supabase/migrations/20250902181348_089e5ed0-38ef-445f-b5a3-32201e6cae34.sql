-- 1.2 PUBLIC LISTINGS - Stop business intelligence leak
-- Remove emergency lockdown and public access
DROP POLICY IF EXISTS "emergency_public_listings" ON public.public_listings;
DROP POLICY IF EXISTS "Public listings are viewable by everyone" ON public.public_listings;

-- Ensure RLS is enabled
ALTER TABLE public.public_listings ENABLE ROW LEVEL SECURITY;

-- Authenticated users only can view listings (no more public access)
CREATE POLICY "listings_authenticated_only"
ON public.public_listings FOR SELECT TO authenticated
USING (true);

-- Only service role can manage listings (for scraper operations)
CREATE POLICY "listings_service_manage"
ON public.public_listings FOR ALL TO service_role
USING (true)
WITH CHECK (true);