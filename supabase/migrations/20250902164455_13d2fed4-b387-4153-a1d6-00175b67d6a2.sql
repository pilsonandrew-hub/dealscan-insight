-- PHASE 1: CRITICAL SECURITY FIXES
-- Step 0: Emergency lockdown and RLS enforcement

-- 0.1 Enable RLS on all public tables (safe even if already enabled)
DO $$
DECLARE r RECORD;
BEGIN
  FOR r IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', r.tablename);
  END LOOP;
END$$;

-- Step 1.1: Fix profiles table RLS policy (CRITICAL - stops email exfiltration)
-- Clean slate for profiles
DROP POLICY IF EXISTS "Users can view their own profile" ON public.profiles;
DROP POLICY IF EXISTS "Users can update their own profile" ON public.profiles;
DROP POLICY IF EXISTS "Users can insert their own profile" ON public.profiles;

-- Owner-only access (using user_id instead of id for profiles)
CREATE POLICY "profiles select own"
ON public.profiles FOR SELECT TO authenticated
USING (user_id = auth.uid());

CREATE POLICY "profiles update own"
ON public.profiles FOR UPDATE TO authenticated
USING (user_id = auth.uid())
WITH CHECK (user_id = auth.uid());

CREATE POLICY "profiles insert own"
ON public.profiles FOR INSERT TO authenticated
WITH CHECK (user_id = auth.uid());

-- Admin override (boolean claim is_admin)
CREATE POLICY "profiles admin all"
ON public.profiles FOR ALL TO authenticated
USING (coalesce((auth.jwt()->>'is_admin')::boolean, false))
WITH CHECK (true);

-- Step 1.2: Fix scraping_jobs access control
-- Add owner_id column if not exists and set up proper ownership
ALTER TABLE public.scraping_jobs ADD COLUMN IF NOT EXISTS owner_id uuid;

-- Backfill owner_id from user context (assuming scraping_jobs should be user-owned)
-- For now, we'll set a trigger to handle this going forward

-- Create trigger to stamp owner_id from JWT on INSERT
CREATE OR REPLACE FUNCTION public.set_owner_from_jwt()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
  IF NEW.owner_id IS NULL THEN
    NEW.owner_id := auth.uid();
  END IF;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_scraping_jobs_owner ON public.scraping_jobs;
CREATE TRIGGER trg_scraping_jobs_owner
BEFORE INSERT ON public.scraping_jobs
FOR EACH ROW EXECUTE FUNCTION public.set_owner_from_jwt();

-- Clean slate for scraping_jobs RLS
DROP POLICY IF EXISTS "Users can manage their own scraping jobs" ON public.scraping_jobs;

-- Owner-only RLS policies
CREATE POLICY "sj select own"
ON public.scraping_jobs FOR SELECT TO authenticated
USING (owner_id = auth.uid());

CREATE POLICY "sj modify own"
ON public.scraping_jobs FOR ALL TO authenticated
USING (owner_id = auth.uid())
WITH CHECK (owner_id = auth.uid());

-- Admin override
CREATE POLICY "sj admin all"
ON public.scraping_jobs FOR ALL TO authenticated
USING (coalesce((auth.jwt()->>'is_admin')::boolean, false))
WITH CHECK (true);

-- Step 1.3: Fix security_audit_log access (restrict to admin only)
DROP POLICY IF EXISTS "Users can view their own audit logs" ON public.security_audit_log;
DROP POLICY IF EXISTS "System can insert audit logs" ON public.security_audit_log;

-- Admin-only access for audit logs
CREATE POLICY "audit_admin_only"
ON public.security_audit_log FOR ALL TO authenticated
USING (coalesce((auth.jwt()->>'is_admin')::boolean, false))
WITH CHECK (coalesce((auth.jwt()->>'is_admin')::boolean, false));

-- System can still insert audit logs via service role
CREATE POLICY "audit_system_insert"
ON public.security_audit_log FOR INSERT TO service_role
WITH CHECK (true);

-- Step 1.4: Add proper indexes for RLS performance
CREATE INDEX IF NOT EXISTS idx_sj_owner_status ON public.scraping_jobs(owner_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_profiles_user_id ON public.profiles(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_user_action ON public.security_audit_log(user_id, action, created_at DESC);