-- 1.1 PROFILES TABLE - Stop email exfiltration permanently
-- Clean slate - remove all existing policies
DROP POLICY IF EXISTS "profiles select own" ON public.profiles;
DROP POLICY IF EXISTS "profiles update own" ON public.profiles;
DROP POLICY IF EXISTS "profiles insert own" ON public.profiles;
DROP POLICY IF EXISTS "profiles_user_only_select" ON public.profiles;
DROP POLICY IF EXISTS "profiles_user_only_update" ON public.profiles;
DROP POLICY IF EXISTS "profiles_user_only_insert" ON public.profiles;
DROP POLICY IF EXISTS "profiles_service_admin" ON public.profiles;
DROP POLICY IF EXISTS "emergency_profiles" ON public.profiles;

-- Ensure RLS is enabled
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

-- Owner-only policies using user_id (NOT id)
CREATE POLICY "profiles_select_own"
ON public.profiles FOR SELECT TO authenticated
USING (user_id = auth.uid());

CREATE POLICY "profiles_update_own"
ON public.profiles FOR UPDATE TO authenticated
USING (user_id = auth.uid())
WITH CHECK (user_id = auth.uid());

CREATE POLICY "profiles_insert_own"
ON public.profiles FOR INSERT TO authenticated
WITH CHECK (user_id = auth.uid());

-- Admin override using is_admin JWT claim
CREATE POLICY "profiles_admin_all"
ON public.profiles FOR ALL TO authenticated
USING (COALESCE((auth.jwt()->>'is_admin')::boolean, false))
WITH CHECK (true);